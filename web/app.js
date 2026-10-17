'use strict';
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => Number.isFinite(Number(value)) && value !== null ? new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:2}).format(Number(value)) : 'Not available';
  const media = value => typeof value === 'string' && /^\/media\/[A-Za-z0-9_-]+$/.test(value) ? value : '';
  const sourceURL = value => { try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const image = (url, alt, attrs = '') => media(url) ? `<img src="${esc(media(url))}" alt="${esc(alt)}" ${attrs}>` : '<span class="muted small">No image available</span>';
  const pendingImage = item => `<img src="${esc(item.url)}" alt="Selected store photograph">`;
  const terminalErrors = new Set(['failed','interrupted']);
  const state = {view:'match', catalogue:[], jobs:[], settings:{}, csrf:'', ready:false, pending:[], pendingIndex:0, selectedJob:null, selectedObject:0, productId:null, editor:null, mode:'identify', expected:'', submitting:false, queueSignature:'', allowanceSignature:'', viewSignature:'', historySignature:'', pollFailures:0, runRequestId:null, retryRequests:{}, detailsOpen:{}, selectedView:'view_1', pendingView:null, viewSubmitting:false, lineageLeaf:null};
  let resizeObserver;
  let pollTimer;
  let editorReturnFocus = null;
  let tourIndex = 0;
  let tourReturnFocus = null;
  let tourTarget = null;
  let tourFrame = 0;
  let tourProductSignature = '';
  let savedProductId = null;
  const main = $('#main');
  const announce = message => { $('#announcer').textContent = message; };
  const feedback = (id, message) => { const el = $(id); if (el) { el.textContent = message; el.classList.toggle('hidden', !message); } };
  const globalError = message => feedback('#globalError', message);

  async function api(path, options = {}) {
    const control = new AbortController();
    const timeout = setTimeout(() => control.abort(), 45000);
    try {
      const response = await fetch(path, {...options, credentials:'same-origin', cache:'no-store', signal:control.signal, headers:{...(options.body ? {'Content-Type':'application/json','X-CSRF-Token':state.csrf} : {}), ...options.headers}});
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { throw new Error(`The server returned an unreadable response (${response.status}). Try again.`); }
      if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `The request failed (${response.status}).`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The server did not respond in time. Your selection is preserved. Check History before starting another run.');
      if (error instanceof TypeError) throw new Error('The workspace could not be reached. Check your connection and refresh this page.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  const heading = (title, description = '', action = '') => `<div class="heading"><div><h1>${esc(title)}</h1>${description ? `<p>${esc(description)}</p>` : ''}</div>${action}</div>`;
  const uploadButton = (label = 'Upload photos') => `<button type="button" data-upload>${esc(label)}</button>`;
  const getProduct = id => state.catalogue.find(p => p.id === id);
  const currentJob = () => state.jobs.find(j => j.id === state.selectedJob);
  const serviceReady = () => state.settings.service_ready ?? state.settings.api_configured;
  const runUnavailable = () => !serviceReady() || Boolean(state.settings.accounting_error);
  const statusName = status => ({queued:'Queued',running:'Running',completed:'Complete',failed:'Failed',interrupted:'Interrupted'}[status] || status || 'Saved');
  const jobDescription = job => `${job.view_count > 1 ? `${job.view_count} views together · ` : ''}${job.status === 'completed' ? `${job.matches?.length || 0} machine${job.matches?.length === 1 ? '' : 's'} · Complete` : statusName(job.status)}`;
  const dateText = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value || '') : d.toLocaleString('en-IN', {dateStyle:'medium',timeStyle:'short'}); };
  function rememberJob(id, keepLineage = false) { state.selectedJob = id; state.selectedObject = 0; state.selectedView = 'view_1'; if (!keepLineage) state.lineageLeaf = id; try { localStorage.setItem('dyson-selected-job', id || ''); } catch {} }
  const jobViews = job => Array.isArray(job.views) && job.views.length ? job.views : [{view_id:'view_1',filename:job.filename,image_url:job.image_url}];
  const canAddView = job => Boolean(job) && job.status === 'completed' && job.mode === 'identify' && job.matches?.length === 1 && jobViews(job).length < 3;
  function viewChain(job) {
    const ancestors = item => {
      const chain = []; const seen = new Set();
      while (item && !seen.has(item.id)) { chain.unshift(item); seen.add(item.id); item = state.jobs.find(j => j.id === item.parent_job_id); }
      return chain;
    };
    let chain = ancestors(job);
    const remembered = state.jobs.find(j => j.id === state.lineageLeaf);
    const rememberedChain = remembered && ancestors(remembered);
    if (rememberedChain?.some(j => j.id === job.id)) chain = rememberedChain;
    const seen = new Set(chain.map(j => j.id));
    while (chain.length < 3) {
      const last = chain[chain.length-1];
      const child = state.jobs.find(j => j.parent_job_id === last.id && jobViews(j).length === jobViews(last).length+1 && !seen.has(j.id));
      if (!child) break;
      chain.push(child); seen.add(child.id);
    }
    state.lineageLeaf = chain[chain.length-1]?.id || job.id;
    return chain;
  }
  const jobSignature = job => JSON.stringify([job,state.settings.accounting_error,job.mode === 'identify' ? viewChain(job) : []]);
  function viewSteps(job) {
    if (job.mode !== 'identify' || (!canAddView(job) && jobViews(job).length === 1 && !state.jobs.some(j => j.parent_job_id === job.id))) return '';
    const chain = viewChain(job);
    return `<div class="view-steps" aria-label="Saved results by number of views">${[1,2,3].map(n => {
      const item = chain.find(j => jobViews(j).length === n);
      const match = item?.matches?.[0];
      const detail = !item ? 'Not added' : item.status === 'completed' ? `${match ? matchTitle(match) : 'No vacuum cleaner detected'} · ${match ? matchConfidence(match) : 'Complete'}` : item.status === 'running' ? 'Checking' : statusName(item.status);
      return `<button type="button" data-view-step="${esc(item?.id || '')}" class="${item?.id === job.id ? 'selected' : ''}" ${item?.id === job.id ? 'aria-current="step"' : ''} ${!item || item.status !== 'completed' ? 'disabled' : ''}><strong>${n} view${n === 1 ? '' : 's'}</strong><span>${esc(detail)}</span></button>`;
    }).join('')}</div>`;
  }
  function viewSelectors(job) {
    const views = jobViews(job);
    return views.length < 2 ? '' : `<div class="view-selectors" aria-label="Store photograph views">${views.map((v,i) => `<button type="button" data-store-view="${esc(v.view_id)}" aria-pressed="${v.view_id === state.selectedView}" class="${v.view_id === state.selectedView ? 'selected' : ''}">View ${i+1}</button>`).join('')}</div>`;
  }
  function viewControls(job) {
    const pending = state.pendingView;
    if (pending?.parentId === job.id) {
      const count = jobViews(job).length+1;
      return `<section class="view-preview" aria-labelledby="viewPreviewTitle"><h2 id="viewPreviewTitle">Review ${count} views of this product</h2><p class="small muted">All ${count} photos will be checked together.</p><div class="view-preview-images">${jobViews(job).map((v,i) => `<figure>${image(v.image_url,`Saved View ${i+1}`)}<figcaption>View ${i+1}</figcaption></figure>`).join('')}<figure>${pendingImage(pending)}<figcaption>View ${count} · ${esc(pending.filename)}</figcaption></figure></div><label class="same-product-confirm"><input type="checkbox" id="sameProductConfirm" ${pending.confirmed ? 'checked' : ''} ${state.viewSubmitting ? 'disabled' : ''}>This photo shows the same physical product as View 1.</label><div class="buttonrow"><button class="primary" type="button" id="runViewButton" ${!pending.confirmed || state.viewSubmitting || runUnavailable() ? 'disabled' : ''}>${state.viewSubmitting ? 'Saving view…' : `Identify using ${count} views`}</button><button type="button" id="cancelViewButton" ${state.viewSubmitting ? 'disabled' : ''}>Cancel</button></div><p id="viewUploadError" role="alert" class="error ${pending.error ? '' : 'hidden'}">${esc(pending.error || '')}</p></section>`;
    }
    return canAddView(job) ? '<div class="add-view-action"><button type="button" id="addViewButton">Add another view</button><p>Add a different angle of this same product.</p><p id="viewUploadError" role="alert" class="error hidden"></p></div>' : '';
  }
  function clearPendingView() { if (state.pendingView) URL.revokeObjectURL(state.pendingView.url); state.pendingView = null; }
  function addProductView(files) {
    const job = currentJob();
    if (state.viewSubmitting || !job || !canAddView(job) || !files.length) return;
    const file = files[0];
    if (files.length !== 1 || !['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 12*1024*1024) { feedback('#viewUploadError','Choose one JPEG, PNG or WebP photo up to 12 MiB.'); return; }
    clearPendingView();
    state.pendingView = {parentId:job.id,filename:file.name,file,url:URL.createObjectURL(file),confirmed:false,requestId:crypto.randomUUID(),error:''};
    renderJob(job); $('#sameProductConfirm')?.focus();
  }
  async function runProductViews() {
    const pending = state.pendingView; const job = currentJob();
    if (state.viewSubmitting || !pending?.confirmed || !job || pending.parentId !== job.id || !canAddView(job) || runUnavailable()) return;
    state.viewSubmitting = true; pending.error = ''; renderJob(job);
    const lockedButtons = Array.from(document.querySelectorAll('button')).filter(button => !button.disabled);
    lockedButtons.forEach(button => { button.disabled = true; });
    try {
      const image = await fileData(pending.file);
      const result = await api('/api/jobs',{method:'POST',body:JSON.stringify({request_id:pending.requestId,images:[image],expected_product_id:null,parent_job_id:job.id,same_product:true})});
      if (result.jobs?.length !== 1) throw new Error('The server did not return the saved run. Check History before trying again.');
      result.jobs.forEach(upsertJob); clearPendingView(); rememberJob(result.jobs[0].id); setView('match'); announce('View saved. The photos will be checked together.'); refresh(true);
    } catch (error) { pending.error = error.message; }
    finally { state.viewSubmitting = false; lockedButtons.forEach(button => { if (button.isConnected) button.disabled = false; }); if (state.view === 'match' && currentJob()) renderJob(currentJob()); }
  }
  function setView(view) {
    state.view = view;
    state.viewSignature = '';
    globalError('');
    render();
    window.scrollTo({top:0, behavior:'instant'});
    main.scrollTop = 0;
  }
  function render() {
    document.querySelectorAll('[data-nav]').forEach(button => {
      const active = button.dataset.nav === (['product','editor'].includes(state.view) ? 'catalogue' : state.view);
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
    });
    main.setAttribute('aria-busy','false');
    if (state.view === 'catalogue') renderCatalogue();
    else if (state.view === 'product') renderProduct();
    else if (state.view === 'editor') renderEditor();
    else if (state.view === 'history') renderHistory();
    else if (state.view === 'dataset') renderDataset();
    else renderMatch();
    renderQueue();
    renderAllowance();
  }
  function focusKey(root) {
    const el = document.activeElement;
    if (!root.contains(el)) return null;
    if (el.id) return `#${CSS.escape(el.id)}`;
    for (const key of ['data-job','data-pending','data-nav','data-object']) if (el.hasAttribute(key)) return `[${key}="${CSS.escape(el.getAttribute(key))}"]`;
    return null;
  }
  function restoreFocus(root,key) { if (key) (root.querySelector(key) || main).focus({preventScroll:true}); }
  function renderQueue() {
    const signature = JSON.stringify([state.pending.map(p => [p.key,p.filename]), state.pendingIndex, state.jobs.map(j => [j.id,j.status,j.matches?.length,j.image_url]),state.selectedJob,state.view]);
    if (signature === state.queueSignature) return;
    state.queueSignature = signature;
    const focus = focusKey($('#queue'));
    $('#queueSection').hidden = !state.jobs.length && !state.pending.length;
    $('#queueCount').textContent = String(state.jobs.length + state.pending.length);
    $('#queue').innerHTML = state.pending.map((p,i) => `<button type="button" class="queueitem ${state.view === 'match' && !state.selectedJob && i === state.pendingIndex ? 'selected' : ''}" data-pending="${i}">${pendingImage(p)}<span><strong>${esc(p.filename)}</strong><small>Ready to run</small></span></button>`).join('') + state.jobs.map(j => `<button type="button" class="queueitem ${state.view === 'match' && j.id === state.selectedJob ? 'selected' : ''}" data-job="${esc(j.id)}">${image(j.image_url,'')}<span><strong>${esc(j.filename)}</strong><small>${esc(jobDescription(j))}</small></span></button>`).join('') || '<p class="asideempty">Your store photos will appear here.</p>';
    restoreFocus($('#queue'),focus);
  }
  function renderAllowance() {
    const s = state.settings;
    const signature = JSON.stringify(s);
    if (signature === state.allowanceSignature) return;
    state.allowanceSignature = signature;
    $('#allowance').innerHTML = `<div class="budget"><span class="small muted">Run allowance remaining</span><strong class="small">${esc(money(s.runtime_remaining_inr))}</strong></div><p class="small muted allowance-details">${esc(money(s.runtime_spent_inr))} spent or reserved</p>${serviceReady() === false ? '<p class="error small">Photo matching is unavailable.</p>' : ''}${s.accounting_error ? `<p class="error small">${esc(s.accounting_error)}</p>` : ''}`;
  }
  function renderMatch() {
    const job = currentJob();
    if (job) { renderJob(job); return; }
    if (state.pending.length) { renderSelected(); return; }
    const products = state.catalogue.filter(p => p.in_catalog && media(p.image_url));
    main.innerHTML = heading('Identify store products','Upload a store photo and compare each vacuum cleaner with the manufacturer catalogue.') + `<section class="upload-workspace"><div class="upload-zone" id="storeUploadZone" data-drop><div class="upload-symbol" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7 9m5-5 5 5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/></svg></div><h2>Drop a store photo here</h2><p>Or choose photos from your device.</p><button class="primary" type="button" id="matchUpload" data-upload>Choose photos</button><p class="filetypes">JPEG, PNG or WebP · Up to 5 photos · 12 MiB each</p><p class="error hidden" id="uploadError" role="alert"></p></div><section class="catalogue-preview" aria-label="Manufacturer reference preview"><div class="preview-product">${products[0] ? image(products[0].image_url, products[0].name) : '<p class="muted">Add manufacturer images in Catalogue.</p>'}</div><div class="preview-caption"><h2>Manufacturer references</h2><p>${products.length} catalogue models${products[0] ? ` · ${esc(products[0].manufacturer)}` : ''}</p><button type="button" class="textbutton" data-nav="catalogue">View catalogue <span aria-hidden="true">→</span></button></div><div class="preview-thumbs">${products.slice(1,5).map(p => `<button type="button" data-product="${esc(p.id)}" aria-label="View ${esc(p.name)}">${image(p.image_url,p.name)}</button>`).join('')}</div></section></section><p class="upload-note">Review your selection before running. Each saved result includes confidence, evidence and an export.</p>`;
  }
  function renderSelected() {
    const p = state.pending[Math.min(state.pendingIndex,state.pending.length-1)];
    state.pendingIndex = state.pending.indexOf(p);
    const products = state.catalogue.filter(p => p.in_catalog);
    main.innerHTML = heading('Review selected photos',`${state.pending.length} photo${state.pending.length === 1 ? '' : 's'} selected.`,uploadButton('Add photos')) + `<section class="selectedlayout"><div class="paneltitle"><span>${esc(p.filename)}</span><button class="quiet small" type="button" data-remove="${state.pendingIndex}">Remove photo</button></div><div class="photo">${pendingImage(p)}</div><div class="selection-strip">${state.pending.map((item,i) => `<button type="button" class="${i === state.pendingIndex ? 'selected' : ''}" data-pending="${i}" aria-label="Preview ${esc(item.filename)}" aria-pressed="${i === state.pendingIndex}">${pendingImage(item)}<span>${esc(item.filename)}</span></button>`).join('')}</div><div class="runcontrols"><div class="field"><label for="mode">What should we check?</label><select id="mode" aria-describedby="modeHelp" ${state.submitting ? 'disabled' : ''}><option value="identify" ${state.mode === 'identify' ? 'selected' : ''}>Identify from the catalogue</option><option value="verify" ${state.mode === 'verify' ? 'selected' : ''}>Verify an expected model</option></select></div><div class="field ${state.mode !== 'verify' ? 'hidden' : ''}" id="expectedField"><label for="expectedModel">Expected model</label><select id="expectedModel" ${state.submitting ? 'disabled' : ''}><option value="">Choose a model</option>${products.map(p => `<option value="${esc(p.id)}" ${state.expected === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div><button id="runButton" type="button" class="primary" ${state.submitting || runUnavailable() || state.mode === 'verify' && !state.expected ? 'disabled' : ''}>${state.submitting ? 'Saving photos…' : `Run matching${state.pending.length > 1 ? ` on ${state.pending.length} photos` : ''}`}</button></div><p class="modehelp" id="modeHelp">Identify finds the catalogue model for each machine. Verify checks whether each machine matches the model you select.</p><p class="error inlinefeedback ${state.settings.accounting_error ? '' : 'hidden'}" role="alert" id="accountingError">${esc(state.settings.accounting_error || '')}</p><p class="error inlinefeedback hidden" role="alert" id="uploadError"></p></section>`;
  }
  async function addPhotos(files) {
    const errors = []; const accepted = [];
    for (const file of files) {
      if (!['image/jpeg','image/png','image/webp'].includes(file.type)) { errors.push(`${file.name}: choose JPEG, PNG or WebP.`); continue; }
      if (file.size > 12 * 1024 * 1024) { errors.push(`${file.name}: the limit is 12 MiB.`); continue; }
      if (state.pending.length + accepted.length >= 5) { errors.push('A run can contain up to 5 photos.'); break; }
      accepted.push({key:crypto.randomUUID(),filename:file.name,file,url:URL.createObjectURL(file)});
    }
    state.pending.push(...accepted);
    if (accepted.length) { state.runRequestId = null; state.pendingIndex = state.pending.length-accepted.length; rememberJob(null); setView('match'); announce(`${accepted.length} photo${accepted.length === 1 ? '' : 's'} selected. Review before running.`); }
    if (errors.length) { if (!$('#uploadError')) globalError(errors.join(' ')); else feedback('#uploadError', errors.join(' ')); }
  }
  const fileData = file => new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve({filename:file.name,data_url:reader.result}); reader.onerror = () => reject(new Error(`${file.name} could not be read. Choose the file again.`)); reader.readAsDataURL(file); });
  async function runMatching() {
    if (state.submitting || !state.pending.length || runUnavailable()) return;
    if (state.mode === 'verify' && !getProduct(state.expected)?.in_catalog) { feedback('#uploadError','Choose the expected model before running.'); $('#expectedModel')?.focus(); return; }
    state.submitting = true; renderSelected();
    try {
      const images = await Promise.all(state.pending.map(p => fileData(p.file)));
      state.runRequestId ||= crypto.randomUUID();
      const result = await api('/api/jobs',{method:'POST',body:JSON.stringify({request_id:state.runRequestId,images,expected_product_id:state.mode === 'verify' ? state.expected : null})});
      if (!Array.isArray(result.jobs) || !result.jobs.length) throw new Error('The server did not return saved jobs. Check History before starting another run.');
      result.jobs.forEach(upsertJob);
      state.pending.forEach(p => URL.revokeObjectURL(p.url)); state.pending = []; state.runRequestId = null;
      rememberJob(result.jobs[0].id); setView('match'); announce('Photos saved. Matching is queued.'); refresh(true);
    } catch (error) { feedback('#uploadError',error.message); globalError(error.message); }
    finally { state.submitting = false; if ($('#runButton')) { $('#runButton').disabled = runUnavailable() || state.mode === 'verify' && !state.expected; $('#runButton').textContent = `Run matching${state.pending.length > 1 ? ` on ${state.pending.length} photos` : ''}`; $('#mode').disabled = false; $('#expectedModel').disabled = false; } }
  }
  function upsertJob(job) { const i = state.jobs.findIndex(j => j.id === job.id); if (i < 0) state.jobs.unshift(job); else state.jobs[i] = job; }
  function exportActions(job) {
    if (!job.exports_available) return `<div><p class="unavailable">${job.status === 'queued' || job.status === 'running' ? 'Downloads become available after the prediction is saved.' : 'No saved prediction is available for this run.'}</p>${job.export_error ? `<p class="error small export-recovery" role="alert">${esc(job.export_error)}</p>` : ''}</div>`;
    return `<div class="exportarea"><div class="exports">${['json','csv'].map(format => `<a class="button" href="/api/jobs/${encodeURIComponent(job.id)}/export.${format}" download data-export="${esc(job.id)}" data-format="${format}">Download ${format.toUpperCase()}</a>`).join('')}</div><p class="error small hidden" role="alert" data-export-error></p></div>`;
  }
  async function downloadPrediction(link) {
    if (link.getAttribute('aria-disabled') === 'true') return;
    const message = $('[data-export-error]',link.closest('.exportarea'));
    message.textContent = ''; message.classList.add('hidden'); link.setAttribute('aria-disabled','true');
    const control = new AbortController(); const timeout = setTimeout(() => control.abort(),45000);
    let url;
    try {
      const response = await fetch(link.href,{credentials:'same-origin',cache:'no-store',signal:control.signal});
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.error === 'string' ? data.error : 'The download failed. Refresh the run and try again.');
      }
      url = URL.createObjectURL(await response.blob());
      const attachment = document.createElement('a'); attachment.href = url; attachment.download = `prediction-${link.dataset.export}.${link.dataset.format}`;
      document.body.append(attachment); attachment.click(); attachment.remove();
      announce(`${link.dataset.format.toUpperCase()} prediction downloaded.`);
    } catch (error) {
      message.textContent = error.name === 'AbortError' ? 'The download timed out. Try the download again.' : error instanceof TypeError ? 'The workspace could not be reached. Reconnect and try the download again.' : error.message;
      message.classList.remove('hidden');
    } finally { clearTimeout(timeout); link.removeAttribute('aria-disabled'); if (url) setTimeout(() => URL.revokeObjectURL(url),1000); }
  }
  const duration = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(value)} seconds` : 'Not recorded';
  const recordedCost = (value,currency) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? new Intl.NumberFormat('en-IN',{style:'currency',currency,minimumFractionDigits:2,maximumFractionDigits:6}).format(value) : 'Not recorded';
  function runDetails(job) {
    const previous = $('#runDetails');
    if (previous?.dataset.job === job.id) state.detailsOpen[job.id] = previous.open;
    const d = job.run_details;
    const header = `<details class="rundetails" id="runDetails" data-job="${esc(job.id)}" ${state.detailsOpen[job.id] ? 'open' : ''}><summary id="runDetailsSummary">Run details</summary>`;
    if (!d) return header + '<p class="legacydetails">Run details were not recorded for this run.</p></details>';
    const costLabel = ['queued','running'].includes(job.status) ? 'Spent or reserved (INR)' : 'Cost recorded (INR)';
    const fields = [['Elapsed time',d.elapsed_seconds == null ? null : duration(d.elapsed_seconds)],['Queue time',d.queued_seconds == null ? null : duration(d.queued_seconds)],['Started',d.started_at ? dateText(d.started_at) : null],['Completed',d.completed_at ? dateText(d.completed_at) : null],[costLabel,d.cost_inr == null ? null : recordedCost(d.cost_inr,'INR')]].filter(([,value]) => value !== null);
    return header + (fields.length ? `<dl>${fields.map(([name,value]) => `<dt>${esc(name)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>` : '<p class="legacydetails">Time and cost have not been recorded yet.</p>') + '</details>';
  }
  function renderJob(job) {
    state.viewSignature = jobSignature(job);
    const views = jobViews(job);
    if (job.status === 'completed') { renderResult(job); return; }
    const failed = terminalErrors.has(job.status);
    const outcome = views.length > 1 && !failed ? `Checking ${views.length} views together…` : job.status === 'failed' ? 'Matching failed' : job.status === 'interrupted' ? 'Matching interrupted' : job.status === 'queued' ? 'Photo queued for identification' : 'Identifying products';
    const blockedReason = state.settings.accounting_error || (!serviceReady() ? 'Photo matching is unavailable. Check the run allowance before retrying.' : '');
    main.innerHTML = heading(outcome,job.filename,uploadButton('Upload more')) + viewSteps(job) + `<section class="statusarea"><div class="statusphoto">${image(job.image_url,'Uploaded store photograph')}</div><div class="statustext"><p class="small muted">${esc(statusName(job.status))}</p><h2 id="jobStage">${esc(job.stage || statusName(job.status))}</h2>${failed ? `<div class="errornote"><p>${esc(job.error || 'The server stopped before the result was saved.')}</p></div><p>Your photograph and any charges are preserved.</p><div class="buttonrow"><button class="primary" type="button" id="retryButton" data-retry="${esc(job.id)}" ${runUnavailable() ? 'disabled' : ''}>Retry as a new run</button><button type="button" data-nav="history">View history</button></div><p id="retryError" class="error ${blockedReason ? '' : 'hidden'}" role="alert">${esc(blockedReason)}</p>` : `<div class="working"><span class="spinner" aria-hidden="true"></span><p>${views.length > 1 ? `Checking ${views.length} views together. Your earlier results remain saved.` : 'Processing this photograph.'} This page updates automatically.</p></div><button type="button" data-nav="history">View history</button>`}${exportActions(job)}</div></section>${runDetails(job)}`;
  }
  const matchTitle = match => match.status === 'not_in_catalog' ? 'Outside catalogue' : match.status === 'not_sure' ? 'Model not established' : match.product_name || 'Model not established';
  const matchConfidence = match => ['High','Medium','Low'].includes(match.confidence) ? `${match.confidence} confidence` : 'Confidence not recorded';
  const textItem = item => typeof item === 'string' ? item : item?.detail || item?.observation || item?.text || JSON.stringify(item);
  const evidenceList = (items, fallback) => Array.isArray(items) && items.length ? `<ul>${items.map(item => `<li>${esc(textItem(item))}</li>`).join('')}</ul>` : `<p class="muted small">${esc(fallback)}</p>`;
  function renderResult(job) {
    const views = jobViews(job);
    if (!views.some(v => v.view_id === state.selectedView)) state.selectedView = views[0].view_id;
    const selectedView = views.find(v => v.view_id === state.selectedView);
    const matches = Array.isArray(job.matches) ? job.matches : [];
    state.selectedObject = Math.min(state.selectedObject, Math.max(0,matches.length-1));
    const match = matches[state.selectedObject];
    if (!match) {
      main.innerHTML = heading('No vacuum cleaner detected',job.filename,uploadButton('Upload more')) + viewSteps(job) + `<div class="savedactions"><p>Complete · ${job.mode === 'verify' ? 'Verify' : 'Identify'}</p>${exportActions(job)}</div><section class="photopanel" aria-label="Checked store photograph"><div class="paneltitle"><span>Store photograph</span><span>Original image</span></div><div class="photo" id="resultPhoto">${image(selectedView.image_url,'Uploaded store photograph','id="storePhoto"')}</div>${viewSelectors(job)}<p class="modehelp">Upload a photo showing a vacuum cleaner to identify its model.</p></section>${runDetails(job)}`;
      setupBoxes([]);
      return;
    }
    const alternatives = Array.isArray(match?.alternatives) ? match.alternatives.filter(a => (typeof a === 'string' ? a : a.id) !== match.product_id) : [];
    const product = match?.status === 'match' ? getProduct(match.product_id) : null;
    const reference = match?.status === 'match' ? media(match.reference_image_url) : '';
    const references = match?.status === 'match' && Array.isArray(match.reference_images) ? match.reference_images : [];
    const referenceSource = sourceURL(match?.source_url);
    const options = matches.map((m,i) => `<option value="${i}" ${i === state.selectedObject ? 'selected' : ''}>${i+1} · ${esc(matchTitle(m))}</option>`).join('');
    const verification = job.mode === 'verify' ? ({confirmed:'Matches expected model',rejected:'Does not match expected model',unresolved:'Cannot verify'}[match?.verification] || 'Cannot verify') : '';
    const title = match?.status === 'not_in_catalog' && match.product_name ? match.product_name : match ? matchTitle(match) : 'No product identified';
    const confidence = match ? `<span class="confidence ${match.status !== 'match' ? 'neutral' : match.confidence === 'High' ? '' : 'medium'}">${esc(matchConfidence(match))}</span>` : '';
    const context = `${views.length > 1 ? `${views.length} views together` : job.filename} · ${matches.length} machine${matches.length === 1 ? '' : 's'}${match?.status === 'not_in_catalog' ? ' · Outside catalogue' : ''}`;
    const recovery = match?.status === 'not_sure' ? '<p class="result-recovery">Review the missing details below or upload another photo.</p>' : '';
    main.innerHTML = `<div class="heading result-heading"><div><div class="result-decision"><h1>${esc(title)}</h1>${confidence}</div><p class="result-context">${esc(context)}</p>${recovery}</div>${uploadButton('Upload more')}</div>${viewSteps(job)}<div class="savedactions"><p>Complete · ${job.mode === 'verify' ? 'Verify' : 'Identify'}</p>${exportActions(job)}</div>${viewControls(job)}<section aria-label="Matching result"><div class="toolbar">${matches.length ? `<label for="objectSelect">Machine</label><select id="objectSelect">${options}</select>` : '<span>No machine result was returned.</span>'}</div><div class="resultbody"><div class="compare"><section class="photopanel"><div class="paneltitle"><span>Store photograph</span><span>${views.length > 1 ? `View ${views.indexOf(selectedView)+1}` : 'Original image'}</span></div><div class="photo" id="resultPhoto">${image(selectedView.image_url,'Store photograph containing the detected machines','id="storePhoto"')}${matches.map((m,i) => `<button type="button" class="box ${i === state.selectedObject ? 'selected' : ''}" data-object="${i}" aria-label="Select machine ${i+1}" aria-pressed="${i === state.selectedObject}" hidden><span>${i+1}</span></button>`).join('')}</div>${viewSelectors(job)}<div class="photofeet"><div class="objecttabs">${matches.map((m,i) => `<button type="button" class="${i === state.selectedObject ? 'selected' : ''}" data-object="${i}" aria-pressed="${i === state.selectedObject}">Machine ${i+1}</button>`).join('')}</div></div></section><section class="reference">${reference ? `<div class="paneltitle"><span>Manufacturer reference</span>${product ? `<button type="button" class="quiet small" data-product="${esc(product.id)}">Current catalogue product ↗</button>` : ''}</div><div class="refimage">${image(reference,`Manufacturer image of ${matchTitle(match)}`,'id="referencePhoto"')}</div>` : '<div class="no-reference"><p class="muted">No manufacturer match established.</p></div>'}<div class="refcaption"><h2>${esc(match ? matchTitle(match) : 'No result')}</h2>${match?.status === 'not_in_catalog' && match.product_name ? `<p class="outside-model">Model: ${esc(match.product_name)}</p>` : ''}${verification ? `<p class="verification">${esc(verification)}</p><p class="small muted">Expected: ${esc(job.expected_product_name || getProduct(job.expected_product_id)?.name || 'Selected model')}</p>` : ''}${reference && references.length ? `<div class="thumbs">${references.map((im,i) => `<button type="button" data-reference="${esc(media(im.url))}" aria-label="Show manufacturer reference ${i+1}">${image(im.url,'')}</button>`).join('')}</div>${referenceSource ? `<p class="source"><a href="${esc(referenceSource)}" target="_blank" rel="noreferrer">Manufacturer source ↗</a></p>` : ''}` : ''}</div></section></div><div class="evidence"><div><h3>Details supporting this result</h3>${evidenceList(Array.isArray(match?.view_evidence) && match.view_evidence.length ? match.view_evidence.map(e => `${e.view_id?.replace('view_','View ')} · ${e.detail || ''}`) : match?.evidence,'No supporting details were recorded.')}</div><div class="missing"><h3>Details that remain unverified</h3>${evidenceList(match?.missing_evidence,'No missing details were recorded.')}${alternatives.length ? `<h3 class="alternatives-title">Other possible models</h3><p class="small">${alternatives.map(a => esc(typeof a === 'string' ? a : a.name)).join(', ')}</p>` : ''}</div></div>${Array.isArray(match?.retake_guidance) && match.retake_guidance.length ? `<section class="retake"><h3>Retake guidance for machine ${state.selectedObject+1}</h3>${evidenceList(match.retake_guidance,'')}</section>` : ''}</div></section>${runDetails(job)}`;
    setupBoxes(matches);
  }
  function setupBoxes(matches) {
    resizeObserver?.disconnect();
    const img = $('#storePhoto'); const holder = $('#resultPhoto');
    if (!img || !holder) return;
    const position = () => {
      if (!img.naturalWidth || !img.naturalHeight) return;
      const scale = Math.min(holder.clientWidth/img.naturalWidth,holder.clientHeight/img.naturalHeight);
      const width = img.naturalWidth*scale; const height = img.naturalHeight*scale;
      const left = (holder.clientWidth-width)/2; const top = (holder.clientHeight-height)/2;
      holder.querySelectorAll('[data-object]').forEach(button => {
        const match = matches[Number(button.dataset.object)];
        const job = currentJob();
        const box = job && jobViews(job).length > 1 ? match?.view_boxes?.[state.selectedView] : match?.box_2d;
        if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite) || box.some(v => v < 0 || v > 1000) || box[0] >= box[2] || box[1] >= box[3]) { button.hidden = true; return; }
        Object.assign(button.style,{left:`${left+box[1]*width/1000}px`,top:`${top+box[0]*height/1000}px`,width:`${(box[3]-box[1])*width/1000}px`,height:`${(box[2]-box[0])*height/1000}px`}); button.hidden = false;
      });
    };
    img.addEventListener('load',position,{once:true}); position();
    resizeObserver = new ResizeObserver(position); resizeObserver.observe(holder);
  }
  async function retry(id) {
    const button = $('#retryButton'); if (!button || button.disabled || runUnavailable()) return;
    button.disabled = true; button.dataset.pending = 'true'; button.textContent = 'Saving new run…';
    try { state.retryRequests[id] ||= crypto.randomUUID(); const result = await api(`/api/jobs/${encodeURIComponent(id)}/retry`,{method:'POST',body:JSON.stringify({request_id:state.retryRequests[id]})}); if (!result.jobs?.length) throw new Error('No new job was returned. Check History before retrying.'); result.jobs.forEach(upsertJob); delete state.retryRequests[id]; rememberJob(result.jobs[0].id); setView('match'); announce('New run saved.'); refresh(true); }
    catch (error) { delete button.dataset.pending; feedback('#retryError',error.message); button.disabled = runUnavailable(); button.textContent = 'Retry as a new run'; }
  }
  function renderCatalogue() {
    const products = state.catalogue.filter(p => p.in_catalog); const negatives = state.catalogue.filter(p => !p.in_catalog);
    main.innerHTML = heading('Manufacturer catalogue',`${products.length} models with reference images and manufacturer details.`,'<button class="primary" type="button" id="addProduct">Add product</button>') + `<section id="catalogueProducts" aria-label="Catalogue models">${productTable(products)}</section>` + (negatives.length ? `<details class="negative-refs"><summary>Outside-catalogue references (${negatives.length})</summary><p class="muted">These references help distinguish similar products.</p>${productTable(negatives)}</details>` : '');
  }
  function productTable(products) {
    return `<div class="product-grid">${products.map(p => `<article class="product-card"><button type="button" class="product-card-image" data-product="${esc(p.id)}" aria-label="Open ${esc(p.name)}">${image(p.image_url, p.name)}</button><div class="product-card-copy"><h2>${esc(p.name)}</h2><p>${p.images?.length || 0} reference image${p.images?.length === 1 ? '' : 's'} · ${media(p.brochure_url) ? 'PDF attached' : 'No PDF attached'}</p><button type="button" class="textbutton" data-product="${esc(p.id)}">View product <span aria-hidden="true">→</span></button></div></article>`).join('')}</div>`;
  }
  function renderProduct() {
    const p = getProduct(state.productId); if (!p) { setView('catalogue'); return; }
    const url = sourceURL(p.source_url); const pdf = media(p.brochure_url); const usable = Boolean(p.brochure_details?.trim());
    tourProductSignature = JSON.stringify(p);
    main.innerHTML = heading(p.name,p.manufacturer,'<button type="button" data-nav="catalogue">Back to catalogue</button>') + `${savedProductId === p.id ? '<p class="save-success" role="status">Product saved. The reference material below is up to date.</p>' : ''}<section class="catalogdetails"><div class="largeproduct" id="manufacturerImages">${image(p.image_url,`${p.name} manufacturer photograph`,'id="productPhoto"')}<div class="thumbs">${(p.images || []).map((im,i) => `<button type="button" data-product-reference="${esc(media(im.url))}" aria-label="Show manufacturer image ${i+1}">${image(im.url,'')}</button>`).join('')}</div></div><div class="productcopy"><div class="product-meta"><span>${p.in_catalog ? 'In catalogue' : 'Outside-catalogue reference'}</span><span>${p.images?.length || 0} images</span></div><section id="manufacturerDocuments" class="document-section"><h2>Manufacturer document</h2><div class="document-attachment"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 3h9l5 5v13H5zM14 3v6h5M9 13h6m-6 4h4"/></svg><div><strong>${pdf ? esc(p.brochure_filename || 'Manufacturer PDF attached') : 'No PDF attached'}</strong><p>${pdf ? 'Original manufacturer document' : 'Add a manufacturer brochure or manual.'}</p></div>${pdf ? `<a class="button" href="${esc(pdf)}" target="_blank" rel="noreferrer">Open PDF ↗</a>` : ''}</div><p class="document-state">${usable ? 'Product details saved for matching.' : 'No product details saved for matching.'} ${pdf ? 'PDF attachment alone does not extract its text.' : ''}</p></section><section class="product-details"><h2>Product details used for matching</h2><p class="preserve-lines">${esc(p.brochure_details || 'Add source-supported details to help distinguish this model.')}</p></section>${url ? `<a class="manufacturer-source" href="${esc(url)}" target="_blank" rel="noreferrer">Manufacturer source ↗</a>` : ''}<button type="button" class="edit-product" data-edit-product="${esc(p.id)}">Edit details and reference files</button></div></section>`;
  }
  function openEditor(id = null) {
    const p = id ? getProduct(id) : null;
    editorReturnFocus = document.activeElement;
    state.editor = {id:p?.id || null,name:p?.name || '',manufacturer:p?.manufacturer || 'Dyson',source_url:p?.source_url || '',brochure_details:p?.brochure_details || '',images:[],brochure:null,saving:false};
    setView('editor'); $('#productName')?.focus();
  }
  function renderEditor() {
    const d = state.editor; if (!d) { setView('catalogue'); return; }
    main.innerHTML = heading(d.id ? 'Edit manufacturer product' : 'Add manufacturer product','Store its manufacturer details and reference material in the catalogue.','<button type="button" data-cancel-editor>Cancel</button>') + `<form class="addform" id="productForm"><div class="formgrid"><div class="field"><label for="productName">Product name</label><input id="productName" name="name" required maxlength="200" value="${esc(d.name)}"></div><div class="field"><label for="manufacturer">Manufacturer</label><input id="manufacturer" name="manufacturer" required maxlength="200" value="${esc(d.manufacturer)}"></div><div class="field full"><label for="sourceURL">Manufacturer source URL</label><input id="sourceURL" name="source_url" type="url" required value="${esc(d.source_url)}" placeholder="https://www.dyson.in/…"></div><div class="field full"><label for="brochureDetails">Product details</label><textarea id="brochureDetails" name="brochure_details" rows="7">${esc(d.brochure_details)}</textarea><p class="small muted">Enter the manufacturer details used for matching, with source and page references. PDF text is not extracted automatically.</p></div><div class="field"><label for="referenceFiles">${d.id ? 'Add manufacturer images' : 'Manufacturer images'}</label><input id="referenceFiles" type="file" accept="image/jpeg,image/png,image/webp" multiple><p class="small muted">JPEG, PNG or WebP · 12 MiB each${d.id ? ' · Existing images stay saved' : ''}</p><ul class="selected-files small" id="referenceFilesList"></ul></div><div class="field"><label for="brochureFile">Manufacturer PDF (optional)</label><input id="brochureFile" type="file" accept="application/pdf"><p class="small muted">Brochure or manual · Up to 12 MiB. The PDF is stored; add its relevant text in Product details.</p><p class="small" id="brochureFileName"></p></div></div><p class="error hidden" role="alert" id="saveError"></p><div class="formactions"><button type="button" data-cancel-editor>Cancel</button><button type="submit" class="primary" id="saveProduct">Save product</button></div></form>`;
    updateEditorFiles();
  }
  function updateEditorFiles() {
    if (!state.editor) return;
    $('#referenceFilesList').innerHTML = state.editor.images.map((f,i) => `<li>${esc(f.name)} <button type="button" class="quiet small" data-remove-reference="${i}" aria-label="Remove ${esc(f.name)}">Remove</button></li>`).join('');
    $('#brochureFileName').textContent = state.editor.brochure ? `${state.editor.brochure.name} selected. Save product to attach it.` : '';
  }
  function cancelEditor() {
    if (state.editor?.saving) return;
    const id = state.editor?.id; state.editor = null;
    if (id) { state.productId = id; setView('product'); } else setView('catalogue');
    if (editorReturnFocus?.isConnected) editorReturnFocus.focus(); else main.focus();
  }
  async function saveProduct(form) {
    const d = state.editor; if (!d || d.saving) return;
    if (!form.reportValidity()) return;
    for (const key of ['name','manufacturer','source_url','brochure_details']) d[key] = form.elements.namedItem(key).value.trim();
    if (!sourceURL(d.source_url)) { feedback('#saveError','Use an http or https manufacturer source URL.'); $('#sourceURL').focus(); return; }
    if (!d.id && !d.images.length) { feedback('#saveError','Choose at least one manufacturer image.'); $('#referenceFiles').focus(); return; }
    d.saving = true; const button = $('#saveProduct'); button.disabled = true; button.textContent = 'Saving…';
    form.querySelectorAll('input,textarea,button').forEach(el => { el.disabled = true; });
    try {
      const body = {name:d.name,manufacturer:d.manufacturer,source_url:d.source_url,brochure_details:d.brochure_details,images:await Promise.all(d.images.map(fileData))};
      if (d.brochure) body.brochure = await fileData(d.brochure);
      const p = await api(d.id ? `/api/catalogue/${encodeURIComponent(d.id)}` : '/api/catalogue',{method:d.id ? 'PATCH' : 'POST',body:JSON.stringify(body)});
      if (!p.id) throw new Error('The server did not return a saved product. Your form is preserved.');
      const i = state.catalogue.findIndex(item => item.id === p.id); if (i < 0) state.catalogue.push(p); else state.catalogue[i] = p;
      state.productId = p.id; savedProductId = p.id; state.editor = null; setView('product'); announce('Manufacturer product saved.');
    } catch (error) { feedback('#saveError',error.message); form.querySelectorAll('input,textarea,button').forEach(el => { el.disabled = false; }); button.textContent = 'Save product'; }
    finally { d.saving = false; }
  }
  function renderHistory() {
    state.historySignature = JSON.stringify(state.jobs);
    main.innerHTML = heading('Saved results','Open a photo to inspect its prediction, evidence and exports.',uploadButton()) + (state.jobs.length ? `<div class="tablewrap" role="region" aria-label="Saved runs" tabindex="0"><table><thead><tr><th scope="col">Photograph</th><th scope="col">Saved</th><th scope="col">Result</th><th scope="col">Spent or reserved</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead><tbody>${state.jobs.map(j => `<tr><td class="rowname">${image(j.image_url,'')}${esc(j.filename)}</td><td>${esc(dateText(j.created_at))}</td><td>${esc(jobDescription(j))}</td><td>${esc(money(j.cost_inr))}</td><td><div class="historyactions"><button type="button" class="rowaction" data-job="${esc(j.id)}">Open run</button>${exportActions(j)}</div></td></tr>`).join('')}</tbody></table></div>` : '<section class="empty"><div><h2>No saved runs yet</h2><p>Upload store photos, review them and run matching to save your first result.</p><button type="button" class="primary" data-upload>Choose photos</button></div></section>');
  }
  function renderDataset() {
    main.innerHTML = heading('Dataset guide','Recommended structure, assumed for this demo and to be agreed with Multiplier.') + `<div class="dataset-guide"><section class="guide-section"><div class="guide-heading"><h2>Manufacturer references</h2><button type="button" data-nav="catalogue">Open catalogue →</button></div><p>Create one record per model, with manufacturer images and supported brochure details. Add or edit these records in Catalogue.</p><dl class="guide-fields"><dt>Model identity</dt><dd>Manufacturer, model name, exact model code and relevant variant limits.</dd><dt>Reference photos</dt><dd>Where available, use 3–5 useful views: full product, body, controls and model label. Keep each view attached to the correct model.</dd><dt>Approved details</dt><dd>Record distinguishing features from the manufacturer. State when an image cannot distinguish a colour, accessory bundle or regional variant.</dd><dt>Sources</dt><dd>Retain the source URL and title for each reference and brochure. The current catalogue editor stores a model-level source URL and brochure details; keep per-image source records in your dataset manifest.</dd></dl></section><section class="guide-section"><div class="guide-heading"><h2>Store photos for evaluation</h2><button type="button" data-upload>Upload store photos →</button></div><p>Build a separate set of real store photographs. Include all catalogue models, visually similar products, outside-catalogue products and difficult lighting or angles.</p><div class="tablewrap"><table><thead><tr><th scope="col">Required field</th><th scope="col">What to record</th></tr></thead><tbody><tr><td>photo_id / filename</td><td>A stable ID and the original image file.</td></tr><tr><td>expected_model_id</td><td>Independently established model, or outside_catalogue.</td></tr><tr><td>source_url / source_title</td><td>Where the photograph and its model label came from.</td></tr><tr><td>label_basis</td><td>The source statement or attached identifier supporting the expected label.</td></tr></tbody></table></div><p class="guide-callout">Keep these answer labels outside Identify mode. Upload only the store photos for inference. Establish labels from source evidence; do not guess them from appearance.</p></section><section class="guide-section"><div class="guide-heading"><h2>Read and score the results</h2><button type="button" data-nav="history">Open saved runs →</button></div><p>A saved run shows the predicted model, qualitative confidence, supporting evidence, missing details, time and cost. Download JSON or CSV from the run.</p><div class="score-explanation"><div><h3>Confidence for one prediction</h3><p>High, Medium or Low describes the evidence behind that result. It is not a measured probability of being correct.</p></div><div><h3>Accuracy across a dataset</h3><p>Compare exported predictions with the separate answer labels. Count correct, wrong, confidently wrong, unsure and failed results. This demo exports predictions; benchmark scoring is separate.</p></div></div></section></div>`;
  }
  const tourSteps = [
    {view:'catalogue', target:'.product-card', title:'Start with manufacturer references', text:'Each model has reference photos and product details. These records are the catalogue used to identify store products.'},
    {view:'product', target:'#manufacturerImages', title:'Inspect the reference images', text:'Use several useful views of the exact model. Select a thumbnail to inspect the body, controls or other distinguishing details.'},
    {view:'product', target:'#manufacturerDocuments', title:'Keep the source document attached', text:'Open the attached manufacturer PDF here. Product details saved below are used for matching; attaching a PDF does not automatically extract its text.'},
    {view:'match', target:'#matchUpload, .runcontrols', title:'Upload and review store photos', text:'Choose photos, then review them. Identify finds the catalogue model. Verify checks a model you select. Running matching makes a paid call; this tour does not start one.'},
    {view:'result', target:'.reference', title:'Compare the predicted model', text:'The uploaded photo and manufacturer reference appear side by side. Select a detected machine to inspect its model and qualitative confidence.'},
    {view:'result', target:'.evidence>div:first-child', title:'Read the supporting evidence', text:'Review the details supporting the match, missing evidence and any retake guidance. Confidence describes this prediction; it is not benchmark accuracy.'},
    {view:'result', target:'.savedactions .exports', title:'Export the saved prediction', text:'Download JSON or CSV for independent scoring against source-backed answer labels. Run details contain time and total cost.'},
    {view:'dataset', target:'.guide-heading', title:'Keep evaluation labels separate', text:'The dataset guide shows the assumed reference and test-photo structure. Keep independently established answers outside Identify mode, then use them to score exported predictions.'}
  ];
  function positionTour() {
    cancelAnimationFrame(tourFrame);
    tourFrame = requestAnimationFrame(() => {
      if (!$('#platformTour').open) return;
      const target = tourTarget && $(tourTarget) || main;
      const r = target.getBoundingClientRect(); const vw = window.innerWidth; const vh = window.innerHeight; const pad = 7;
      const x = Math.max(8, r.left-pad); const y = Math.max(8, r.top-pad); const right = Math.min(vw-8, r.right+pad); const bottom = Math.min(vh-8, r.bottom+pad);
      const width = Math.max(0,right-x); const height = Math.max(0,bottom-y);
      const box = (sel,left,top,w,h) => Object.assign($(sel).style,{left:`${left}px`,top:`${top}px`,width:`${Math.max(0,w)}px`,height:`${Math.max(0,h)}px`});
      box('[data-shade="top"]',0,0,vw,y); box('[data-shade="left"]',0,y,x,height); box('[data-shade="right"]',right,y,vw-right,height); box('[data-shade="bottom"]',0,bottom,vw,vh-bottom); box('#tourFocus',x,y,width,height);
      const dialog = $('#platformTour'); const dw = dialog.offsetWidth; const dh = dialog.offsetHeight; const gap = 18;
      let left = right+gap; let top = y;
      if (left+dw > vw-16) { left = x-dw-gap; if (left < 16) { left = Math.max(16,Math.min(x,vw-dw-16)); top = bottom+gap; if (top+dh > vh-16) top = y-dh-gap; } }
      Object.assign(dialog.style,{left:`${Math.max(16,Math.min(left,vw-dw-16))}px`,top:`${Math.max(16,Math.min(top,vh-dh-16))}px`});
    });
  }
  function showTour(index) {
    tourIndex = index;
    const step = tourSteps[index]; let text = step.text; let target = step.target;
    if (step.view === 'product') {
      const p = state.catalogue.find(p => p.in_catalog && media(p.brochure_url)) || state.catalogue.find(p => p.in_catalog);
      if (p) { state.productId = p.id; setView('product'); } else { setView('catalogue'); target = '#addProduct'; text = 'Add a manufacturer product first. Store its source, images and product details in the catalogue.'; }
    } else if (step.view === 'result') {
      const job = state.jobs.find(j => j.status === 'completed');
      if (job) { rememberJob(job.id); setView('match'); if (!$(target)) { target = '.savedactions'; text = 'This saved run has no matching object or saved export for this step. Inspect the recorded result; the tour does not generate a replacement.'; } }
      else { setView('history'); target = '.empty'; text = 'There is no completed result yet. After a real run, open it here to inspect the comparison, evidence, confidence and downloads. The tour does not create sample predictions.'; }
    } else { if (step.view === 'match') rememberJob(null); setView(step.view); }
    const dialog = $('#platformTour'); tourTarget = target;
    $('#tourProgress').textContent = `${index+1} of ${tourSteps.length}`;
    $('#tourTitle').textContent = step.title; $('#tourText').textContent = text;
    $('#tourBack').disabled = index === 0; $('#tourNext').textContent = index === tourSteps.length-1 ? 'Finish tour' : 'Next';
    $('#tourOverlay').hidden = false;
    const anchor = $(target) || main;
    anchor.scrollIntoView({block:'center',behavior:'instant'});
    if (!dialog.open) dialog.showModal();
    $('#tourNext').focus({preventScroll:true}); positionTour();
  }
  function closeTour() { $('#platformTour').close(); $('#tourOverlay').hidden = true; tourTarget = null; cancelAnimationFrame(tourFrame); if (tourReturnFocus?.isConnected) tourReturnFocus.focus(); else $('#startTour').focus(); }
  async function refresh(force = false) {
    try {
      const data = await api('/api/bootstrap');
      if (!Array.isArray(data.jobs) || !Array.isArray(data.catalogue) || !data.csrf_token || !data.settings) throw new Error('The server returned an incomplete workspace. Refresh the page to try again.');
      const oldJob = currentJob(); const oldStatus = oldJob?.status; const previousCatalogue = JSON.stringify(state.catalogue);

      state.csrf = data.csrf_token; state.catalogue = data.catalogue; state.jobs = data.jobs; state.settings = data.settings; state.pollFailures = 0;
      if (!state.ready) { state.ready = true; try { const id = localStorage.getItem('dyson-selected-job'); if (state.jobs.some(j => j.id === id)) rememberJob(id); } catch {} render(); }
      else {
        renderQueue(); renderAllowance();
        const retryButton = $('#retryButton'); if (retryButton && !retryButton.dataset.pending) retryButton.disabled = runUnavailable();
        const runButton = $('#runButton');
        if (runButton) { runButton.disabled = state.submitting || runUnavailable() || state.mode === 'verify' && !state.expected; feedback('#accountingError',state.settings.accounting_error || ''); }
        const job = currentJob();
        const viewRunButton = $('#runViewButton'); if (viewRunButton) viewRunButton.disabled = state.viewSubmitting || !state.pendingView?.confirmed || runUnavailable();
        if (state.view === 'match' && job && state.pendingView?.parentId !== job.id && !state.viewSubmitting && jobSignature(job) !== state.viewSignature) { const focus = focusKey(main); renderJob(job); restoreFocus(main,focus); if (job.status !== oldStatus) announce(`${job.filename}: ${statusName(job.status)}.`); }
        // Keep active forms and selected-file controls intact while background jobs update.
        if (state.view === 'product' && JSON.stringify(getProduct(state.productId)) !== tourProductSignature && !$('#platformTour').open) renderProduct();
        if (state.view === 'catalogue' && previousCatalogue !== JSON.stringify(state.catalogue) && !$('#platformTour').open) renderCatalogue();
        if (state.view === 'history' && (force || JSON.stringify(state.jobs) !== state.historySignature) && !main.contains(document.activeElement)) renderHistory();
      }
      if ($('#globalError').dataset.connection === 'true') { globalError(''); delete $('#globalError').dataset.connection; }
    } catch (error) {
      state.pollFailures++;
      if (!state.ready) { main.setAttribute('aria-busy','false'); main.innerHTML = heading('Workspace unavailable') + `<p class="error" role="alert">${esc(error.message)}</p><button type="button" id="reloadWorkspace">Try again</button>`; }
      else { globalError(`${error.message} Saved jobs will refresh when the connection returns.`); $('#globalError').dataset.connection = 'true'; }
    } finally { clearTimeout(pollTimer); pollTimer = setTimeout(refresh, state.pollFailures ? Math.min(15000,2000*state.pollFailures) : 2000); }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button,a'); if (!button || button.disabled) return;
    if (state.viewSubmitting) return;
    if (button.id === 'addViewButton') { if (canAddView(currentJob())) $('#productViewInput').click(); }
    else if (button.id === 'cancelViewButton') { clearPendingView(); renderJob(currentJob()); $('#addViewButton')?.focus(); }
    else if (button.id === 'runViewButton') runProductViews();
    else if (button.dataset.viewStep) { rememberJob(button.dataset.viewStep,true); setView('match'); }
    else if (button.dataset.storeView) { state.selectedView = button.dataset.storeView; renderResult(currentJob()); $(`[data-store-view="${CSS.escape(state.selectedView)}"]`)?.focus(); }
    else if (button.id === 'startTour' || button.id === 'startGuideTour') { if (!state.ready || state.editor?.saving || state.submitting) return; tourReturnFocus = button; showTour(0); }
    else if (button.id === 'closeTour') closeTour();
    else if (button.id === 'tourBack') showTour(Math.max(0,tourIndex-1));
    else if (button.id === 'tourNext') { if (tourIndex === tourSteps.length-1) closeTour(); else showTour(tourIndex+1); }
    else if (button.dataset.export) { event.preventDefault(); downloadPrediction(button); }
    else if (button.hasAttribute('data-upload')) { if (state.submitting || state.editor?.saving) return; $('#photoInput').click(); }
    else if (button.dataset.nav) { if (state.editor?.saving) return; if (button.dataset.nav === 'match' && state.view !== 'match') rememberJob(null); setView(button.dataset.nav); }
    else if (button.hasAttribute('data-pending')) { rememberJob(null); state.pendingIndex = Number(button.dataset.pending); setView('match'); }
    else if (button.dataset.job) { rememberJob(button.dataset.job); setView('match'); }
    else if (button.hasAttribute('data-remove')) { if (state.submitting) return; state.runRequestId = null; const [item] = state.pending.splice(Number(button.dataset.remove),1); if (item) URL.revokeObjectURL(item.url); state.pendingIndex = Math.max(0,Math.min(state.pendingIndex,state.pending.length-1)); render(); }
    else if (button.id === 'runButton') runMatching();
    else if (button.hasAttribute('data-object')) selectObject(Number(button.dataset.object),true);
    else if (button.dataset.reference) { const img = $('#referencePhoto'); if (img && media(button.dataset.reference)) img.src = media(button.dataset.reference); }
    else if (button.dataset.productReference) { const img = $('#productPhoto'); if (img && media(button.dataset.productReference)) img.src = media(button.dataset.productReference); }
    else if (button.dataset.product) { state.productId = button.dataset.product; setView('product'); }
    else if (button.dataset.editProduct) openEditor(button.dataset.editProduct);
    else if (button.id === 'addProduct') openEditor();
    else if (button.hasAttribute('data-cancel-editor')) cancelEditor();
    else if (button.hasAttribute('data-remove-reference')) { state.editor.images.splice(Number(button.dataset.removeReference),1); updateEditorFiles(); }
    else if (button.dataset.retry) retry(button.dataset.retry);
    else if (button.id === 'reloadWorkspace') refresh(true);
  });
  function selectObject(index, focusButton = false) {
    state.selectedObject = index;
    if (currentJob()) renderResult(currentJob());
    if (focusButton) $(`.objecttabs [data-object="${index}"]`)?.focus(); else $('#objectSelect')?.focus();
  }
  document.addEventListener('change', event => {
    const input = event.target;
    if (state.viewSubmitting) return;
    if (input.id === 'productViewInput') { addProductView(Array.from(input.files || [])); input.value = ''; }
    else if (input.id === 'sameProductConfirm') { if (state.pendingView) { state.pendingView.confirmed = input.checked; $('#runViewButton').disabled = !input.checked || runUnavailable(); } }
    else if (input.id === 'photoInput') { addPhotos(Array.from(input.files || [])); input.value = ''; }
    else if (input.id === 'mode') { state.mode = input.value; state.runRequestId = null; $('#expectedField').classList.toggle('hidden',state.mode !== 'verify'); $('#runButton').disabled = runUnavailable() || state.mode === 'verify' && !state.expected; }
    else if (input.id === 'expectedModel') { state.expected = input.value; state.runRequestId = null; $('#runButton').disabled = runUnavailable() || state.mode === 'verify' && !state.expected; }
    else if (input.id === 'objectSelect') selectObject(Number(input.value));
    else if (input.id === 'referenceFiles') {
      const accepted = []; const errors = [];
      for (const f of input.files || []) { if (!['image/jpeg','image/png','image/webp'].includes(f.type) || f.size > 12*1024*1024) errors.push(`${f.name}: choose JPEG, PNG or WebP up to 12 MiB.`); else accepted.push(f); }
      state.editor.images.push(...accepted); updateEditorFiles(); input.value = ''; feedback('#saveError',errors.join(' '));
    } else if (input.id === 'brochureFile') { const f = input.files?.[0]; if (f && (f.type !== 'application/pdf' || f.size > 12*1024*1024)) { feedback('#saveError','Choose an original PDF up to 12 MiB.'); input.value = ''; } else { state.editor.brochure = f || null; updateEditorFiles(); } }
  });
  document.addEventListener('toggle', event => { if (event.target.id === 'runDetails') state.detailsOpen[event.target.dataset.job] = event.target.open; },true);
  document.addEventListener('input', event => { if (state.editor && ['name','manufacturer','source_url','brochure_details'].includes(event.target.name)) state.editor[event.target.name] = event.target.value; });
  document.addEventListener('submit', event => { if (event.target.id === 'productForm') { event.preventDefault(); saveProduct(event.target); } });
  document.addEventListener('keydown', event => { if (state.viewSubmitting) return; if (event.key === 'Escape' && state.pendingView && state.view === 'match') { event.preventDefault(); clearPendingView(); renderJob(currentJob()); $('#addViewButton')?.focus(); return; } if (event.key === 'Escape' && $('#platformTour').open) { event.preventDefault(); closeTour(); return; } if (event.key === 'Escape' && state.view === 'editor') { event.preventDefault(); cancelEditor(); } });
  $('#platformTour').addEventListener('cancel', event => { event.preventDefault(); closeTour(); });
  window.addEventListener('resize',positionTour);
  window.addEventListener('scroll',positionTour,true);
  document.addEventListener('dragover', event => { const zone = event.target.closest('[data-drop]'); if (zone) { event.preventDefault(); zone.classList.add('dragging'); } });
  document.addEventListener('dragleave', event => { const zone = event.target.closest('[data-drop]'); if (zone && !zone.contains(event.relatedTarget)) zone.classList.remove('dragging'); });
  document.addEventListener('drop', event => { const zone = event.target.closest('[data-drop]'); if (zone) { event.preventDefault(); zone.classList.remove('dragging'); if (!state.submitting && !state.viewSubmitting) addPhotos(Array.from(event.dataTransfer?.files || [])); } });
  window.addEventListener('pagehide',() => { clearTimeout(pollTimer); resizeObserver?.disconnect(); clearPendingView(); state.pending.forEach(p => URL.revokeObjectURL(p.url)); });
  refresh();
})();
