/* DOM integration tests for the generated standalone page; not a visual browser test. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const html = fs.readFileSync('dist/index.html', 'utf8');
let checks = 0;
function check(name, fn) { fn(); checks++; console.log(`PASS ${name}`); }
function boot({brokenStorage=false, saved=null}={}) {
  const errors=[], downloads=[];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', e => { errors.push(e); console.error(e.message, e.detail?.stack || ""); });
  const dom = new JSDOM(html, {url:'https://hatua-test.invalid/', runScripts:'dangerously', virtualConsole,
    beforeParse(w) {
      w.matchMedia = () => ({matches:false}); w.confirm=()=>true;
      w.HTMLElement.prototype.scrollIntoView=function(){};
      w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
      w.HTMLDialogElement.prototype.close=function(){this.open=false;};
      w.URL.createObjectURL=blob=>{downloads.push({blob});return 'blob:test';};
      w.URL.revokeObjectURL=()=>{};
      w.HTMLAnchorElement.prototype.click=function(){downloads.at(-1).filename=this.download;};
      if (brokenStorage) Object.defineProperty(w,'localStorage',{get(){throw new Error('blocked');}});
      if(saved) for(const [key,value] of Object.entries(saved)) w.localStorage.setItem(key,value);
    }});
  return {dom,w:dom.window,$:id=>dom.window.document.getElementById(id),errors,downloads};
}
const main=boot(); const {w,$,errors,downloads}=main;
const input=(id,value)=>{$(id).value=value;$(id).dispatchEvent(new w.Event('input',{bubbles:true}));};
check('demo starts on teacher walkthrough without script errors',()=>{
  assert.equal(errors.length,0); assert.equal($('tab-test').hidden,false); assert.match($('data-badge').textContent,/fictional/);
});
check('no external assets or application network connections',()=>{
  assert.equal(w.document.querySelectorAll('script[src],link[href],img[src^="http"],iframe').length,0);
  assert.match(w.document.querySelector('meta[http-equiv="Content-Security-Policy"]').content,/connect-src 'none'/);
});
$('begin-test').click();
check('scenario opens Cynthia; family stays locked before approval',()=>{
  assert.match($('learner').textContent,/Cynthia/);assert.equal($('g-share'),null);assert.equal($('teacher-name').value,'Test Teacher');
});
check('source record dialog opens and closes',()=>{
  $('learner').querySelector('[data-ev]').click();assert.equal($('ev').open,true);assert.match($('ev-body').textContent,/Assessment record/);$('ev-close').click();assert.equal($('ev').open,false);
});
const original=$('draft-text').value;
check('blank and unsafe drafts cannot be approved',()=>{
  input('draft-text',' ');assert.equal($('approve').disabled,true);
  input('draft-text',original+'\n- A gifted learner.');assert.equal($('approve').disabled,true);
  input('draft-text',original);assert.equal($('approve').disabled,false);
});
$('approve').click();
check('approval unlocks language choice, sharing requires separate action',()=>{
  assert.ok($('g-share'));assert.equal($('g-approve').disabled,true);
  $('learner').querySelector('[data-lang="sw"]').click();assert.match($('learner').textContent,/Habari/);
  $('g-share').checked=true;$('g-share').dispatchEvent(new w.Event('change'));$('g-approve').click();
  assert.ok($('g-download'));
});
check('approved family message and decisions download locally',()=>{
  $('g-download').click();assert.equal(downloads.at(-1).filename,'hatua-HT-0003-sw.txt');
  $('btn-download').click();assert.equal(downloads.at(-1).filename,'approvals.json');
  const items=JSON.parse($('save-text').value);assert.equal(items.length,2);assert.equal(items[1].share,true);assert.equal(items[0].teacher,'Test Teacher');
});
check('changing teacher decision invalidates previous family approval',()=>{
  $('undo').click();input('draft-text',original+'\nPlease discuss this at the next meeting.');$('approve').click();
  assert.equal($('g-share'),null);assert.match($('learner').textContent,/prepared family message may not reflect/);
  assert.equal(JSON.parse($('save-text').value).length,1);
});
check('rejecting a draft keeps family message locked',()=>{
  $('undo').click();$('reject').click();assert.match($('learner').textContent,/You rejected/);assert.equal($('g-share'),null);
});
check('live search and empty results are usable',()=>{
  input('q-class','Kiprono');assert.match($('list-class').textContent,/Kiprono/);assert.match($('r-class').textContent,/Showing 1 of 40/);
  input('q-class','no-such-learner');assert.match($('list-class').textContent,/Nobody matches/);$('clear-class').click();
});
check('feedback is downloaded separately and privacy remains accessible',()=>{
  $('open-test').click();$('feedback-helped').value='Evidence links were useful.';
  $('feedback-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  assert.equal(downloads.at(-1).filename,'hatua-teacher-feedback.txt');assert.match($('feedback-status').textContent,/Nothing was sent/);
  $('open-privacy').click();assert.equal($('tab-privacy').hidden,false);assert.match($('tab-privacy').textContent,/ordinary unencrypted files/);
});
const saved=Object.fromEntries(Object.keys(w.localStorage).map(k=>[k,w.localStorage.getItem(k)]));
check('decisions survive a reload of the same dataset',()=>{
  const reload=boot({saved});assert.equal(reload.errors.length,0);reload.$('begin-test').click();assert.match(reload.$('learner').textContent,/You rejected/);reload.dom.window.close();
});
check('clear-data removes stored decisions and unsent feedback only for Hatua',()=>{
  w.localStorage.setItem('unrelated-app','keep');$('clear-data').click();assert.equal(w.localStorage.getItem('unrelated-app'),'keep');
  assert.equal(Object.keys(w.localStorage).filter(k=>k.startsWith('hatua-')).length,0);
  assert.equal($('feedback-helped').value,'');assert.equal($('savebar').hidden,true);assert.match($('clear-status').textContent,/cleared/);
});
check('storage-blocked browser still supports review with a visible warning',()=>{
  const blocked=boot({brokenStorage:true});assert.equal(blocked.errors.length,0);assert.equal(blocked.$('storage-notice').hidden,false);
  blocked.$('begin-test').click();blocked.$('approve').click();assert.ok(blocked.$('g-share'));blocked.dom.window.close();
});
check('malformed stored decisions do not crash the page',()=>{
  const key=Object.keys(saved).find(k=>k.endsWith('-decisions'));
  const corrupt=boot({saved:{[key]:'null'}});assert.equal(corrupt.errors.length,0);corrupt.dom.window.close();
});
check('keyboard tab navigation moves the selected panel',()=>{
  const b=w.document.querySelector('[data-tab="privacy"]');b.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Home',bubbles:true}));
  assert.equal($('tab-test').hidden,false);
});
assert.equal(errors.length,0);
main.dom.window.close();
console.log(`${checks} UI integration checks passed.`);
