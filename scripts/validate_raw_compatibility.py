"""Exercise a packaged app against local RAWs through its ordinary HTTP API.

Use --cases with a JSON array of {id, model, mode, path} records; optional
sha256 verifies public sample provenance. RAWs remain read-only. The app
imports copies into its local import cache. --out should be an ignored local
directory: logs contain a local session token and reports contain photo data.
Requires numpy, Pillow and tifffile; use PYTHONPATH=. from the repository root.
See docs/MULTICAMERA_0.2.34.md for the public sample inventory and test limits.
"""
from pathlib import Path
import argparse,subprocess,time,re,json,urllib.request,urllib.parse,urllib.error,hashlib,io,math
import numpy as np
from PIL import Image,ImageCms,JpegImagePlugin
import tifffile

parser=argparse.ArgumentParser()
parser.add_argument('--app',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--cases',type=Path,required=True)
parser.add_argument('--port',type=int,default=18781)
args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
cases=json.loads(args.cases.read_text());log=(out/'server.log').open('w')
root=out/'inputs';root.mkdir(exist_ok=True)
for case in cases:
 p=Path(case['path']);link=root/p.name
 if not link.exists():link.symlink_to(p.resolve())
proc=subprocess.Popen([str(args.app.resolve()),'--no-browser','--port',str(args.port),'--root',str(root.resolve())],stdout=log,stderr=subprocess.STDOUT)
report={'scope':'Real-file compatibility of the shipped app; not colour calibration','cases':[]}
films=['provia','velvia','astia','classic_chrome','classic_negative','pro_neg_std','pro_neg_hi','eterna','eterna_bleach','nostalgic_negative','reala_ace','acros']
try:
 for _ in range(120):
  match=re.search(r'(http://127.0.0.1:\d+)/#session=(\S+)',(out/'server.log').read_text())
  if match:break
  if proc.poll() is not None:raise RuntimeError('Application exited at startup')
  time.sleep(.25)
 assert match,'No local endpoint'
 base,token=match.groups()
 def request(route,body=None,raw=None):
  data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
  req=urllib.request.Request(base+route,data=data,headers={'X-Fuji-Session':token,'Content-Type':'application/octet-stream' if raw is not None else 'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=240) as response:return response.read(),dict(response.headers)
  except urllib.error.HTTPError as e:
   text=e.read().decode(errors='replace')[:600]
   raise RuntimeError(f'HTTP {e.code}: {text}') from None
 def data(route,body=None):return json.loads(request(route,body)[0])
 info=data('/api/library');report['version']=info['version'];defaults={**info['recipe'],'noise_reduction':-4,'grain':'off'}
 def jpeg(payload,expected=None,detail=False):
  image=Image.open(io.BytesIO(payload));image.load()
  assert image.format=='JPEG'
  if expected:assert image.size==tuple(expected),(image.size,expected)
  if detail:assert JpegImagePlugin.get_sampling(image)==0
  if image.info.get('icc_profile'):
   profile=ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile']))
   assert 'sRGB' in ImageCms.getProfileDescription(profile)
  pixels=np.asarray(image)
  assert pixels.std()>1,'Image is essentially constant'
  return image
 def save_small(image,destination,edge=1440):
  copy=image.copy();copy.thumbnail((edge,edge),Image.Resampling.LANCZOS);copy.save(destination,quality=95)
 for case in cases:
  entry={k:v for k,v in case.items() if k!='path'};entry['checks']=[];entry['issues']=[];report['cases'].append(entry)
  path=Path(case['path']);directory=out/str(case['id']);directory.mkdir(exist_ok=True)
  current='availability';started=time.monotonic()
  try:
   deadline=time.monotonic()+300
   while not path.exists() and time.monotonic()<deadline:time.sleep(.5)
   assert path.exists(),'Sample was not downloaded'
   from kora.raw import require_local
   require_local(path);before=path.stat();original_hash=hashlib.sha256(path.read_bytes()).hexdigest()
   if case.get('sha256'):assert original_hash==case['sha256']
   entry['bytes']=before.st_size;entry['sha256']=original_hash
   current='folder discovery'
   listing=data('/api/folder',{'path':str(root.resolve()),'recursive':False})['files']
   item=next(x for x in listing if Path(x['path'])==path.resolve());entry['checks'].append({'name':current,'ok':True})
   current='file import'
   try:
    imported=data('/api/library') # keep session/library independent of UI state
    item=json.loads(request('/api/import?name='+urllib.parse.quote(path.name),raw=path.read_bytes())[0])
    assert item['bytes']==before.st_size and item['name']==path.name
    entry['checks'].append({'name':current,'ok':True})
   except Exception as error:entry['issues'].append({'stage':current,'error':str(error)})
   id=item['id'];entry['photo_id']=id
   current='RAW metadata and decode';t=time.monotonic();photo=data('/api/photo/'+id)
   size=(photo['developed_size']['width'],photo['developed_size']['height']);entry['size']=size
   entry['camera']=photo['exif'].get('Model');entry['make']=photo['exif'].get('Make');entry['orientation']=photo['sizes']['flip']
   entry['normalization']=photo['input_normalization'];entry['open_seconds']=round(time.monotonic()-t,3)
   (directory/'metadata.json').write_text(json.dumps(photo,indent=2))
   entry['checks'].append({'name':current,'ok':True})
   current='thumbnail';thumb=jpeg(request('/api/thumbnail/'+id)[0]);thumb.save(directory/'thumbnail.jpg')
   entry['checks'].append({'name':current,'size':thumb.size,'ok':True})
   current='embedded reference'
   if photo['preview_available']:
    ref=jpeg(request('/api/preview/'+id)[0]);ref.save(directory/'embedded.jpg')
   previews={}
   for film in films:
    current='preview '+film;t=time.monotonic()
    recipe={**defaults,'film':film};im=jpeg(request('/api/render',{'id':id,'recipe':recipe,'quality':'interactive'})[0])
    if film in ('provia','classic_negative'):save_small(im,directory/(film+'.jpg'));previews[film]=np.asarray(im).copy()
    entry['checks'].append({'name':current,'ok':True,'size':im.size,'seconds':round(time.monotonic()-t,3)})
   current='tonal and texture extremes'
   stress={**defaults,'film':'classic_negative','dynamic_range':400,'highlights':-100,'whites':-100,'shadows':100,'blacks':-50,'highlight_tone':-2,'shadow_tone':4,'grain':'strong','grain_size':'large','color_chrome':'strong','fx_blue':'strong','clarity':4,'sharpness':4,'noise_reduction':4}
   im=jpeg(request('/api/render',{'id':id,'recipe':stress,'quality':'interactive'})[0]);save_small(im,directory/'extremes.jpg')
   entry['checks'].append({'name':current,'ok':True})
   current='exposure response';means=[]
   for exposure in (-2,2):
    im=jpeg(request('/api/render',{'id':id,'recipe':{**defaults,'exposure':exposure},'quality':'interactive'})[0]);means.append(float(np.asarray(im).mean()))
   assert means[1]>means[0]+1,means
   entry['checks'].append({'name':current,'ok':True,'mean_minus_plus':means})
   current='recipe reset';im=jpeg(request('/api/render',{'id':id,'recipe':defaults,'quality':'interactive'})[0])
   np.testing.assert_array_equal(np.asarray(im),previews['provia']);entry['checks'].append({'name':current,'ok':True})
   current='Fit detail';fit=jpeg(request('/api/tile',{'id':id,'recipe':defaults,'x':0,'y':0,'level':4,'size':768})[0],(min(768,math.ceil(size[0]/4)),min(768,math.ceil(size[1]/4))),detail=True)
   fit.save(directory/'fit-tile.jpg');entry['checks'].append({'name':current,'ok':True})
   x=max(0,(size[0]//2//768)*768);y=max(0,(size[1]//2//768)*768)
   current='100% detail';tile=jpeg(request('/api/tile',{'id':id,'recipe':defaults,'x':x,'y':y,'level':1,'size':768})[0],(min(768,size[0]-x),min(768,size[1]-y)),detail=True)
   tile.save(directory/'zoom100.jpg');entry['checks'].append({'name':current,'ok':True})
   current='without film detail';jpeg(request('/api/tile',{'id':id,'recipe':defaults,'neutral':True,'x':x,'y':y,'level':1,'size':768})[0],tile.size,detail=True)
   entry['checks'].append({'name':current,'ok':True})
   current='full JPEG export';t=time.monotonic();image=jpeg(request('/api/export',{'id':id,'recipe':defaults})[0],size)
   assert image.info.get('icc_profile'),'Export has no ICC profile'
   crop=np.asarray(image.crop((x,y,x+tile.width,y+tile.height)),dtype=np.float32)
   delta=float(abs(crop-np.asarray(tile,dtype=np.float32)).mean());entry['tile_export_mae_8bit']=round(delta,4)
   if delta>8:entry['issues'].append({'stage':current,'error':f'Tile/export mean pixel difference {delta:.2f}/255 requires review'})
   save_small(image,directory/'full-export.jpg');entry['checks'].append({'name':current,'ok':True,'size':image.size,'seconds':round(time.monotonic()-t,3)})
   del image,crop
   current='cropped TIFF16 export';recipe={**defaults,'film':'classic_negative','file_type':'tiff16','image_size':'S','digital_crop':1.4,'aspect':'1:1'}
   payload,headers=request('/api/export',{'id':id,'recipe':recipe})
   with tifffile.TiffFile(io.BytesIO(payload)) as tif:
    array=tif.asarray();expected=round(int(min(size)/1.4)*.5)
    assert array.dtype==np.uint16 and array.shape==(expected,expected,3),(array.dtype,array.shape,expected)
    assert tif.pages[0].tags.get(34675),'TIFF has no ICC profile'
    assert np.unique(array[::5,::5]).size>256,'No extra 16-bit precision'
   entry['checks'].append({'name':current,'ok':True,'size':[expected,expected],'dtype':'uint16'});del array,payload
   assert path.stat().st_mtime_ns==before.st_mtime_ns and path.stat().st_size==before.st_size
   assert hashlib.sha256(path.read_bytes()).hexdigest()==original_hash
   entry['checks'].append({'name':'original unchanged','ok':True});entry['complete']=True
  except Exception as error:
   entry['complete']=False;entry['issues'].append({'stage':current,'error':str(error)})
  entry['seconds']=round(time.monotonic()-started,3)
  (out/'results.json').write_text(json.dumps(report,indent=2))
  print(case['id'],case.get('model'),entry['complete'],entry['seconds'],entry['issues'],flush=True)
finally:
 proc.terminate()
 try:proc.wait(timeout=10)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
