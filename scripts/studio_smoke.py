"""Live integration test; --live explicitly permits three bounded Meta requests.

Uses a separately generated synthetic video and a fresh isolated test profile.
Automated choices are NOT human preference or quality evidence.
"""
import argparse,json,time,uuid,subprocess
from pathlib import Path
import imageio_ffmpeg
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');args=p.parse_args()
if not args.live:raise SystemExit('Pass --live to run real generation and paid Meta planning.')
root=Path(__file__).resolve().parents[1];out=root/'artifacts/studio-check';out.mkdir(exist_ok=True)
source=out/'source.mp4'
if not source.exists():
 # Original synthetic fixture, never a user's private video.
 from PIL import Image,ImageDraw
 im=Image.new('RGB',(960,540));d=ImageDraw.Draw(im)
 for y in range(540):
  t=y/540;d.line((0,y,960,y),fill=(int(251-155*t),int(190-70*t),int(139+12*t)))
 d.ellipse((620,90,760,230),fill='#ffe3a5');d.polygon([(0,350),(170,190),(380,380),(570,250),(780,385),(960,240),(960,540),(0,540)],fill='#47687a');d.rectangle((0,375,960,540),fill='#567e92')
 d.text((20,20),'SYNTHETIC VIDEO / INTEGRATION TEST',fill='white');im.save(out/'source.png')
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-loop','1','-i',str(out/'source.png'),'-t','12','-r','24','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
profile=uuid.uuid4().hex
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8765/studio/',wait_until='networkidle')
 page.evaluate('(id)=>{localStorage.setItem("sonvane-profile",id);localStorage.removeItem("sonvane-project")}',profile);page.reload(wait_until='networkidle')
 before=page.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget']
 page.screenshot(path=str(out/'empty-desktop.png'),full_page=True)
 page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#brief').fill('Warm instrumental music for this quiet sunset test video. Gentle piano and strings, no vocals. Keep the scene peaceful.')
 page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#context').select_option('travel');page.evaluate('nextFileManual=true');page.locator('#video-file').set_input_files(str(source));page.locator('.quick-mode').evaluate('e=>e.open=true');page.locator('#create').click()
 def await_project(expected_round=1):
  deadline=time.monotonic()+900;last=None;state=None
  while time.monotonic()<deadline:
   pid=page.evaluate('localStorage.getItem("sonvane-project")')
   if pid:
    state=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
    if state['message']!=last:print(pid,state['status'],state['message'],flush=True);last=state['message']
    if state['round']>=expected_round and state['status'] in ('complete','error'):break
   page.wait_for_timeout(1500)
  assert state and state['status']=='complete',state
  # Wait for UI polling to render the completed result, not just the API state.
  for _ in range(20):
   if page.locator('#result-panel').is_visible() and page.locator('#revise').is_enabled():break
   page.wait_for_timeout(500)
  page.locator('.optional-results,.export-options').evaluate_all('es=>es.forEach(e=>e.open=true)')
  return state
 first=await_project();assert len(first['tracks'])==3 and first['selected_by']=='automatic recommendation'
 assert first['personalization']['pairs']==0
 page.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');page.wait_for_timeout(600)
 assert page.locator('#preview').evaluate('v=>v.currentTime')>0
 page.locator('#preview').evaluate('v=>v.pause()')
 page.screenshot(path=str(out/'result-desktop.png'),full_page=True)
 selected=first['selected'];alternative=next(t['id'] for t in first['tracks'] if t['id']!=selected)
 page.locator(f'[data-listen="{alternative}"]').click();page.locator('#remember-comparison').evaluate('e=>e.open=true');page.locator('#remember-choice').check();page.locator('#compared-with').select_option(selected);page.locator('#jury-use-track').click()
 for _ in range(60):
  data=page.request.get(f'http://127.0.0.1:8765/api/studio/projects/{first["id"]}').json()
  if data['selected']==alternative and data['profile']['pair_count']==1:break
  page.wait_for_timeout(500)
 assert data['profile']['pair_count']==1 and data['selected']==alternative
 page.wait_for_timeout(1000)
 page.locator('#feedback').fill('For travel videos, prefer a gentler pulse and less percussion. Keep warm piano and no vocals. This is an automated integration-test instruction, not a human preference study.')
 page.locator('#feedback-panel').evaluate('e=>e.parentElement.open=true');page.locator('#remember-note').check();page.locator('#revise').click()
 revised=await_project(2);assert revised['round']==2 and len(revised['tracks'])==6
 assert revised['personalization']['pairs']==1 and len(revised['profile']['notes'])==1
 assert any(abs(t.get('personal_adjustment',0))>0 for t in revised['tracks'] if t['id'] in revised['active_ids'])
 for id,name in [('download-video','soundtrack.mp4'),('download-audio','soundtrack.wav'),('download-record','record.json')]:
  with page.expect_download() as dl:page.locator('#'+id).click()
  dl.value.save_as(out/name)
 report=json.loads((out/'record.json').read_text());assert report['selected'] and 'rights_note' in report
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'result-mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 # Second video has original test-tone audio, exercising Muse 1.2 and ducked mixing.
 source_audio=out/'source-audio.mp4'
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(source),'-f','lavfi','-i','sine=frequency=220:sample_rate=16000:duration=12','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-shortest',str(source_audio)],check=True)
 page.locator('#new-project').click();page.wait_for_load_state('networkidle');page.set_viewport_size({'width':1440,'height':1100})
 page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#context').select_option('travel');page.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');page.locator('.input-preferences').evaluate('e=>e.open=true');page.locator('#brief').fill('Another synthetic sunset test. Keep the quiet mood and the original audio.')
 page.evaluate('nextFileManual=true');page.locator('#video-file').set_input_files(str(source_audio));page.locator('.quick-mode').evaluate('e=>e.open=true');page.locator('#create').click();second=await_project()
 assert second['id']!=first['id'] and second['personalization']['pairs']==1 and second['meta_model']=='muse-spark-1.2'
 assert second['video']['has_audio'] and len(second['tracks'])==3
 after=page.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget']
 assert not errors,errors
 (out/'live-report.json').write_text(json.dumps({'profile':profile,'projects':[first['id'],second['id']],'rounds':3,'generated_tracks':9,'real_tunejury':True,'learned_pairs':1,'remembered_notes':1,'cross_project_personalization':True,'browser_errors':errors,'before':before,'after':after,'data':'Synthetic original test video and automated choices; not human musical-quality or preference validation'},indent=2))
 print('LIVE STUDIO CHECK PASSED',json.dumps(after),flush=True)
 browser.close()
