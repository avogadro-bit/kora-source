/* Geometry and bounded scheduling shared by Fit and the zoomed RAW viewer. */
(function(root,factory){
 const api=factory();
 if(typeof module==="object"&&module.exports)module.exports=api;else root.KoraViewer=api;
})(globalThis,()=>{
 "use strict";
 function density(value){return Number.isFinite(value)&&value>0?value:1;}
 function scaleForZoom(zoom,dpr){return zoom/density(dpr);}
 function planTiles({width,height,viewportWidth,viewportHeight,scale,panX=0,panY=0,dpr=1,size=768}){
  if(!width||!height||!viewportWidth||!viewportHeight||!(scale>0))return {tiles:[],visible:[],level:1};
  // Never stretch a reduced tile over more physical pixels than it contains.
  const level=2**Math.floor(Math.log2(Math.max(1,Math.min(8,1/(scale*density(dpr))))));
  const left=(viewportWidth-width*scale)/2+panX,top=(viewportHeight-height*scale)/2+panY;
  const x0=Math.max(0,-left/scale),y0=Math.max(0,-top/scale);
  const x1=Math.min(width,(viewportWidth-left)/scale),y1=Math.min(height,(viewportHeight-top)/scale);
  const span=size*level,tiles=[];
  for(let y=Math.max(0,Math.floor(y0/span)-1)*span;y<Math.min(height,(Math.ceil(y1/span)+1)*span);y+=span){
   for(let x=Math.max(0,Math.floor(x0/span)-1)*span;x<Math.min(width,(Math.ceil(x1/span)+1)*span);x+=span){
    const w=Math.min(span,width-x),h=Math.min(span,height-y);
    tiles.push({x,y,width:w,height:h,level,size,visible:x<x1&&x+w>x0&&y<y1&&y+h>y0,
     distance:Math.hypot(x+w/2-(x0+x1)/2,y+h/2-(y0+y1)/2)});
   }
  }
  tiles.sort((a,b)=>Number(b.visible)-Number(a.visible)||a.distance-b.distance);
  return {tiles,visible:tiles.filter(t=>t.visible),level,bounds:{x0,y0,x1,y1}};
 }

 class DetailQueue{
  constructor({load,cached,ready,error,state,limit=2}){
   Object.assign(this,{load,cached,ready,error,state,limit});
   this.wanted=new Map();this.pending=new Map();this.failed=new Set();
  }
  update(tiles){
   this.wanted=new Map(tiles.map(tile=>[tile.key,tile]));this.failed.clear();
   for(const [key,job] of this.pending)if(!this.wanted.has(key))job.controller.abort();
   this.pump();
  }
  pause(){this.wanted.clear();this.failed.clear();for(const job of this.pending.values())job.controller.abort();}
  pump(){
   for(const [key,tile] of this.wanted){
    if(this.pending.size>=this.limit)break;
    if(this.cached(key)||this.pending.has(key)||this.failed.has(key))continue;
    const job={controller:new AbortController()};this.pending.set(key,job);
    Promise.resolve().then(()=>this.load(tile,job.controller.signal)).then(async result=>{
     if(this.wanted.has(key)&&!job.controller.signal.aborted)await this.ready(tile,result);
    }).catch(error=>{
     if(!job.controller.signal.aborted&&this.wanted.has(key)){
      this.failed.add(key);this.error?.(error,tile);
     }
    }).finally(()=>{
     if(this.pending.get(key)===job)this.pending.delete(key);
     this.pump();
    });
   }
   this.state?.();
  }
 }
 return {density,scaleForZoom,planTiles,DetailQueue};
});
