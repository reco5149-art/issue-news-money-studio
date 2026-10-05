const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(fail=false) {
  const elements={};
  const $=id=>elements[id] ||= {value:'',textContent:'',oninput(){}};
  $('source-link').value='https://youtu.be/abcdefghijk';
  $('source-text').value='이전 영상 원고입니다. 새 영상 분석과 섞이면 안 됩니다.';
  $('image-mode').value='ai';
  const calls=[];
  const ctx=vm.createContext({$,state:{ratio:'4:5'},toast(){},showPreview(){},refresh:async()=>{},
    busy:async(_,fn)=>fn(),api:async(path)=>{
      calls.push(path);
      if(path==='/api/import') {
        if(fail) throw Error('영상 접근 제한');
        return {text:'새 영상에서 확인한 자막입니다.',source_url:$('source-link').value,source_name:'출처'};
      }
      return {};
    }});
  const src=fs.readFileSync('static/app.js','utf8');
  vm.runInContext(src.slice(src.indexOf('let importedLink'),src.indexOf('function showPreview()')),ctx);
  vm.runInContext(src.slice(src.indexOf('$("generate-btn").onclick'),src.indexOf('function setAsset(')),ctx);
  return {$,calls,ctx};
}
test('generate imports link before generation and reuses successful transcript',async()=>{
  const h=setup();await h.$('generate-btn').onclick();await h.$('generate-btn').onclick();
  assert.deepEqual(h.calls,['/api/import','/api/generate','/api/generate']);
  assert.match(h.$('source-text').value,/새 영상/);
});
test('failed import never generates with stale manuscript',async()=>{
  const h=setup(true);await assert.rejects(h.$('generate-btn').onclick(),/접근 제한/);
  assert.deepEqual(h.calls,['/api/import']);assert.equal(h.$('source-review').open,true);
});
test('changing a link requires importing again',async()=>{
  const h=setup();await h.$('generate-btn').onclick();
  h.$('source-link').value='https://www.instagram.com/reel/abc/';
  await h.$('generate-btn').onclick();
  assert.deepEqual(h.calls,['/api/import','/api/generate','/api/import','/api/generate']);
});
test('explicit manual transcript bypasses failed platform access',async()=>{
  const h=setup(true);h.$('source-text').value='사용자가 직접 확인한 영상 자막을 붙여넣었습니다.';
  h.$('manual-transcript-btn').onclick();await h.$('generate-btn').onclick();
  assert.deepEqual(h.calls,['/api/generate']);
  assert.match(h.$('source-name').value,/직접 확인/);
});
