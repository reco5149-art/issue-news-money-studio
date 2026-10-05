const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup({dirty=false, stale=false, failEvaluation=false}={}) {
  const elements = {};
  const $ = id => elements[id] ||= {value:'',checked:false,disabled:false,textContent:'',dataset:{},addEventListener(){},close(){}};
  ['facts-check','rights-check'].forEach(id=>$(id).checked=true);
  $('schedule-at').value='2099-01-01T15:00';
  const post = {id:'test',status:'draft',slides:[{title:'test',body:'body'}],quality:{status:'passed'},facts_checked:true,rights_checked:true};
  const calls=[];
  const context = vm.createContext({$,state:{current:post},editorDirty:dirty,esc:String,showPreview(){},refresh:async()=>{},toast(){},view(){},document:{querySelectorAll:selector=>selector.includes("photo-")?[]:Object.values(elements)},Date,Error,
    api:async(path,options)=>{
      calls.push(options.method+' '+path);
      if(options.method==='PUT') return {...post,...JSON.parse(options.body),quality:{status:stale?'stale':'passed'}};
      if(path.endsWith('/evaluate')) {if(failEvaluation) throw Error('평가 서버 오류');return {...post,quality:{status:'passed'}};}
      return {...post,status:'scheduled'};
    }});
  const src=fs.readFileSync('static/app.js','utf8');
  vm.runInContext(src.slice(src.indexOf('async function saveEditor()'),src.indexOf('$("discover-btn").onclick')),context);
  return {$,context,calls};
}
test('check changes save before scheduling without redundant evaluation',async()=>{
  const h=setup({dirty:true}); await h.$('schedule-post').onclick();
  assert.deepEqual(h.calls,['PUT /api/posts/test','POST /api/posts/test/schedule']);
  assert.equal(h.context.state.current.status,'scheduled');
});
test('changed content cannot schedule using old passing score',async()=>{
  const h=setup({dirty:true,stale:true});await h.$('schedule-post').onclick();
  assert.deepEqual(h.calls,['PUT /api/posts/test']);
  assert.match(h.$('editor-notice').textContent,/다시 평가/);
});
test('evaluate saves dirty form first',async()=>{
  const h=setup({dirty:true});await h.$('evaluate-post').onclick();
  assert.deepEqual(h.calls,['PUT /api/posts/test','POST /api/posts/test/evaluate']);
});
test('evaluation error remains visible and retry enabled',async()=>{
  const h=setup({failEvaluation:true});await h.$('evaluate-post').onclick();
  assert.equal(h.context.state.current.quality.status,'error');
  assert.match(h.$('editor-notice').textContent,/평가 서버 오류/);
  assert.equal(h.$('evaluate-post').disabled,false);
});
test('blocked score explains failed card without scheduling',async()=>{
  const h=setup();h.context.state.current.quality={status:'blocked',cards:[{card:2,hook:20,sync:15,grounding:20,cta:5,critical:false}]};
  await h.$('schedule-post').onclick();assert.deepEqual(h.calls,[]);
  assert.match(h.$('editor-notice').textContent,/2번 카드/);
});
