'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const UUID = () => crypto.randomUUID().replaceAll('-', '');
let profileId = localStorage.getItem('sonvane-profile') || UUID();
localStorage.setItem('sonvane-profile', profileId);
let project = null, file = null, service = null, working = false, polling = false;
let voicePlayToken=0;
let chatSignature='',voiceRecorder=null,voiceStarting=false,transcribing=false,voiceTick=null;
let juryPreviewId=null,juryPreviewProject=null,juryPlayToken=0;
let previewMode = 'mix', trackSignature = '', videoSignature = '', mixSignature = '', fileURL = null;
let sourceDuration=null,trimError='',sectionPlayback=false;
let sourceFile=null,nextFileManual=false;
let analysisStage=null,analysisError='',autoSubmitted=new WeakSet();
let workspaceTab=null,workspaceProject=null,workspacePlan=null,workspaceSelected=null;
let cueDraft=null,cueRevision=null,cueProject=null,cueDirty=false,effectURL=null,cuePlaybackEnd=null;
const running = () => project && (project.chat_pending || project.cue_pending || ['planning','generating','scoring','mixing'].includes(project.status));
const generating = () => project && ['planning','generating','scoring','mixing'].includes(project.status);
const endpoint = suffix => `/api/studio/projects/${project.id}${suffix}`;
const json = body => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
const show = (id, visible) => $(id).classList.toggle('hidden', !visible);

// Render CommonMark without raw HTML, remote images, or unsafe link schemes.
const chatMarkdown=window.markdownit('commonmark',{html:false,linkify:false});
chatMarkdown.validateLink=url=>{try{return ['http:','https:','mailto:'].includes(new URL(url,location.origin).protocol);}catch{return false;}};
chatMarkdown.renderer.rules.image=(tokens,i,options,env,self)=>self.renderInline(tokens[i].children||[],options,env);
const defaultLinkOpen=chatMarkdown.renderer.rules.link_open || ((tokens,i,options,env,self)=>self.renderToken(tokens,i,options));
chatMarkdown.renderer.rules.link_open=(tokens,i,options,env,self)=>{tokens[i].attrSet('rel','noopener noreferrer');return defaultLinkOpen(tokens,i,options,env,self);};
function speechWords(container){
  const walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT),nodes=[];let node,text='';
  while(node=walker.nextNode()){nodes.push({node,start:text.length});text+=node.nodeValue;}
  const words=Array.from(text.matchAll(/\S+/g),m=>({start:m.index,end:m.index+m[0].length,text:m[0]}));
  for(const {node,start} of nodes){
    const value=node.nodeValue,fragment=document.createDocumentFragment();let at=0;
    words.forEach((word,index)=>{
      const a=Math.max(0,word.start-start),b=Math.min(value.length,word.end-start);if(a>=b)return;
      fragment.append(document.createTextNode(value.slice(at,a)));
      const span=document.createElement('span');span.className='speech-word';span.dataset.word=index;span.textContent=value.slice(a,b);
      span.setAttribute('role','button');span.tabIndex=index===0?0:-1;span.setAttribute('aria-label',`Read from “${word.text}”`);fragment.append(span);at=b;
    });
    fragment.append(document.createTextNode(value.slice(at)));node.replaceWith(fragment);
  }
}
let activeSpeech=null,speechFrame=0,highlightedWords=[];
const speechCache=new Map();
function clearSpeechHighlight(){highlightedWords.forEach(el=>el.classList.remove('is-speaking'));highlightedWords=[];}
function highlightSpeech(){
  cancelAnimationFrame(speechFrame);const audio=$('reply-audio');
  if(activeSpeech){
    const index=activeSpeech.words.findIndex(w=>audio.currentTime>=w.start && audio.currentTime<w.end);
    if(index!==activeSpeech.lastIndex || highlightedWords.some(el=>!el.isConnected)){
      clearSpeechHighlight();activeSpeech.lastIndex=index;
      if(index>=0){
        highlightedWords=Array.from(document.querySelectorAll(`[data-turn="${activeSpeech.turnId}"] .speech-word[data-word="${index}"]`));
        highlightedWords.forEach(el=>el.classList.add('is-speaking'));
        // Follow speech inside the transcript only, without moving the page or video.
        if(highlightedWords.length && !audio.paused){
          const container=$('conversation'),bounds=container.getBoundingClientRect(),word=highlightedWords[0].getBoundingClientRect();
          if(word.bottom>bounds.bottom-18)container.scrollTop+=word.bottom-bounds.bottom+18;
          else if(word.top<bounds.top+18)container.scrollTop+=word.top-bounds.top-18;
        }
      }
    }
  }else clearSpeechHighlight();
  if(!audio.paused && !audio.ended)speechFrame=requestAnimationFrame(highlightSpeech);
}

// Existing saved plans may be verbose. Show an excerpt; retain the original in details.
function shortExcerpt(text, limit=240) {
  const clean=String(text || '').replace(/\s+/g,' ').trim();
  if(clean.length<=limit)return clean;
  const sentences=Array.from(new Intl.Segmenter('en',{granularity:'sentence'}).segment(clean),x=>x.segment.trim());
  if(sentences[0]?.length<=limit)return sentences[0];
  const cut=clean.slice(0,limit-1);return cut.slice(0,Math.max(cut.lastIndexOf(' '),limit-40))+'…';
}
// Only emphasize spans already in the text; no extra request and no raw model HTML.
function recommendationMarkup(text, highlights=[]){
  const value=String(text||''),lower=value.toLowerCase();
  const fallback=Array.from(value.matchAll(/\b(?:warm|gentle|soft|calm|peaceful|sparse|restrained|ambient|slow|steady|upbeat)(?:[ -](?:warm|gentle|soft|calm|peaceful|sparse|restrained|ambient|slow|steady|upbeat)){0,2}(?:\s+(?:instrumental|piano|guitar|strings|music))?\b|\b(?:no vocals|no percussion|without drums|leave room for (?:the )?voice|original audio|slow forward motion)\b/gi),m=>m[0]);
  const phrases=Array.isArray(highlights)&&highlights.length?highlights:fallback;
  const spans=[];let budget=Math.floor(value.length*.45);
  for(const item of phrases){
    if(typeof item!=='string')continue;
    const phrase=item.trim(),start=lower.indexOf(phrase.toLowerCase()),end=start+phrase.length;
    if(!phrase || start<0 || phrase.length>60 || phrase.length>budget || spans.length===3)continue;
    if(start>0 && /[a-z0-9]/i.test(value[start-1]) || end<value.length && /[a-z0-9]/i.test(value[end]))continue;
    // Avoid emphasizing a positive fragment when the preceding words negate it.
    if(/\b(?:no|not|without|avoid|never|less)(?:\s+\w+){0,2}\s+$/i.test(value.slice(Math.max(0,start-35),start)))continue;
    if(spans.some(s=>start<s.end && end>s.start))continue;
    spans.push({start,end});budget-=phrase.length;
  }
  spans.sort((a,b)=>a.start-b.start);let html='',at=0;
  for(const span of spans){html+=esc(value.slice(at,span.start))+`<strong class="key-phrase">${esc(value.slice(span.start,span.end))}</strong>`;at=span.end;}
  return html+esc(value.slice(at));
}
// Present every sentence of the original analysis as a bullet, without truncation or a model call.
function renderOriginalPoints(id, text){
  const value=String(text||'').trim();
  const points=Array.from(new Intl.Segmenter('en',{granularity:'sentence'}).segment(value),s=>s.segment.trim()).filter(Boolean);
  $(id).innerHTML=points.map(point=>`<li>${esc(point)}</li>`).join(' ');
}
function renderStageSpeaker(){
  const stages={
    planning:['Muse Spark','Planning the sound','I’m preparing a musical direction for your video.','situation-brief-v1.png'],
    generating:['ACE-Step','Creating music','Creating variations from your approved musical direction.',null],
    scoring:['TuneJury','Evaluating the music','I’m scoring the generated music. You’ll see the recorded scores when the mix is ready.','situation-compare-v2.png'],
    mixing:['Sonvane','Preparing your mix','Combining the ranking signals and mixing the selected soundtrack with your video.','situation-record-v1.png']
  };
  const plan=project?.pending_sound_plan || project?.sound_plan;
  const effectsOnly=plan && !plan.cues.some(c=>c.enabled&&c.kind==='music');
  const stage=project?.status==='planning' && project?.pending_sound_plan?['Sonvane','Using your approved plan','Preparing your approved sound plan. No new Spark analysis is needed.',null]:effectsOnly && ['generating','scoring'].includes(project?.status)?['Sonvane','Preparing sound effects','Preparing your approved synthesized effects. No music is generated or scored.',null]:stages[project?.status];
  show('progress-speaker',!!stage && !project?.cancellation_requested);
  if(!stage)return;
  const [name,role,speech,art]=stage;
  $('progress-speaker').innerHTML=`${art?`<img class="speaker-art" src="/demo/${art}" alt="Illustrated ${esc(name)} workflow">`:'<span class="generator-symbol" aria-hidden="true">♫</span>'}<div class="speaker-copy"><p class="speaker-name">${esc(name)} <span>· ${esc(role)}</span></p><p class="speaker-speech">${esc(speech)}</p></div>`;
}
function renderJury(selected){
  const rated=selected.evaluation_kind!=='not-rated' && Number.isFinite(selected.score);
  show('jury-verdict',rated);show('remember-comparison',rated);if(!rated){clearJuryPreview();return;}
  // Compare the selected track's round, including when the listener revisits an old round.
  const tracks=project.tracks.filter(t=>t.round===selected.round && t.evaluation_kind!=='not-rated' && Number.isFinite(t.score)).sort((a,b)=>b.score-a.score);
  const best=tracks[0],ties=tracks.filter(t=>t.score===best.score);
  $('jury-speech').textContent=tracks.length===1?'Music evaluated with A1.':ties.length>1?'Tied for highest A1 score.':`Highest A1: ${best.name}.`;
  $('jury-compare-title').textContent=`Compare ${tracks.length} version${tracks.length===1?'':'s'} · Round ${selected.round}`;
  $('jury-scores').innerHTML=tracks.map(t=>`<button type="button" class="jury-score ${t.id===selected.id?'chosen':''}" data-listen="${t.id}" aria-label="Listen to ${esc(t.name)}, A1 score ${t.score.toFixed(3)}" aria-pressed="false"><span class="jury-track-name"><strong>${esc(t.name)}</strong><span class="jury-track-status">${t.id===selected.id?'In your video':ties.includes(t)?'Highest A1':''}</span></span><span class="jury-listen-label">▷ Listen</span><span class="jury-number" aria-label="A1 score ${t.score.toFixed(3)}">${t.score.toFixed(3)}<small>A1</small></span></button>`).join('');
  $('jury-selection-note').textContent=project.selected_by==='listener'?'Your video uses your selected version.':'Recommendation combines A1, brief match and your saved comparisons.';
  if(juryPreviewProject!==project.id || juryPreviewId && !tracks.some(t=>t.id===juryPreviewId))clearJuryPreview();
  juryPreviewProject=project.id;updateJuryPlayback();
}
function clearJuryPreview(){juryPlayToken++;juryPreviewId=null;$('jury-audio').pause();$('jury-audio').removeAttribute('src');$('jury-audio').load();show('jury-preview',false);}
function updateJuryPlayback(){
  const audio=$('jury-audio'),track=project?.tracks.find(t=>t.id===juryPreviewId);
  document.querySelectorAll('[data-listen]').forEach(button=>{
    const active=button.dataset.listen===juryPreviewId,playing=active&&!audio.paused;
    button.classList.toggle('auditioning',active);button.setAttribute('aria-pressed',String(playing));
    button.querySelector('.jury-listen-label').textContent=playing?'Ⅱ Pause':active?'▷ Continue':'▷ Listen';
  });
  show('jury-preview',!!track);
  if(track){
    $('jury-preview-name').textContent=`Listening: ${track.name} · Round ${track.round}`;
    $('jury-use-track').dataset.pick=track.id;
    $('jury-use-track').textContent=track.id===project.selected?'Already in your video ✓':'Use in my video';
    $('jury-use-track').disabled=track.id===project.selected || !!(working||running());
  }
}
async function auditionTrack(id){
  if(working||running())return;
  const track=project?.tracks.find(t=>t.id===id);if(!track || track.evaluation_kind==='not-rated')return;
  const audio=$('jury-audio');
  if(juryPreviewId===id){if(audio.paused)await audio.play().catch(()=>toast('Press play to hear this version.'));else audio.pause();return;}
  const position=juryPreviewId && !audio.ended?audio.currentTime:0,token=++juryPlayToken;
  audio.pause();juryPreviewId=id;juryPreviewProject=project.id;updateJuryPlayback();
  try{
    audio.src=endpoint('/audio/'+id);
    await new Promise((resolve,reject)=>{
      const done=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(Error('This music preview could not load.'));};
      const timer=setTimeout(failed,15000),cleanup=()=>{clearTimeout(timer);audio.removeEventListener('loadedmetadata',done);audio.removeEventListener('error',failed);};
      audio.addEventListener('loadedmetadata',done);audio.addEventListener('error',failed);audio.load();
    });
    if(token!==juryPlayToken)return;
    audio.currentTime=Math.min(position,Math.max(0,audio.duration-.05));
    await audio.play().catch(()=>toast('Press play to hear this version.'));
  }catch(error){if(token===juryPlayToken){clearJuryPreview();toast(error.message,true);}}
  updateJuryPlayback();
}
for(const event of ['play','pause','ended'])$('jury-audio').addEventListener(event,updateJuryPlayback);
document.addEventListener('click',event=>{const button=event.target.closest('[data-listen]');if(button)auditionTrack(button.dataset.listen);});


function toast(text, error = false) {
  $('toast').textContent = text; $('toast').className = 'toast' + (error ? ' error' : '');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => show('toast', false), 7000);
}
function connection(message = '') {
  $('connection-message').textContent = message; show('connection-note', !!message);
}
async function api(url, options = {}) {
  const r = await fetch(url, {...options, signal:AbortSignal.timeout(options.method ? 150000 : 20000)});
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw Error(typeof e.detail === 'string' ? e.detail : `Request failed (${r.status})`);
  }
  return r.json();
}
function draftKey() { return `sonvane-draft-${project?.id || 'new'}`; }
function saveDraft() {
  let previous;try{previous=JSON.parse(localStorage.getItem(draftKey()));}catch{}
  localStorage.setItem(draftKey(), JSON.stringify({brief:$('brief').value, context:$('context').value,
    preserve:$('preserve-audio').checked, feedback:$('feedback').value, remember:$('remember-note').checked,
    chat:$('chat-input').value,filename:file?.name || (!project?previous?.filename:null) || null,
    trim:file?{name:file.name,size:file.size,modified:file.lastModified,start:$('trim-start').value,end:$('trim-end').value}:(!project?previous?.trim:null) || null,
    workspaceTab,
    cues:project && cueProject===project.id && cueDirty?{revision:cueRevision,plan:cueDraft}:null}));
}
function restoreDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(draftKey())); if (!d) return;
    $('chat-input').value=d.chat || '';
    $('brief').value = d.brief || ''; $('context').value = d.context || 'general';
    $('preserve-audio').checked = d.preserve !== false; $('feedback').value = d.feedback || '';
    $('remember-note').checked = !!d.remember;
    if(['plan','results','muse'].includes(d.workspaceTab)){workspaceTab=d.workspaceTab;workspaceProject=project?.id;workspacePlan=project?.sound_plan?.revision;workspaceSelected=project?.selected;}
    if(d.cues && project?.sound_plan?.revision===d.cues.revision){cueDraft=d.cues.plan;cueRevision=d.cues.revision;cueProject=project.id;cueDirty=true;drawCues();}
    renderWorkspace();
    if (!project && d.filename) toast(`Your direction was saved. Reselect ${d.filename} to continue.`);
  } catch { /* A malformed local draft does not block the project. */ }
}
function disable() {
  const busy = working || running() || voiceStarting || transcribing || voiceRecorder?.active;
  const budget = service?.budget;
  const exhausted = budget && (budget.reserved_usd + .25 > budget.limit_usd || budget.requests >= budget.max_requests);
  document.body.classList.toggle('busy', !!busy);
  const invalidClip=file && (!sourceDuration || !!trimError);
  $('create').disabled = busy || invalidClip || !(file || project) || !service?.generator_ready || !service?.meta_ready || project?.round >= 4 || exhausted;
  $('create').textContent = working && file ? 'Preparing your video…' : 'Quick full-clip soundtrack ↗';
  if(project?.sound_plan)$('create').disabled=true;
  $('plan-sound').disabled=!!busy || invalidClip || !(file||project) || (!project?.sound_plan && (!service?.meta_ready || exhausted));
  show('new-sound-plan',!!project?.sound_plan);$('new-sound-plan').disabled=!!busy || !project?.sound_plan || !service?.meta_ready || exhausted;
  $('plan-sound').textContent=analysisError||project?.cue_error?'Try analysis again ↗':'Analyze this video ↗';
  document.querySelectorAll('#sound-plan-panel input,#sound-plan-panel textarea,#sound-plan-panel select,#sound-plan-panel button').forEach(e=>e.disabled=!!busy);
  $('approve-sound-plan').disabled=!!busy || !cueDraft || !!cueValidation() || project?.round>=4 || (cueDraft?.cues.some(c=>c.enabled&&c.kind==='music')&&!service?.generator_ready);
  const reviewRevision=!!project?.sound_plan && !$('edit-region').checked;
  $('revise').textContent=reviewRevision?'Edit the sound plan ↑':'Revise with Muse ↗';
  $('revise').disabled = !!busy || !project || (!reviewRevision && (project.round >= 4 || exhausted || !service?.meta_ready));
  for (const id of ['new-project','video-file','project-history','brief','context','preserve-audio','remember-choice','compared-with','apply-mix','mix-level','mix-original','mix-duck','edit-region','region-start','region-end']) $(id).disabled = !!busy;
  syncMixDucking(busy);
  for(const id of ['trim-start','trim-end','trim-start-range','trim-end-range'])$(id).disabled=!!busy || !sourceDuration;
  $('preview-section').disabled=!!busy || !file || !sourceDuration || !!trimError;
  document.querySelectorAll('[data-pick], [data-forget], [data-listen]').forEach(b => b.disabled = !!busy);
  $('jury-use-track').disabled=!!busy || !juryPreviewId || juryPreviewId===project?.selected;
  $('stop-job').disabled = !generating() || project.cancellation_requested;
  $('stop-job').textContent = project?.cancellation_requested ? 'Stopping…' : 'Stop generation';
  $('resume-job').disabled = !!busy || !project?.can_resume || (project?.resume_requires_generator && !service?.generator_ready);
  $('send-chat').disabled=!$('chat-input').value.trim() || !!busy || invalidClip || !(file||project) || !service?.meta_ready || exhausted;
  $('chat-input').disabled=!!(working||running()||transcribing);
  $('record-voice').disabled=!!(working||running()||voiceStarting||transcribing);
  $('chat-status').textContent=project?.chat_pending?'Muse is considering your message…':generating()?'Music is being prepared…':working?'Working…':'Ready when you are';
  if(project && project.video.duration<10)$('edit-region').disabled=true;
  if (project) $('round-note').textContent = project.round >= 4
    ? 'Four generation rounds used. You can still listen, select, adjust the mix, or resume saved work.'
    : `Creates three new candidates. ${4-project.round} generation round${4-project.round===1?'':'s'} remaining. Previous tracks stay available.`;
}
function renderMemory(p) {
  $('memory-count').textContent = p.pair_count + p.notes.length;
  $('memory-summary').textContent = p.pair_count
    ? `${p.pair_count} remembered comparison${p.pair_count===1?' trains':'s train'} your personal ranking. You can remove any of them.`
    : p.notes.length ? 'Your saved directions will guide Muse on matching video contexts.' : 'Only preferences you choose to remember are saved.';
  $('memory-list').innerHTML = [...p.notes.map(n => `<div class="memory-item"><small>${esc(n.context)} · Direction</small><p>${esc(n.text)}</p><button class="text-button" data-forget="${n.id}">Forget this direction</button></div>`),
    ...p.pairs.map(n => `<div class="memory-item"><small>${esc(n.context)} · Learned comparison</small><p>${esc(n.winner)} over ${esc(n.loser)}</p><button class="text-button" data-forget="${n.id}">Forget this comparison</button></div>`)].join('') || '<p class="helper">No remembered preferences yet.</p>';
  $('clear-memory').disabled = !!(working || running()) || !(p.pairs.length+p.notes.length);
}
async function refreshMemory() { renderMemory(await api(`/api/studio/profiles/${profileId}`)); }
async function refreshHistory() {
  const {projects} = await api(`/api/studio/projects?profile_id=${profileId}`);
  $('project-history').innerHTML = '<option value="">New video</option>' + projects.map(p => `<option value="${p.id}">${esc(p.name)} · ${esc(p.status)}${p.track_name?' · '+esc(p.track_name):''}</option>`).join('');
  $('project-history').value = project?.id || '';
}
async function refreshStatus() {
  service = await api('/api/studio/status');
  const ready = service.generator_ready && service.meta_ready;
  $('service-dot').classList.toggle('ready', ready);
  $('service-status').textContent = ready ? 'Ready to make music' : 'The studio needs setup';
  const b = service.budget;
  $('budget-status').textContent = `Meta budget: $${b.reserved_usd.toFixed(2)} reserved / $${b.limit_usd.toFixed(2)} · Local generation`;
  disable();
}
function setVideo(src) {
  if (videoSignature === src) return;
  const v = $('preview'), position = v.currentTime || 0, shouldPlay = !v.paused;
  v.pause(); videoSignature = src; v.src = src;
  v.addEventListener('loadedmetadata', () => {
    v.currentTime = Math.min(position, Math.max(0, v.duration-.05));
    if (shouldPlay) v.play().catch(() => {});
  }, {once:true});
}
function renderRecommendationEvidence(selected) {
  const notRated=selected.evaluation_kind==='not-rated';
  const scene=selected.scene_summary?.trim() || '';
  $('scene-summary').textContent=scene;show('evidence-scene',!!scene);
  $('ranking-note').textContent=notRated
    ? 'Effects-only output. No music was generated or scored.'
    : selected.sound_plan
      ? 'Music sections only. Gaps and sound effects are excluded from scoring.'
      : 'Scores are based on audio windows across each music track.';
  show('evidence-method',!notRated);show('personal-evidence-note',!notRated);
  if(notRated){$('score-evidence').replaceChildren();return;}
  const tracks=project.tracks.filter(t=>t.round===selected.round).sort((a,b)=>b.utility-a.utility);
  const hasPersonal=tracks.some(t=>Number.isFinite(t.personal_adjustment)&&Math.abs(t.personal_adjustment)>=.0005);
  const score=value=>Number.isFinite(value)?value.toFixed(3):'—';
  const adjustment=value=>Number.isFinite(value)?`${value>=0?'+':''}${value.toFixed(3)}`:'—';
  $('personal-evidence-note').textContent=hasPersonal?'':'No personal adjustment in this round.';
  show('personal-evidence-note',!hasPersonal);
  $('score-evidence').innerHTML=`<table class="evidence-table${hasPersonal?' has-personal':''}" role="table"><caption>Round ${esc(String(selected.round))} · Recommendation order</caption><thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Version</th><th scope="col" role="columnheader">TuneJury A1</th><th scope="col" role="columnheader">Brief match</th>${hasPersonal?'<th scope="col" role="columnheader">Personal</th>':''}</tr></thead><tbody role="rowgroup">${tracks.map(t=>{
    const recommended=t.id===project.recommended;
    return `<tr role="row"${recommended?' class="is-recommended"':''}><th scope="row" role="rowheader"><span class="evidence-name">${esc(t.name)}</span>${recommended?'<span class="evidence-badge">Recommended</span>':''}</th><td role="cell" data-label="TuneJury A1">${score(t.score)}</td><td role="cell" data-label="Brief match">${score(t.alignment)}</td>${hasPersonal?`<td role="cell" data-label="Personal">${adjustment(t.personal_adjustment)}</td>`:''}</tr>`;
  }).join('')}</tbody></table>`;
}

function render() {
  disable(); if (!project){renderWorkspace();return;}
  show('trim-panel',false);sectionPlayback=false;
  const selection=project.video.selection;
  show('clip-origin',!!selection && (selection.start>0 || selection.end<selection.source_duration-.05));
  if(selection)$('clip-origin').textContent=`Selected from original: ${timeLabel(selection.start)}–${timeLabel(selection.end)} of ${timeLabel(selection.source_duration)}. Preview and downloads contain this section.`;
  renderConversation();
  renderSoundPlan();
  $('upload-label').textContent = project.name;
  $('video-duration').textContent = `${project.video.duration.toFixed(1)} sec`;
  show('empty-preview', false); show('preview', true);
  const selected = project.tracks.find(t => t.id === project.selected), mix = project.renders[project.selected];
  show('preview-switch', !!mix);
  if(mix && !mixSignature && videoSignature===endpoint('/source') && !$('preview').paused)previewMode='original';
  const revision = mix ? encodeURIComponent(mix) : '';
  const mixURL = endpoint(`/preview?track_id=${project.selected}&v=${revision}`);
  setVideo(mix && previewMode==='mix' ? mixURL : endpoint('/source'));
  $('show-mix').classList.toggle('active', previewMode==='mix');
  $('show-original').classList.toggle('active', previewMode==='original');
  $('show-mix').setAttribute('aria-pressed',String(previewMode==='mix'));$('show-original').setAttribute('aria-pressed',String(previewMode==='original'));
  $('preview-label').textContent = mix && previewMode==='mix' ? 'With soundtrack' : 'Original video';
  show('progress-panel', generating() || ['error','cancelled'].includes(project.status));renderStageSpeaker();
  $('progress-message').textContent = project.cancellation_requested ? 'Stopping after the current step…' : project.message;
  const n = project.generation_progress?.completed || 0;
  $('progress-detail').textContent = project.cancellation_requested
    ? 'An in-flight Muse request may still finish and count toward usage. Saved work will remain available.'
    : project.can_resume ? 'Resume continues the saved plan without another Muse request or generation round.'
    : project.error || (project.status==='generating' ? `${n} of 3 music candidates saved. You can stop and resume this work.` : 'This shows real work. Your project is saved on the server.');
  if(project.status==='generating'&&project.generation_progress?.cue_total)$('progress-detail').textContent=`Variation ${n+1} of 3 · ${project.generation_progress.cue_completed} of ${project.generation_progress.cue_total} music sections saved.`;
  show('stop-job', !!generating()); show('resume-job', !!project.can_resume);
  document.querySelectorAll('[data-step]').forEach(e => e.classList.toggle('active', e.dataset.step===project.status));
  document.querySelector('[data-step=planning]').textContent=project.pending_sound_plan?'Approved plan':'Muse plans';
  const effectsOnly=project.pending_sound_plan && !project.pending_sound_plan.cues.some(c=>c.enabled&&c.kind==='music');
  document.querySelector('[data-step=generating]').textContent=effectsOnly?'Prepare effects':'ACE-Step generates';
  document.querySelector('[data-step=scoring]').textContent=effectsOnly?'Check effects':'TuneJury evaluates';
  for (const id of ['result-panel','feedback-panel','alternatives-panel']) show(id, !!(selected && mix));
  if (selected && mix) {
    renderJury(selected);
    $('selected-name').textContent = `${selected.name} · Round ${selected.round}`;
    $('pick-label').textContent = project.selected_by==='listener' ? 'Your chosen soundtrack' : selected.id===project.recommended ? 'Recommended for this video' : 'Your current soundtrack';
    if(selected.evaluation_kind==='not-rated')$('pick-label').textContent='Your approved sound design';
    $('music-direction').textContent = selected.direction || '';
    $('download-video').href = endpoint(`/preview?download=true&track_id=${selected.id}&v=${revision}`);
    $('download-audio').href = endpoint(`/audio/${selected.id}?download=true`); $('download-record').href = endpoint('/record');
    show('download-audio',selected.evaluation_kind!=='not-rated');show('download-design',!!selected.sound_plan);
    $('download-design').href=endpoint('/sound-design?download=true');
    $('download-design').textContent=selected.evaluation_kind==='not-rated'?'Sound design ↓':'Music + effects ↓';
    renderRecommendationEvidence(selected);
    if (mixSignature !== mix) {
      mixSignature = mix;
      const settings = project.render_settings?.[selected.id] || {level:selected.mix_level || .3,preserve_audio:project.preserve_audio,duck:true};
      $('mix-level').value = Math.round(settings.level*100); $('mix-value').value = `${$('mix-level').value}%`;
      $('mix-original').checked = settings.preserve_audio; $('mix-duck').checked = settings.duck;
    }
  }
  const signature = project.tracks.map(t=>t.id+':'+t.round).join(',') + project.selected + project.recommended;
  if (signature !== trackSignature) {
    trackSignature = signature;
    const otherTracks=project.tracks.filter(t=>t.round!==selected?.round);
    const rounds=[...new Set(otherTracks.map(t=>t.round))].sort((a,b)=>b-a);
    show('generation-history',otherTracks.length>0);
    $('generation-history-label').textContent=`Other generations · ${otherTracks.length} saved version${otherTracks.length===1?'':'s'}`;
    $('alternatives').innerHTML=rounds.map(round=>{
      const tracks=otherTracks.filter(t=>t.round===round);
      return `<details class="generation-round"><summary>Round ${round} · ${tracks.length} version${tracks.length===1?'':'s'}</summary>${tracks.map(t=>`<article class="track"><div class="track-top"><span class="track-name">${esc(t.name)}</span><button class="button secondary" data-pick="${t.id}">Use in my video ↗</button></div><details class="track-brief"><summary>Music brief</summary><p class="track-description">${esc(t.prompt)}</p></details>${t.evaluation_kind==='not-rated'?'<p class="helper">Choose this sound design to hear it with your video.</p>':`<audio controls preload="none" aria-label="Listen to ${esc(t.name)}, round ${round} — music only" src="${endpoint('/audio/'+t.id)}"></audio>`}</article>`).join('')}</details>`;
    }).join('');
    $('compared-with').innerHTML = project.tracks.map(t => `<option value="${t.id}">${esc(t.name)} · Round ${t.round}</option>`).join('');
    $('compared-with').value = project.selected || '';
  }
  show('activity-panel', !!project.events.length);
  $('activity').innerHTML = [...project.events].reverse().map(e => `<div class="activity-entry"><small>${esc(e.stage)}</small>${esc(e.message)}</div>`).join('');
  renderMemory(project.profile);renderWorkspace(); disable();
}
async function poll() {
  if (polling) return; polling = true; let failures = 0;
  try {
    while (running()) {
      await new Promise(r => setTimeout(r, Math.min(10000, 1800 * (failures+1))));
      try { project = await api(endpoint('')); failures=0; connection(); const x=scrollX,y=scrollY;render();window.scrollTo({left:x,top:y,behavior:'instant'}); }
      catch { failures++; connection('Connection interrupted. Reconnecting to your saved job; no new generation will be started.'); }
    }
    if (project?.error) toast(project.error, true);
    else if (project?.status==='cancelled') toast('Stopped. Completed work was saved.');
    else if(project?.status==='complete')toast('Your studio is up to date.');
    await Promise.allSettled([refreshStatus(), refreshHistory()]);
  } finally { polling=false; disable(); }
}
async function perform(fn) {
  if (working || running()) return; working=true; disable();
  try { await fn(); connection(); }
  catch (e) {
    toast(e.message, true);
    // Reconcile an uncertain POST response before offering another paid action.
    if (project) { try { project=await api(endpoint('')); } catch { connection('Could not confirm the last action. Reconnect to recover the saved project.'); } }
  } finally {
    working=false; render();
    if (running()) poll(); else await Promise.allSettled([refreshHistory(),refreshStatus()]);
  }
}
async function openProject(id) {
  if (running() || working) return;
  stopReplyVoice();clearJuryPreview();show('voice-output',false);
  saveDraft();
  if (!id) { localStorage.removeItem('sonvane-project'); location.href='/studio/'; return; }
  const next = await api(`/api/studio/projects/${id}`);
  if (next.profile_id!==profileId) throw Error('This project belongs to another local profile.');
  project=next; file=null; sourceDuration=null;localStorage.setItem('sonvane-project',id);
  trackSignature=''; videoSignature=''; mixSignature=''; previewMode='mix';
  $('preview').pause(); $('preview').removeAttribute('src'); $('preview').load();
  $('brief').value=project.brief; $('context').value=project.context; $('preserve-audio').checked=project.preserve_audio;
  $('feedback').value=''; $('remember-note').checked=false; restoreDraft(); render();
  if (running()) poll();
}
function chooseFile(f, options={}) {
  if (!f || working || running() || voiceStarting || transcribing || voiceRecorder?.active) return;
  if (f.size>250*1024*1024) { toast('Please use a video under 250 MB.',true); return; }
  if (!/\.(mp4|mov)$/i.test(f.name)) { toast('Choose an MP4 or MOV video.',true); return; }
  stopReplyVoice();clearJuryPreview();show('voice-output',false);
  saveDraft();let savedTrim;
  try{savedTrim=JSON.parse(localStorage.getItem('sonvane-draft-new'))?.trim;}catch{}
  analysisStage='reading';analysisError='';
  sourceFile=f;file=f;delete document.body.dataset.videoShape;$('video-format').textContent='';project=null;sourceDuration=null;trimError='Reading video length…';sectionPlayback=false;localStorage.removeItem('sonvane-project');
  cueDraft=null;cueRevision=null;cueProject=null;cueDirty=false;show('sound-plan-panel',false);$('effect-preview').pause();
  trackSignature=''; videoSignature=''; mixSignature=''; previewMode='mix';chatSignature='';$('conversation').replaceChildren();
  $('upload-label').textContent=f.name; $('project-history').value=''; $('video-duration').textContent='';
  for (const id of ['result-panel','feedback-panel','alternatives-panel','progress-panel','activity-panel','preview-switch']) show(id,false);
  show('trim-panel',true);$('video-settings').open=options.auto===false;$('trim-panel').open=options.auto===false;show('clip-origin',false);$('trim-source').textContent='Reading your video…';$('trim-status').textContent=trimError;
  $('trim-start').value='0';$('trim-end').value='30';
  if (fileURL) URL.revokeObjectURL(fileURL); fileURL=URL.createObjectURL(f);
  $('preview').onloadedmetadata=()=>{
    if(file!==f)return;
    const duration=$('preview').duration;
    sourceDuration=Number.isFinite(duration)?Math.floor((duration+.000001)*100)/100:null;
    $('trim-source').textContent=sourceDuration?`${timeLabel(sourceDuration)} original · ${(f.size/1024/1024).toFixed(1)} MB`:'Video length unavailable.';
    $('trim-end').value=String(Math.min(30,sourceDuration || 30));
    if(savedTrim?.name===f.name && savedTrim.size===f.size && savedTrim.modified===f.lastModified){$('trim-start').value=savedTrim.start;$('trim-end').value=savedTrim.end;}
    for(const id of ['trim-start-range','trim-end-range','trim-start','trim-end'])$(id).max=String(sourceDuration || 0);
    if(options.range){$('trim-start').value=options.range.start;$('trim-end').value=options.range.end;}
    updateTrim(false);saveDraft();
    if(options.auto===false){analysisStage=null;renderWorkspace();}else autoAnalyze(f);
  };
  $('preview').onerror=()=>{if(file===f){sourceDuration=null;trimError='This browser could not open the video. Try an MP4 with H.264 video.';analysisError=trimError;analysisStage=null;renderWorkspace();$('trim-status').textContent=trimError;$('trim-status').className='error';disable();}};
  $('preview').pause(); $('preview').src=fileURL; show('preview',true); show('empty-preview',false);
  $('preview-label').textContent='Original video';renderWorkspace();saveDraft();disable();
}
function timeLabel(seconds){const tenths=Math.round(seconds*10),m=Math.floor(tenths/600),s=((tenths%600)/10).toFixed(1).padStart(4,'0');return `${m}:${s}`;}
function updateTrim(seek=true){
  const start=$('trim-start').valueAsNumber,end=$('trim-end').valueAsNumber,length=Math.round((end-start)*1e6)/1e6;
  trimError=sourceDuration>600?'Choose a video no longer than 10 minutes.':!sourceDuration?'Video length is unavailable.':sourceDuration<3?'Choose a video at least 3 seconds long.':sourceDuration>600?'Choose a source video no longer than 10 minutes.':
    !Number.isFinite(start)||!Number.isFinite(end)||start<0||end>sourceDuration||end<=start?'Choose start and end times inside your video.':length<3||length>30?'Your section must be between 3 and 30 seconds.':'';
  $('trim-status').textContent=trimError || `${timeLabel(start)} → ${timeLabel(end)} · ${length.toFixed(1)} seconds selected`;
  $('trim-status').className=trimError?'error':'';
  $('trim-start-range').value=String(start);$('trim-end-range').value=String(end);
  sectionPlayback=false;
  if(seek && file){$('preview').pause();if(!trimError)$('preview').currentTime=start;}
  $('video-duration').textContent=sourceDuration?`${timeLabel(sourceDuration)} original`:'';
  renderAnalysisScope();
  disable();
}
for(const side of ['start','end']){
  $(`trim-${side}`).addEventListener('input',()=>{updateTrim();saveDraft();});
  $(`trim-${side}-range`).addEventListener('input',()=>{$(`trim-${side}`).value=$(`trim-${side}-range`).value;updateTrim();saveDraft();});
}
$('preview-section').addEventListener('click',()=>{
  if(trimError || !file)return;sectionPlayback=true;$('preview').currentTime=Number($('trim-start').value);
  if(window.innerWidth<=900)$('preview').scrollIntoView({behavior:'smooth',block:'center'});
  $('preview').play().catch(()=>toast('Press play in the video to preview your section.'));
});
$('preview').addEventListener('timeupdate',()=>{if(file && sectionPlayback && $('preview').currentTime>=Number($('trim-end').value)){$('preview').pause();sectionPlayback=false;}});
$('video-file').addEventListener('change',e=>{const auto=!nextFileManual;nextFileManual=false;chooseFile(e.target.files[0],{auto});});
$('dropzone').addEventListener('dragover',e=>{e.preventDefault();$('dropzone').classList.add('dragging');});
$('dropzone').addEventListener('dragleave',()=> $('dropzone').classList.remove('dragging'));
$('dropzone').addEventListener('drop',e=>{e.preventDefault();$('dropzone').classList.remove('dragging');chooseFile(e.dataTransfer.files[0]);});
async function saveDirection() {
  project=await api(endpoint('/direction'),{...json({brief:$('brief').value,context:$('context').value,preserve_audio:$('preserve-audio').checked}),method:'PUT'});
}
async function ensureProject(){
  if (file) {
    if(!sourceDuration || trimError)throw Error(trimError || 'Wait for the video length to load.');
    const form=new FormData();form.append('file',file);form.append('profile_id',profileId);form.append('context',$('context').value);form.append('brief',$('brief').value);form.append('preserve_audio',String($('preserve-audio').checked));
    form.append('trim_start',$('trim-start').value);form.append('trim_end',$('trim-end').value);
    if(analysisStage){analysisStage='uploading';renderWorkspace();}
    project=await api('/api/studio/projects',{method:'POST',body:form});file=null;
    localStorage.setItem('sonvane-project',project.id);localStorage.removeItem('sonvane-draft-new');saveDraft();render();
  }
}
$('create').addEventListener('click',()=>perform(async()=>{
  await ensureProject();
  await saveDirection();project=await api(endpoint('/generate'),json({}));
}));
$('edit-region').addEventListener('change',disable);
$('revise').addEventListener('click',()=>perform(async()=>{
  if(project.sound_plan && !$('edit-region').checked){setWorkspaceTab('plan');$('sound-plan-panel').scrollIntoView({behavior:'smooth',block:'start'});toast('Edit the music descriptions or timing above, then approve the revised plan.');return;}
  if (!$('feedback').value.trim()) throw Error('Describe what you would like to change.');
  await saveDirection();project=await api(endpoint('/generate'),json({feedback:$('feedback').value,remember:$('remember-note').checked,...($('edit-region').checked?{edit_start:Number($('region-start').value),edit_end:Number($('region-end').value)}:{})}));
  $('feedback').value='';$('remember-note').checked=false;saveDraft();
}));
$('stop-job').addEventListener('click',async()=>{
  if (!running()) return;
  $('stop-job').disabled=true;
  try { project=await api(endpoint('/cancel'),json({}));render(); }
  catch (e) { toast(e.message,true);disable(); }
});
$('resume-job').addEventListener('click',()=>perform(async()=>{project=await api(endpoint('/resume'),json({}));}));
$('mix-level').addEventListener('input',()=>{$('mix-value').value=`${$('mix-level').value}%`;});
$('apply-mix').addEventListener('click',()=>perform(async()=>{
  project=await api(endpoint('/mix'),json({level:Number($('mix-level').value)/100,preserve_audio:$('mix-original').checked,duck:$('mix-duck').checked}));
  $('preserve-audio').checked=project.preserve_audio;saveDraft();previewMode='mix';toast('Mix updated. No music was regenerated.');
}));
document.addEventListener('click',e=>{
  const pick=e.target.closest('[data-pick]'),forget=e.target.closest('[data-forget]');
  if (pick) perform(async()=>{
    $('jury-audio').pause();
    const remember=$('remember-choice').checked;
    project=await api(endpoint('/select'),json({track_id:pick.dataset.pick,remember,compared_with:remember?$('compared-with').value:null}));
    $('remember-choice').checked=false;previewMode='mix';toast(remember?'Choice saved. Your personal ranking has been updated.':'Your selected soundtrack is ready.');
  });
  if (forget) perform(async()=>{
    await api(`/api/studio/profiles/${profileId}/${forget.dataset.forget}`,{method:'DELETE'});
    if(project)project=await api(endpoint(''));await refreshMemory();toast('Preference removed. Rankings updated; your selected audio stays the same.');
  });
});
$('clear-memory').addEventListener('click',()=>perform(async()=>{
  await api(`/api/studio/profiles/${profileId}`,{method:'DELETE'});if(project)project=await api(endpoint(''));await refreshMemory();toast('All remembered preferences cleared.');
}));
$('show-original').addEventListener('click',()=>{previewMode='original';render();});
$('show-mix').addEventListener('click',()=>{previewMode='mix';render();});
$('new-project').addEventListener('click',()=>openProject('').catch(e=>toast(e.message,true)));
$('project-history').addEventListener('change',e=>openProject(e.target.value).catch(err=>toast(err.message,true)));
for (const id of ['brief','context','preserve-audio','feedback','remember-note','chat-input']) $(id).addEventListener('input',saveDraft);
window.addEventListener('pagehide',saveDraft);
document.addEventListener('play',e=>{if(!['AUDIO','VIDEO'].includes(e.target.tagName))return;if(e.target!==$('reply-audio'))stopReplyVoice();if(e.target!==$('jury-audio'))juryPlayToken++;document.querySelectorAll('audio,video').forEach(el=>{if(el!==e.target)el.pause();});},true);
async function reconnect() {
  try {
    await refreshStatus();
    const saved=localStorage.getItem('sonvane-project');
    if(!project && saved){project=await api(`/api/studio/projects/${saved}`);if(project.profile_id!==profileId)project=null;
      if(project){$('brief').value=project.brief;$('context').value=project.context;$('preserve-audio').checked=project.preserve_audio;restoreDraft();}}
    if(project){project=await api(endpoint(''));render();if(running())poll();}
    await refreshMemory();await refreshHistory();connection();
  }
  catch { connection('Cannot reach the studio. Check the server or SSH connection, then reconnect.'); }
}
$('reconnect').addEventListener('click',reconnect);window.addEventListener('online',reconnect);
async function boot() {
  try {
    await refreshStatus();await refreshMemory();
    const id=localStorage.getItem('sonvane-project');
    if(id){project=await api(`/api/studio/projects/${id}`).catch(()=>null);if(project?.profile_id!==profileId)project=null;}
    if(project){$('brief').value=project.brief;$('context').value=project.context;$('preserve-audio').checked=project.preserve_audio;render();if(running())poll();}
    restoreDraft();
    const brief=new URLSearchParams(location.search).get('brief');
    if(brief){$('brief').value=brief.slice(0,2000);saveDraft();history.replaceState(null,'',location.pathname);}
    await refreshHistory();disable();
  } catch { connection('Cannot reach the studio. Check the server or SSH connection, then reconnect.'); }
}
boot();

function renderConversation(){
  const turns=project?.conversation || [];
  const signature=JSON.stringify(turns);
  if(signature===chatSignature)return;chatSignature=signature;
  const conversation=$('conversation'), previousTop=conversation.scrollTop;
  const followLatest=conversation.scrollHeight-conversation.clientHeight-previousTop<40;
  $('conversation').innerHTML=turns.map(t=>`<article class="chat-message ${esc(t.role)}" data-turn="${esc(t.id)}"><small>${t.role==='user'?'You':t.role==='assistant'?'Muse':'Studio'}</small><div class="${t.role==='assistant'?'chat-markdown':'chat-plain'}">${t.role==='assistant'?chatMarkdown.render(t.text):esc(t.text)}</div>${t.result?`<p class="chat-result ${t.action_status==='error'?'error':''}">${esc(t.action_status==='running'?'In progress':t.action_status==='complete'?'Completed':t.action_status)} · ${esc(t.result)}</p>`:''}${t.role==='assistant'?`<button type="button" class="text-button" data-speak="${t.id}">Read aloud</button><span class="speech-hint">Or click a word to listen from there.</span>`:''}</article>`).join('');
  $('conversation').querySelectorAll('.chat-markdown').forEach(speechWords);
  conversation.scrollTop=followLatest?conversation.scrollHeight:previousTop;
}
$('send-chat').addEventListener('click',()=>perform(async()=>{
  const message=$('chat-input').value.trim();if(!message)throw Error('Write a message or record your voice first.');
  stopReplyVoice();await ensureProject();await saveDirection();
  project=await api(endpoint('/chat'),json({message,request_id:UUID(),allow_memory:$('chat-memory').checked,listen:$('chat-listen').checked && !!(project?.video?.has_audio || project?.tracks?.some(t=>t.id===project.selected))}));
  $('preserve-audio').checked=project.preserve_audio;
  $('chat-input').value='';$('chat-memory').checked=false;saveDraft();
}));
$('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(!$('send-chat').disabled)$('send-chat').click();}});
document.addEventListener('click',e=>{
  const example=e.target.closest('[data-message]'),speak=e.target.closest('[data-speak]');
  if(example){$('chat-input').value=example.dataset.message;saveDraft();disable();$('chat-input').focus();}
  if(speak)readReply(speak);
});
function finishVoiceUI(){clearInterval(voiceTick);$('record-voice').classList.remove('recording');$('record-voice').textContent='Record voice';voiceStarting=false;disable();}
$('record-voice').addEventListener('click',async()=>{
  if(voiceRecorder?.active){voiceRecorder.stop();transcribing=true;$('voice-status').textContent='Transcribing with Muse…';finishVoiceUI();return;}
  stopReplyVoice();document.querySelectorAll('audio,video').forEach(el=>el.pause());voiceStarting=true;disable();
  voiceRecorder=new StudioRecorder(async blob=>{
    transcribing=true;finishVoiceUI();$('voice-status').textContent='Transcribing with Muse…';
    try{const form=new FormData();form.append('file',blob,'voice.wav');const result=await api('/api/studio/voice/transcribe',{method:'POST',body:form});
      if(!result.speech_detected||!result.text.trim())throw Error('No clear speech was detected. Try again or type your message.');
      $('chat-input').value=result.text;saveDraft();$('voice-status').textContent='Review your words, then send.';
    }catch(error){$('voice-status').textContent='';toast(error.message,true);}
    finally{transcribing=false;finishVoiceUI();await refreshStatus().catch(()=>{});}
  },error=>{transcribing=false;finishVoiceUI();$('voice-status').textContent='';toast(error.message,true);});
  try{await voiceRecorder.start();voiceStarting=false;$('record-voice').classList.add('recording');$('record-voice').textContent='Stop recording';
    voiceTick=setInterval(()=>{if(voiceRecorder?.active)$('voice-status').textContent=`Recording ${Math.floor((Date.now()-voiceRecorder.started)/1000)} / 30 sec`;},250);disable();
  }catch(error){voiceRecorder?.cancel();finishVoiceUI();toast(error.name==='NotAllowedError'?'Microphone access was denied. Allow it in the browser or type your message.':error.message,true);}
});
window.addEventListener('pagehide',()=>{voiceRecorder?.cancel();stopReplyVoice();clearInterval(voiceTick);});

function stopReplyVoice(){voicePlayToken++;StudioSpeech.stop();$('reply-audio').pause();cancelAnimationFrame(speechFrame);activeSpeech=null;clearSpeechHighlight();}
async function readReply(button,wordIndex=0){
  stopReplyVoice();const token=voicePlayToken,turnId=button.dataset.speak,url=endpoint(`/speech/${turnId}`);
  button.disabled=true;button.textContent='Preparing voice…';
  try{
    if(!speechCache.has(url))speechCache.set(url,api(url,json({})).catch(error=>{speechCache.delete(url);throw error;}));
    const result=await speechCache.get(url);if(token!==voicePlayToken)return;
    const audio=$('reply-audio');
    if(audio.getAttribute('src')!==result.url){
      audio.src=result.url;
      await new Promise((resolve,reject)=>{
        const done=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(Error('Reply audio could not load.'));};
        const timer=setTimeout(failed,15000);
        const cleanup=()=>{clearTimeout(timer);audio.removeEventListener('loadedmetadata',done);audio.removeEventListener('error',failed);};
        audio.addEventListener('loadedmetadata',done);audio.addEventListener('error',failed);audio.load();
      });
    }
    if(token!==voicePlayToken)return;
    activeSpeech={turnId,words:result.words||[],lastIndex:null};audio.speechData=activeSpeech;
    audio.currentTime=result.words?.[wordIndex]?.start||0;show('voice-output',true);
    await audio.play().catch(()=>toast('Reply audio is ready. Press play to listen.'));highlightSpeech();
  }catch(error){if(token===voicePlayToken)toast(error.message,true);}finally{button.disabled=false;button.textContent='Read aloud';}
}
$('reply-audio').addEventListener('play',()=>{if(!activeSpeech && $('reply-audio').speechData){activeSpeech=$('reply-audio').speechData;activeSpeech.lastIndex=null;}});
for(const event of ['play','pause','seeked','timeupdate'])$('reply-audio').addEventListener(event,highlightSpeech);
$('reply-audio').addEventListener('ended',()=>{cancelAnimationFrame(speechFrame);clearSpeechHighlight();});
$('conversation').addEventListener('click',event=>{
  const word=event.target.closest('.speech-word');if(!word || word.closest('a') || window.getSelection()?.toString())return;
  readReply(word.closest('.chat-message').querySelector('[data-speak]'),Number(word.dataset.word));
});
$('conversation').addEventListener('keydown',event=>{
  const word=event.target.closest('.speech-word');if(!word)return;
  if(['Enter',' '].includes(event.key)){event.preventDefault();word.click();}
  if(['ArrowLeft','ArrowRight'].includes(event.key)){
    const next=Number(word.dataset.word)+(event.key==='ArrowRight'?1:-1),target=word.closest('.chat-message').querySelector(`[data-word="${next}"]`);
    if(target){event.preventDefault();word.tabIndex=-1;target.tabIndex=0;target.focus();}
  }
});
$('stop-speaking').addEventListener('click',stopReplyVoice);

function cueValidation(){
  if(!cueDraft||!project)return '';
  const music=[];let effects=0;
  for(const c of cueDraft.cues){
    const length=Math.round((c.end-c.start)*1e6)/1e6;
    if(!Number.isFinite(c.start)||!Number.isFinite(c.end)||c.start<0||c.end>project.video.duration||length<=0)return 'Keep every cue inside this video, with its end after its start.';
    if(c.kind==='music'&&length<3)return 'Each music section needs at least 3 seconds.';
    if(c.kind==='sfx'&&(length<.1||length>5))return 'Each effect needs between 0.1 and 5 seconds.';
    if(!c.description.trim())return 'Give each cue a description.';
    if(!Number.isFinite(c.gain)||c.gain<0||c.gain>1)return 'Cue levels must be between 0 and 100%.';
    if(!Number.isFinite(c.bpm)||c.bpm<45||c.bpm>180)return 'Use a tempo between 45 and 180 BPM.';
    if(c.enabled){if(c.kind==='music')music.push(c);else effects++;}
  }
  if(music.length>3||effects>5)return 'Use at most 3 enabled music sections and 5 effects.';
  music.sort((a,b)=>a.start-b.start);
  if(music.some((c,i)=>i&&music[i-1].end>c.start+1e-6))return 'Music sections overlap. Adjust their start and end times.';
  return '';
}
function drawCueTimeline(){
  if(!cueDraft||!project)return;
  const lane=kind=>cueDraft.cues.filter(c=>c.enabled&&c.kind===kind).map(c=>`<span data-placement="${c.id}" title="${esc(c.description)}">${kind==='music'?'Music':esc(c.effect)}</span>`).join('');
  $('cue-timeline').innerHTML=`<div class="cue-time-axis"><span>Clip start · 0:00</span><span>${timeLabel(project.video.duration)}</span></div><div class="cue-lane" aria-label="Music placements">${lane('music')}</div><div class="cue-lane effects" aria-label="Effect placements">${lane('sfx')}</div>`;
  $('cue-timeline').querySelectorAll('[data-placement]').forEach(e=>{const c=cueDraft.cues.find(c=>c.id===e.dataset.placement);e.style.left=`${Math.max(0,100*c.start/project.video.duration)}%`;e.style.width=`${Math.max(0,100*(c.end-c.start)/project.video.duration)}%`;});
  $('sound-plan-error').textContent=cueValidation()||project.cue_error||'';
  const n=cueDraft.cues.filter(c=>c.enabled&&c.kind==='music').length,fx=cueDraft.cues.filter(c=>c.enabled&&c.kind==='sfx').length;
  $('plan-choice-summary').innerHTML=[
    ['Video section',`${project.video.duration.toFixed(1)} seconds`],
    ['Music',n?`${n} section${n===1?'':'s'} · 3 versions`:'No added music'],
    ['Sound effects',fx?`${fx} accent${fx===1?'':'s'}`:'None'],
    ['Original audio',$('preserve-audio').checked?'Keep':'Mute']
  ].map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('');
  const alreadyGenerated=!cueDirty && project.tracks.some(t=>t.sound_plan?.revision===cueRevision);
  $('cue-generation-count').textContent=n?(alreadyGenerated?'Creates another round of three. Your existing versions are kept.':'We’ll make three versions and suggest one. You can choose another.'):`${fx} sound effect${fx===1?'':'s'} · No added music`;
  $('approve-sound-plan').textContent=n?(alreadyGenerated?'Make 3 more versions':'Make my music'):'Add these sounds';
  $('cue-recommendations').innerHTML=cueDraft.cues.filter(c=>c.enabled).sort((a,b)=>a.start-b.start).map(c=>`<article class="cue-recommendation"><span>${timeLabel(c.start)}–${timeLabel(c.end)}</span><div><strong>${c.kind==='music'?'Background music':esc(c.effect)+' effect'}</strong><p>${esc(shortExcerpt(c.description,150))}</p></div></article>`).join('') || '<p>Keep this section without added music or effects.</p>';
  const selected=project.tracks.find(t=>t.id===project.selected);
  $('sound-plan-preview-note').textContent=selected && (cueDirty || selected.sound_plan?.revision!==cueRevision)?'Your current video still plays the previous version. Approve this plan to create a new version.':'';
  $('sound-plan-state').textContent=cueDirty?'Unsaved changes':project.sound_plan?.status==='approved'?'Approved version':'Ready for your choice';
  renderWorkspace();
}
function drawCues(){
  if(!cueDraft)return;
  $('sound-plan-summary').innerHTML=recommendationMarkup(shortExcerpt(cueDraft.summary,260),cueDraft.highlights);
  $('scene-description').textContent=shortExcerpt(cueDraft.scene_description,200);show('scene-observation',!!cueDraft.scene_description);
  renderOriginalPoints('sound-plan-summary-full',cueDraft.summary);
  renderOriginalPoints('scene-description-full',cueDraft.scene_description || 'No separate observation was saved for this plan.');
  show('plan-explanation',true);
  const origin=project.video.selection;
  show('sound-plan-origin',!!origin && (origin.start>0 || origin.end<origin.source_duration-.05));
  $('sound-plan-origin').textContent=origin?`Timeline 0–${project.video.duration.toFixed(1)}s corresponds to ${timeLabel(origin.start)}–${timeLabel(origin.end)} in your original video.`:'Times are relative to the selected clip.';
  $('cue-list').innerHTML=cueDraft.cues.map((c,i)=>`<article class="cue-card ${c.enabled?'':'disabled-cue'}" data-cue="${c.id}"><div class="cue-card-head"><label class="check"><input type="checkbox" data-field="enabled" ${c.enabled?'checked':''} aria-label="Include cue ${i+1}"></label><strong>${c.kind==='music'?'Music section':'Sound effect'} ${i+1}</strong><button type="button" class="text-button" data-remove-cue="${c.id}">Remove</button></div><p class="cue-reason">${esc(c.reason||'Added by you. Adjust the timing and sound.')}</p><div class="cue-fields"><label>Start · seconds<input type="number" data-field="start" min="0" max="${project.video.duration}" step="0.1" value="${c.start}"></label><label>End · seconds<input type="number" data-field="end" min="0.1" max="${project.video.duration}" step="0.1" value="${c.end}"></label><label>${c.kind==='music'?'Music cue level':'Effect level'} · %<input type="number" data-field="gain" min="0" max="100" step="1" value="${Math.round(c.gain*100)}"></label></div><label>${c.kind==='music'?'Music generation prompt':'Effect intent (the selected type controls the sound)'}<textarea data-field="description" maxlength="500" rows="2">${esc(c.description)}</textarea></label>${c.kind==='music'?`<div class="cue-fields"><label>Tempo · BPM<input data-field="bpm" type="number" min="45" max="180" value="${c.bpm}"></label></div>`:`<div class="cue-effect-row"><label>Synthesized effect<select data-field="effect">${['whoosh','chime','impact','click','riser'].map(e=>`<option value="${e}" ${c.effect===e?'selected':''}>${e[0].toUpperCase()+e.slice(1)}</option>`).join('')}</select></label><button type="button" class="button secondary" data-preview-effect="${c.id}">Hear effect ▷</button></div>`}<button type="button" class="cue-preview-time" data-preview-cue="${c.id}">Watch this moment ▷</button></article>`).join('')||'<p class="helper">No added sound is proposed. Keep the original, or add a music section or effect.</p>';
  drawCueTimeline();disable();
}
function renderSoundPlan(){
  const plan=project?.sound_plan;show('sound-plan-panel',!!plan);
  if(!plan){cueDraft=null;cueRevision=null;cueProject=project?.id;cueDirty=false;return;}
  if(cueProject!==project.id||cueRevision!==plan.revision){cueDraft=JSON.parse(JSON.stringify({scene_description:plan.scene_description||'',summary:plan.summary,highlights:plan.highlights||[],scene_points:plan.scene_points||[],sound_points:plan.sound_points||[],cues:plan.cues}));cueRevision=plan.revision;cueProject=project.id;cueDirty=false;drawCues();}
  else drawCueTimeline();
}
$('cue-list').addEventListener('input',event=>{
  const field=event.target.dataset.field,card=event.target.closest('[data-cue]');if(!field||!card)return;
  const c=cueDraft.cues.find(c=>c.id===card.dataset.cue);
  c[field]=field==='enabled'?event.target.checked:['start','end','bpm','gain'].includes(field)?event.target.valueAsNumber/(field==='gain'?100:1):event.target.value;
  cueDirty=true;card.classList.toggle('disabled-cue',!c.enabled);drawCueTimeline();saveDraft();disable();
});
$('cue-list').addEventListener('click',async event=>{
  const remove=event.target.closest('[data-remove-cue]'),watch=event.target.closest('[data-preview-cue]'),hear=event.target.closest('[data-preview-effect]');
  if(remove){cueDraft.cues=cueDraft.cues.filter(c=>c.id!==remove.dataset.removeCue);cueDirty=true;drawCues();saveDraft();}
  if(watch){const c=cueDraft.cues.find(c=>c.id===watch.dataset.previewCue);if(cueValidation())return toast(cueValidation(),true);previewMode='original';render();const v=$('preview');
    if(v.readyState<1)await new Promise(resolve=>v.addEventListener('loadedmetadata',resolve,{once:true}));
    v.currentTime=c.start;cuePlaybackEnd=c.end;v.play().catch(()=>{});revealIfOutside(v);}
  if(hear){
    const c=cueDraft.cues.find(c=>c.id===hear.dataset.previewEffect);if(cueValidation())return toast(cueValidation(),true);
    hear.disabled=true;
    try{const r=await fetch('/api/studio/sound-effects/preview',json({effect:c.effect,duration:c.end-c.start,gain:c.gain}));if(!r.ok)throw Error('Could not preview the effect. Check its duration.');
      if(effectURL)URL.revokeObjectURL(effectURL);effectURL=URL.createObjectURL(await r.blob());$('effect-preview').src=effectURL;show('effect-preview',true);await $('effect-preview').play();
    }catch(e){toast(e.message,true);}finally{hear.disabled=false;}
  }
});
function addCue(kind){
  if(!cueDraft||cueDraft.cues.length>=8)return toast('Use at most eight cues. Remove an unused cue first.',true);
  let start=0;const minimum=kind==='music'?3:.5;
  if(kind==='music')for(const c of cueDraft.cues.filter(c=>c.enabled&&c.kind==='music').sort((a,b)=>a.start-b.start)){if(c.start-start>=3)break;start=c.end;}
  if(start+minimum>project.video.duration)return toast('No three-second gap remains. Adjust or remove a music section first.',true);
  cueDraft.cues.push({id:UUID(),kind,start,end:Math.min(project.video.duration,start+minimum),description:kind==='music'?'Warm instrumental piano, gentle motion, no vocals.':'A soft transition accent.',reason:'Added by you.',effect:kind==='music'?'none':'whoosh',bpm:90,gain:kind==='music'?1:.2,enabled:true});cueDirty=true;drawCues();saveDraft();
}
$('add-music-cue').addEventListener('click',()=>addCue('music'));
$('add-sfx-cue').addEventListener('click',()=>addCue('sfx'));
async function persistCueDraft(){
  if(cueValidation())throw Error(cueValidation());
  project=await api(endpoint('/sound-plan'),{...json({...cueDraft,revision:cueRevision}),method:'PUT'});
  cueDirty=false;renderSoundPlan();saveDraft();
}
$('save-sound-plan').addEventListener('click',()=>perform(async()=>{await persistCueDraft();toast('Plan saved. No audio has been generated.');}));
$('approve-sound-plan').addEventListener('click',()=>perform(async()=>{
  await persistCueDraft();project=await api(endpoint('/generate'),json({cue_revision:project.sound_plan.revision}));
}));
async function requestSoundPlan(){
  analysisError='';analysisStage=file?'uploading':'analyzing';renderWorkspace();
  try{
    if(!service)await refreshStatus();
    const b=service?.budget;
    if(!service?.meta_ready)throw Error('Muse needs an API key on this server before it can analyze the video.');
    if(b && (b.reserved_usd+.25>b.limit_usd || b.requests>=b.max_requests))throw Error('The configured Muse usage limit has been reached.');
    if(file && trimError)throw Error(trimError);
    stopReplyVoice();await ensureProject();await saveDirection();
    analysisStage='analyzing';renderWorkspace();
    project=await api(endpoint('/sound-plan'),json({request_id:UUID()}));renderSoundPlan();setWorkspaceTab('plan');saveDraft();
  }catch(error){analysisError=error.message;throw error;}
  finally{analysisStage=null;renderWorkspace();}
}
function autoAnalyze(selectedFile){
  if(file!==selectedFile || autoSubmitted.has(selectedFile))return;
  autoSubmitted.add(selectedFile);
  if(trimError){analysisStage=null;analysisError=trimError;$('video-settings').open=true;$('trim-panel').open=true;renderWorkspace();return;}
  perform(requestSoundPlan);
}
$('choose-video').addEventListener('click',()=>$('video-file').click());

$('plan-sound').addEventListener('click',()=>{
  if(project?.sound_plan){setWorkspaceTab('plan');$('workspace-tabs').scrollIntoView({behavior:'smooth',block:'start'});}
  else perform(requestSoundPlan);
});
$('new-sound-plan').addEventListener('click',()=>perform(requestSoundPlan));
$('preview').addEventListener('timeupdate',()=>{if(cuePlaybackEnd!==null&&$('preview').currentTime>=cuePlaybackEnd){$('preview').pause();cuePlaybackEnd=null;}});


function renderWorkspace(){
  show('mix-tools',!!(project?.selected&&project.renders?.[project.selected]));
  document.body.classList.toggle('has-project',!!project);
  document.body.classList.toggle('has-video',!!(project||file));
  show('workspace-tabs',false);show('video-tools',!!(project||file));
  const hasPlan=!!project?.sound_plan;
  const hasResult=!!(project?.selected&&project.renders[project.selected]);
  if(workspaceProject!==project?.id){
    workspaceTab=hasResult?'results':hasPlan?'plan':'muse';workspaceProject=project?.id;
    workspacePlan=project?.sound_plan?.revision;workspaceSelected=project?.selected;
  }else{
    if(project?.selected && project.selected!==workspaceSelected && hasResult)workspaceTab='results';
    else if(project?.sound_plan?.revision && project.sound_plan.revision!==workspacePlan)workspaceTab='plan';
    workspaceSelected=project?.selected;workspacePlan=project?.sound_plan?.revision;
  }
  if(!workspaceTab || workspaceTab==='plan'&&!hasPlan || workspaceTab==='results'&&!hasResult)workspaceTab=hasPlan?'plan':hasResult?'results':'muse';
  const creationStep=analysisStage||project?.cue_pending?1:generating()||['error','cancelled'].includes(project?.status)?3:hasResult&&workspaceTab!=='plan'?4:hasPlan?2:1;
  document.querySelectorAll('[data-creation-step]').forEach(e=>{const n=Number(e.dataset.creationStep);e.classList.toggle('done',n<creationStep);if(n===creationStep)e.setAttribute('aria-current','step');else e.removeAttribute('aria-current');});
  for(const name of ['plan','results','muse']){
    const enabled=name==='muse'?!!(project||file):!!project && (name==='plan'&&hasPlan||name==='results'&&hasResult);
    const active=enabled && name===workspaceTab;
    $('tab-'+name).disabled=!enabled;$('tab-'+name).setAttribute('aria-selected',String(active));$('tab-'+name).tabIndex=active?0:-1;
    show('workspace-'+name,name==='muse'?!!(project||file):name==='plan'?!generating()&&hasPlan&&(!hasResult||workspaceTab==='plan'):!generating()&&hasResult&&workspaceTab!=='plan');
  }
  // Conversation is part of the current choice, before secondary editing tools.
  const conversationHost=hasResult && workspaceTab!=='plan' ? $('result-panel') : hasPlan ? $('sound-plan-panel') : $('workspace-results');
  const conversationArea=$('muse-disclosure');
  if(conversationHost.nextElementSibling!==conversationArea)conversationHost.insertAdjacentElement('afterend',conversationArea);
  show('muse-disclosure',!!project && !generating() && !analysisStage && !project.cue_pending);
  const discussingResult=hasResult && workspaceTab!=='plan';
  const chatMode=discussingResult?'result':hasPlan?'plan':'initial';
  const selectedTrack=(project?.tracks||[]).find(t=>t.id===project.selected);
  $('chat-stage').textContent=discussingResult?'After creation · Listen & adjust':selectedTrack?'Reviewing a new plan':'Before music creation';
  $('conversation-title').textContent=discussingResult?'Refine with Muse':hasPlan?'Plan with Muse':'Discuss your video';
  $('chat-guidance').textContent=discussingResult?'Listen to your video, then tell Muse what works or what you want to change.':hasPlan?(selectedTrack?'Discuss the proposed direction. Any shared audio is from your previously created track, not this new plan.':'No music has been created yet. Ask about the proposed mood or instruments, then choose Make my music when you’re ready.'):'Talk about the mood you want for your video. There is no generated music to listen to yet.';
  $('chat-input').placeholder=discussingResult?'The music feels too loud. Lower it and keep the same track.':hasPlan?'Why are you suggesting this musical direction?':'What kind of music would suit this video?';
  const canShareAudio=!!(selectedTrack || project?.video?.has_audio);
  show('chat-listen-option',canShareAudio);
  $('chat-listen-label').textContent=selectedTrack?`${discussingResult?'Share selected track':'Share previously created track'} · Up to 10 seconds`:'Share original video audio · Up to 10 seconds';
  if($('chat-examples').dataset.mode!==chatMode){
    const examples=discussingResult?[
      ['Why this track?','Why was this track recommended?'],
      ['Lower the music','Lower the music level to 15 percent. Keep the same track.']
    ]:[
      ['Why this direction?','Why are you suggesting this musical direction for my video?'],
      ['Explore another mood','Suggest a different musical mood for this video and explain the tradeoff.']
    ];
    $('chat-examples').innerHTML=examples.map(([label,message])=>`<button type="button" data-message="${esc(message)}">${esc(label)}</button>`).join('');
    $('chat-examples').dataset.mode=chatMode;
  }
  show('analysis-panel',!!(project||file) && (!hasPlan && !hasResult && !generating() || !!analysisStage || !!project?.cue_pending));
  const pending=!!analysisStage || !!project?.cue_pending;
  $('analysis-speaker').textContent=analysisStage==='reading'||analysisStage==='uploading'?'Sonvane · Preparing your video':'Muse Spark · Video analysis';
  $('analysis-title').textContent=analysisError||project?.cue_error?'Analysis needs attention':analysisStage==='uploading'?'Preparing your video…':pending?'Understanding your video…':'Ready to analyze your video';
  $('analysis-message').textContent=analysisError||project?.cue_error||(analysisStage==='uploading'?'Uploading and preparing the selected section.':pending?'I’m looking at the selected scene to suggest music and effects that fit.':'Analyze the selected section to get a music recommendation.');
  show('plan-sound',!pending && !hasPlan);
  show('change-section',!!project);renderAnalysisScope();
  $('workspace-guidance').textContent=project?.cue_pending?'Muse is preparing your sound plan…':generating()?'Your sound is being created. Progress is saved as it completes.':project?.status==='error'?'This run needs attention. Your saved work is still available.':project?.status==='cancelled'?'Generation stopped. Resume saved work when you are ready.':hasPlan&&(workspaceTab==='plan'||cueDirty||project.sound_plan.status!=='approved')?'Like this idea? Choose Make my music.':hasResult?'Play your video. Save it when you’re happy.':project||file?'We’re finding a sound for your video.':'Add a video. We’ll help you give it music.';
}
function setWorkspaceTab(name){
  if(!(project||file) || name==='plan'&&!project?.sound_plan || name==='results'&&!(project?.selected&&project.renders[project.selected]))return;
  workspaceTab=name;workspaceProject=project?.id;workspacePlan=project?.sound_plan?.revision;workspaceSelected=project?.selected;
  renderWorkspace();saveDraft();
}
$('workspace-tabs').addEventListener('click',event=>{const tab=event.target.closest('[data-workspace-tab]');if(tab)setWorkspaceTab(tab.dataset.workspaceTab);});
$('workspace-tabs').addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const tabs=Array.from($('workspace-tabs').querySelectorAll('button')).filter(b=>!b.disabled);
  if(!tabs.length)return;
  const i=tabs.indexOf(document.activeElement);
  const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  event.preventDefault();setWorkspaceTab(tabs[next].dataset.workspaceTab);tabs[next].focus();
});

function renderAnalysisScope(){
  const range=project?.video?.selection;
  renderSourceOverview(range || (sourceDuration?{start:Number($('trim-start').value),end:Number($('trim-end').value),source_duration:sourceDuration}:null));
  if(range){const whole=range.start===0 && range.end>=range.source_duration-.05;$('analysis-scope').textContent=whole?`Your whole ${project.video.duration.toFixed(1)}-second video. Music and export keep this length.`:`Working section: ${timeLabel(range.start)}–${timeLabel(range.end)} of ${timeLabel(range.source_duration)}. Music and export cover this section only.`;return;}
  if(sourceDuration){const a=Number($('trim-start').value),b=Number($('trim-end').value);$('analysis-scope').textContent=sourceDuration>30?`Starting with ${timeLabel(a)}–${timeLabel(b)} of your ${timeLabel(sourceDuration)} video. Analysis, music and export cover this section only.`:`Analyzing your ${sourceDuration.toFixed(1)}-second video. Music starts only after you approve.`;}
  else $('analysis-scope').textContent='';
}

$('change-section').addEventListener('click',()=>{
  if(working||running())return;
  if(sourceFile){chooseFile(sourceFile,{auto:false,range:project?.video?.selection});$('trim-panel').open=true;}
  else{nextFileManual=true;$('video-file').click();}
});

$('empty-preview').addEventListener('dragover',e=>{e.preventDefault();$('empty-preview').classList.add('dragging');});
$('empty-preview').addEventListener('dragleave',()=>$('empty-preview').classList.remove('dragging'));
$('empty-preview').addEventListener('drop',e=>{e.preventDefault();$('empty-preview').classList.remove('dragging');chooseFile(e.dataTransfer.files[0]);});

$('play-result').addEventListener('click',async()=>{
  if(!project?.renders[project.selected])return;
  const v=$('preview');
  if(!v.paused && previewMode==='mix'){v.pause();return;}
  previewMode='mix';render();revealIfOutside(v);
  try{await v.play();}catch{toast('Press the play button in the video to listen.');}
});
for(const event of ['play','pause','ended','emptied'])$('preview').addEventListener(event,()=>{
  $('play-result').textContent=!$('preview').paused && previewMode==='mix'?'Pause video Ⅱ':'Play video ▷';
});

// Browser media metadata includes display orientation. Do not infer format from length.
function renderVideoFormat(){
  const v=$('preview'),w=v.videoWidth,h=v.videoHeight;
  if(!w||!h)return;
  const ratio=w/h,shape=ratio<.92?'portrait':ratio>1.08?'landscape':'square';
  document.body.dataset.videoShape=shape;
  const common=[[9,16],[4,5],[1,1],[4,3],[3,2],[16,9],[21,9]];
  const match=common.find(([a,b])=>Math.abs(ratio-a/b)/(a/b)<.015);
  const label=match?`${match[0]}:${match[1]}`:`${w} × ${h}`;
  $('video-format').textContent=`${shape==='portrait'?'Vertical':shape==='square'?'Square':'Landscape'} · ${label}`;
  // The video element and its panel share the media's ratio: no letterboxing or crop.
  const panel=document.querySelector('.preview-panel'),column=document.querySelector('.preview-column');
  const sideBySide=innerWidth>=1180 || innerWidth>=960 && shape!=='landscape';
  const top=document.querySelector('.sonvane-header').getBoundingClientRect().height+16;
  column.style.setProperty('--preview-top',`${top}px`);
  const overhead=['.preview-heading','.preview-switch','#clip-origin','#mix-tools'].reduce((sum,selector)=>sum+panel.querySelector(selector).getBoundingClientRect().height,2);
  const height=sideBySide?Math.max(200/ratio,Math.min(640,innerHeight-overhead-top-16)):Math.max(280,Math.min(shape==='landscape'?520:640,innerHeight*.66));
  const width=`${Math.floor(height*ratio)}px`;
  if(panel.style.getPropertyValue('--preview-width')!==width)panel.style.setProperty('--preview-width',width);
  column.classList.toggle('preview-can-stick',sideBySide && column.getBoundingClientRect().height<=innerHeight-top-16);
}
function renderSourceOverview(range){
  const valid=range && Number.isFinite(range.source_duration) && range.source_duration>0 && Number.isFinite(range.start) && Number.isFinite(range.end) && range.end>range.start;
  const partial=valid && (range.start>0 || range.end<range.source_duration-.05);
  show('source-overview',!!partial);
  document.body.classList.toggle('has-selected-section',!!partial);
  if(!partial)return;
  $('source-length').textContent=`Full video · ${timeLabel(range.source_duration)}`;
  const start=Math.max(0,Math.min(100,100*range.start/range.source_duration));
  const end=Math.max(start,Math.min(100,100*range.end/range.source_duration));
  $('source-range-mark').style.left=`${start}%`;$('source-range-mark').style.width=`${end-start}%`;
  $('source-range').setAttribute('aria-label',`Selected ${timeLabel(range.start)} to ${timeLabel(range.end)} of ${timeLabel(range.source_duration)}`);
  $('source-range-label').textContent=`${timeLabel(range.start)}–${timeLabel(range.end)} · ${(range.end-range.start).toFixed(1)} seconds`;
}
$('preview').addEventListener('loadedmetadata',renderVideoFormat);
$('preview').addEventListener('resize',renderVideoFormat);
window.addEventListener('resize',renderVideoFormat);

// Changes to metadata rows or playback controls can change the viewport height budget.
let previewLayoutFrame=0;
const previewLayoutObserver=new ResizeObserver(()=>{
  cancelAnimationFrame(previewLayoutFrame);previewLayoutFrame=requestAnimationFrame(renderVideoFormat);
});
for(const selector of ['.preview-column','.preview-heading','.preview-switch','#clip-origin','#mix-tools'])previewLayoutObserver.observe(document.querySelector(selector));

// A direct route from the decision to its conversation; never submits a message.
document.addEventListener('click',event=>{
  if(!event.target.closest('[data-talk-muse]'))return;
  $('muse-disclosure').open=true;
  $('conversation-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  $('chat-input').focus({preventScroll:true});
});

$('chat-input').addEventListener('input',disable);
$('preserve-audio').addEventListener('change',()=>{if(cueDraft)drawCueTimeline();});


function revealIfOutside(element){
  const box=element.getBoundingClientRect(),header=document.querySelector('.sonvane-header').getBoundingClientRect().bottom;
  if(box.bottom<header || box.top>innerHeight)element.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'nearest'});
}
function syncMixDucking(busy=working||running()){
  const hasAudio=!!project?.video?.has_audio;
  $('mix-original').disabled=!!busy||!hasAudio;
  const available=hasAudio&&$('mix-original').checked;
  $('mix-duck').disabled=!!busy||!available;
  $('mix-duck-option').classList.toggle('unavailable',!available);
  $('mix-duck-option').title=!hasAudio?'This video has no original audio.':!available?'Enable Keep original audio to use this.':'Music becomes quieter when the original audio is louder.';
}
$('mix-original').addEventListener('change',()=>syncMixDucking());

// Prepare files first; the next explicit click retains the user activation needed by Web Share.
let sharedFile=null,sharedTrack=null,shareRequest=0;
function saveShareFile(blob,name){
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;
  document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
$('close-share').addEventListener('click',()=>$('share-dialog').close());
$('share-dialog').addEventListener('close',()=>{shareRequest++;sharedFile=null;sharedTrack=null;});
$('share-result').addEventListener('click',async()=>{
  if(!project?.renders[project.selected])return;
  const request=++shareRequest,title=project.tracks.find(t=>t.id===project.selected)?.name||'Your soundtrack';
  const url=$('download-video').href;sharedFile=null;
  const track=project.tracks.find(t=>t.id===project.selected);
  // Capture only shareable fields from the same selection as the fetched video.
  sharedTrack={name:track?.name||title,score:track?.score,evaluation_kind:track?.evaluation_kind,prompt:track?.prompt||'',bpm:track?.bpm_requested};
  $('share-track').textContent=title;$('share-status').textContent='Preparing your selected mix…';
  for(const id of ['share-device','share-card'])$(id).disabled=true;
  $('share-dialog').showModal();
  try{
    const response=await fetch(url);if(!response.ok)throw Error('Could not prepare this mix. Close and try again.');
    const blob=await response.blob();if(request!==shareRequest)return;
    if(!blob.size||!blob.type.startsWith('video/'))throw Error('The video is not ready. Please try again.');
    sharedFile=new File([blob],'sonvane-video.mp4',{type:'video/mp4'});
    $('share-card').disabled=false;
    const supported=!!navigator.canShare&&!!navigator.share&&navigator.canShare({files:[sharedFile]});
    $('share-device').disabled=!supported;
    $('share-status').textContent=supported?'Ready. Choose where to send your video.':'App sharing is unavailable here. Send a video card, or use Save video in Studio for an MP4.';
  }catch(error){if(request===shareRequest)$('share-status').textContent=error.message;}
});
$('share-device').addEventListener('click',async()=>{
  if(!sharedFile)return;
  try{await navigator.share({files:[sharedFile]});}
  catch(error){if(error.name!=='AbortError')$('share-status').textContent='This browser could not open sharing. Use Save video in Studio to download the MP4.';}
});
$('share-card').addEventListener('click',async()=>{
  if(!sharedFile)return;
  const file=sharedFile,track={...sharedTrack},title=esc(track.name),request=shareRequest;
  $('share-card').disabled=true;
  try{
    const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not build the video card.'));reader.readAsDataURL(file);});
    if(request!==shareRequest)return;
    const rated=track.evaluation_kind!=='not-rated'&&typeof track.score==='number'&&Number.isFinite(track.score);
    const score=rated?track.score.toFixed(3):'Not rated';
    const prompt=track.prompt?esc(track.prompt):'No generation prompt recorded.';
    const tempo=Number.isFinite(track.bpm)?` · ${esc(track.bpm)} BPM requested`:'';
    const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>${title} · Sonvane</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f6f5f0;color:#19232b;font-family:Inter,system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px}header a{display:flex;align-items:center;gap:8px;text-decoration:none;color:inherit}a{color:#075ee8}a:focus-visible{outline:2px solid #075ee8;outline-offset:4px}header{display:flex;align-items:center;gap:8px;margin-bottom:18px}.brand{font-size:28px;font-weight:750;letter-spacing:-1.7px}.brand span{color:#075ee8}video{display:block;width:100%;max-height:74vh;background:#101920;border-radius:10px}h1{font-size:22px;line-height:1.3;margin:18px 0 5px;overflow-wrap:anywhere}p{font-size:14px;line-height:1.55;color:#56616b;margin:0}.details{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start;margin:16px 0 12px}.details h1{margin:0 0 4px}.score{text-align:right}.score strong{display:block;font-size:26px;line-height:1.15;font-variant-numeric:tabular-nums}.score span,.label{font-size:12px;color:#56616b}.prompt{border-top:1px solid #d6dad9;padding-top:12px}.prompt p{margin-top:4px;color:#19232b;white-space:pre-wrap;overflow-wrap:anywhere}.note{font-size:12px;margin-top:10px}footer{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between}footer{margin-top:18px;padding-top:12px;border-top:1px solid #d6dad9;font-size:12px;color:#56616b}@media(max-width:600px){main{padding:16px}h1{font-size:20px}}
    </style></head><body><main><header><a href="https://yonghyunk1m-sonvane.hf.space/demo/" target="_blank" rel="noopener noreferrer" aria-label="Sonvane overview"><svg width="32" height="32" viewBox="0 0 48 48" aria-hidden="true"><path d="M36 10H21C14.4 10 10 13.8 10 19C10 24.2 14.4 28 21 28H27" fill="none" stroke="#202b38" stroke-width="7" stroke-linecap="round"/><path d="M12 38H27C33.6 38 38 34.2 38 29C38 23.8 33.6 20 27 20H21" fill="none" stroke="#075ee8" stroke-width="7" stroke-linecap="round"/></svg><span class="brand">sonvane<span>.</span></span></a></header><video controls playsinline preload="metadata" aria-label="Video with selected soundtrack" src="${data}"></video><section class="details"><div><h1>${title}</h1><p>Chosen by the creator${tempo}</p></div><div class="score"><strong>${score}</strong><span>TuneJury A1</span></div></section><section class="prompt"><span class="label">GENERATION PROMPT</span><p>${prompt}</p></section><p class="note">${rated?"TuneJury predicts music preference. Higher is better; this is not a rating out of 10.":"No music preference score is available for this soundtrack."}</p><footer><span>Video and sound included in this file.</span><a href="https://yonghyunk1m-sonvane.hf.space/demo/" target="_blank" rel="noopener noreferrer">Made with Sonvane ↗</a></footer></main></body></html>`;
    saveShareFile(new Blob([html],{type:'text/html;charset=utf-8'}),'sonvane-video-card.html');
    $('share-status').textContent='Video card saved. Send this HTML file; it includes the video and sound.';
  }catch(error){if(request===shareRequest)$('share-status').textContent=error.message;}
  finally{if(request===shareRequest)$('share-card').disabled=false;}
});
