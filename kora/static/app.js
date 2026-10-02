"use strict";
const $ = s => document.querySelector(s);
const session = new URLSearchParams(location.hash.slice(1)).get("session") || sessionStorage.getItem("film-session") || sessionStorage.getItem("fuji-session") || "";
sessionStorage.setItem("film-session", session); history.replaceState(null, "", "/");
let files = [], selected = null, filter = "all", defaults, recipe, selectionVersion = 0, toastTimer;
const selectedIds = new Set(), recipesById = new Map();
let rawExtensions = new Set([".raf", ".dng"]);
const pictures = new Map();
const embeddedPictures = new Map();
const thumbnailPictures = new Map(), thumbnailRequests = new Set();
let thumbnailQueue=[],thumbnailWorkers=0,thumbnailTimer;
let thumbnailWorkerLimit=2;
let fullResolutionPrefetch=false,prefetchTimer,prefetchedId=null;
let exportInProgress=false,lastExportTiming=null;
let shootingSettings=null, opticsInfo=null, sourceCamera=null;
let engineState=null;
let nativeWindow=false;
let recipeFolder=null;
let undoStack=[],future=[],copiedSettings=null;
let renderRevision=0, renderTimer, renderBusy=false, renderAgain=false, renderURL, beforeURL, comparing=false, currentRenderQuality=null, renderController=null;
let fullWidth=0,fullHeight=0,tileTimer,tileGeneration=0,previewVariant=null;
window.filmDiagnosticContext=()=>({client_version:$("#app-version")?.textContent||"",photo_id:selected?.id||"",film:recipe?.film||"",grain:recipe?.grain||"",grain_size:recipe?.grain_size||"",zoom:typeof viewScale==="number"?viewScale:0,pan_x:panX,pan_y:panY,width:fullWidth,height:fullHeight,revision:renderRevision,generation:tileGeneration});
const tileURLs=new Map();
const tileViewId=crypto.randomUUID();
const films = [
 ["provia","PROVIA / Standard","Balanced color for everyday photography."], ["velvia","Velvia / Vivid","A vivid palette with deep color."],
 ["astia","ASTIA / Soft","Delicate color and soft tonality."], ["classic_chrome","Classic Chrome","A restrained palette with a documentary character."],
 ["classic_negative","Classic Negative","Official Classic Negative LUT · GFX ETERNA 55."], ["pro_neg_std","PRO Neg. Std","Measured contrast for portraits."],
 ["pro_neg_hi","PRO Neg. Hi","Higher-contrast portrait color."], ["eterna","ETERNA / Cinema","A soft palette inspired by cinema."],
 ["eterna_bleach","ETERNA Bleach Bypass","Strong contrast and muted color."], ["nostalgic_negative","Nostalgic Negative","Warm tones with a nostalgic character."],
 ["reala_ace","REALA ACE","Natural color with clear tonal separation."], ["acros","ACROS","Silver-halide-inspired black and white tonality."],
 ["monochrome","Monochrome","A classic black and white rendering."], ["sepia","Sepia","Brown-toned monochrome."]
];
const officialFilms = new Set(["provia","velvia","astia","classic_chrome","classic_negative","pro_neg_std","eterna","eterna_bleach","reala_ace","acros"]);
const wb = [["camera","Camera"],["auto","Auto"],["auto_white","Auto White Priority"],["auto_ambience","Auto Ambience Priority"],["daylight","Daylight"],["shade","Shade"],["tungsten","Tungsten"],["fluorescent1","Fluorescent 1"],["fluorescent2","Fluorescent 2"],["fluorescent3","Fluorescent 3"],["underwater","Underwater"],["kelvin","Color Temperature"]];
const effect = [["off","Off"],["weak","Weak"],["strong","Strong"]];
function element(tag, text, className) { const e = document.createElement(tag); if(text !== undefined) e.textContent = text; if(className)e.className=className; return e; }
function toast(text) { clearTimeout(toastTimer); $("#toast").textContent=text; $("#toast").hidden=false; toastTimer=setTimeout(()=>$("#toast").hidden=true,4500); }
let activityRequests=0,activityShowTimer,activityHideTimer,activityVisibleAt=0;
function beginActivity(){
 activityRequests++;clearTimeout(activityHideTimer);if(activityRequests!==1)return;clearTimeout(activityShowTimer);activityShowTimer=setTimeout(()=>{if(!activityRequests)return;const bar=$("#activity-bar");bar.hidden=false;bar.setAttribute("aria-valuetext","Processing");activityVisibleAt=performance.now();},90);
}
function endActivity(){
 activityRequests=Math.max(0,activityRequests-1);if(activityRequests)return;clearTimeout(activityShowTimer);const bar=$("#activity-bar");if(bar.hidden)return;const wait=Math.max(0,180-(performance.now()-activityVisibleAt));activityHideTimer=setTimeout(()=>{if(activityRequests)return;bar.hidden=true;bar.setAttribute("aria-valuetext","Idle");},wait);
}
async function api(path, options={}) {
 const requestId=crypto.randomUUID();
 beginActivity();
 const controller=new AbortController(),abort=()=>controller.abort(options.signal.reason);
 if(options.signal?.aborted)abort();else options.signal?.addEventListener("abort",abort,{once:true});
 const timer=setTimeout(()=>controller.abort(new DOMException("The request took too long. Please try again.","TimeoutError")),path.startsWith("/api/export")?600000:120000);
 const requestStarted=performance.now();
 try{const response = await fetch(path, {...options,signal:controller.signal, headers:{"X-Fuji-Session":session,"X-Film-Request-ID":requestId,...options.headers}});
  const headersReceived=performance.now();
  if(response.status===403){$("#connection-message").textContent="This session has expired. Reopen KŌRA from the Dock.";$("#connection-status").hidden=false;}
  else connectionHealthy();
  if(!response.ok){const value=await response.json();throw new Error(value.error||"Request failed");}
  const type=response.headers.get("content-type")||"";
  const result=await (type.startsWith("image/")||type.startsWith("application/zip") ? response.blob() : response.json());
  if(path==="/api/library")nativeWindow=!!result.native_window;
  if(path.startsWith('/api/export'))lastExportTiming={request:(headersReceived-requestStarted)/1000,transfer:(performance.now()-headersReceived)/1000,server:response.headers.get('Server-Timing')||''};
  return result;
 }catch(e){let details={};try{if(typeof options.body==="string"){const body=JSON.parse(options.body);for(const k of ["x","y","size","level","generation"])if(typeof body[k]==="number")details[k]=body[k];}}catch(_){}
  reportError(e,path.split("?")[0].replaceAll("/","."),{...details,request_id:requestId});if(e instanceof TypeError)checkConnection();throw e;}
 finally{clearTimeout(timer);options.signal?.removeEventListener("abort",abort);endActivity();}
}
let healthCheckBusy=false,healthFailures=0,lastHealthy=Date.now();
function connectionHealthy(){healthFailures=0;lastHealthy=Date.now();$("#connection-status").hidden=true;}
async function checkConnection(){
 if(healthCheckBusy||document.hidden)return;healthCheckBusy=true;const started=Date.now();
 try{const response=await fetch("/api/health",{headers:{"X-Fuji-Session":session},signal:AbortSignal.timeout(10000),cache:"no-store"});
  if(response.status===403){$("#connection-message").textContent="This session has expired. Reopen KŌRA from the Dock.";$("#connection-status").hidden=false;}
  else if(response.ok)connectionHealthy();else throw new Error("Health check failed");
 }
 catch{if(lastHealthy<=started){healthFailures++;if(healthFailures>=2){$("#connection-message").textContent=healthFailures>=3&&Date.now()-lastHealthy>=30000?"The app is not responding. Check the connection again; if it persists, reopen KŌRA from the Dock.":"The app is responding slowly. Processing may still be running; keep this photo open.";$("#connection-status").hidden=false;}}}
 finally{healthCheckBusy=false;}
}
$("#connection-retry").onclick=checkConnection;
window.addEventListener("focus",checkConnection);
document.addEventListener("visibilitychange",checkConnection);
setInterval(checkConnection,15000);
function section(name) { const e=element("section",undefined,"control-section");e.append(element("h3",name));$("#controls").append(e);return e; }
function select(parent, label, key, choices) {const l=element("label",label),s=element("select");s.dataset.key=key;for(const [v,t] of choices){const o=element("option",t);o.value=v;s.append(o);}l.append(s);parent.append(l);}
function slider(parent,label,key,min,max,step=1) {
 const precise=key==="highlights"||key==="whites";
 const row=element("div",undefined,"range-row"),l=element("label",label),o=element(precise?"input":"output"),i=element("input");
 i.type="range";i.min=min;i.max=max;i.step=precise ? .1 : step;i.dataset.key=key;i.id="control-"+key;l.htmlFor=i.id;
 if(precise){
  o.type="number";o.min=min;o.max=max;o.step=.1;o.dataset.toneValue=key;o.className="tone-value";
  o.setAttribute("aria-label",label+" value");o.title="Type a value · arrows: 0.1 · Shift + arrows: 1";
  const commit=()=>{
   const value=Number(o.value);
   if(o.value===""||!Number.isFinite(value)){o.value=recipe?.[key]??0;return;}
   const next=Math.round(Math.max(min,Math.min(max,value))*10)/10;
   o.value=next;if(next===recipe?.[key])return;
   i.value=next;i.dispatchEvent(new Event("input",{bubbles:true}));
  };
  o.addEventListener("change",commit);o.addEventListener("blur",commit);
  o.addEventListener("keydown",e=>{
   if(e.key==="Enter"){e.preventDefault();commit();o.blur();}
   if(e.key==="Escape"){o.value=recipe?.[key]??0;o.blur();}
  });
  for(const control of [i,o])control.addEventListener("keydown",e=>{
   if(!e.shiftKey||!["ArrowUp","ArrowRight","ArrowDown","ArrowLeft"].includes(e.key))return;
   e.preventDefault();control.value=Math.max(min,Math.min(max,Number(control.value)+(["ArrowUp","ArrowRight"].includes(e.key)?1:-1)));
   control.dispatchEvent(new Event(control===i?"input":"change",{bubbles:true}));
  });
 }else{o.dataset.output=key;}
 l.append(o);row.append(l,i);parent.append(row);
}
function setupWBGrid(parent){
 const wrap=element("div",undefined,"wb-grid-wrap"),title=element("div","WHITE BALANCE SHIFT","wb-grid-title");
 const canvas=element("canvas");canvas.id="wb-grid";canvas.width=380;canvas.height=380;canvas.tabIndex=0;canvas.setAttribute("role","group");canvas.setAttribute("aria-label","White balance grid. Left and right arrows adjust red. Up and down arrows adjust blue. Home centers the marker.");
 const readout=element("output");readout.id="wb-grid-value";readout.setAttribute("aria-live","polite");
 const reset=element("button","Center R/B");reset.type="button";reset.id="wb-grid-reset";
 const foot=element("div",undefined,"wb-grid-footer");foot.append(readout,reset);
 const axes=element("div",undefined,"wb-axis-legend");
 for(const [label,axis] of [["← Cyan · R−","cyan"],["Red · R+ →","red"],["↑ Blue · B+","blue"],["↓ Yellow · B−","yellow"]])axes.append(element("span",label,"wb-axis-"+axis));
 wrap.append(title,axes,canvas,foot,element("small","Click or drag · arrows to adjust · −9 to +9"));parent.append(wrap);
 let dragging=false,saved=false;
 function setShift(red,blue,record=true){
  if(!recipe)return;
  red=Math.max(-9,Math.min(9,Math.round(red)));blue=Math.max(-9,Math.min(9,Math.round(blue)));
  if(red===recipe.wb_red&&blue===recipe.wb_blue)return;
  if(record)recordUndo();
  applyPatchToSelection({wb_red:red,wb_blue:blue});populate();persist();scheduleRender();
 }
 function move(e){const box=canvas.getBoundingClientRect();const x=(e.clientX-box.left)/box.width,y=(e.clientY-box.top)/box.height;
  const red=Math.max(-9,Math.min(9,Math.round((x*380-20)/340*18-9))),blue=Math.max(-9,Math.min(9,Math.round(9-(y*380-20)/340*18)));
  if(red!==recipe?.wb_red||blue!==recipe?.wb_blue){setShift(red,blue,!saved);saved=true;}}
 canvas.onpointerdown=e=>{if(e.button!==0||!recipe)return;e.preventDefault();canvas.focus();dragging=true;saved=false;canvas.setPointerCapture(e.pointerId);move(e);};
 canvas.onpointermove=e=>{if(dragging)move(e);};
 canvas.onpointerup=e=>{if(dragging)move(e);dragging=false;};canvas.onpointercancel=()=>{dragging=false;};canvas.onlostpointercapture=()=>{dragging=false;};
 canvas.onkeydown=e=>{const steps={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};if(e.key==="Home"){e.preventDefault();e.stopPropagation();setShift(0,0);}else if(steps[e.key]&&recipe){e.preventDefault();e.stopPropagation();const [r,b]=steps[e.key];setShift(recipe.wb_red+r,recipe.wb_blue+b);}};
 reset.onclick=()=>setShift(0,0);
}
function drawWBGrid(){
 const canvas=$("#wb-grid");if(!canvas||!recipe)return;const ctx=canvas.getContext("2d");ctx.fillStyle="#111412";ctx.fillRect(0,0,380,380);
 for(let b=-9;b<=9;b++)for(let r=-9;r<=9;r++){ctx.fillStyle=`rgb(${132+r*8},132,${132+b*8})`;ctx.beginPath();ctx.arc(20+(r+9)/18*340,20+(9-b)/18*340,2.4,0,Math.PI*2);ctx.fill();}
 const redAxis=ctx.createLinearGradient(20,0,360,0);redAxis.addColorStop(0,"#75b8b7");redAxis.addColorStop(.5,"#92998c");redAxis.addColorStop(1,"#cb8981");
 const blueAxis=ctx.createLinearGradient(0,20,0,360);blueAxis.addColorStop(0,"#86a9d1");blueAxis.addColorStop(.5,"#92998c");blueAxis.addColorStop(1,"#c5b578");
 ctx.lineWidth=1.2;ctx.setLineDash([3,5]);ctx.strokeStyle=redAxis;ctx.beginPath();ctx.moveTo(10,190);ctx.lineTo(370,190);ctx.stroke();ctx.strokeStyle=blueAxis;ctx.beginPath();ctx.moveTo(190,10);ctx.lineTo(190,370);ctx.stroke();ctx.setLineDash([]);
 const x=20+(recipe.wb_red+9)/18*340,y=20+(9-recipe.wb_blue)/18*340;
 ctx.strokeStyle="#111412";ctx.lineWidth=5;ctx.strokeRect(x-7,y-7,14,14);ctx.strokeStyle="#c9ccc3";ctx.lineWidth=1.5;ctx.strokeRect(x-7,y-7,14,14);
 const sign=n=>n>0?"+"+n:String(n);$("#wb-grid-value").textContent=`R : ${sign(recipe.wb_red)}   B : ${sign(recipe.wb_blue)}`;
 canvas.setAttribute("aria-description",`Red ${recipe.wb_red}, Blue ${recipe.wb_blue}`);
}
const referenceFilms=new Set(["pro_neg_hi","nostalgic_negative","classic_negative"]);
function hasReferenceFilm(film){return referenceFilms.has(film);}
function filmSourceLabel(film){return hasReferenceFilm(film)?"PHOTO APPROXIMATION":officialFilms.has(film)?"FUJIFILM LUT":"INTERPRETATION";}
function syncFilmChoices(currentFilm){
 const menu=$("#film");menu.replaceChildren();
 for(const [v,t] of films){if(!officialFilms.has(v)&&!hasReferenceFilm(v))continue;const o=element("option",t);o.value=v;menu.append(o);}
 // Preserve legacy recipes without offering their retired simulations for selection.
 if(currentFilm&&!officialFilms.has(currentFilm)&&!hasReferenceFilm(currentFilm)){
  const name=films.find(f=>f[0]===currentFilm)?.[1]||currentFilm;
  const o=element("option",name+" · legacy recipe (retired)");o.value=currentFilm;o.disabled=true;menu.append(o);
 }
 if(currentFilm)menu.value=currentFilm;
}
function setupControls(){
 syncFilmChoices();
 let s=section("LIGHT & CONTRAST");select(s,"Dynamic Range","dynamic_range",[[100,"DR100"],[200,"DR200"],[400,"DR400"]]);select(s,"D Range Priority","dr_priority",[["off","Off"],["auto","Auto"],["weak","Weak"],["strong","Strong"]]);select(s,"Push / Pull · EV","exposure",Array.from({length:19},(_,i)=>{const v=Number(((i-9)/3).toFixed(6));return [v,(v>0?"+":"")+v.toFixed(2)];}));
 slider(s,"Highlight Tone","highlight_tone",-2,4,.5);slider(s,"Shadow Tone","shadow_tone",-2,4,.5);
 s.append(element("p","− softens · + hardens. Response based on X-M5 references; rendering remains an approximation.","tone-note"));
 s.append(element("p","DR100 keeps normal contrast. DR200 and DR400 progressively protect highlights.","tone-note"));
 const recovery=element("details",undefined,"tone-recovery");recovery.id="tone-recovery";
 recovery.append(element("summary","RAW recovery · additional controls"),element("p","Independent KŌRA corrections. Whites and Blacks have no separate X RAW STUDIO equivalent.","tone-note"));s.append(recovery);
 slider(recovery,"Highlights","highlights",-100,100);slider(recovery,"Whites","whites",-100,100);slider(recovery,"Shadows","shadows",-100,100);slider(recovery,"Blacks","blacks",-100,100);
 s=section("WHITE BALANCE");select(s,"Mode","wb",wb);slider(s,"Color Temperature · K","kelvin",2500,10000,10);slider(s,"Red Shift","wb_red",-9,9);slider(s,"Blue Shift","wb_blue",-9,9);setupWBGrid(s);
 s=section("COLOR & DETAIL");slider(s,"Color","color",-4,4);slider(s,"Sharpness","sharpness",-4,4);slider(s,"Clarity","clarity",-5,5);slider(s,"Noise Reduction","noise_reduction",-4,4);
 s=section("TEXTURE & EFFECTS");const grid=element("div",undefined,"select-grid");s.append(grid);select(grid,"Grain Effect","grain",effect);select(grid,"Grain Size","grain_size",[["small","Small"],["large","Large"]]);select(grid,"Color Chrome Effect","color_chrome",effect);select(grid,"Color Chrome FX Blue","fx_blue",effect);select(s,"Monochromatic Filter","mono_filter",[["none","None"],["yellow","Yellow"],["red","Red"],["green","Green"]]);
 slider(s,"Monochromatic Color · warm / cool","mono_warm",-18,18);slider(s,"Monochromatic Color · green / magenta","mono_green",-18,18);
 select(s,"Smooth Skin Effect","smooth_skin",effect);
 s=section("LENS CORRECTIONS");select(s,"Lens Distortion","lens_distortion",[["off","Off"],["auto","Automatic Profile"]]);select(s,"Lens Vignetting","lens_vignetting",[["off","Off"],["auto","Automatic Profile"]]);const opticalNote=element("p","Choose a photo to identify its lens.");opticalNote.id="optics-status";opticalNote.setAttribute("role","status");s.append(opticalNote);
 const opticalApply=element("button","Apply available corrections");opticalApply.id="optics-apply";opticalApply.type="button";opticalApply.hidden=true;opticalApply.addEventListener("click",applyAvailableOptics);s.append(opticalApply);
 s=section("CROP & OUTPUT");select(s,"File Type","file_type",[["jpeg","JPEG"],["tiff8","TIFF · 8-bit"],["tiff16","TIFF · 16-bit"]]);
 select(s,"Image Size","image_size",[["L","L · full developed resolution"],["M","M · 50% of the pixels"],["S","S · 25% of the pixels"]]);
 select(s,"Image Aspect","aspect",[["original","Original"],["3:2","3:2"],["16:9","16:9"],["1:1","1:1"],["4:3","4:3"]]);
 select(s,"JPEG Quality","image_quality",[["fine","Fine"],["normal","Normal"]]);
 select(s,"Export Color Space","color_space",[["srgb","sRGB"],["adobe_rgb","Adobe RGB (1998)"]]);
 select(s,"Digital Teleconverter · crop without super-resolution","digital_crop",[[1,"Off"],[1.4,"1.4×"],[2,"2×"]]);

}
function populate(){
 syncFilmChoices(recipe.film);
 drawWBGrid();updateOpticsStatus();
 for(const input of document.querySelectorAll("[data-key]")){input.value=recipe[input.dataset.key] ?? defaults[input.dataset.key];const out=document.querySelector(`[data-output="${input.dataset.key}"]`);if(out)out.textContent=Number(input.value)>0&&input.dataset.key!=="kelvin"?"+"+input.value:input.value;}
 for(const input of document.querySelectorAll("[data-tone-value]")){input.value=recipe[input.dataset.toneValue];input.disabled=recipe.dr_priority!=="off";}
 $("#film-description").textContent=hasReferenceFilm(recipe.film)?"Photo approximation based on X-M5 references · adapted to your RAW.":officialFilms.has(recipe.film)?"Official Fujifilm LUT · GFX ETERNA 55 · uncalibrated photo adaptation.":"Independent interpretation · this film has no LUT in the official pack.";
 const unsupported=recipe.target_model==="X-T4"&&["reala_ace","nostalgic_negative"].includes(recipe.film);
 $("#validation-note").textContent=unsupported?"This simulation is unavailable on the X-T4.":"";
 $("#control-kelvin").disabled=recipe.wb!=="kelvin";
 const mono=["acros","monochrome","sepia"].includes(recipe.film);
 for(const key of ["mono_filter","mono_warm","mono_green"])document.querySelector(`[data-key="${key}"]`).disabled=!mono;
 document.querySelector('[data-key="image_quality"]').disabled=recipe.file_type!=="jpeg";
 for(const key of ["dynamic_range","highlight_tone","shadow_tone","highlights","whites","shadows","blacks"])document.querySelector(`[data-key="${key}"]`).disabled=recipe.dr_priority!=="off";
 if(["highlights","whites","shadows","blacks"].some(key=>Number(recipe[key]||0)!==0))$("#tone-recovery").open=true;
}
function selectedTargets(){return selectedIds.size?[...selectedIds]:(selected?[selected.id]:[]);}
function syncActiveRecipe(){if(selected&&recipe)recipesById.set(selected.id,structuredClone(recipe));}
function ensureRecipe(id,seed=recipe||defaults){if(!recipesById.has(id))recipesById.set(id,structuredClone(seed));return recipesById.get(id);}
function snapshotRecipes(ids=selectedTargets()){return ids.map(id=>[id,structuredClone(ensureRecipe(id))]);}
function recordUndo(){undoStack.push(snapshotRecipes());if(undoStack.length>100)undoStack.shift();future=[];}
function restoreSnapshot(snapshot){const current=snapshotRecipes(snapshot.map(([id])=>id));for(const [id,value] of snapshot)recipesById.set(id,structuredClone(value));if(selected)recipe=structuredClone(ensureRecipe(selected.id));return current;}
function applyPatchToSelection(patch){for(const id of selectedTargets())recipesById.set(id,{...ensureRecipe(id),...structuredClone(patch)});if(selected)recipe=structuredClone(ensureRecipe(selected.id));}
function applyFullToSelection(value){const next={...defaults,...structuredClone(value)};for(const id of selectedTargets())recipesById.set(id,structuredClone(next));if(selected)recipe=structuredClone(ensureRecipe(selected.id));else recipe=next;}
function exportLabel(){const count=selectedIds.size;return count>1?`Export ${count} JPEGs`:"Export Image";}
function scheduleFullPrefetch(id,delay=1200){
 clearTimeout(prefetchTimer);if(exportInProgress||!fullResolutionPrefetch||!id||prefetchedId===id)return;
 prefetchTimer=setTimeout(()=>{prefetchedId=id;fetch("/api/prefetch",{method:"POST",headers:{"X-Fuji-Session":session,"Content-Type":"application/json"},body:JSON.stringify({id})}).then(response=>{if(!response.ok&&prefetchedId===id)prefetchedId=null;}).catch(()=>{if(prefetchedId===id)prefetchedId=null;});},delay);
}
function updateSelectionState(){
 const count=selectedIds.size,label=count?`${count} photo${count===1?"":"s"} selected`:"No photo selected";
 $("#selection-state").textContent=count>1?label+" · adjustments are linked":count===1?"1 photo selected · individual editing":label;
 $("#selection-clear").disabled=count<=1;
 if(!$("#export-image").disabled)$("#export-image").textContent=exportLabel();
}
function persist(){syncActiveRecipe();$("#recipe-state").textContent=selectedIds.size>1?`Recipe updated on ${selectedIds.size} photos`:"Recipe updated";updateSelectionState();}
function visibleFiles(){const term=$("#search").value.toLowerCase();return files.filter(f=>(filter==="all"||f.format===filter||(filter==="OTHER"&&!["RAF","DNG"].includes(f.format)))&&f.name.toLowerCase().includes(term));}
function queueThumbnail(f){
 if(!f.local||pictures.has(f.id)||thumbnailPictures.has(f.id)||thumbnailRequests.has(f.id))return;
 thumbnailRequests.add(f.id);thumbnailQueue.push(f);clearTimeout(thumbnailTimer);thumbnailTimer=setTimeout(drainThumbnailQueue,180);
}
function drainThumbnailQueue(){
 while(thumbnailWorkers<thumbnailWorkerLimit&&thumbnailQueue.length){const f=thumbnailQueue.shift();thumbnailWorkers++;
  api("/api/thumbnail/"+f.id).then(blob=>{const url=URL.createObjectURL(blob);thumbnailPictures.set(f.id,url);while(thumbnailPictures.size>96){const key=thumbnailPictures.keys().next().value;URL.revokeObjectURL(thumbnailPictures.get(key));thumbnailPictures.delete(key);}for(const image of document.querySelectorAll(`img[data-photo-id="${f.id}"]`)){image.src=url;image.hidden=false;image.previousElementSibling.hidden=true;}}).catch(()=>{}).finally(()=>{thumbnailRequests.delete(f.id);thumbnailWorkers--;drainThumbnailQueue();});
 }
}
const thumbnailObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;const f=files.find(item=>item.id===entry.target.dataset.photoId);if(f)queueThumbnail(f);thumbnailObserver.unobserve(entry.target);}},{root:$("#filmstrip"),rootMargin:"0px 300px"});
function drawLibrary(){
 thumbnailObserver.disconnect();
 const visible=visibleFiles();$("#count").textContent=files.length;$("#filmstrip").replaceChildren();
 if(!visible.length)$("#filmstrip").append(element("p",files.length?"No files match this filter.":"Choose a photo folder.","no-files"));
 for(const f of visible){
  const entry=element("div",undefined,"strip-entry"+(selectedIds.has(f.id)?" batch-selected":""));
  const b=element("button",undefined,"strip-item"+(f.id===selected?.id?" selected":""));b.title=f.name;b.setAttribute("aria-label", "Open "+f.name);
  const visual=element("span",undefined,"strip-visual"),placeholder=element("span",f.format,"strip-placeholder"),im=element("img");im.alt="Thumbnail of "+f.name;im.dataset.photoId=f.id;const source=pictures.get(f.id)||thumbnailPictures.get(f.id);if(source){im.src=source;placeholder.hidden=true;}else{im.hidden=true;visual.dataset.photoId=f.id;thumbnailObserver.observe(visual);}visual.append(placeholder,im);if(f.id===selected?.id)visual.append(element("span","VIEWING","strip-active-badge"));
  const caption=element("span",undefined,"strip-caption");caption.append(element("strong",f.name),element("small",f.format));b.append(visual,caption);
  b.onclick=()=>openPhoto(f,selectedIds.size>1&&selectedIds.has(f.id));
  const check=element("button",selectedIds.has(f.id)?"✓":"","strip-select");check.type="button";check.title=selectedIds.has(f.id)?"Remove from editing group":"Include in editing group";check.setAttribute("aria-label",check.title+": "+f.name);check.setAttribute("aria-pressed",String(selectedIds.has(f.id)));check.onclick=e=>{e.stopPropagation();toggleSelected(f);};
  entry.append(b,check);$("#filmstrip").append(entry);
 }
 updateSelectionState();
}
function toggleSelected(f){
 syncActiveRecipe();undoStack=[];future=[];
 if(selectedIds.has(f.id)){
  if(selectedIds.size===1)return toast("Keep at least one photo selected.");
  selectedIds.delete(f.id);
  if(selected?.id===f.id){const next=files.find(item=>selectedIds.has(item.id));return openPhoto(next,true);}
 }else{selectedIds.add(f.id);ensureRecipe(f.id,recipe);}
 drawLibrary();toast(selectedIds.size>1?`${selectedIds.size} photos selected. New adjustments will apply to the group.`:"Individual editing restored.");
}
$("#selection-clear").onclick=()=>{if(!selected)return;selectedIds.clear();selectedIds.add(selected.id);undoStack=[];future=[];drawLibrary();toast("Group cleared. Adjustments now apply only to the photo being viewed.");};
async function openPhoto(f,preserveSelection=false){
 clearTimeout(prefetchTimer);
 syncActiveRecipe();
 if(!preserveSelection){selectedIds.clear();selectedIds.add(f.id);undoStack=[];future=[];}else if(!selectedIds.has(f.id)){selectedIds.add(f.id);}
 ensureRecipe(f.id,recipe||defaults);recipe=structuredClone(ensureRecipe(f.id));
 opticsInfo=null;shootingSettings=null;sourceCamera=null;currentRenderQuality=null;previewVariant=null;fullWidth=fullHeight=0;clearDetailTiles(true);$("#shooting").disabled=true;const version=++selectionVersion;renderRevision++;comparing=false;beforeURL && URL.revokeObjectURL(beforeURL);beforeURL=null;selected=f;$("#export-image").disabled=true;$("#compare").disabled=true;populate();drawLibrary();$("#filename").textContent=f.name;$("#file-subtitle").textContent=f.format+" · "+f.group;$("#preview").hidden=true;$("#empty").hidden=true;$("#loading").hidden=false;$("#zoom").disabled=true;resetView();$("#recipe-state").textContent=selectedIds.size>1?`Editing ${selectedIds.size} selected photos`:"Photo recipe restored";$("#preview-kind").textContent="Opening…";
 try{
  const info=await api("/api/photo/"+f.id);if(version!==selectionVersion)return;
  fullWidth=info.developed_size?.width||info.sizes.width;fullHeight=info.developed_size?.height||info.sizes.height;opticsInfo=info.optics;updateOpticsStatus();shootingSettings=info.shooting_settings;$("#shooting").disabled=!shootingSettings;const x=info.exif;sourceCamera=String(x.Model||"").trim().toUpperCase();populate();$("#file-subtitle").textContent=[info.input_normalization?.label||f.format, `Developed ${fullWidth} × ${fullHeight}`, info.source_exposure?.ev ? `Base${info.source_exposure.reference_matched?" estimated":""} ${info.source_exposure.ev>0?"+":""}${info.source_exposure.ev.toFixed(2)} EV` : null].filter(Boolean).join(" · ");
  $("#photo-info").textContent=[info.input_normalization?.label||f.format,x.FNumber?"ƒ/"+x.FNumber:null,x.ExposureTime?x.ExposureTime+" s":null,x.ISO?"ISO "+x.ISO:null].filter(Boolean).join("   ·   ")||"File metadata";
  if(info.preview_available&&!info.source_exposure?.white_balance?.shift_removed){if(!embeddedPictures.has(f.id)){const blob=await api("/api/preview/"+f.id);if(version!==selectionVersion)return;embeddedPictures.set(f.id,URL.createObjectURL(blob));while(embeddedPictures.size>32){const key=embeddedPictures.keys().next().value;URL.revokeObjectURL(embeddedPictures.get(key));embeddedPictures.delete(key);}}if(version!==selectionVersion)return;$("#preview").src=embeddedPictures.get(f.id);$("#preview").hidden=false;$("#zoom").disabled=false;$("#preview-kind").textContent="EMBEDDED PREVIEW · recipe not applied";drawLibrary();}
  else{$("#preview-kind").textContent="Developing RAW…";}
  scheduleRender(0);
 }catch(e){reportError(e,"handled");if(version===selectionVersion){toast(e.message);$("#preview-kind").textContent=e.message;$("#photo-info").textContent="This file could not be opened.";}}
 finally{if(version===selectionVersion)$("#loading").hidden=true;}
}
function applySettings(value){recordUndo();applyFullToSelection(value);populate();persist();scheduleRender(0);}
$("#shooting").onclick=()=>{if(shootingSettings){applySettings(shootingSettings);toast("Recognized capture settings applied. Import remains partial.");}};
$("#undo").onclick=()=>{if(!undoStack.length)return;future.push(restoreSnapshot(undoStack.pop()));populate();persist();scheduleRender(0);};
$("#redo").onclick=()=>{if(!future.length)return;undoStack.push(restoreSnapshot(future.pop()));populate();persist();scheduleRender(0);};
$("#copy-settings").onclick=()=>{copiedSettings=structuredClone(recipe);toast("Settings copied.");};
$("#paste-settings").onclick=()=>{if(copiedSettings)applySettings(copiedSettings);else toast("Copy settings first.");};
$("#store-preset").onclick=()=>{try{localStorage.setItem("film-studio-"+$("#preset-slot").value,JSON.stringify(recipe));toast("Recipe saved to "+$("#preset-slot").value);}catch(e){reportError(e,"handled");toast("Local storage is unavailable. Save the recipe as JSON instead.");}};
$("#recall-preset").onclick=async()=>{try{const slot=$("#preset-slot").value,body=localStorage.getItem("film-studio-"+slot)||localStorage.getItem("fuji-studio-"+slot);if(!body)return toast("This slot is empty.");const result=await api("/api/recipe",{method:"POST",headers:{"Content-Type":"application/json"},body});applySettings(result.recipe);}catch(e){reportError(e,"handled");toast(e.message);}};
function scheduleRender(delay=70){
 if(beforeURL)URL.revokeObjectURL(beforeURL);beforeURL=null;
 renderRevision++;currentRenderQuality=null;previewVariant=null;comparing=false;clearDetailTiles(true); $("#compare").textContent="View Without Film";
 $("#export-image").disabled=true;$("#compare").disabled=true;$("#recipe-state").textContent="Settings pending…";
 clearTimeout(renderTimer);
 renderTimer=setTimeout(queueRender,delay);
}
function queueRender(){
 if(!selected)return;
 if(exportInProgress){renderAgain=true;return;}
 if(renderBusy){
  renderAgain=true;renderController?.abort();
  return;
 }
 updateRender();
}
async function updateRender(){
 if(!selected)return;
 renderBusy=true;renderAgain=false;
 const controller=new AbortController();renderController=controller;
 const revision=renderRevision,id=selected.id,settings=structuredClone(recipe);
 const showOverlay=photo.hidden;$("#loading").hidden=!showOverlay;$("#loading").textContent="Updating preview…";
 $("#recipe-state").textContent="Updating screen preview…";
 try{
  const blob=await api("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,recipe:settings,quality:"interactive"}),signal:controller.signal});
  if(revision!==renderRevision||id!==selected?.id)return;
  const nextURL=await decodedPreviewURL(blob);
  if(revision!==renderRevision||id!==selected?.id){URL.revokeObjectURL(nextURL);return;}
  const previousURL=renderURL;renderURL=nextURL;previewVariant="recipe";
  $("#preview").src=renderURL;$("#preview").hidden=false;$("#zoom").disabled=false;
  if(previousURL)URL.revokeObjectURL(previousURL);
 currentRenderQuality="interactive";
 $("#preview-kind").textContent="QUICK PREVIEW · "+(films.find(f=>f[0]===settings.film)?.[1]||settings.film);
  $("#recipe-state").textContent="Refining image…";
  if(pictures.has(id))URL.revokeObjectURL(pictures.get(id));pictures.set(id,URL.createObjectURL(blob));while(pictures.size>32){const key=pictures.keys().next().value;URL.revokeObjectURL(pictures.get(key));pictures.delete(key);}drawLibrary();
  $("#export-image").disabled=false;$("#compare").disabled=false;updateSelectionState();
  updateView(180);
  scheduleFullPrefetch(id);
 }catch(e){reportError(e,"handled");if(e.name!=="AbortError"&&revision===renderRevision){toast(e.message);$("#recipe-state").textContent="Render failed · previous preview";}}
 finally{if(renderController===controller)renderController=null;renderBusy=false;$("#loading").hidden=true;if(renderAgain||revision!==renderRevision){renderAgain=false;queueRender();}}
}
$("#compare").onclick=async()=>{
 if(!selected||!renderURL)return;
 const id=selected.id,rev=renderRevision;
 $("#compare").disabled=true;
 try{
  if(!beforeURL){const b=await api("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,recipe,neutral:true,quality:"interactive"})});if(id!==selected?.id||rev!==renderRevision)return;const url=await decodedPreviewURL(b);if(id!==selected?.id||rev!==renderRevision){URL.revokeObjectURL(url);return;}beforeURL=url;}
  comparing=!comparing;$("#preview").src=comparing?beforeURL:renderURL;
  previewVariant=comparing?"neutral":"recipe";clearDetailTiles(false);
  $("#compare").textContent=comparing?"View Recipe":"View Without Film";
  $("#preview-kind").textContent=comparing?"RAW BASE · no film simulation or recipe settings":("AFTER · "+filmSourceLabel(recipe.film));
  updateView(0);
 }catch(e){reportError(e,"handled");toast(e.message);}
 finally{if(id===selected?.id&&rev===renderRevision)$("#compare").disabled=false;}
};
$("#export-image").onclick=async()=>{
 if(!selected||exportInProgress)return;exportInProgress=true;lastExportTiming=null;syncActiveRecipe();const targets=files.filter(file=>selectedIds.has(file.id));
 clearTimeout(tileTimer);clearTimeout(prefetchTimer);detailQueue.pause();
 const started=performance.now(),baseLabel=targets.length>1?`Exporting ${targets.length} full-resolution JPEGs`:"Exporting full-resolution image",showElapsed=()=>{$("#export-image").textContent=`${baseLabel}… ${Math.floor((performance.now()-started)/1000)} s`;};
 $("#export-image").disabled=true;showElapsed();const elapsedTimer=setInterval(showElapsed,1000);
 try{let blob,download,message;if(targets.length>1){const items=targets.map(file=>({id:file.id,recipe:structuredClone(ensureRecipe(file.id))}));if(items.some(item=>item.recipe.file_type!=="jpeg"))throw new Error("Batch export supports JPEG only. Select JPEG in Crop & Output.");blob=await api("/api/export-batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items})});download=`kora-${targets.length}-photos.zip`;message=`${targets.length} JPEGs exported with their current recipes.`;}else{const settings=structuredClone(recipe);blob=await api("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:selected.id,recipe:settings})});download=selected.name.replace(/\.[^.]+$/,"-")+settings.film+(settings.file_type==="jpeg"?".jpg":".tif");message="Image exported with its current recipe.";}
 const seconds=((performance.now()-started)/1000).toFixed(1),url=URL.createObjectURL(blob),a=element("a");a.href=url;a.download=download;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);toast(`${message} ${seconds} s.`);
 const report=$("#export-report");report.hidden=false;report.textContent=`JPEG ready in ${seconds} s · request ${lastExportTiming.request.toFixed(1)} s · transfer ${lastExportTiming.transfer.toFixed(1)} s`;report.title=lastExportTiming.server;
 }catch(e){reportError(e,"handled");toast(e.message);}finally{clearInterval(elapsedTimer);exportInProgress=false;$("#export-image").disabled=false;$("#export-image").textContent=exportLabel();if(renderAgain&&!renderBusy)queueRender();scheduleTileRefresh(0);scheduleFullPrefetch(selected?.id);}
};

async function importFiles(items){
 const raws=[...items].filter(f=>rawExtensions.has("."+f.name.split(".").pop().toLowerCase()));if(!raws.length)return toast("Choose a compatible RAW file (RAF, DNG, CR3, NEF, ARW…).");let first;
 $("#import").disabled=true;
 for(let i=0;i<raws.length;i++){
  const f=raws[i];$("#import").textContent=`Import ${i+1}/${raws.length}…`;
  try{const added=await api("/api/import?name="+encodeURIComponent(f.name),{method:"POST",body:f,headers:{"Content-Type":"application/octet-stream"}});files.push(added);first ||= added;}catch(e){reportError(e,"handled");toast(f.name+" : "+e.message);}
 }
 $("#import").disabled=false;$("#import").textContent="Import Files";drawLibrary();if(first)await openPhoto(first);$("#file-input").value="";
}
$("#import").onclick=()=>$("#file-input").click();$("#file-input").onchange=e=>importFiles(e.target.files);
$("#recipe-form").addEventListener("submit",e=>e.preventDefault());
$("#recipe-form").addEventListener("input",e=>{const key=e.target.dataset.key;if(!key||!recipe)return;recordUndo();applyPatchToSelection({[key]:typeof defaults[key]==="number"?Number(e.target.value):e.target.value});populate();persist();scheduleRender();});
$("#reset").onclick=()=>{applySettings(defaults);toast("Recipe reset to PROVIA defaults.");};
$("#save-recipe").onclick=async()=>{try{const result=await api("/api/recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(recipe)});const url=URL.createObjectURL(new Blob([JSON.stringify(result.recipe,null,2)+"\n"],{type:"application/json"}));const a=element("a");a.href=url;a.download=(recipe.name.replace(/[^\p{L}\p{N}_-]+/gu,"-")||"recipe")+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Recipe JSON saved.");}catch(e){reportError(e,"handled");toast(e.message);}};
function renderRecipeLibrary(data,selectedId=""){
 recipeFolder=data?.folder||null;const select=$("#recipe-library-select");select.replaceChildren();
 const items=data?.recipes||[],placeholder=element("option",recipeFolder?(items.length?"Choose a saved recipe…":"No valid recipes found"):"Choose a recipe folder…");placeholder.value="";select.append(placeholder);
 for(const item of items){const stem=item.filename.replace(/\.json$/i,""),option=element("option",item.name+(stem===item.name?"":" · "+item.filename));option.value=item.id;option.title=item.filename+" · "+item.film;select.append(option);}
 select.value=[...select.options].some(option=>option.value===selectedId)?selectedId:"";select.disabled=!items.length;$("#refresh-recipes").disabled=!recipeFolder;$("#choose-recipe-folder").title=recipeFolder||"Choose the folder containing your recipe JSON files";
}
async function loadRecipeFolder(path,{quiet=false}={}){
 const data=await api("/api/recipes/folder",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path})});renderRecipeLibrary(data);localStorage.setItem("film-recipe-folder",data.folder);
 if(!quiet){const skipped=data.invalid_count?" "+data.invalid_count+" invalid JSON file"+(data.invalid_count===1?" was":"s were")+" ignored.":"";toast(data.recipes.length+" recipe"+(data.recipes.length===1?"":"s")+" found."+skipped);}
 return data;
}
$("#choose-recipe-folder").onclick=()=>openFolderPicker("recipes");
$("#refresh-recipes").onclick=async()=>{if(!recipeFolder)return;try{await loadRecipeFolder(recipeFolder);}catch(e){reportError(e,"handled");toast(e.message);}};
$("#recipe-library-select").onchange=async e=>{const id=e.target.value;if(!id)return;try{const result=await api("/api/recipes/load",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});applySettings(result.recipe);toast(result.recipe.name+" loaded.");}catch(err){reportError(err,"handled");toast(err.message);}};
$("#search").oninput=drawLibrary;for(const b of document.querySelectorAll("[data-filter]"))b.onclick=()=>{filter=b.dataset.filter;for(const x of document.querySelectorAll("[data-filter]"))x.classList.toggle("active",x===b);drawLibrary();};

$("#about").onclick=()=>$("#engine-dialog").showModal();$("#close-dialog").onclick=()=>$("#engine-dialog").close();
function updateLutSetup(engine){
 if(engine?.app_version)$("#app-version").textContent='KŌRA '+engine.app_version;
 engineState=engine;const missing=engine?.missing_luts||[],status=$("#lut-status");
 status.classList.toggle("ready",!missing.length);
 status.textContent=missing.length?`${missing.length} of 10 official LUTs are missing.`:"All 10 official LUTs are installed and verified.";
 $("#choose-lut-archive").textContent=missing.length?"2. Choose Downloaded ZIP":"Reinstall from ZIP";
}
$("#setup").onclick=()=>$("#setup-dialog").showModal();
$("#setup-close").onclick=()=>$("#setup-dialog").close();
$("#choose-lut-archive").onclick=()=>$("#lut-input").click();
$("#lut-input").onchange=async()=>{
 const input=$("#lut-input"),archive=input.files[0];if(!archive)return;
 const button=$("#choose-lut-archive"),progress=$("#lut-progress"),error=$("#lut-error");
 button.disabled=true;progress.hidden=false;error.textContent="";$("#lut-status").textContent="Verifying and installing the LUTs…";
 try{
  const result=await api("/api/luts/install?name="+encodeURIComponent(archive.name),{method:"POST",headers:{"Content-Type":"application/zip"},body:archive});
  updateLutSetup(result.engine);toast("Official LUTs installed and verified.");
  if(selected)scheduleRender(0);
 }catch(e){reportError(e,"handled");error.textContent=e.message;updateLutSetup(engineState);}
 finally{button.disabled=false;progress.hidden=true;input.value="";}
};
document.addEventListener("keydown",e=>{if(["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName)||$("#engine-dialog").open||$("#folder-dialog").open)return;const list=visibleFiles(),i=list.findIndex(f=>f.id===selected?.id),j=i+(e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0);if(j!==i&&list[j]){e.preventDefault();openPhoto(list[j]);}});
let drags=0;document.addEventListener("dragenter",e=>{if(e.dataTransfer.types.includes("Files")){e.preventDefault();drags++;$("#drop-overlay").hidden=false;}});document.addEventListener("dragleave",()=>{if(--drags<=0)$("#drop-overlay").hidden=true;});document.addEventListener("dragover",e=>e.preventDefault());document.addEventListener("drop",e=>{e.preventDefault();drags=0;$("#drop-overlay").hidden=true;importFiles(e.dataTransfer.files);});
setupControls();
(async()=>{try{const data=await api("/api/library");rawExtensions=new Set(data.engine.raw_extensions||[".raf",".dng"]);thumbnailWorkerLimit=Math.max(2,Math.min(8,Number(data.performance?.thumbnail_workers)||2));fullResolutionPrefetch=!!data.performance?.full_resolution_prefetch;$("#file-input").accept=[...rawExtensions].join(",");files=[];defaults=data.recipe;recipe=structuredClone(defaults);populate();drawLibrary();renderRecipeLibrary(null);updateLutSetup(data.engine);$("#input-folder").textContent="Choose a folder to begin";const savedRecipeFolder=localStorage.getItem("film-recipe-folder");if(savedRecipeFolder)loadRecipeFolder(savedRecipeFolder,{quiet:true}).catch(e=>{reportError(e,"handled");localStorage.removeItem("film-recipe-folder");renderRecipeLibrary(null);});if(data.engine.missing_luts?.length)$("#setup-dialog").showModal();}catch(e){reportError(e,"handled");toast(e.message);$("#file-subtitle").textContent="Reopen the full link displayed in the terminal.";}})();

// The quick image remains underneath progressively decoded RAW tiles in EVERY
// view. Zoom percentages count physical screen pixels, including Retina.
let zoomMode="fit",viewScale=1,panX=0,panY=0,panGesture=null;
const viewport=$("#canvas"),photo=$("#preview"),detailLayer=$("#detail-layer"),TILE_SIZE=768;
const detailNodes=new Map(),tileDecodes=new Map();
let activeTilePlan=null;
const screenDensity=()=>KoraViewer.density(window.devicePixelRatio);
const detailQueue=new KoraViewer.DetailQueue({
 cached:key=>tileURLs.has(key),
 load:(tile,signal)=>api("/api/tile",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({id:tile.id,recipe:tile.settings,neutral:tile.neutral,x:tile.x,y:tile.y,
   size:TILE_SIZE,level:tile.level,view_id:tileViewId,generation:tile.generation}),signal}),
 ready:async(tile,blob)=>{
  if(tile.generation!==tileGeneration)return;
  const previous=tileURLs.get(tile.key);if(previous)URL.revokeObjectURL(previous);
  tileURLs.set(tile.key,URL.createObjectURL(blob));
  await addDetailTile(tile);trimTileCache();
 },
 error:error=>reportError(error,"viewer.detail"),
 state:()=>updateDetailStatus()
});
async function decodedPreviewURL(blob){
 const url=URL.createObjectURL(blob),image=new Image();image.src=url;
 try{await image.decode();return url;}catch(error){URL.revokeObjectURL(url);throw error;}
}
function outputGeometry(){
 let w=fullWidth||photo.naturalWidth,h=fullHeight||photo.naturalHeight;if(!w||!h)return {width:0,height:0};
 let cw=Math.floor(w/Number(recipe?.digital_crop||1)),ch=Math.floor(h/Number(recipe?.digital_crop||1));
 if(recipe?.aspect&&recipe.aspect!=="original"){let [rw,rh]=recipe.aspect.split(":").map(Number),ratio=rw/rh;if(h>w)ratio=1/ratio;if(cw/ch>ratio)cw=Math.round(ch*ratio);else ch=Math.round(cw/ratio);}
 const factor={L:1,M:.7071,S:.5}[recipe?.image_size]||1,edge=Math.round(Math.max(cw,ch)*factor);
 if(edge<Math.max(cw,ch)){const maximum=Math.max(cw,ch);cw=Math.max(1,Math.round(cw*edge/maximum));ch=Math.max(1,Math.round(ch*edge/maximum));}
 return {width:cw,height:ch};
}
function fitScale(){const geometry=outputGeometry();return Math.min(viewport.clientWidth/geometry.width,viewport.clientHeight/geometry.height,1/screenDensity());}
function clearDetailTiles(dropCache=false){
 clearTimeout(tileTimer);tileGeneration++;detailQueue.pause();activeTilePlan=null;
 detailLayer.replaceChildren();detailNodes.clear();tileDecodes.clear();detailLayer.hidden=true;
 if(dropCache){for(const url of tileURLs.values())URL.revokeObjectURL(url);tileURLs.clear();}
}
function trimTileCache(){
 while(tileURLs.size>128){
  const key=[...tileURLs.keys()].find(key=>!detailNodes.has(key)&&!tileDecodes.has(key)&&!activeTilePlan?.keys.has(key));
  if(!key)break;URL.revokeObjectURL(tileURLs.get(key));tileURLs.delete(key);
 }
}
function addDetailTile(tile){
 const {key,x,y,width,height,level,generation}=tile;
 if(detailNodes.has(key))return Promise.resolve();
 if(tileDecodes.has(key))return tileDecodes.get(key);
 const url=tileURLs.get(key);if(!url)return Promise.resolve();
 // Keep recently visible tiles warm when the user pans back.
 tileURLs.delete(key);tileURLs.set(key,url);
 const pending=(async()=>{
  const image=element("img");image.alt="";image.decoding="async";image.src=url;
  try{
   await image.decode();
   if(generation!==tileGeneration||!activeTilePlan?.keys.has(key))return;
   image.dataset.x=x;image.dataset.y=y;image.dataset.width=width;image.dataset.height=height;image.dataset.level=level;
   detailNodes.set(key,image);detailLayer.append(image);detailLayer.hidden=false;layoutDetailTiles(image);
   updateDetailStatus();
  }catch(error){
   if(tileURLs.get(key)===url){tileURLs.delete(key);URL.revokeObjectURL(url);}
   throw error;
  }finally{if(tileDecodes.get(key)===pending)tileDecodes.delete(key);}
 })();tileDecodes.set(key,pending);return pending;
}
function layoutDetailTiles(only){
 const images=only?[only]:detailLayer.querySelectorAll("img");
 for(const image of images){image.style.left=Number(image.dataset.x)*viewScale+"px";image.style.top=Number(image.dataset.y)*viewScale+"px";image.style.width=Number(image.dataset.width)*viewScale+"px";image.style.height=Number(image.dataset.height)*viewScale+"px";image.style.zIndex=Number(image.dataset.level)===activeTilePlan?.level?2:1;}
}
function scheduleTileRefresh(delay=120){
 clearTimeout(tileTimer);
 if(exportInProgress||!selected||!previewVariant||!fullWidth||!fullHeight)return;
 if(delay<=0){refreshVisibleTiles();return;}
 tileTimer=setTimeout(refreshVisibleTiles,delay);
}
function updateDetailStatus(){
 const plan=activeTilePlan;if(!plan||exportInProgress||!previewVariant)return;
 const ready=plan.visible.every(tile=>detailNodes.has(tile.key));
 if(ready){
  // Keep the old level visible until every replacement in the viewport is
  // decoded. Switching levels must not flash the 1800-pixel quick preview.
  for(const [key,image] of detailNodes)if(!plan.keys.has(key)){image.remove();detailNodes.delete(key);}
  $("#preview-kind").textContent=(comparing?"RAW BASE · HIGH QUALITY":zoomMode==="fit"?"HIGH QUALITY · FIT":"SOURCE-RESOLUTION DETAIL")+" · "+(comparing?"Without film":films.find(f=>f[0]===recipe.film)?.[1]||recipe.film);
  $("#recipe-state").textContent="Image ready";
 }else{
  $("#recipe-state").textContent=plan.visible.some(t=>detailQueue.failed.has(t.key))?"Some detail unavailable · move or zoom to retry":"Refining image…";
 }
}
function refreshVisibleTiles(){
 if(exportInProgress||!selected||!previewVariant)return;
 const geometry=outputGeometry(),id=selected.id,revision=renderRevision,settings=structuredClone(recipe);
 const plan=KoraViewer.planTiles({...geometry,viewportWidth:viewport.clientWidth,viewportHeight:viewport.clientHeight,
  scale:viewScale,panX,panY,dpr:screenDensity(),size:TILE_SIZE});
 const tiles=plan.tiles.map(t=>({...t,id,settings,neutral:comparing,generation:tileGeneration,
  key:`${id}:${revision}:${previewVariant}:${t.level}:${t.x}:${t.y}`}));
 activeTilePlan={...plan,tiles,visible:tiles.filter(t=>t.visible),keys:new Set(tiles.map(t=>t.key))};
 for(const [key,image] of detailNodes){
  const {x0,y0,x1,y1}=plan.bounds||{},x=Number(image.dataset.x),y=Number(image.dataset.y);
  if(!activeTilePlan.keys.has(key)&&(x>=x1||y>=y1||x+Number(image.dataset.width)<=x0||y+Number(image.dataset.height)<=y0)){
   image.remove();detailNodes.delete(key);
  }
 }
 layoutDetailTiles();
 for(const tile of tiles)if(tileURLs.has(tile.key))addDetailTile(tile).catch(error=>{detailQueue.failed.add(tile.key);reportError(error,"viewer.decode");updateDetailStatus();});
 detailQueue.update(tiles);trimTileCache();
}
function updateView(tileDelay=120){
 const ready=!photo.hidden&&photo.naturalWidth>0;
 for(const id of ["zoom","zoom-in","zoom-out"])$("#"+id).disabled=!ready;
 if(!ready)return;
 viewScale=zoomMode==="fit"?fitScale():KoraViewer.scaleForZoom(Number(zoomMode),screenDensity());
 const geometry=outputGeometry(),displayWidth=geometry.width*viewScale,displayHeight=geometry.height*viewScale;
 const maxX=Math.max(0,(displayWidth-viewport.clientWidth)/2),maxY=Math.max(0,(displayHeight-viewport.clientHeight)/2);
 panX=Math.max(-maxX,Math.min(maxX,panX));panY=Math.max(-maxY,Math.min(maxY,panY));
 // Size the bitmap directly instead of transforming its full 60 MP surface.
 // WebKit can rasterize very large transformed JPEGs with a non-uniform
 // backing surface, making a correct 3:2 DNG look vertically compressed.
 photo.style.width=displayWidth+"px";photo.style.height=displayHeight+"px";
 photo.style.transform=`translate(-50%,-50%) translate(${panX}px,${panY}px)`;
 detailLayer.style.width=displayWidth+"px";detailLayer.style.height=displayHeight+"px";detailLayer.style.transform=photo.style.transform;
 layoutDetailTiles();
 viewport.classList.toggle("pannable",maxX>0||maxY>0);
 const select=$("#zoom");select.querySelector('[data-custom]')?.remove();
 const val=zoomMode==="fit"?"fit":String(zoomMode);
 if(![...select.options].some(o=>o.value===val)){const o=element("option",Math.round(Number(zoomMode)*100)+" %");o.value=val;o.dataset.custom="1";select.append(o);}
 select.value=val;
 scheduleTileRefresh(tileDelay);
}
function resetView(){zoomMode="fit";panX=panY=0;updateView(0);}
function changeZoom(value,point){
 if(photo.hidden||!photo.naturalWidth)return;
 if(value==="fit"){resetView();return;}
 const next=Math.max(.02,Math.min(4,Number(value))),nextScale=KoraViewer.scaleForZoom(next,screenDensity()),box=viewport.getBoundingClientRect();
 const x=point?point.clientX-box.left-viewport.clientWidth/2:0,y=point?point.clientY-box.top-viewport.clientHeight/2:0;
 panX=x-(x-panX)*nextScale/viewScale;panY=y-(y-panY)*nextScale/viewScale;zoomMode=next;updateView(100);
}
photo.addEventListener("load",()=>updateView(0));photo.draggable=false;
$("#zoom").title="100% = one image pixel per screen pixel. Fit also loads high-quality RAW detail.";
$("#zoom").onchange=e=>changeZoom(e.target.value);
$("#zoom-in").onclick=()=>changeZoom(viewScale*screenDensity()*1.25);$("#zoom-out").onclick=()=>changeZoom(viewScale*screenDensity()/1.25);
viewport.addEventListener("wheel",e=>{if(photo.hidden)return;e.preventDefault();changeZoom(viewScale*screenDensity()*Math.exp(-e.deltaY*(e.deltaMode===1?.04:.002)),e);},{passive:false});
viewport.addEventListener("dblclick",e=>{if(!photo.hidden)changeZoom(zoomMode==="fit"?1:"fit",e);});
viewport.addEventListener("pointerdown",e=>{if(e.button!==0||photo.hidden||!viewport.classList.contains("pannable"))return;panGesture={x:e.clientX,y:e.clientY,px:panX,py:panY};viewport.setPointerCapture(e.pointerId);viewport.classList.add("dragging");e.preventDefault();});
viewport.addEventListener("pointermove",e=>{if(!panGesture)return;panX=panGesture.px+e.clientX-panGesture.x;panY=panGesture.py+e.clientY-panGesture.y;updateView();});
for(const event of ["pointerup","pointercancel","lostpointercapture"])viewport.addEventListener(event,()=>{panGesture=null;viewport.classList.remove("dragging");scheduleTileRefresh(0);});
new ResizeObserver(()=>updateView()).observe(viewport);
// Moving a window between displays can change density without changing its
// CSS dimensions. Re-evaluate both physical zoom and tile resolution.
let densityQuery;
function watchDensity(){
 densityQuery?.removeEventListener("change",densityChanged);
 densityQuery=matchMedia(`(resolution: ${screenDensity()}dppx)`);densityQuery.addEventListener("change",densityChanged);
}
function densityChanged(){watchDensity();updateView(0);}
watchDensity();

// Resizable framing around the photograph. Values are local UI preferences;
// double-clicking any separator restores that edge to its default size.
const frameDefaults={left:180,right:260,top:32,bottom:108},workspace=$(".workspace");
let frameLayout={...frameDefaults};
try{const saved=JSON.parse(localStorage.getItem("film-view-layout")||"null");if(saved)for(const key of Object.keys(frameDefaults))if(Number.isFinite(saved[key]))frameLayout[key]=saved[key];}catch(_){reportError(_,"handled");}
// Upgrade the previous defaults without discarding manually resized panels.
if([42,52,62].includes(frameLayout.top))frameLayout.top=frameDefaults.top;
if([146,218,250].includes(frameLayout.bottom))frameLayout.bottom=frameDefaults.bottom;
if([190,224].includes(frameLayout.left))frameLayout.left=frameDefaults.left;
if([286,326].includes(frameLayout.right))frameLayout.right=frameDefaults.right;
function frameLimits(key){
 const viewerHeight=$(".viewer").clientHeight||innerHeight;
 if(key==="left")return [120,Math.max(120,Math.min(480,innerWidth-frameLayout.right-340))];
 if(key==="right")return [240,Math.max(240,Math.min(520,innerWidth-frameLayout.left-340))];
 if(key==="top")return [32,Math.max(32,Math.min(140,viewerHeight-frameLayout.bottom-120))];
 return [100,Math.max(100,Math.min(360,viewerHeight-frameLayout.top-120))];
}
function setFrameSize(key,value,save=false){const [minimum,maximum]=frameLimits(key);frameLayout[key]=Math.round(Math.max(minimum,Math.min(maximum,value)));applyFrameLayout();if(save)persistFrameLayout();}
function applyFrameLayout(){
 const desktop=innerWidth>800;
 if(desktop)for(const key of Object.keys(frameDefaults)){const [minimum,maximum]=frameLimits(key);frameLayout[key]=Math.round(Math.max(minimum,Math.min(maximum,frameLayout[key])));}
 for(const key of ["left","right"]){const property="--"+key;if(desktop)workspace.style.setProperty(property,frameLayout[key]+"px");else workspace.style.removeProperty(property);}
 for(const [key,property] of [["top","--viewer-head"],["bottom","--viewer-bottom"]]){if(desktop)workspace.style.setProperty(property,frameLayout[key]+"px");else workspace.style.removeProperty(property);}
 for(const handle of document.querySelectorAll("[data-resize]")){const key=handle.dataset.resize,[minimum,maximum]=frameLimits(key);handle.setAttribute("aria-valuemin",minimum);handle.setAttribute("aria-valuemax",maximum);handle.setAttribute("aria-valuenow",frameLayout[key]);handle.title="Drag to resize · double-click to reset";}
}
function persistFrameLayout(){try{localStorage.setItem("film-view-layout",JSON.stringify(frameLayout));}catch(_){reportError(_,"handled");}}
for(const handle of document.querySelectorAll("[data-resize]")){
 const key=handle.dataset.resize;let gesture=null;
 handle.onpointerdown=e=>{if(e.button!==0||innerWidth<=800)return;gesture={x:e.clientX,y:e.clientY,value:frameLayout[key]};handle.setPointerCapture(e.pointerId);handle.classList.add("resizing");document.body.classList.add("layout-resizing");document.body.classList.toggle("vertical",key==="top"||key==="bottom");e.preventDefault();};
 handle.onpointermove=e=>{if(!gesture)return;const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;setFrameSize(key,gesture.value+(key==="left"?dx:key==="right"?-dx:key==="top"?dy:-dy));};
 const finish=()=>{if(!gesture)return;gesture=null;handle.classList.remove("resizing");document.body.classList.remove("layout-resizing","vertical");persistFrameLayout();scheduleTileRefresh(0);};
 handle.onpointerup=finish;handle.onpointercancel=finish;handle.onlostpointercapture=finish;
 handle.ondblclick=()=>setFrameSize(key,frameDefaults[key],true);
 handle.onkeydown=e=>{const step=e.shiftKey?25:8;let delta=0;if(key==="left")delta=e.key==="ArrowRight"?step:e.key==="ArrowLeft"?-step:0;else if(key==="right")delta=e.key==="ArrowLeft"?step:e.key==="ArrowRight"?-step:0;else if(key==="top")delta=e.key==="ArrowDown"?step:e.key==="ArrowUp"?-step:0;else delta=e.key==="ArrowUp"?step:e.key==="ArrowDown"?-step:0;if(e.key==="Home"){e.preventDefault();setFrameSize(key,frameDefaults[key],true);}else if(delta){e.preventDefault();setFrameSize(key,frameLayout[key]+delta,true);}};
}
addEventListener("resize",applyFrameLayout);applyFrameLayout();
let panels={library:false,editor:true};
try{const saved=JSON.parse(localStorage.getItem("film-view-panels")||localStorage.getItem("fuji-view-panels"));if(saved&&typeof saved.library==="boolean"&&typeof saved.editor==="boolean")panels=saved;}catch(_){reportError(_,"handled");}
function updatePanels(){
 for(const side of ["library","editor"]){$("."+side).hidden=!panels[side];$(".workspace").classList.toggle("hide-"+side,!panels[side]);$("#toggle-"+side).setAttribute("aria-pressed",String(panels[side]));}
 $("#focus-view").textContent=!panels.library&&!panels.editor?"Show Panels":"Photo View";
 try{localStorage.setItem("film-view-panels",JSON.stringify(panels));}catch(_){reportError(_,"handled");}
}
for(const side of ["library","editor"])$("#toggle-"+side).onclick=()=>{panels[side]=!panels[side];updatePanels();};
$("#focus-view").onclick=()=>{const show=!panels.library&&!panels.editor;panels={library:show,editor:show};updatePanels();};updatePanels();
// A native window can enter fullscreen on launch. Browsers require a user click.
$("#fullscreen").onclick=async()=>{
 try{
  if(nativeWindow){await api("/api/window/fullscreen",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});return;}
  if(document.fullscreenElement)await document.exitFullscreen();
  else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();
  else toast("Use your browser’s full-screen command.");
 }catch(e){reportError(e,"handled");toast("Could not change full-screen mode: "+e.message);}
};
document.addEventListener("fullscreenchange",()=>{$("#fullscreen").title=document.fullscreenElement?"Exit Full Screen":"Full Screen";});
document.addEventListener("keydown",e=>{if(["INPUT","SELECT","TEXTAREA","BUTTON"].includes(document.activeElement.tagName)||document.activeElement.id==="wb-grid"||$("#folder-dialog").open||$("#engine-dialog").open||$("#setup-dialog").open)return;
 if(e.key==="Tab"){e.preventDefault();$("#focus-view").click();}else if(["+","="].includes(e.key)){e.preventDefault();changeZoom(viewScale*1.25);}else if(e.key==="-"){e.preventDefault();changeZoom(viewScale/1.25);}else if(e.key==="0")resetView();else if(e.key==="1")changeZoom(1);
});
// Local folder browser: no copying of RAW files and no upload of a directory.
let folderPath=null,folderParent=null,folderRevision=0,folderPurpose="photos";
$("#choose-lut-folder").onclick=()=>openFolderPicker("luts");
async function browseFolder(path){
 const revision=++folderRevision;$("#folder-error").textContent="";$("#folder-select").disabled=true;
 try{const data=await api("/api/folders"+(path?"?path="+encodeURIComponent(path):""));if(revision!==folderRevision)return;
 folderPath=data.path;folderParent=data.parent;$("#folder-path").value=data.path||"";$("#folder-up").disabled=!data.parent;
 $("#folder-shortcuts").replaceChildren();
 for(const item of data.shortcuts||[]){const b=element("button",item.name,"folder-shortcut"+(item.path===data.path?" active":""));b.type="button";b.title=item.path;b.onclick=()=>browseFolder(item.path);$("#folder-shortcuts").append(b);}
 $("#folder-breadcrumbs").replaceChildren();
 for(const [index,item] of (data.breadcrumbs||[]).entries()){if(index)$("#folder-breadcrumbs").append(element("span","›","folder-separator"));const b=element("button",item.name,"folder-crumb");b.type="button";b.title=item.path;b.disabled=index===data.breadcrumbs.length-1;b.onclick=()=>browseFolder(item.path);$("#folder-breadcrumbs").append(b);}
 $("#folder-list").replaceChildren();
 for(const f of data.folders){const b=element("button",undefined,"folder-row");b.type="button";b.title=f.path;b.append(element("span","▰","folder-icon"),element("span",f.name,"folder-name"),element("span","›","folder-open"));b.onclick=()=>browseFolder(f.path);$("#folder-list").append(b);}
 if(!data.folders.length)$("#folder-list").append(element("p","This folder has no subfolders.","no-files"));
 $("#folder-selection-name").textContent=data.name||"None";$("#folder-selection-name").title=data.path||"";
 $("#folder-selection-details").textContent=folderPurpose==="luts"?"The official LUTs will be located and verified in this folder and its subfolders.":folderPurpose==="recipes"?"JSON recipe files in this folder will appear in the recipe menu.":`${data.raw_count||0} compatible RAW file${data.raw_count===1?"":"s"} directly in this folder`;
 $("#folder-select").disabled=!data.path;
 }catch(e){reportError(e,"handled");if(revision===folderRevision)$("#folder-error").textContent=e.message;}
}
function openFolderPicker(purpose="photos"){
 folderPurpose=["luts","recipes"].includes(purpose)?purpose:"photos";
 const initialFolder=folderPurpose==="recipes"&&recipeFolder?recipeFolder:folderPurpose==="photos"&&currentFolder?currentFolder:folderPath;
 $("#folder-dialog h2").textContent=folderPurpose==="luts"?"Choose the extracted LUT folder":folderPurpose==="recipes"?"Choose your recipe folder":"Choose a photo folder";
 $("#folder-dialog .eyebrow").textContent=folderPurpose==="luts"?"LUT IMPORT":folderPurpose==="recipes"?"SAVED RECIPES":"INPUT FOLDER";
 $("#folder-dialog .folder-hint").textContent=folderPurpose==="luts"?"Choose the GFX ETERNA 55 folder you unzipped, or its F-Log2 subfolder.":folderPurpose==="recipes"?"Choose the folder where your JSON recipes are saved. The app will remember it.":"Browse from a familiar location, or enter a path. The selected folder is read in place.";
 $("#folder-dialog .folder-recursive").hidden=folderPurpose!=="photos";
 $("#folder-select").textContent=folderPurpose==="luts"?"Install LUTs from This Folder":folderPurpose==="recipes"?"Use This Recipe Folder":"Choose This Folder";
 $("#folder-dialog").showModal();browseFolder(initialFolder);
}
$("#choose-folder").onclick=$("#empty-import").onclick=openFolderPicker;
$("#folder-close").onclick=()=>$("#folder-dialog").close();$("#folder-up").onclick=()=>browseFolder(folderParent);
$("#folder-path-form").onsubmit=e=>{e.preventDefault();browseFolder($("#folder-path").value.trim());};
$("#folder-select").onclick=async()=>{
 if(!folderPath)return;const button=$("#folder-select");button.disabled=true;button.textContent="Reading Folder…";
 if(folderPurpose==="luts"){
  const progress=$("#lut-progress");progress.hidden=false;$("#lut-error").textContent="";
  try{
   const result=await api("/api/luts/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:folderPath})});
   updateLutSetup(result.engine);$("#folder-dialog").close();toast("Official LUTs installed and verified.");if(selected)scheduleRender(0);
  }catch(e){reportError(e,"handled");$("#folder-error").textContent=e.message;}
  finally{button.disabled=false;button.textContent="Install LUTs from This Folder";progress.hidden=true;}
  return;
 }
 if(folderPurpose==="recipes"){
  try{await loadRecipeFolder(folderPath);$("#folder-dialog").close();}
  catch(e){reportError(e,"handled");$("#folder-error").textContent=e.message;}finally{button.disabled=false;button.textContent="Use This Recipe Folder";}
  return;
 }
 try{await selectPhotoFolder(folderPath,$("#folder-recursive").checked);$("#folder-dialog").close();}
 catch(e){reportError(e,"handled");$("#folder-error").textContent=e.message;}finally{button.disabled=false;button.textContent="Choose This Folder";}
};

let currentFolder=null,folderLoadRevision=0;
const folderNodes=new Map(),expandedFolders=new Set(),folderLoads=new Map();
let folderRoots=[];
async function readTreeFolder(path){
 if(folderNodes.has(path))return folderNodes.get(path);
 if(!folderLoads.has(path))folderLoads.set(path,api("/api/folders"+(path?"?path="+encodeURIComponent(path):"")).then(data=>{folderNodes.set(data.path,data);return data;}).finally(()=>folderLoads.delete(path)));
 return folderLoads.get(path);
}
async function initializeFolderTree(){
 try{const data=await readTreeFolder(null);folderRoots=data.shortcuts||[];if(currentFolder)await revealFolder(currentFolder);else drawFolderTree();}
 catch(e){reportError(e,"handled");$("#folder-tree-error").textContent=e.message;}
}
async function revealFolder(path){
 const data=await readTreeFolder(path);
 if(!folderRoots.some(root=>path===root.path||path.startsWith(root.path+"/")))folderRoots.push({path:data.path,name:data.name});
 // Expand ancestors of the closest shortcut, not the entire home directory.
 const root=folderRoots.filter(root=>path===root.path||path.startsWith(root.path+"/")).sort((a,b)=>b.path.length-a.path.length)[0];
 for(const crumb of data.breadcrumbs||[]){if(root&&(crumb.path===root.path||crumb.path.startsWith(root.path+"/"))&&crumb.path!==path){await readTreeFolder(crumb.path);expandedFolders.add(crumb.path);}}
 drawFolderTree();
}
function drawFolderTree(){
 const host=$("#folder-tree");host.replaceChildren();
 function branch(items,depth=0){
  const list=element("ul");
  for(const item of items){
   const li=element("li"),row=element("div",undefined,"tree-folder-row"+(item.path===currentFolder?" active":""));row.style.paddingLeft=(8+depth*14)+"px";
   const expanded=expandedFolders.has(item.path),cached=folderNodes.get(item.path);
   const toggle=element("button",expanded?"▾":"▸","tree-toggle");toggle.type="button";toggle.setAttribute("aria-label",(expanded?"Collapse ":"Expand ")+item.name);toggle.setAttribute("aria-expanded",String(expanded));toggle.disabled=!!cached&&!cached.folders.length;
   toggle.onclick=async()=>{if(expanded){expandedFolders.delete(item.path);drawFolderTree();return;}toggle.disabled=true;toggle.textContent="…";try{await readTreeFolder(item.path);expandedFolders.add(item.path);$("#folder-tree-error").textContent="";}catch(e){reportError(e,"handled");$("#folder-tree-error").textContent=e.message;}finally{drawFolderTree();}};
   const button=element("button",undefined,"tree-folder-name");button.type="button";button.title=item.path;button.append(element("span","▰","tree-folder-icon"),element("span",item.name));if(item.path===currentFolder)button.setAttribute("aria-current","true");
   button.onclick=()=>selectPhotoFolder(item.path,$("#tree-recursive").checked).catch(e=>$("#folder-tree-error").textContent=e.message);
   row.append(toggle,button);li.append(row);if(expanded&&cached?.folders.length)li.append(branch(cached.folders,depth+1));list.append(li);
  }return list;
 }
 host.append(branch(folderRoots));
}
$("#folder-tree-refresh").onclick=async()=>{folderNodes.clear();$("#folder-tree-error").textContent="";await initializeFolderTree();for(const path of expandedFolders){try{await readTreeFolder(path);}catch{expandedFolders.delete(path);}}drawFolderTree();};
$("#tree-recursive").onchange=()=>{if(currentFolder)selectPhotoFolder(currentFolder,$("#tree-recursive").checked).catch(e=>$("#folder-tree-error").textContent=e.message);};
async function selectPhotoFolder(path,recursive=false){
 clearTimeout(prefetchTimer);prefetchedId=null;
 const revision=++folderLoadRevision;$("#folder-tree-error").textContent="";$("#folder-tree").setAttribute("aria-busy","true");
 try{
 const data=await api("/api/folder",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path,recursive})});
 if(revision!==folderLoadRevision)return;
 syncActiveRecipe();selectionVersion++;renderRevision++;renderController?.abort();selected=null;fullWidth=fullHeight=0;clearDetailTiles(true);selectedIds.clear();undoStack=[];future=[];thumbnailQueue=[];clearTimeout(thumbnailTimer);files=data.files;filter="all";$("#search").value="";for(const b of document.querySelectorAll("[data-filter]"))b.classList.toggle("active",b.dataset.filter==="all");
 photo.hidden=true;$("#empty").hidden=false;$("#loading").hidden=true;$("#filename").textContent="Choose a photo";$("#file-subtitle").textContent=files.length+" RAW file"+(files.length===1?"":"s")+" in this folder";$("#photo-info").textContent="";$("#preview-kind").textContent="No photo selected";$("#recipe-state").textContent="Recipe retained";
 $("#compare").disabled=$("#export-image").disabled=true;resetView();
 currentFolder=data.folder;folderPath=data.folder;$("#tree-recursive").checked=recursive;$("#current-folder-name").textContent=data.folder.split("/").filter(Boolean).pop()||"/";$("#current-folder-path").textContent=data.folder;$("#current-folder-count").textContent=files.length+" RAW photos";
 $("#input-folder").textContent=data.folder;$("#input-folder").title=data.folder;drawLibrary();drawFolderTree();
 revealFolder(data.folder).catch(e=>$("#folder-tree-error").textContent=e.message);
 if(data.limit_reached)toast("The library is limited to the first 5,000 RAW files in this folder.");
 const first=files.find(f=>f.local);if(first)await openPhoto(first);else if(!files.length)toast("This folder contains no compatible RAW files.");
 }finally{if(revision===folderLoadRevision)$("#folder-tree").setAttribute("aria-busy","false");}
}
initializeFolderTree();

function updateOpticsStatus(){
 const note=$("#optics-status");if(!note)return;
 const button=$("#optics-apply"),available=Boolean(selected&&opticsInfo&&(opticsInfo.distortion||opticsInfo.vignetting));
 if(button){button.hidden=!available;button.disabled=!available||!Object.keys(availableOpticsPatch(opticsInfo,recipe)).length;button.textContent=button.disabled?"Available corrections applied":"Apply available corrections";}
 if(!opticsInfo){note.textContent="Choose a photo to identify its lens.";return;}
 const state=(key,available)=>!available?"no profile":recipe?.[key]==="auto"?"enabled":"available · off";
 const identified=opticsInfo.lens_name&&opticsInfo.source!=="lensfun"?"Detected lens: "+opticsInfo.lens_name+". ":"";
 note.textContent=identified+opticsInfo.label+". Distortion: "+state("lens_distortion",opticsInfo.distortion)+". Vignetting: "+state("lens_vignetting",opticsInfo.vignetting)+".";
}
function availableOpticsPatch(profile,current){
 const patch={};
 for(const [capability,key] of [["distortion","lens_distortion"],["vignetting","lens_vignetting"]]){
  if(profile?.[capability]&&current?.[key]!=="auto")patch[key]="auto";
 }
 return patch;
}
function applyAvailableOptics(){
 if(!selected||!opticsInfo)return;
 const patch=availableOpticsPatch(opticsInfo,recipe);if(!Object.keys(patch).length)return;
 recordUndo();applyPatchToSelection(patch);populate();persist();scheduleRender(0);
}
