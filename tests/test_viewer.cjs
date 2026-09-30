const {test}=require('node:test'),assert=require('node:assert/strict');
const {planTiles,scaleForZoom,DetailQueue}=require('../kora/static/viewer.js');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const frame={width:9536,height:6344,viewportWidth:1512,viewportHeight:1000,size:768};

test('Fit covers the whole photo with enough samples for Retina, including fractional density',()=>{
 const scale=Math.min(frame.viewportWidth/frame.width,frame.viewportHeight/frame.height);
 for(const dpr of [1,1.25,2,3]){
  const plan=planTiles({...frame,scale,dpr});
  assert.ok(plan.visible.length>0);
  assert.ok(plan.level*scale*dpr<=1);
  assert.equal(plan.visible.reduce((area,t)=>area+t.width*t.height,0),frame.width*frame.height);
 }
 assert.ok(planTiles({...frame,scale,dpr:2}).level<planTiles({...frame,scale,dpr:1}).level);
});
test('100% is one photo pixel per physical screen pixel on every display',()=>{
 for(const dpr of [1,1.25,2,3]){
  const scale=scaleForZoom(1,dpr);assert.equal(scale*dpr,1);
  const plan=planTiles({...frame,scale,dpr});assert.equal(plan.level,1);
  assert.ok(plan.visible.every(t=>t.visible));
  const firstMargin=plan.tiles.findIndex(t=>!t.visible);
  if(firstMargin>=0)assert.ok(plan.tiles.slice(firstMargin).every(t=>!t.visible));
 }
});
test('panning and image edges keep coverage in source coordinates',()=>{
 for(const panX of [-4000,0,4000])for(const panY of [-2600,0,2600]){
  const plan=planTiles({...frame,scale:1,dpr:1,panX,panY});
  for(const tile of plan.tiles){assert.ok(tile.x>=0&&tile.y>=0);assert.ok(tile.x+tile.width<=frame.width);assert.ok(tile.y+tile.height<=frame.height);}
  const {x0,y0,x1,y1}=plan.bounds;
  for(let y=Math.ceil(y0);y<y1;y+=97)for(let x=Math.ceil(x0);x<x1;x+=97){
   assert.equal(plan.visible.filter(t=>x>=t.x&&x<t.x+t.width&&y>=t.y&&y<t.y+t.height).length,1);
  }
 }
 assert.equal(planTiles({...frame,scale:0}).tiles.length,0);
});

function harness(){
 const jobs=[],cache=new Set(),delivered=[],errors=[];let active=0,maximum=0;
 const q=new DetailQueue({cached:key=>cache.has(key),ready:async(t,r)=>{cache.add(t.key);delivered.push(t.key);},error:e=>errors.push(e),
  load:(tile,signal)=>new Promise((resolve,reject)=>{
   active++;maximum=Math.max(maximum,active);
   const finish=fn=>value=>{active--;fn(value);};
   const job={key:tile.key,resolve:finish(resolve),reject:finish(reject),signal};jobs.push(job);
   signal.addEventListener('abort',()=>job.reject(new Error('aborted')),{once:true});
   if(signal.aborted)job.reject(new Error('aborted'));
  })});
 return {q,jobs,cache,delivered,errors,maximum:()=>maximum};
}
const tiles=(...keys)=>keys.map(key=>({key}));
test('moving the viewport reuses overlapping in-flight tiles and limits concurrency',async()=>{
 const h=harness();h.q.update(tiles('a','b','c'));await tick();assert.deepEqual(h.jobs.map(j=>j.key),['a','b']);
 h.q.update(tiles('b','c','d'));await tick();
 assert.equal(h.jobs[0].signal.aborted,true);assert.equal(h.jobs[1].signal.aborted,false);
 assert.equal(h.jobs.filter(j=>j.key==='b').length,1);
 h.jobs.find(j=>j.key==='b').resolve('b');await tick();
 h.jobs.find(j=>j.key==='c').resolve('c');await tick();
 h.jobs.find(j=>j.key==='d').resolve('d');await tick();
 assert.deepEqual(h.delivered,['b','c','d']);assert.equal(h.maximum(),2);assert.equal(h.errors.length,0);
});
test('changing photos discards stale work, and cached regions are reused',async()=>{
 const h=harness();h.q.update(tiles('old'));await tick();h.q.pause();h.q.update(tiles('new'));await tick();
 h.jobs.find(j=>j.key==='new').resolve('new');await tick();
 assert.deepEqual(h.delivered,['new']);h.q.update(tiles('new'));await tick();assert.equal(h.jobs.length,2);
});
test('errors retain the available image and retry only on a new view request',async()=>{
 const h=harness();h.cache.add('cached');h.q.update(tiles('cached','bad'));await tick();
 h.jobs[0].reject(new Error('decoder unavailable'));await tick();await tick();
 assert.equal(h.jobs.length,1);assert.equal(h.errors.length,1);assert.ok(h.cache.has('cached'));
 h.q.update(tiles('cached','bad'));await tick();assert.equal(h.jobs.length,2);
 h.jobs[1].resolve('good');await tick();assert.deepEqual(h.delivered,['bad']);
});
