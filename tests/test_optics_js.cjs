const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../kora/static/app.js'),'utf8');
function setup(profile,current={lens_distortion:'off',lens_vignetting:'off'}){
 const note={},button={},actions=[];
 const context={selected:{id:'photo'},opticsInfo:profile,recipe:{...current},
  $:selector=>selector==='#optics-status'?note:button,
  recordUndo:()=>actions.push('undo'),
  applyPatchToSelection:patch=>{actions.push({...patch});Object.assign(context.recipe,patch);},
  populate:()=>{},persist:()=>actions.push('persist'),scheduleRender:delay=>actions.push(delay)};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function updateOpticsStatus(){')),context);
 return {context,note,button,actions};
}
test('detected correction is suggested and can be applied without changing unsupported corrections',()=>{
 const {context,button,note,actions}=setup({distortion:true,vignetting:false,label:'Lensfun · Test lens',source:'lensfun'});
 context.updateOpticsStatus();assert.equal(button.hidden,false);assert.equal(button.disabled,false);
 assert.match(note.textContent,/available · off/);assert.match(note.textContent,/Vignetting: no profile/);
 context.applyAvailableOptics();assert.deepEqual(actions,['undo',{lens_distortion:'auto'},'persist',0]);
 assert.equal(context.recipe.lens_vignetting,'off');
 context.updateOpticsStatus();assert.equal(button.disabled,true);
 context.applyAvailableOptics();assert.equal(actions.length,4);
});
test('both calibrated corrections are applied together with undo and rendering',()=>{
 const {context,actions}=setup({distortion:true,vignetting:true});context.applyAvailableOptics();
 assert.deepEqual(actions,['undo',{lens_distortion:'auto',lens_vignetting:'auto'},'persist',0]);
});
test('unknown lens and no selection never offer or apply a guessed correction',()=>{
 for(const profile of [null,{distortion:false,vignetting:false,label:'No lens profile identified',lens_name:'XCD 38V'}]){
  const {context,button,actions}=setup(profile);context.updateOpticsStatus();context.applyAvailableOptics();
  assert.equal(button.hidden,true);assert.deepEqual(actions,[]);
 }
 const {context,button,actions}=setup({distortion:true,vignetting:true});context.selected=null;
 context.updateOpticsStatus();context.applyAvailableOptics();assert.equal(button.hidden,true);assert.deepEqual(actions,[]);
});
