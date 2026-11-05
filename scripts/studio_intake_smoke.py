"""Opt-in real check: selecting one video causes one Muse analysis, no music generation."""
import argparse,json,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
if not args.live:raise SystemExit('Pass --live to allow ONE Meta analysis request; no music generation.')
root=Path(__file__).resolve().parents[1];out=root/'artifacts/studio-intake-check';out.mkdir(parents=True,exist_ok=True)
source=root/'artifacts/studio-check/source.mp4'
if not source.exists():raise SystemExit('The original synthetic studio video fixture is required.')
base='http://127.0.0.1:8765'
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1440,'height':1000});errors=[];posts=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
 p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('(id)=>{localStorage.clear();localStorage.setItem("sonvane-profile",id)}',uuid.uuid4().hex);p.reload(wait_until='networkidle')
 before=p.request.get(base+'/api/studio/status').json()['budget'];(out/'start.json').write_text(json.dumps({'before':before}))
 expect(p.locator('#choose-video')).to_be_visible();expect(p.locator('#workspace-tabs')).to_be_hidden();p.screenshot(path=str(out/'empty.png'))
 p.locator('#video-file').set_input_files(str(source))
 expect(p.locator('#analysis-panel')).to_be_visible(timeout=20000)
 expect(p.locator('#sound-plan-panel')).to_be_visible(timeout=150000)
 pid=p.evaluate('localStorage.getItem("sonvane-project")');url=base+'/api/studio/projects/'+pid
 data=p.request.get(url).json();(out/'state.json').write_text(json.dumps({'project':pid,'profile':data['profile_id'],'before':before}))
 assert data['round']==0 and data['tracks']==[] and data['sound_plan']['scene_description']
 expect(p.locator('#scene-description-full')).to_have_text(data['sound_plan']['scene_description'])
 assert all(any(h in text for text in [data['sound_plan']['summary'],*data['sound_plan']['sound_points']]) for h in data['sound_plan']['highlights'])
 expect(p.locator('#sound-plan-summary')).to_have_text(p.evaluate('(s)=>shortExcerpt(s,260)',data['sound_plan']['summary']))
 expect(p.locator('#scene-description')).to_have_text(p.evaluate('(s)=>shortExcerpt(s,200)',data['sound_plan']['scene_description']))
 expect(p.locator('#sound-plan-summary-full')).to_have_text(data['sound_plan']['summary'])
 rendered=p.locator('#sound-plan-summary .key-phrase').all_text_contents()
 assert all(h in data['sound_plan']['highlights'] for h in rendered) if data['sound_plan']['highlights'] else True
 expect(p.locator('#approve-sound-plan')).to_be_enabled();expect(p.locator('#cue-editor')).not_to_have_attribute('open','')
 assert len([x for x in posts if x.endswith('/sound-plan')])==1
 assert not [x for x in posts if x.endswith('/generate')]
 p.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');p.wait_for_timeout(300);p.locator('#preview').evaluate('v=>v.pause()')
 p.locator('#sound-plan-panel').screenshot(path=str(out/'recommendation.png'))
 for width in [320,390,768,1024,1440]:
  p.set_viewport_size({'width':width,'height':1000});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
 p.set_viewport_size({'width':1440,'height':1000})
 # Metadata events and reload must never replay a paid analysis.
 p.locator('#preview').evaluate('v=>v.dispatchEvent(new Event("loadedmetadata"))');p.reload(wait_until='networkidle');expect(p.locator('#sound-plan-panel')).to_be_visible()
 p.locator('#cue-editor').evaluate('e=>e.open=true');p.locator('#save-sound-plan').click();expect(p.locator('#save-sound-plan')).to_be_enabled()
 saved=p.request.get(url).json();assert saved['sound_plan']['scene_description']==data['sound_plan']['scene_description'] and saved['round']==0 and saved['sound_plan']['highlights']==data['sound_plan']['highlights'] and saved['sound_plan']['sound_points']==data['sound_plan']['sound_points'] and saved['sound_plan']['scene_points']==data['sound_plan']['scene_points']
 after=p.request.get(base+'/api/studio/status').json()['budget'];assert after['requests']==before['requests']+1
 assert not errors,errors
 (out/'report.json').write_text(json.dumps({'real_muse_analysis':True,'automatic_after_file_selection':True,'requests_added':1,'no_generation_before_confirmation':True,'scene_description':data['sound_plan']['scene_description'],'recommendation':data['sound_plan']['summary'],'highlights':data['sound_plan']['highlights'],'highlighted_phrases':rendered,'scene_points':data['sound_plan']['scene_points'],'sound_points':data['sound_plan']['sound_points'],'scene_preserved_on_edit':True,'no_replay_on_reload_or_metadata':True,'browser_errors':errors,'before':before,'after':after},indent=2))
 print('AUTO ANALYSIS PASSED',json.dumps({'project':pid,'scene':data['sound_plan']['scene_description'],'budget':after}),flush=True);b.close()
