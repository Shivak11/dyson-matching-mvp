'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const main = {innerHTML:'',scrollTop:0,setAttribute(){}};
const controls = new Map([['#main',main],['#platformTour',{addEventListener(){}}],['#announcer',{}]]);
const listeners = {};
let payload;
let fail = false;
const context = {
  document:{querySelector:key => controls.get(key) || null,querySelectorAll:() => [],addEventListener:(type,fn) => { listeners[type] = fn; }},
  window:{addEventListener(){},scrollTo(){}},localStorage:{setItem(){}},CSS:{escape:x => x},
  URL:class extends URL { static createObjectURL() { return "blob:test"; } static revokeObjectURL() {} },Intl,console,AbortController,crypto:{randomUUID:() => 'request-1'},setTimeout:() => 1,clearTimeout(){},
  FileReader:class { readAsDataURL() { this.result = 'data:image/jpeg;base64,AAAA'; this.onload(); } },
  ResizeObserver:class {observe(){} disconnect(){}},
  fetch:async (path,options = {}) => {
    if (path === '/api/bootstrap') return {ok:true,text:async () => JSON.stringify({jobs:context.ui.state.jobs,catalogue:[],csrf_token:'test',settings:{service_ready:true}})};
    payload = JSON.parse(options.body);
    return {ok:!fail,status:fail ? 503 : 200,text:async () => JSON.stringify(fail ? {error:'Try again later.'} : {jobs:[child]})};
  }
};
vm.createContext(context);
vm.runInContext(source.replace(/  refresh\(\);\n\}\)\(\);\s*$/, '  globalThis.ui = {state,jobViews,canAddView,viewChain,viewSteps,viewControls,renderResult,renderJob,jobDescription,setupBoxes,addProductView,runProductViews,clearPendingView};\n})();'),context);
const ui = context.ui;
ui.state.settings = {service_ready:true};
const root = {id:'one',mode:'identify',status:'completed',filename:'first.jpg',image_url:'/media/first',matches:[{status:'not_sure',confidence:'Low',evidence:['Trigger is hidden.'],box_2d:[100,100,900,900]}]};
const views = [1,2,3].map(n => ({view_id:`view_${n}`,filename:`${n}.jpg`,image_url:`/media/photo${n}`}));
const child = {...root,id:'two',parent_job_id:'one',root_job_id:'one',view_count:2,views:views.slice(0,2),matches:[{status:'match',product_name:'Dyson V15',confidence:'High',view_boxes:{view_1:[10,20,400,600]},view_evidence:[{view_id:'view_2',feature:'trigger',detail:'Trigger is visible.'}]}]};
const third = {...child,id:'three',parent_job_id:'two',view_count:3,views,matches:[{status:'not_sure',confidence:'Low'}]};
const branch = {...child,id:'other-two'};
ui.state.jobs = [third,branch,child,root];
ui.state.selectedJob = child.id;
assert.equal(ui.jobViews(root).length,1);
assert.equal(ui.canAddView(root),true);
for (const blocked of [{...root,mode:'verify'},{...root,status:'running'},{...root,matches:[]},{...root,matches:[{},{}]},third]) assert.equal(ui.canAddView(blocked),false);
assert.match(ui.jobDescription(child),/2 views together/);
ui.state.lineageLeaf = third.id;
assert.deepEqual(Array.from(ui.viewChain(root),j => j.id),['one','two','three']);
assert.doesNotMatch(ui.viewSteps(root),/other-two/);
ui.state.lineageLeaf = branch.id;
assert.deepEqual(Array.from(ui.viewChain(branch),j => j.id),['one','other-two']);
ui.state.jobs = [child,root]; ui.state.lineageLeaf = child.id;
assert.match(ui.viewSteps(child),/3 views<\/strong><span>Not added/);
ui.renderResult(child);
assert.match(main.innerHTML,/View 2 · Trigger is visible/);
assert.match(main.innerHTML,/data-store-view="view_2"/);
ui.state.selectedView = 'view_2'; ui.renderResult(child);
assert.match(main.innerHTML,/src="\/media\/photo2"/);
ui.state.jobs = [third,child,root]; ui.state.selectedJob = third.id; ui.renderResult(third);
assert.match(main.innerHTML,/Low confidence/);
assert.doesNotMatch(main.innerHTML,/id="addViewButton"/);
assert.equal(ui.viewControls({...root,mode:'verify'}),'');
// A later photo cannot inherit the first photo's bounding box.
const boxButton = {dataset:{object:'0'},style:{},hidden:false};
controls.set('#storePhoto',{naturalWidth:1000,naturalHeight:1000,addEventListener(){}});
controls.set('#resultPhoto',{clientWidth:1000,clientHeight:1000,querySelectorAll:() => [boxButton]});
ui.state.selectedJob = child.id; ui.state.selectedView = 'view_2'; ui.setupBoxes(child.matches);
assert.equal(boxButton.hidden,true);
ui.state.selectedView = 'view_1'; ui.setupBoxes(child.matches);
assert.equal(boxButton.hidden,false); assert.equal(boxButton.style.left,'20px');
controls.delete('#storePhoto'); controls.delete('#resultPhoto');
(async () => {
  ui.state.selectedJob = root.id;
  ui.addProductView([{name:'second.jpg',type:'image/jpeg',size:12}]);
  const pending = ui.state.pendingView;
  assert.equal(pending.confirmed,false);
  assert.match(ui.viewControls(root),/id="runViewButton" disabled/);
  pending.confirmed = true; fail = true;
  await ui.runProductViews();
  assert.equal(ui.state.pendingView,pending);
  assert.equal(pending.requestId,'request-1');
  assert.equal(pending.error,'Try again later.');
  assert.equal(payload.parent_job_id,'one'); assert.equal(payload.same_product,true);
  assert.equal(payload.expected_product_id,null); assert.equal(payload.images.length,1);
  assert.equal(payload.images[0].filename,'second.jpg');
  fail = false;
  await ui.runProductViews();
  assert.equal(payload.request_id,'request-1');
  assert.equal(ui.state.pendingView,null); assert.equal(ui.state.selectedJob,'two');
  assert.equal(root.matches[0].status,'not_sure');
  ui.state.selectedJob = child.id;
  ui.addProductView([{name:'third.jpg',type:'image/jpeg',size:12}]);
  assert.equal(ui.state.pendingView.confirmed,false);
  assert.match(ui.viewControls(child),/Identify using 3 views/);
  ui.clearPendingView();
  console.log('Multiple-view UI assertions passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
