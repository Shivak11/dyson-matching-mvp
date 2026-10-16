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
  const state = {view:'match', catalogue:[], jobs:[], settings:{}, csrf:'', ready:false, pending:[], pendingIndex:0, selectedJob:null, selectedObject:0, productId:null, editor:null, mode:'identify', expected:'', submitting:false, queueSignature:'', allowanceSignature:'', viewSignature:'', historySignature:'', pollFailures:0, runRequestId:null, retryRequests:{}, detailsOpen:{}};
  let resizeObserver;
  let pollTimer;
  let editorReturnFocus = null;
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
      if (error instanceof TypeError) throw new Error('The local server could not be reached. Start the server and refresh this page.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  const heading = (title, description = '', action = '') => `<div class="heading"><div><h1>${esc(title)}</h1>${description ? `<p>${esc(description)}</p>` : ''}</div>${action}</div>`;
  const uploadButton = (label = 'Upload photos') => `<button type="button" data-upload>${esc(label)}</button>`;
  const getProduct = id => state.catalogue.find(p => p.id === id);
  const currentJob = () => state.jobs.find(j => j.id === state.selectedJob);
  const runUnavailable = () => !state.settings.api_configured || Boolean(state.settings.accounting_error);
  const statusName = status => ({queued:'Queued',running:'Running',completed:'Complete',failed:'Failed',interrupted:'Interrupted'}[status] || status || 'Saved');
  const jobDescription = job => job.status === 'completed' ? `${job.matches?.length || 0} machine${job.matches?.length === 1 ? '' : 's'} · Complete` : statusName(job.status);
  const dateText = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value || '') : d.toLocaleString('en-IN', {dateStyle:'medium',timeStyle:'short'}); };
  function rememberJob(id) { state.selectedJob = id; state.selectedObject = 0; try { localStorage.setItem('dyson-selected-job', id || ''); } catch {} }
  function setView(view) {
    state.view = view;
    state.viewSignature = '';
    globalError('');
    render();
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
    $('#queueCount').textContent = `${state.jobs.length + state.pending.length} photo${state.jobs.length + state.pending.length === 1 ? '' : 's'}`;
    $('#queue').innerHTML = state.pending.map((p,i) => `<button type="button" class="queueitem ${state.view === 'match' && !state.selectedJob && i === state.pendingIndex ? 'selected' : ''}" data-pending="${i}">${pendingImage(p)}<span><strong>${esc(p.filename)}</strong><small>Ready to run</small></span></button>`).join('') + state.jobs.map(j => `<button type="button" class="queueitem ${state.view === 'match' && j.id === state.selectedJob ? 'selected' : ''}" data-job="${esc(j.id)}">${image(j.image_url,'')}<span><strong>${esc(j.filename)}</strong><small>${esc(jobDescription(j))}</small></span></button>`).join('') || '<p class="asideempty">Your store photos will appear here.</p>';
    restoreFocus($('#queue'),focus);
  }
  function renderAllowance() {
    const s = state.settings;
    const signature = JSON.stringify(s);
    if (signature === state.allowanceSignature) return;
    state.allowanceSignature = signature;
    $('#allowance').innerHTML = `<div class="budget"><span class="small muted">Run allowance remaining</span><strong class="small">${esc(money(s.runtime_remaining_inr))}</strong></div><p class="small muted">${esc(s.model_label || 'Model not configured')} · OpenRouter</p><p class="small muted allowance-details">${esc(money(s.runtime_spent_inr))} spent or reserved<br>${esc(money(s.stage_remaining_inr))} remaining in stage budget</p>${s.api_configured === false ? '<p class="error small">OpenRouter key is not configured.</p>' : ''}${s.accounting_error ? `<p class="error small">${esc(s.accounting_error)}</p>` : ''}`;
  }
  function renderMatch() {
    const job = currentJob();
    if (job) { renderJob(job); return; }
    if (state.pending.length) { renderSelected(); return; }
    main.innerHTML = heading('Match store photos','Identify each machine using your manufacturer catalogue.', uploadButton()) + `<section class="empty"><div><h2>Upload a store photograph</h2><p>Choose the photos you want to check. You can inspect them before starting a run.</p><button class="primary upload" type="button" data-upload><span class="plus" aria-hidden="true">+</span> Choose photos</button><p class="filetypes">JPEG, PNG or WebP · Up to 5 photos · 12 MiB each</p><p class="error hidden" id="uploadError" role="alert"></p></div></section>`;
  }
  function renderSelected() {
    const p = state.pending[Math.min(state.pendingIndex,state.pending.length-1)];
    state.pendingIndex = state.pending.indexOf(p);
    const products = state.catalogue.filter(p => p.in_catalog);
    main.innerHTML = heading('Review selected photos',`${state.pending.length} photo${state.pending.length === 1 ? '' : 's'} selected.`,uploadButton('Add photos')) + `<section class="selectedlayout"><div class="paneltitle"><span>${esc(p.filename)}</span><button class="quiet small" type="button" data-remove="${state.pendingIndex}">Remove photo</button></div><div class="photo">${pendingImage(p)}</div><div class="selection-strip">${state.pending.map((item,i) => `<button type="button" class="${i === state.pendingIndex ? 'selected' : ''}" data-pending="${i}" aria-label="Preview ${esc(item.filename)}" aria-pressed="${i === state.pendingIndex}">${pendingImage(item)}<span>${esc(item.filename)}</span></button>`).join('')}</div><div class="runcontrols"><div class="field"><label for="mode">What should we check?</label><select id="mode" aria-describedby="modeHelp" ${state.submitting ? 'disabled' : ''}><option value="identify" ${state.mode === 'identify' ? 'selected' : ''}>Identify from the catalogue</option><option value="verify" ${state.mode === 'verify' ? 'selected' : ''}>Verify an expected model</option></select></div><div class="field ${state.mode !== 'verify' ? 'hidden' : ''}" id="expectedField"><label for="expectedModel">Expected model</label><select id="expectedModel" ${state.submitting ? 'disabled' : ''}><option value="">Choose a model</option>${products.map(p => `<option value="${esc(p.id)}" ${state.expected === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div><button id="runButton" type="button" class="primary" ${state.submitting || runUnavailable() || state.mode === 'verify' && !state.expected ? 'disabled' : ''}>${state.submitting ? 'Saving photos…' : `Run matching${state.pending.length > 1 ? ` on ${state.pending.length} photos` : ''}`}</button></div><p class="modehelp" id="modeHelp">Identify finds the catalogue model for each machine. Verify checks whether each machine matches the model you select.</p><div class="runinfo">${esc(state.settings.model_label || 'Model not configured')} through OpenRouter · ${esc(money(state.settings.runtime_remaining_inr))} available for runs</div><p class="error inlinefeedback ${state.settings.accounting_error ? '' : 'hidden'}" role="alert" id="accountingError">${esc(state.settings.accounting_error || '')}</p><p class="error inlinefeedback hidden" role="alert" id="uploadError"></p></section>`;
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
      message.textContent = error.name === 'AbortError' ? 'The download timed out. Try the download again.' : error instanceof TypeError ? 'The local server could not be reached. Reconnect and try the download again.' : error.message;
      message.classList.remove('hidden');
    } finally { clearTimeout(timeout); link.removeAttribute('aria-disabled'); if (url) setTimeout(() => URL.revokeObjectURL(url),1000); }
  }
  const recorded = value => value === null || value === undefined || value === '' ? 'Not recorded' : String(value);
  const duration = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(value)} seconds` : 'Not recorded';
  const recordedCost = (value,currency) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? new Intl.NumberFormat('en-IN',{style:'currency',currency,minimumFractionDigits:2,maximumFractionDigits:6}).format(value) : 'Not recorded';
  function runDetails(job) {
    const previous = $('#runDetails');
    if (previous?.dataset.job === job.id) state.detailsOpen[job.id] = previous.open;
    const d = job.run_details;
    const header = `<details class="rundetails" id="runDetails" data-job="${esc(job.id)}" ${state.detailsOpen[job.id] ? 'open' : ''}><summary id="runDetailsSummary">Run details</summary>`;
    if (!d) return header + '<p class="legacydetails">Run details were not recorded for this run.</p></details>';
    const fields = [['Elapsed time',duration(d.elapsed_seconds)],['Queue time',duration(d.queued_seconds)],['Started',d.started_at ? dateText(d.started_at) : null],['Completed',d.completed_at ? dateText(d.completed_at) : null],['Requested AI model',d.requested_model],['Requested provider',d.requested_provider],['Reasoning',d.reasoning_effort],['Pipeline version',d.pipeline_version],['Configuration SHA-256',d.config_sha256],['Catalogue SHA-256',d.catalogue_sha256],['Cost recorded (INR)',recordedCost(d.cost_inr,'INR')],['Cost basis',d.cost_basis]];
    const requests = Array.isArray(d.requests) ? d.requests : [];
    return header + `<dl>${fields.map(([name,value]) => `<dt>${esc(name)}</dt><dd>${esc(recorded(value))}</dd>`).join('')}</dl>` + (requests.length ? `<div class="tablewrap" id="requestRecords" role="region" aria-label="Request cost records" tabindex="0"><table><thead><tr>${['Request','Status','AI model used','Actual provider','Elapsed time','Charged USD','Reserved USD','Cost basis'].map(name => `<th scope="col">${name}</th>`).join('')}</tr></thead><tbody>${requests.map(r => `<tr>${[r.operation,r.status,r.model,r.provider,duration(r.elapsed_seconds),recordedCost(r.cost_usd,'USD'),recordedCost(r.reserved_cost_usd,'USD'),r.cost_basis].map(value => `<td>${esc(recorded(value))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '<p class="legacydetails">No request records were saved.</p>') + '</details>';
  }
  function renderJob(job) {
    state.viewSignature = JSON.stringify([job,state.settings.accounting_error]);
    if (job.status === 'completed') { renderResult(job); return; }
    const failed = terminalErrors.has(job.status);
    main.innerHTML = heading(job.filename,failed ? 'The photo is saved. Matching did not complete.' : 'Matching continues if you leave this page.',uploadButton('Upload more')) + `<section class="statusarea"><div class="statusphoto">${image(job.image_url,'Uploaded store photograph')}</div><div class="statustext"><p class="small muted">${esc(statusName(job.status))}</p><h2 id="jobStage">${esc(job.stage || statusName(job.status))}</h2>${failed ? `<div class="errornote"><p>${esc(job.error || 'The server stopped before the result was saved.')}</p></div><p>Your photograph and any charges are preserved.</p><div class="buttonrow"><button class="primary" type="button" id="retryButton" data-retry="${esc(job.id)}" ${state.settings.accounting_error ? 'disabled' : ''}>Retry as a new run</button><button type="button" data-nav="history">View history</button></div><p id="retryError" class="error ${state.settings.accounting_error ? '' : 'hidden'}" role="alert">${esc(state.settings.accounting_error || '')}</p>` : '<div class="working"><span class="spinner" aria-hidden="true"></span><p>Waiting for the next saved stage.</p></div><button type="button" data-nav="history">View history</button>'}<p class="small costline">Spent or reserved: ${esc(money(job.cost_inr))}</p>${exportActions(job)}</div></section>${runDetails(job)}`;
  }
  const matchTitle = match => match.status === 'not_in_catalog' ? 'Outside catalogue' : match.status === 'not_sure' ? 'Model not established' : match.product_name || 'Model not established';
  const matchConfidence = match => match.status === 'not_in_catalog' ? 'Not in catalogue' : match.status === 'not_sure' ? 'Not sure · Insufficient evidence' : ['High','Medium','Low'].includes(match.confidence) ? `Match · ${match.confidence} confidence` : 'Match · Confidence not recorded';
  const textItem = item => typeof item === 'string' ? item : item?.detail || item?.observation || item?.text || JSON.stringify(item);
  const evidenceList = (items, fallback) => Array.isArray(items) && items.length ? `<ul>${items.map(item => `<li>${esc(textItem(item))}</li>`).join('')}</ul>` : `<p class="muted small">${esc(fallback)}</p>`;
  function renderResult(job) {
    const matches = Array.isArray(job.matches) ? job.matches : [];
    state.selectedObject = Math.min(state.selectedObject, Math.max(0,matches.length-1));
    const match = matches[state.selectedObject];
    const alternatives = Array.isArray(match?.alternatives) ? match.alternatives.filter(a => (typeof a === 'string' ? a : a.id) !== match.product_id) : [];
    const product = match?.status === 'match' ? getProduct(match.product_id) : null;
    const reference = match?.status === 'match' ? media(match.reference_image_url) : '';
    const references = match?.status === 'match' && Array.isArray(match.reference_images) ? match.reference_images : [];
    const referenceSource = sourceURL(match?.source_url);
    const options = matches.map((m,i) => `<option value="${i}" ${i === state.selectedObject ? 'selected' : ''}>${i+1} · ${esc(matchTitle(m))}</option>`).join('');
    const verification = job.mode === 'verify' ? ({confirmed:'Matches expected model',rejected:'Does not match expected model',unresolved:'Cannot verify'}[match?.verification] || 'Cannot verify') : '';
    main.innerHTML = heading(job.filename,`${matches.length} machine${matches.length === 1 ? '' : 's'} found in this photograph.`,uploadButton('Upload more')) + `<div class="savedactions"><p>Complete · ${job.mode === 'verify' ? 'Verify' : 'Identify'}</p>${exportActions(job)}</div><section aria-label="Matching result"><div class="toolbar">${matches.length ? `<label for="objectSelect">Machine</label><select id="objectSelect">${options}</select>` : '<span>No machine result was returned.</span>'}<div class="right">${match ? `<span class="confidence ${match.status !== 'match' ? 'neutral' : match.confidence === 'High' ? '' : 'medium'}">${esc(matchConfidence(match))}</span>` : ''}<span class="small muted">${esc(money(job.cost_inr))}</span></div></div><div class="resultbody"><div class="compare"><section class="photopanel"><div class="paneltitle"><span>Store photograph</span><span>Original image</span></div><div class="photo" id="resultPhoto">${image(job.image_url,'Store photograph containing the detected machines','id="storePhoto"')}${matches.map((m,i) => `<button type="button" class="box ${i === state.selectedObject ? 'selected' : ''}" data-object="${i}" aria-label="Select machine ${i+1}" aria-pressed="${i === state.selectedObject}" hidden><span>${i+1}</span></button>`).join('')}</div><div class="photofeet"><div class="objecttabs">${matches.map((m,i) => `<button type="button" class="${i === state.selectedObject ? 'selected' : ''}" data-object="${i}" aria-pressed="${i === state.selectedObject}">Machine ${i+1}</button>`).join('')}</div></div></section><section class="reference">${reference ? `<div class="paneltitle"><span>Manufacturer reference</span>${product ? `<button type="button" class="quiet small" data-product="${esc(product.id)}">Current catalogue product ↗</button>` : ''}</div><div class="refimage">${image(reference,`Manufacturer image of ${matchTitle(match)}`,'id="referencePhoto"')}</div>` : '<div class="no-reference"><p class="muted">No manufacturer match established.</p></div>'}<div class="refcaption"><h2>${esc(match ? matchTitle(match) : 'No result')}</h2>${match?.status === 'not_in_catalog' && match.product_name ? `<p class="outside-model">Model: ${esc(match.product_name)}</p>` : ''}${verification ? `<p class="verification">${esc(verification)}</p><p class="small muted">Expected: ${esc(job.expected_product_name || getProduct(job.expected_product_id)?.name || 'Selected model')}</p>` : ''}${reference && references.length ? `<div class="thumbs">${references.map((im,i) => `<button type="button" data-reference="${esc(media(im.url))}" aria-label="Show manufacturer reference ${i+1}">${image(im.url,'')}</button>`).join('')}</div>${referenceSource ? `<p class="source"><a href="${esc(referenceSource)}" target="_blank" rel="noreferrer">Manufacturer source ↗</a></p>` : ''}` : ''}</div></section></div><div class="evidence"><div><h3>Details supporting this result</h3>${evidenceList(match?.evidence,'No supporting details were recorded.')}</div><div class="missing"><h3>Details that remain unverified</h3>${evidenceList(match?.missing_evidence,'No missing details were recorded.')}${alternatives.length ? `<h3 class="alternatives-title">Other possible models</h3><p class="small">${alternatives.map(a => esc(typeof a === 'string' ? a : a.name)).join(', ')}</p>` : ''}</div></div>${Array.isArray(match?.retake_guidance) && match.retake_guidance.length ? `<section class="retake"><h3>Retake guidance for machine ${state.selectedObject+1}</h3>${evidenceList(match.retake_guidance,'')}</section>` : ''}</div></section>${runDetails(job)}`;
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
        const box = matches[Number(button.dataset.object)]?.box_2d;
        if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite) || box.some(v => v < 0 || v > 1000) || box[0] >= box[2] || box[1] >= box[3]) { button.hidden = true; return; }
        Object.assign(button.style,{left:`${left+box[1]*width/1000}px`,top:`${top+box[0]*height/1000}px`,width:`${(box[3]-box[1])*width/1000}px`,height:`${(box[2]-box[0])*height/1000}px`}); button.hidden = false;
      });
    };
    img.addEventListener('load',position,{once:true}); position();
    resizeObserver = new ResizeObserver(position); resizeObserver.observe(holder);
  }
  async function retry(id) {
    const button = $('#retryButton'); if (!button || button.disabled || state.settings.accounting_error) return;
    button.disabled = true; button.textContent = 'Saving new run…';
    try { state.retryRequests[id] ||= crypto.randomUUID(); const result = await api(`/api/jobs/${encodeURIComponent(id)}/retry`,{method:'POST',body:JSON.stringify({request_id:state.retryRequests[id]})}); if (!result.jobs?.length) throw new Error('No new job was returned. Check History before retrying.'); result.jobs.forEach(upsertJob); delete state.retryRequests[id]; rememberJob(result.jobs[0].id); setView('match'); announce('New run saved.'); refresh(true); }
    catch (error) { feedback('#retryError',error.message); button.disabled = false; button.textContent = 'Retry as a new run'; }
  }
  function renderCatalogue() {
    const products = state.catalogue.filter(p => p.in_catalog); const negatives = state.catalogue.filter(p => !p.in_catalog);
    main.innerHTML = heading('Manufacturer catalogue',`${products.length} products with manufacturer images and stored details.`,'<button class="primary" type="button" id="addProduct">+ Add product</button>') + productTable(products) + (negatives.length ? `<details class="negative-refs"><summary>Outside-catalogue comparison references (${negatives.length})</summary><p class="small muted">These references help distinguish lookalikes. They are outside the active catalogue.</p>${productTable(negatives)}</details>` : '');
  }
  function productTable(products) {
    return `<div class="tablewrap"><table><thead><tr><th scope="col">Product</th><th scope="col">Manufacturer</th><th scope="col">Reference images</th><th scope="col">Brochure</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead><tbody>${products.map(p => `<tr><td class="rowname">${image(p.image_url,'')}${esc(p.name)}</td><td>${esc(p.manufacturer)}</td><td>${p.images?.length || 0} image${p.images?.length === 1 ? '' : 's'}</td><td>${p.brochure_url ? 'PDF stored' : 'No PDF added'}</td><td><button type="button" class="rowaction" data-product="${esc(p.id)}">View details</button></td></tr>`).join('')}</tbody></table></div>`;
  }
  function renderProduct() {
    const p = getProduct(state.productId); if (!p) { setView('catalogue'); return; }
    const url = sourceURL(p.source_url);
    main.innerHTML = heading(p.name,'Manufacturer images and product details.','<button type="button" data-nav="catalogue">Back to catalogue</button>') + `<section class="catalogdetails"><div class="largeproduct">${image(p.image_url,`${p.name} manufacturer photograph`,'id="productPhoto"')}<div class="thumbs">${(p.images || []).map((im,i) => `<button type="button" data-product-reference="${esc(media(im.url))}" aria-label="Show manufacturer image ${i+1}">${image(im.url,'')}</button>`).join('')}</div></div><div class="productcopy"><h2>${esc(p.name)}</h2><dl><dt>Manufacturer</dt><dd>${esc(p.manufacturer)}</dd><dt>Catalogue</dt><dd>${p.in_catalog ? 'Active product' : 'Outside-catalogue comparison'}</dd><dt>Source</dt><dd>${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">Manufacturer source ↗</a>` : 'No source added'}</dd><dt>References</dt><dd>${p.images?.length || 0} manufacturer image${p.images?.length === 1 ? '' : 's'}</dd><dt>Brochure</dt><dd>${media(p.brochure_url) ? `<a href="${esc(media(p.brochure_url))}" target="_blank" rel="noreferrer">Open original PDF ↗</a>` : 'No PDF added'}</dd></dl><h3>Brochure / product details</h3><p class="preserve-lines">${esc(p.brochure_details || 'No details have been added.')}</p><button type="button" class="edit-product" data-edit-product="${esc(p.id)}">Edit details / add material</button></div></section>`;
  }
  function openEditor(id = null) {
    const p = id ? getProduct(id) : null;
    editorReturnFocus = document.activeElement;
    state.editor = {id:p?.id || null,name:p?.name || '',manufacturer:p?.manufacturer || 'Dyson',source_url:p?.source_url || '',brochure_details:p?.brochure_details || '',images:[],brochure:null,saving:false};
    setView('editor'); $('#productName')?.focus();
  }
  function renderEditor() {
    const d = state.editor; if (!d) { setView('catalogue'); return; }
    main.innerHTML = heading(d.id ? 'Edit manufacturer product' : 'Add manufacturer product','Store its details and reference material in the local catalogue.','<button type="button" data-cancel-editor>Cancel</button>') + `<form class="addform" id="productForm"><div class="formgrid"><div class="field"><label for="productName">Product name</label><input id="productName" name="name" required maxlength="200" value="${esc(d.name)}"></div><div class="field"><label for="manufacturer">Manufacturer</label><input id="manufacturer" name="manufacturer" required maxlength="200" value="${esc(d.manufacturer)}"></div><div class="field full"><label for="sourceURL">Manufacturer source URL</label><input id="sourceURL" name="source_url" type="url" required value="${esc(d.source_url)}" placeholder="https://www.dyson.in/…"></div><div class="field full"><label for="brochureDetails">Brochure / product details</label><textarea id="brochureDetails" name="brochure_details" rows="7">${esc(d.brochure_details)}</textarea><p class="small muted">Enter details from the manufacturer source or brochure.</p></div><div class="field"><label for="referenceFiles">${d.id ? 'Add manufacturer images' : 'Manufacturer images'}</label><input id="referenceFiles" type="file" accept="image/jpeg,image/png,image/webp" multiple><p class="small muted">JPEG, PNG or WebP · 12 MiB each${d.id ? ' · Existing images stay saved' : ''}</p><ul class="selected-files small" id="referenceFilesList"></ul></div><div class="field"><label for="brochureFile">Brochure PDF (optional)</label><input id="brochureFile" type="file" accept="application/pdf"><p class="small muted">Original PDF · Up to 12 MiB</p><p class="small" id="brochureFileName"></p></div></div><p class="error hidden" role="alert" id="saveError"></p><div class="formactions"><button type="button" data-cancel-editor>Cancel</button><button type="submit" class="primary" id="saveProduct">Save product</button></div></form>`;
    updateEditorFiles();
  }
  function updateEditorFiles() {
    if (!state.editor) return;
    $('#referenceFilesList').innerHTML = state.editor.images.map((f,i) => `<li>${esc(f.name)} <button type="button" class="quiet small" data-remove-reference="${i}" aria-label="Remove ${esc(f.name)}">Remove</button></li>`).join('');
    $('#brochureFileName').textContent = state.editor.brochure?.name || '';
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
      state.productId = p.id; state.editor = null; setView('product'); announce('Manufacturer product saved.');
    } catch (error) { feedback('#saveError',error.message); form.querySelectorAll('input,textarea,button').forEach(el => { el.disabled = false; }); button.textContent = 'Save product'; }
    finally { d.saving = false; }
  }
  function renderHistory() {
    state.historySignature = JSON.stringify(state.jobs);
    main.innerHTML = heading('Saved runs','Reopen a photograph to inspect its result or download its prediction.',uploadButton()) + (state.jobs.length ? `<div class="tablewrap" role="region" aria-label="Saved runs" tabindex="0"><table><thead><tr><th scope="col">Photograph</th><th scope="col">Saved</th><th scope="col">Result</th><th scope="col">Spent or reserved</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead><tbody>${state.jobs.map(j => `<tr><td class="rowname">${image(j.image_url,'')}${esc(j.filename)}</td><td>${esc(dateText(j.created_at))}</td><td>${esc(jobDescription(j))}</td><td>${esc(money(j.cost_inr))}</td><td><div class="historyactions"><button type="button" class="rowaction" data-job="${esc(j.id)}">Open run</button>${exportActions(j)}</div></td></tr>`).join('')}</tbody></table></div>` : '<section class="empty"><div><h2>No saved runs yet</h2><p>Upload store photos, review them and run matching to save your first result.</p><button type="button" class="primary" data-upload>Choose photos</button></div></section>');
  }
  async function refresh(force = false) {
    try {
      const data = await api('/api/bootstrap');
      if (!Array.isArray(data.jobs) || !Array.isArray(data.catalogue) || !data.csrf_token || !data.settings) throw new Error('The server returned an incomplete workspace. Refresh the page to try again.');
      const oldJob = currentJob(); const oldStatus = oldJob?.status;

      state.csrf = data.csrf_token; state.catalogue = data.catalogue; state.jobs = data.jobs; state.settings = data.settings; state.pollFailures = 0;
      if (!state.ready) { state.ready = true; try { const id = localStorage.getItem('dyson-selected-job'); if (state.jobs.some(j => j.id === id)) rememberJob(id); } catch {} render(); }
      else {
        renderQueue(); renderAllowance();
        const runButton = $('#runButton');
        if (runButton) { runButton.disabled = state.submitting || runUnavailable() || state.mode === 'verify' && !state.expected; feedback('#accountingError',state.settings.accounting_error || ''); }
        const job = currentJob();
        if (state.view === 'match' && job && JSON.stringify([job,state.settings.accounting_error]) !== state.viewSignature) { const focus = focusKey(main); renderJob(job); restoreFocus(main,focus); if (job.status !== oldStatus) announce(`${job.filename}: ${statusName(job.status)}.`); }
        // Keep active forms and selected-file controls intact while background jobs update.
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
    if (button.dataset.export) { event.preventDefault(); downloadPrediction(button); }
    else if (button.hasAttribute('data-upload')) { if (state.submitting || state.editor?.saving) return; $('#photoInput').click(); }
    else if (button.dataset.nav) { if (state.editor?.saving) return; setView(button.dataset.nav); }
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
    if (input.id === 'photoInput') { addPhotos(Array.from(input.files || [])); input.value = ''; }
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
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && state.view === 'editor') { event.preventDefault(); cancelEditor(); } });
  window.addEventListener('pagehide',() => { clearTimeout(pollTimer); resizeObserver?.disconnect(); state.pending.forEach(p => URL.revokeObjectURL(p.url)); });
  refresh();
})();
