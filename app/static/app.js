'use strict';
let session = null, service = null, polling = false, actionBusy = false;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const busy = () => actionBusy || session?.score_status === 'running' || session?.agent_status === 'running';
const endpoint = suffix => `/api/sessions/${session.id}${suffix}`;
const audioURL = id => endpoint(`/audio/${id}`);
function toast(message, error=false) { $('toast').textContent=message; $('toast').className=`toast${error?' error':''}`; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').classList.add('hidden'),6500); }
async function api(url, options={}) {
  const response = await fetch(url, options);
  if (!response.ok) { let data;try {data=await response.json();}catch{data={detail:`HTTP ${response.status}`};} throw new Error(typeof data.detail==='string'?data.detail:'Please check your input.'); }
  return response.json();
}
function json(method, body={}) { return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}; }
function form() {return {brief:$('brief').value,query_en:$('query').value,min_duration:Number($('min-duration').value),max_duration:Number($('max-duration').value),diversity:Number($('diversity').value)/100};}
function fillForm() { $('brief').value=session.brief; $('query').value=session.query_en; $('min-duration').value=session.min_duration; $('max-duration').value=session.max_duration; $('diversity').value=session.diversity*100; $('diversity-value').value=`${Math.round(session.diversity*100)}%`; }
async function saveBrief() {session=await api(endpoint('/brief'),json('PUT',form()));}
async function perform(task) { if(busy())return; actionBusy=true; render();try{await task();}catch(e){toast(e.message,true);}finally{actionBusy=false;render();if(busy())poll();} }
async function refreshService() {service=await api('/api/status');}
function render() {
  if (!session) return;
  const isBusy=busy(), scored=session.tracks.filter(t=>t.score!==null).length;
  document.body.classList.toggle('busy',isBusy);
  document.body.classList.toggle('has-tracks',session.tracks.length>0);
  document.body.classList.toggle('has-selection',!!session.selected);
  $('connection').textContent=service?.meta_ready?'Muse configured':'Local mode';
  $('connection').classList.toggle('ready',!!service?.meta_ready);
  $('meta-dot').classList.toggle('ready',!!service?.meta_ready);
  $('meta-note').textContent=service?.meta_ready?'Uses your brief, measured features, and choices. Raw audio stays local.':'Add a Meta API key to enable Muse. Local scoring and A/B listening work without it.';
  const outcome=[...session.activity].reverse().find(e=>['meta','meta_result','limit','error'].includes(e.kind));
  $('planner-outcome').classList.toggle('hidden',!outcome);
  $('planner-outcome').textContent=outcome?.message||'';
  if(service) $('budget-note').textContent=`This app: ${service.budget.requests}/${service.budget.max_requests} requests · Reserved $${service.budget.reserved_usd.toFixed(2)} / $${service.budget.limit_usd.toFixed(2)} · Reported token cost $${service.budget.reported_usd.toFixed(4)}`;
  $('track-count').textContent=session.tracks.length;
  $('files').disabled=isBusy;
  $('save-brief').disabled=isBusy;
  $('demo').disabled=isBusy||session.tracks.length>0;
  $('score').disabled=isBusy||session.tracks.length<2;
  $('score').textContent=session.score_status==='running'?`Scoring ${scored}/${session.tracks.length}`:'Score tracks →';
  $('run-agent').disabled=isBusy||!service?.meta_ready||scored<2;
  $('run-agent').textContent=session.agent_status==='running'?'Muse is planning…':'Plan with Muse ↗';
  $('new-session').disabled=isBusy;
  $('test-warning').classList.toggle('hidden',!session.tracks.some(t=>t.source==='synthetic-test'));
  $('score-summary').textContent=session.score_error||session.agent_error||(scored?`${scored} clips scored · A1 · First 10 seconds at most`:'Add at least two clips to start comparing.');
  $('step-1').classList.toggle('active',!scored);
  $('step-2').classList.toggle('active',scored>0&&!session.selected);
  $('step-3').classList.toggle('active',!!session.selected);
  if(session.tracks.length) {
    const ordered=[...session.tracks].sort((a,b)=>(b.score??-Infinity)-(a.score??-Infinity));
    $('tracks').innerHTML=ordered.map((t,i)=>`<article class="track ${session.selected===t.id?'chosen':''}"><span class="track-rank">${String(i+1).padStart(2,'0')}</span><div><div class="track-name" title="${esc(t.name)}">${esc(t.name)}</div><div class="track-meta"><span>${t.duration.toFixed(1)}s</span>${session.shortlist.includes(t.id)?'<span class="badge">SHORTLIST</span>':''}${t.source==='synthetic-test'?'<span class="badge test">TEST</span>':''}<span>${t.alignment!==null?`CLAP ${t.alignment.toFixed(3)}`:'Similarity not scored'}</span></div><audio class="track-audio" controls preload="metadata" aria-label="Play ${esc(t.name)}" src="${audioURL(t.id)}"></audio></div><div class="track-actions"><div class="track-score">${t.score!==null?t.score.toFixed(2):'—'}<small>TuneJury A1</small></div><button class="track-select" data-select="${t.id}" ${isBusy?'disabled':''}>${session.selected===t.id?'Your pick ✓':'Keep this track'}</button></div></article>`).join('');
  } else $('tracks').innerHTML='<div class="empty"><span class="empty-icon" aria-hidden="true">♪</span><p>No candidates yet.</p><small>Add music you made or have permission to use.</small></div>';
  $('vote-count').textContent=`${session.votes.length} ${session.votes.length===1?'choice':'choices'} recorded`;
  const pair=session.pair, hasPair=!!pair;
  $('vote-controls').classList.toggle('hidden',!hasPair||pair.revealed);
  $('reveal').classList.toggle('hidden',!hasPair||!pair.revealed);
  $('next').disabled=isBusy||scored<2||(hasPair&&!pair.revealed);
  if(hasPair) {
    $('comparison').innerHTML='<div class="compare-grid">'+['a','b'].map(side=>{
      const t=session.tracks.find(t=>t.id===pair[side]);
      return `<div class="compare-card"><div class="compare-head"><span class="compare-letter">${side.toUpperCase()}</span><span class="compare-caption">${pair.revealed?esc(t.name):'Name & score hidden'}</span></div><canvas class="waveform" id="wave-${side}" aria-hidden="true"></canvas><audio controls preload="metadata" aria-label="Play candidate ${side.toUpperCase()}" src="${audioURL(t.id)}"></audio>${pair.revealed?`<p class="field-note">TuneJury A1 ${t.score.toFixed(2)}</p>`:''}</div>`;
    }).join('')+'</div>';
    requestAnimationFrame(()=>['a','b'].forEach(side=>drawWave($(`wave-${side}`),session.tracks.find(t=>t.id===pair[side]).waveform)));
    if(pair.revealed) {
      const v=[...session.votes].reverse().find(v=>v.a===pair.a&&v.b===pair.b);
      $('reveal').innerHTML=`<strong>${v?.disagreement?'Your choice differs from the score ranking.':v?.winner?'Your choice is recorded.':'No preference recorded.'}</strong>This records one listening choice. It does not establish your preference for music you have not heard.${v?.reason?`<p>“${esc(v.reason)}”</p>`:''}`;
    }
  } else $('comparison').innerHTML=`<div class="empty compact">${scored>=2?'No new comparison meets the current criteria. Check the length limits or try other candidates.':'Score your candidates to prepare an A/B comparison.'}</div>`;
  document.querySelectorAll('[data-vote]').forEach(b=>b.disabled=isBusy);
  const selected=session.tracks.find(t=>t.id===session.selected);
  $('selected-name').textContent=selected?.name||'Which track will you take?';
  const seconds=selected?Math.round(selected.duration):0;
  const duration=selected?`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`:'';
  $('selected-note').textContent=selected?`${duration} · WAV · Full-length audio`:'Choose “Keep this track” in your list. You can change your pick at any time.';
  $('selected-status').textContent=selected?'Selected by you':'No track selected';
  $('selected-preview').classList.toggle('hidden',!selected);
  $('selected-test').classList.toggle('hidden',selected?.source!=='synthetic-test');
  const player=$('selected-audio');
  if(selected){
    if(player.dataset.track!==selected.id){player.src=audioURL(selected.id);player.dataset.track=selected.id;}
    player.setAttribute('aria-label',`Play ${selected.name}`);
    requestAnimationFrame(()=>drawWave($('selected-wave'),selected.waveform));
  }else if(player.dataset.track){player.pause();player.removeAttribute('src');delete player.dataset.track;player.load();}
  const downloads={export:selected?endpoint('/export'):null,'download-audio':selected?`${audioURL(selected.id)}?download=true`:null,'download-record':selected?endpoint('/record'):null};
  Object.entries(downloads).forEach(([id,url])=>{
    const link=$(id),disabled=!selected||isBusy;
    link.classList.toggle('disabled',disabled);link.setAttribute('aria-disabled',String(disabled));link.tabIndex=disabled?-1:0;
    if(url)link.href=url;else link.removeAttribute('href');
  });
  $('activity').innerHTML=session.activity.length?[...session.activity].reverse().map(e=>`<div class="activity-item"><span class="activity-kind">${esc(e.kind)}</span><p>${esc(e.message)}</p>${e.details?`<details><summary>Tool inputs & results</summary><pre>${esc(JSON.stringify(e.details,null,2))}</pre></details>`:''}</div>`).join(''):'<p class="muted">Your session notes will appear here.</p>';
}
function drawWave(canvas, values) {if(!canvas)return;const ratio=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*ratio;canvas.height=62*ratio;const c=canvas.getContext('2d');c.scale(ratio,ratio);const w=canvas.clientWidth,h=62,max=Math.max(.001,...values);c.fillStyle=canvas.id==='selected-wave'?'#99bcf5':getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();values.forEach((v,i)=>{const height=Math.max(2,v/max*48);c.fillRect(i*w/values.length,(h-height)/2,Math.max(1,w/values.length-1),height);});}
async function poll() {if(polling)return;polling=true;try{while(session.score_status==='running'||session.agent_status==='running'){await new Promise(r=>setTimeout(r,1500));session=await api(endpoint(''));render();}await refreshService();fillForm();render();if(session.score_error||session.agent_error)toast(session.score_error||session.agent_error,true);}catch(e){toast(e.message,true);}finally{polling=false;}}
async function uploadFiles(files) {await perform(async()=>{for(const file of files){const data=new FormData();data.append('file',file);session=await api(endpoint('/tracks'),{method:'POST',body:data});}toast(`Added ${files.length} ${files.length===1?'file':'files'}.`);});}
$('files').addEventListener('change',e=>{uploadFiles([...e.target.files]);e.target.value='';});
$('dropzone').addEventListener('dragover',e=>{e.preventDefault();$('dropzone').classList.add('dragover');});
$('dropzone').addEventListener('dragleave',()=>$('dropzone').classList.remove('dragover'));
$('dropzone').addEventListener('drop',e=>{e.preventDefault();$('dropzone').classList.remove('dragover');uploadFiles([...e.dataTransfer.files]);});
$('diversity').addEventListener('input',e=>$('diversity-value').value=`${e.target.value}%`);
$('save-brief').addEventListener('click',()=>perform(async()=>{await saveBrief();toast('Brief saved. Rescore candidates if you changed the sound query.');}));
$('demo').addEventListener('click',()=>perform(async()=>{session=await api(endpoint('/demo'),{method:'POST'});toast('Synthetic test clips added.');}));
$('score').addEventListener('click',()=>perform(async()=>{await saveBrief();session=await api(endpoint('/score'),{method:'POST'});}));
$('run-agent').addEventListener('click',()=>perform(async()=>{await saveBrief();session=await api(endpoint('/agent'),{method:'POST'});}));
$('next').addEventListener('click',()=>perform(async()=>{session=await api(endpoint('/next'),{method:'POST'});$('reason').value='';}));
document.addEventListener('click',e=>{const vote=e.target.closest('[data-vote]'),choice=e.target.closest('[data-select]');if(vote)perform(async()=>{session=await api(endpoint('/vote'),json('POST',{winner:vote.dataset.vote,reason:$('reason').value}));});if(choice)perform(async()=>{session=await api(endpoint('/select'),json('POST',{track_id:choice.dataset.select}));toast('Your pick is ready.');requestAnimationFrame(()=>$('final-selection').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'}));});});
document.addEventListener('play',e=>{if(e.target.tagName==='AUDIO')document.querySelectorAll('audio').forEach(a=>{if(a!==e.target)a.pause();});},true);
$('new-session').addEventListener('click',()=>perform(async()=>{session=await api('/api/sessions',{method:'POST'});localStorage.setItem('tunejury-session',session.id);fillForm();}));
async function boot() {try{await refreshService();const id=localStorage.getItem('tunejury-session');if(id){try{session=await api(`/api/sessions/${id}`);}catch{session=null;}}if(!session){session=await api('/api/sessions',{method:'POST'});localStorage.setItem('tunejury-session',session.id);}fillForm();render();const incomingBrief=new URLSearchParams(location.search).get("brief");if(incomingBrief){$("brief").value=incomingBrief.slice(0,2000);$("sidebar-fold").open=true;toast("Your demo brief is ready to edit. Save it or add your tracks to continue.");history.replaceState(null,"",location.pathname);}if(busy())poll();}catch(e){toast(`Could not connect to the server: ${e.message}`,true);}}
const sidebarFold=$('sidebar-fold'), compactSidebar=matchMedia('(max-width:560px)');
function adaptSidebar(){sidebarFold.open=!compactSidebar.matches;}
compactSidebar.addEventListener('change',adaptSidebar);adaptSidebar();
boot();
