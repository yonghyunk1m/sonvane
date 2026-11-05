"""Real recovery check: --live permits ONE bounded Meta request and local generation.

Uses an isolated test profile and original synthetic media. It tests behavior,
not musical quality or human preference. Never runs on an existing user project.
"""
import argparse,json,time,uuid,subprocess
from pathlib import Path
import imageio_ffmpeg
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
if not args.live:raise SystemExit('Pass --live to allow one Meta planning request and local generation.')
root=Path(__file__).resolve().parents[1];out=root/'artifacts/recovery-check';out.mkdir(parents=True,exist_ok=True)
source=root/'artifacts/studio-check/source-audio.mp4'
if not source.exists():
 source=out/'synthetic.mp4'
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=12','-f','lavfi','-i','sine=frequency=220:sample_rate=16000:duration=12','-c:v','libx264','-c:a','aac','-pix_fmt','yuv420p',str(source)],check=True)
profile=uuid.uuid4().hex
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8765/studio/',wait_until='networkidle')
 page.evaluate('(p)=>{localStorage.clear();localStorage.setItem("sonvane-profile",p)}',profile);page.reload(wait_until='networkidle')
 budget_before=page.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget']
 page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#brief').fill('A quiet instrumental soundtrack for this synthetic test video. Gentle piano, no vocals.');page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#context').select_option('travel')
 # Draft survives a navigation round trip before uploading.
 page.get_by_role('navigation').get_by_text('Overview',exact=True).click();page.wait_for_url('**/demo/')
 page.get_by_role('navigation').get_by_text('Studio',exact=True).click();page.wait_for_url('**/studio/');page.wait_for_timeout(500)
 assert 'synthetic test video' in page.locator('#brief').input_value()
 page.evaluate('nextFileManual=true');page.locator('#video-file').set_input_files(str(source));assert page.locator('#preview').is_visible()
 page.locator('.quick-mode').evaluate('e=>e.open=true');page.locator('#create').click()
 deadline=time.monotonic()+900;pid=None;state=None;last=None
 while time.monotonic()<deadline:
  pid=page.evaluate('localStorage.getItem("sonvane-project")')
  if pid:
   state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
   if state['message']!=last:print(state['status'],state['message'],flush=True);last=state['message']
   if state['status']=='error':raise AssertionError(state['error'])
   if state['status']=='generating' and state.get('generation_progress',{}).get('completed',0)>=1:break
  page.wait_for_timeout(250)
 assert state and state['status']=='generating',state
 page.locator('#stop-job').click()
 for _ in range(120):
  state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
  if state['status']=='cancelled':break
  page.wait_for_timeout(500)
 assert state['status']=='cancelled' and state['can_resume'],state
 before_files=json.loads((root/f'.data/projects/{pid}/round-1/result.json').read_text())
 assert 1<=len(before_files)<3,before_files
 print('Stopped with',len(before_files),'saved candidates.',flush=True)
 page.reload(wait_until='networkidle');page.locator('#resume-job').wait_for(state='visible');page.locator('#resume-job').click()
 # A failed read must recover without issuing another generation request.
 failures={'remaining':1}
 def intercept(route):
  if route.request.method=='GET' and failures['remaining']:
   failures['remaining']-=1;route.abort()
  else:route.continue_()
 page.route(f'**/api/studio/projects/{pid}',intercept)
 deadline=time.monotonic()+900;last=None
 while time.monotonic()<deadline:
  state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
  if state['message']!=last:print(state['status'],state['message'],flush=True);last=state['message']
  if state['status'] in ('complete','error'):break
  page.wait_for_timeout(1000)
 assert state['status']=='complete' and state['round']==1 and len(state['tracks'])==3,state
 after_files=json.loads((root/f'.data/projects/{pid}/round-1/result.json').read_text());assert after_files[:len(before_files)]==before_files
 page.wait_for_timeout(2500);assert failures['remaining']==0
 assert page.locator('#connection-note').is_hidden()
 assert page.locator('#result-panel').is_visible()
 page.locator('#mix-level').fill('17');page.locator('#mix-duck').uncheck();page.locator('#apply-mix').click()
 for _ in range(60):
  state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
  if state.get('mix_settings',{}).get('level')==.17:break
  page.wait_for_timeout(500)
 assert state['render_settings'][state['selected']]['level']==.17
 assert state['render_settings'][state['selected']]['duck'] is False
 page.wait_for_timeout(700)
 page.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');page.wait_for_timeout(700)
 assert page.locator('#preview').evaluate('v=>v.currentTime')>0
 page.locator('#preview').evaluate('v=>v.pause()')
 selected=state['selected'];alternative=next(t['id'] for t in state['tracks'] if t['id']!=selected)
 page.locator('.optional-results').evaluate_all('es=>es.forEach(e=>e.open=true)');page.locator(f'[data-listen="{alternative}"]').click();page.locator('#remember-comparison').evaluate('e=>e.open=true');page.locator('#remember-choice').check();page.locator('#compared-with').select_option(selected);page.locator('#jury-use-track').click()
 for _ in range(60):
  state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
  if state['selected']==alternative and state['profile']['pair_count']==1:break
  page.wait_for_timeout(500)
 assert state['profile']['pair_count']==1
 page.wait_for_timeout(700);page.locator('#memory-details summary').click();page.locator('[data-forget]').click()
 for _ in range(30):
  state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
  if state['personalization']['pairs']==0:break
  page.wait_for_timeout(500)
 assert state['personalization']['pairs']==0 and state['selected']==alternative
 assert all(t['personal_adjustment']==0 for t in state['tracks'])
 page.wait_for_timeout(700)
 with page.expect_download() as dl:page.locator('#download-video').click()
 dl.value.save_as(out/'mixed-video.mp4')
 page.screenshot(path=str(out/'studio-desktop.png'),full_page=True)
 page.locator('#new-project').click();page.wait_for_load_state('networkidle');page.wait_for_timeout(400)
 page.locator('#project-history').select_option(pid);page.wait_for_timeout(700);assert page.locator('#selected-name').inner_text()
 for width in [390,320]:
  page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.screenshot(path=str(out/f'studio-{width}.png'),full_page=True)
 budget_after=page.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget']
 assert budget_after['requests']==budget_before['requests']+1,(budget_before,budget_after)
 assert not errors,errors
 report={'project':pid,'profile':profile,'saved_candidates_at_stop':len(before_files),'candidates_after_resume':3,'planning_requests':1,'rounds':1,'network_recovery':True,'mix_without_regeneration':True,'memory_delete_refresh':True,'history_restoration':True,'browser_errors':errors,'before':budget_before,'after':budget_after,'evidence':'Synthetic integration fixture; not human musical-quality evidence.'}
 (out/'report.json').write_text(json.dumps(report,indent=2));print('RECOVERY CHECK PASSED',json.dumps(report),flush=True);browser.close()
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(out/'mixed-video.mp4'),'-f','null','-'],check=True,capture_output=True)
