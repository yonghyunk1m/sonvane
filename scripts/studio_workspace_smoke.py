"""Progressive Studio checks: real local uploads, intercepted Muse, no paid calls."""
import copy,json,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/studio-design-check';OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/'artifacts/trim-check/long-source.mp4'
if not source.exists():raise SystemExit('Run the no-cost video_trim_smoke.py to prepare the local fixture.')
base='http://127.0.0.1:8765';widths=[320,390,768,1024,1440]
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1440,'height':1000});errors=[];calls=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('(id)=>{localStorage.clear();localStorage.setItem("sonvane-profile",id)}',uuid.uuid4().hex);p.reload(wait_until='networkidle')
 before=p.request.get(base+'/api/studio/status').json()['budget']['requests']
 expect(p.locator('#choose-video')).to_be_visible();assert p.locator('.studio-grid .primary:visible').count()==1
 fail=False
 def proposal(route):
  calls.append(route.request.url)
  if fail:route.fulfill(status=503,json={'detail':'Injected analysis failure'});return
  url=route.request.url.removesuffix('/sound-plan');data=p.request.get(url).json();duration=data['video']['duration']
  data['sound_plan']={'scene_description':'Browser fixture: a test pattern with a tone.','summary':'A restrained instrumental backing is suggested for this fixture.','revision':uuid.uuid4().hex,'status':'draft','model':'intercepted-test','cues':[{'id':uuid.uuid4().hex,'kind':'music','start':0,'end':duration,'description':'Soft instrumental piano, no vocals.','reason':'Browser fixture','effect':'none','bpm':90,'gain':1,'enabled':True}]}
  route.fulfill(json=data)
 def no_generation(route):raise AssertionError('No generation may start before explicit confirmation')
 p.route('**/sound-plan',proposal);p.route('**/generate',no_generation)
 p.locator('#video-file').set_input_files(str(source));expect(p.locator('#sound-plan-panel')).to_be_visible(timeout=30000)
 assert len(calls)==1;expect(p.locator('#analysis-scope')).to_contain_text('0:00.0–0:30.0');expect(p.locator('#analysis-scope')).to_contain_text('0:45.0')
 expect(p.locator('#workspace-tabs')).to_be_hidden();expect(p.locator('#chat-input')).to_be_visible();expect(p.locator('#trim-start')).to_be_hidden()
 assert p.locator('#sound-plan-panel .primary:visible').count()==1
 for width in widths:
  p.set_viewport_size({'width':width,'height':1000});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
 p.set_viewport_size({'width':1440,'height':1000});p.locator('#sound-plan-panel').screenshot(path=str(OUT/'simple-recommendation.png'))
 # Change section reuses the browser's original File, waits for explicit Analyze, then uploads the chosen section.
 p.locator('#change-section').click();expect(p.locator('#trim-start')).to_be_visible()
 p.locator('#trim-start').fill('22.3');p.locator('#trim-end').fill('28.3');p.wait_for_timeout(500);assert len(calls)==1
 p.locator('#plan-sound').click();expect(p.locator('#sound-plan-panel')).to_be_visible(timeout=30000);assert len(calls)==2
 pid=p.evaluate('localStorage.getItem("sonvane-project")');actual=p.request.get(base+'/api/studio/projects/'+pid).json()
 assert actual['video']['duration']==6 and actual['video']['selection']['start']==22.3 and actual['round']==0
 p.locator('#chat-input').fill('Unsent direction');p.reload(wait_until='networkidle');assert len(calls)==2
 expect(p.locator('#chat-input')).to_have_value('Unsent direction')
 # A failed request offers an explicit retry and cannot replay on reload or media events.
 fail=True;p.locator('#plan-sound').click();expect(p.locator('#analysis-title')).to_have_text('Analysis needs attention');count=len(calls)
 p.locator('#preview').evaluate('v=>v.dispatchEvent(new Event("loadedmetadata"))');p.wait_for_timeout(500);assert len(calls)==count
 fail=False;p.locator('#plan-sound').click();expect(p.locator('#sound-plan-panel')).to_be_visible();assert len(calls)==count+1
 # Finished projects expose only the main export. Other versions/downloads are optional.
 finished=json.loads((ROOT/'artifacts/sound-plan-check/state.json').read_text())
 p.evaluate('(s)=>{localStorage.clear();localStorage.setItem("sonvane-profile",s.profile);localStorage.setItem("sonvane-project",s.project)}',finished);p.reload(wait_until='networkidle')
 expect(p.locator('#download-video')).to_be_visible();expect(p.locator('#download-audio')).to_be_hidden();expect(p.locator('#chat-input')).to_be_visible()
 p.locator('.export-options').evaluate('e=>e.open=true');expect(p.locator('#download-audio')).to_be_visible()
 for width in widths:
  p.set_viewport_size({'width':width,'height':1000});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),('results',width)
 assert p.request.get(base+'/api/studio/status').json()['budget']['requests']==before
 assert not errors,errors
 (OUT/'report.json').write_text(json.dumps({'automatic_initial_analysis_intercepted':True,'first_30_seconds_explicit':True,'manual_section_22_3_to_28_3_verified':True,'no_generation_before_confirmation':True,'failure_requires_explicit_retry':True,'unsent_chat_restored':True,'optional_controls_collapsed':True,'widths':widths,'model_calls':0,'browser_errors':errors},indent=2))
 print('Progressive Studio passed: automatic intake, explicit scope, real section changes, retry, collapsed controls; zero model calls.');b.close()
