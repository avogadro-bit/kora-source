const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../kora/static/app.js'),'utf8');
function setup(){
 const menu={children:[],value:'',replaceChildren(){this.children=[];this.value='';},append(o){this.children.push(o);}};
 const context={$:()=>menu,element:(tag,text)=>({tag,text,disabled:false})};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('const films ='),source.indexOf('const wb ='))+source.slice(source.indexOf('const referenceFilms='),source.indexOf('function setupControls(')),context);
 return {menu,update:context.syncFilmChoices};
}
test('official and reference-based films are selectable without a Fuji source',()=>{
 const {menu,update}=setup();update('classic_negative');
 assert.equal(menu.children.length,12);
 assert.equal(menu.value,'classic_negative');
 for(const film of ['classic_negative','pro_neg_hi','nostalgic_negative']){
  const option=menu.children.find(o=>o.value===film);
  assert.ok(option);assert.equal(option.disabled,false);assert.doesNotMatch(option.text,/approximation|LUT/);
 }
 for(const retired of ['monochrome','sepia'])assert.ok(!menu.children.some(o=>o.value===retired));
});
test('legacy recipes remain identifiable but cannot be selected again',()=>{
 const {menu,update}=setup();
 for(const retired of ['monochrome','sepia']){
  update(retired);assert.equal(menu.children.length,13);assert.equal(menu.value,retired);
  const legacy=menu.children.find(o=>o.value===retired);assert.equal(legacy.disabled,true);assert.match(legacy.text,/legacy recipe/);
 }
 update('provia');assert.equal(menu.children.length,12);assert.equal(menu.value,'provia');
});
