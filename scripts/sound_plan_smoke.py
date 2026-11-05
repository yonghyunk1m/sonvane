"""One real Muse proposal; user-reviewed two-section music generation + local effects."""
import argparse,json,time,uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright,expect
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
if not args.live:raise SystemExit('Use --live to permit one Meta request and local GPU generation.')
root=Path(__file__).resolve().parents[1];out=root/'artifacts/sound-plan-check';out.mkdir(parents=True,exist_ok=True)
source=root/'artifacts/studio-check/source.mp4'
if not source.exists():raise SystemExit('Create the original 12-second studio test fixture first.')
base='http://127.0.0.1:8765';profile=uuid.uuid4().hex
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1440,'height':1050});errors=[];console_errors=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.on('console',lambda m:console_errors.append(m.text) if m.type=='error' and 'Content Security Policy' in m.text else None)
 p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('id=>{localStorage.clear();localStorage.setItem("sonvane-profile",id)}',profile);p.reload(wait_until='networkidle')
 before=p.request.get(base+'/api/studio/status').json()['budget']
 p.evaluate('document.body.classList.add("has-video");document.getElementById("video-tools").classList.remove("hidden");document.getElementById("video-settings").open=true');p.locator('.input-preferences').evaluate('e=>e.open=true');p.locator('#brief').fill('A synthetic sunset video. Recommend restrained instrumental piano sections and only a subtle synthesized transition if useful. I will review all times before generation.')
 p.locator('#context').select_option('travel');p.locator('#video-file').set_input_files(str(source))
 expect(p.locator('#sound-plan-panel')).to_be_visible(timeout=150000)
 expect(p.locator('#approve-sound-plan')).to_be_enabled(timeout=10000);p.locator('#cue-editor').evaluate('e=>e.open=true')
 pid=p.evaluate('localStorage.getItem("sonvane-project")');url=base+f'/api/studio/projects/{pid}'
 def state():return p.request.get(url).json()
 first=state();assert first['round']==0 and first['tracks']==[] and first['sound_plan']['status']=='draft'
 assert p.request.get(base+'/api/studio/status').json()['budget']['requests']==before['requests']+1
 (out/'proposal.json').write_text(json.dumps(first['sound_plan'],indent=2))
 (out/'state.json').write_text(json.dumps({'project':pid,'profile':profile,'before':before}))
 print('REAL PROPOSAL SAVED; no music generated.',flush=True)
 while p.locator('[data-remove-cue]').count():p.locator('[data-remove-cue]').first.click()
 p.locator('#add-music-cue').click();card=p.locator('.cue-card').nth(0)
 card.locator('[data-field="end"]').fill('4');card.locator('[data-field="description"]').fill('Gentle warm solo piano, sparse sustained notes, peaceful instrumental music, no vocals and no percussion.')
 p.locator('#add-music-cue').click();card=p.locator('.cue-card').nth(1)
 card.locator('[data-field="start"]').fill('8');card.locator('[data-field="end"]').fill('12');card.locator('[data-field="description"]').fill('Soft bowed strings with a warm piano response, slowly rising instrumental ending, no vocals and no drums.')
 p.locator('#add-sfx-cue').click();card=p.locator('.cue-card').nth(2)
 card.locator('[data-field="start"]').fill('5');card.locator('[data-field="end"]').fill('5.6');card.locator('[data-field="effect"]').select_option('chime');card.locator('[data-field="gain"]').fill('18')
 expect(p.locator('#sound-plan-error')).to_have_text('')
 bars=p.locator('[data-placement]');assert bars.count()==3
 assert bars.nth(1).evaluate('e=>e.getBoundingClientRect().width')>100
 card.locator('[data-preview-effect]').click();expect(p.locator('#effect-preview')).to_be_visible()
 p.locator('#effect-preview').evaluate('a=>a.muted=true');p.wait_for_timeout(200)
 assert p.locator('#effect-preview').evaluate('a=>a.duration')>.5
 # Unsaved cue edits must survive Overview/Studio navigation.
 p.get_by_role('navigation').get_by_text('Overview',exact=True).click();p.wait_for_url('**/demo/')
 p.get_by_role('navigation').get_by_text('Studio',exact=True).click();p.wait_for_url('**/studio/');p.wait_for_load_state('networkidle')
 p.locator('#cue-editor').evaluate('e=>e.open=true');expect(p.locator('.cue-card')).to_have_count(3);expect(p.locator('.cue-card').nth(1).locator('[data-field="start"]')).to_have_value('8')
 p.locator('#save-sound-plan').click();expect(p.locator('#save-sound-plan')).to_be_enabled()
 saved=state();assert saved['round']==0 and saved['tracks']==[]
 assert p.request.post(url+'/generate',data=json.dumps({'cue_revision':first['sound_plan']['revision']}),headers={'Content-Type':'application/json'}).status==409
 p.locator('#sound-plan-panel').screenshot(path=str(out/'review-desktop.png'))
 for width in [390,320]:
  p.set_viewport_size({'width':width,'height':844});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
 p.locator('#sound-plan-panel').screenshot(path=str(out/'review-mobile.png'))
 p.set_viewport_size({'width':1440,'height':1050});p.locator('#approve-sound-plan').click()
 deadline=time.monotonic()+900;last=None;stopped=False
 while time.monotonic()<deadline:
  data=state()
  if data['message']!=last:print(data['status'],data['message'],flush=True);last=data['message']
  if not stopped and data['status']=='generating' and data.get('generation_progress',{}).get('completed',0)>=1:
   p.locator('#stop-job').click();stopped=True
  if data['status']=='cancelled':
   expect(p.locator('#resume-job')).to_be_visible(timeout=10000);p.locator('#resume-job').click()
  if data['round']>=1 and data['status'] in ('complete','error'):break
  p.wait_for_timeout(600)
 assert data['status']=='complete',data.get('error')
 assert len(data['tracks'])==3 and data['round']==1
 disk=json.loads((root/f'.data/projects/{pid}/project.json').read_text())
 for t in disk['tracks']:
  assert t['windows']==[[0.,4.],[8.,12.]],t['windows']
  raw,sr=sf.read(t['path'],always_2d=True)
  assert not np.any(raw[4*sr:8*sr]) and np.any(raw[:4*sr]) and np.any(raw[8*sr:])
  assert t['sound_plan']['status']=='approved' and len(t['cue_seeds'])==2
 p.wait_for_timeout(2500);p.locator('.export-options').evaluate('e=>e.open=true');expect(p.locator('#download-design')).to_be_visible()
 p.locator('.export-options').evaluate('e=>e.open=true')
 response=p.request.get(base+p.locator('#download-design').get_attribute('href'));assert response.ok
 (out/'music-and-effects.wav').write_bytes(response.body());bed,sr=sf.read(out/'music-and-effects.wav',always_2d=True)
 assert not np.any(bed[4*sr:5*sr]) and np.any(bed[5*sr:int(5.6*sr)]) and not np.any(bed[int(5.6*sr):8*sr])
 p.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');p.wait_for_timeout(600);assert p.locator('#preview').evaluate('v=>v.currentTime')>0
 after=p.request.get(base+'/api/studio/status').json()['budget'];assert after['requests']==before['requests']+1
 assert not errors,errors;assert not console_errors,console_errors
 p.screenshot(path=str(out/'completed-desktop.png'),full_page=True)
 (out/'report.json').write_text(json.dumps({'project':pid,'profile':profile,'real_muse_proposal':True,'no_generation_before_approval':True,'reviewed_music_intervals':[[0,4],[8,12]],'effect_interval':[5,5.6],'variations':3,'actual_music_cues_generated':6,'stopped_and_resumed':stopped,'unapproved_version_rejected':True,'music_gaps_silent':True,'sfx_excluded_from_music_evaluation':True,'browser_errors':errors,'before':before,'after':after,'fixture':'Original synthetic video; automated edits, not human timing or music-quality validation'},indent=2))
 print('SOUND PLAN LIVE CHECK PASSED',after,flush=True);b.close()
