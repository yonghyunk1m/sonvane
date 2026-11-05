"""Read-only saved results + in-browser state fixtures. No model requests or mutations."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/studio-speakers-check';OUT.mkdir(parents=True,exist_ok=True)
base='http://127.0.0.1:8765';state=json.loads((ROOT/'artifacts/sound-plan-check/state.json').read_text())
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1440,'height':1100});errors=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 def read_only(route):
  assert route.request.method=='GET',route.request.url
  route.continue_()
 p.route('**/api/**',read_only)
 p.goto(base+'/studio/',wait_until='networkidle')
 p.evaluate('(s)=>{localStorage.clear();localStorage.setItem("sonvane-profile",s.profile);localStorage.setItem("sonvane-project",s.project)}',state)
 p.reload(wait_until='networkidle');expect(p.locator('#jury-verdict')).to_be_visible()
 expect(p.locator('#video-settings')).not_to_have_attribute('open','')
 expect(p.locator('#jury-scores')).to_be_visible()
 expect(p.locator('[data-creation-step="4"]')).to_have_attribute('aria-current','step')
 expect(p.locator('#play-result')).to_be_visible()
 p.locator('#play-result').focus();p.keyboard.press('Enter')
 expect(p.locator('#preview')).to_have_js_property('paused',False)
 expect(p.locator('#play-result')).to_contain_text('Pause')
 p.locator('#play-result').click();expect(p.locator('#play-result')).to_contain_text('Play')
 with p.expect_download() as download:p.locator('#download-video').click()
 assert download.value.suggested_filename.endswith('.mp4')
 expect(p.locator('#jury-scores')).to_be_visible()
 data=p.request.get(base+'/api/studio/projects/'+state['project']).json()
 selected=next(t for t in data['tracks'] if t['id']==data['selected'])
 tracks=sorted([t for t in data['tracks'] if t['round']==selected['round']],key=lambda t:-t['score'])
 expect(p.locator('.jury-number')).to_have_count(len(tracks))
 for i,t in enumerate(tracks):expect(p.locator('.jury-number').nth(i)).to_contain_text(f'{t["score"]:.3f}')
 expect(p.locator('#jury-speech')).to_contain_text(tracks[0]['name'])
 p.locator('#result-panel').screenshot(path=str(OUT/'results.png'))
 # Old verbose proposals keep their full text, but no longer dominate the default view.
 scene='A small white delivery robot approaches the camera along a campus walkway. '+('The background contains trees and low brick buildings. '*8)
 summary='I suggest warm, restrained piano to match the robot’s gentle movement. '+('These model-written timing notes belong in the full analysis, not the main recommendation. '*9)
 p.evaluate('([scene,summary])=>{project.sound_plan.scene_points=[];project.sound_plan.sound_points=[];project.sound_plan.scene_description=scene;project.sound_plan.summary=summary;cueRevision=null;render();setWorkspaceTab("plan")}',[scene,summary])
 expect(p.locator('[data-creation-step="2"]')).to_have_attribute('aria-current','step')
 expect(p.locator('#approve-sound-plan')).to_have_text('Make 3 more versions')
 expect(p.locator('#scene-description')).to_have_text(scene.split('. ')[0]+'.')
 expect(p.locator('#sound-plan-summary')).to_have_text(summary.split('. ')[0]+'.')
 expect(p.locator('#plan-explanation')).not_to_have_attribute('open','')
 expect(p.locator('#scene-description-full li')).to_have_count(9)
 expect(p.locator('#sound-plan-summary-full li')).to_have_count(10)
 expect(p.locator('#scene-description-full')).to_have_text(scene.strip())
 expect(p.locator('#sound-plan-summary-full')).to_have_text(summary.strip())
 p.locator('#sound-plan-panel').screenshot(path=str(OUT/'plan.png'))
 widths=[320,390,768,1024,1440]
 for view in ['plan','results']:
  p.evaluate('(v)=>setWorkspaceTab(v)',view)
  for width in widths:
   p.set_viewport_size({'width':width,'height':1100});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(view,width)
 p.set_viewport_size({'width':1440,'height':1100})
 # The actual status selects the speaker, not a timed decorative sequence.
 for status,actor in [('planning','Muse Spark'),('generating','ACE-Step'),('scoring','TuneJury'),('mixing','Sonvane')]:
  p.evaluate('(s)=>{delete project.pending_sound_plan;project.status=s;render()}',status)
  expect(p.locator('[data-creation-step="3"]')).to_have_attribute('aria-current','step');expect(p.locator('#workspace-plan')).to_be_hidden();expect(p.locator('#workspace-results')).to_be_hidden()
  expect(p.locator('#progress-speaker')).to_be_visible();expect(p.locator('#progress-speaker .speaker-name')).to_contain_text(actor)
 p.locator('#progress-panel').screenshot(path=str(OUT/'progress.png'))
 p.evaluate('()=>{project.pending_sound_plan=project.sound_plan;project.status="planning";render()}')
 expect(p.locator('#progress-speaker .speaker-name')).to_contain_text('Sonvane')
 expect(p.locator('#progress-speaker')).to_contain_text('No new Spark analysis')
 p.evaluate('()=>{project.status="cancelled";render()}');expect(p.locator('#progress-speaker')).to_be_hidden()
 # Effects-only runs must never pretend TuneJury is evaluating music.
 p.evaluate('()=>{project.sound_plan.cues=[];project.pending_sound_plan=project.sound_plan;project.status="scoring";render()}')
 expect(p.locator('#progress-speaker .speaker-name')).to_contain_text('Sonvane')
 p.evaluate('()=>{project.status="complete";project.tracks.find(t=>t.id===project.selected).evaluation_kind="not-rated";render()}')
 expect(p.locator('#jury-verdict')).to_be_hidden()
 # Cross-round selection must never compare the previous selection against a later round's scores.
 p.evaluate('()=>{const t=project.tracks.find(t=>t.id===project.selected);delete t.evaluation_kind;project.tracks.push({...t,id:"other-round",round:t.round+1,score:999});render()}')
 assert '999' not in p.locator('#jury-scores').inner_text()
 assert not errors,errors
 (OUT/'report.json').write_text(json.dumps({'real_recorded_scores_verified':True,'long_saved_text_preserved':True,'stage_speakers_verified':True,'effects_only_not_scored':True,'selected_round_scores_only':True,'responsive_widths':widths,'browser_errors':errors,'model_calls':0},indent=2))
 print('PASS: readable excerpts, actual recorded scores, status-driven speakers, effects-only and round isolation; zero model calls.')
 b.close()
