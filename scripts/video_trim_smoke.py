"""Real local clip upload + browser controls; generation is intercepted, no paid calls."""
import json,subprocess,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from app.video import FFMPEG
root=Path(__file__).resolve().parents[1];out=root/'artifacts/trim-check';out.mkdir(parents=True,exist_ok=True)
source=out/'long-source.mp4'
if not source.exists():
    subprocess.run([FFMPEG,'-y','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=24:d=45',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=45','-c:v','libx264','-threads','2',
        '-c:a','aac',str(source)],check=True)
base='http://127.0.0.1:8765'
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);p=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('id=>localStorage.setItem("sonvane-profile",id)',uuid.uuid4().hex);p.reload(wait_until='networkidle')
    before=p.request.get(base+'/api/studio/status').json()['budget']['requests']
    p.evaluate('nextFileManual=true');p.locator('#video-file').set_input_files(str(source));p.locator('#trim-panel').evaluate('e=>e.open=true');expect(p.locator('#trim-source')).to_contain_text('0:45.0')
    expect(p.locator('#create')).to_be_enabled()
    p.locator('#trim-start').fill('1.1');p.locator('#trim-end').fill('4.1');expect(p.locator('#create')).to_be_enabled()
    p.locator('#trim-start').fill('0');p.locator('#trim-end').fill('31');expect(p.locator('#create')).to_be_disabled();expect(p.locator('#send-chat')).to_be_disabled()
    p.locator('#trim-start').fill('22.3');p.locator('#trim-end').fill('28.3');expect(p.locator('#trim-status')).to_contain_text('6.0 seconds selected')
    p.locator('#preview').evaluate('v=>v.muted=true');p.locator('#preview-section').click();p.wait_for_timeout(700)
    assert 22.3<=p.locator('#preview').evaluate('v=>v.currentTime')<24
    p.locator('#preview').evaluate('v=>v.currentTime=28.35');p.wait_for_timeout(250);assert p.locator('#preview').evaluate('v=>v.paused')
    p.screenshot(path=str(out/'selection-desktop.png'),full_page=True)
    for width in (390,320):
        p.set_viewport_size({'width':width,'height':844});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
    p.screenshot(path=str(out/'selection-mobile.png'),full_page=True)
    p.get_by_role('navigation').get_by_text('Overview',exact=True).click();p.wait_for_url('**/demo/')
    p.get_by_role('navigation').get_by_text('Studio',exact=True).click();p.wait_for_url('**/studio/');p.wait_for_load_state('networkidle')
    p.evaluate('nextFileManual=true');p.locator('#video-file').set_input_files(str(source));p.locator('#trim-panel').evaluate('e=>e.open=true');expect(p.locator('#trim-start')).to_have_value('22.3');expect(p.locator('#trim-end')).to_have_value('28.3')
    def no_generation(route):
        pid=route.request.url.split('/')[-2]
        response=p.request.get(base+f'/api/studio/projects/{pid}');route.fulfill(json=response.json())
    p.route('**/generate',no_generation)
    p.locator('.quick-mode').evaluate('e=>e.open=true');p.locator('#create').click();expect(p.locator('#trim-panel')).to_be_hidden(timeout=20000)
    expect(p.locator('#clip-origin')).to_contain_text('0:22.3–0:28.3')
    pid=p.evaluate('localStorage.getItem("sonvane-project")');data=p.request.get(base+f'/api/studio/projects/{pid}').json()
    assert data['video']['duration']==6 and data['video']['selection']['start']==22.3
    p.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');p.wait_for_timeout(600)
    assert 5.9<=p.locator('#preview').evaluate('v=>v.duration')<=6.1
    assert p.request.get(base+'/api/studio/status').json()['budget']['requests']==before
    assert not errors,errors
    p.screenshot(path=str(out/'trimmed-project.png'),full_page=True)
    (out/'report.json').write_text(json.dumps({'project':pid,'selection':data['video']['selection'],'preview_stops_at_end':True,'draft_restored':True,'mobile_widths':[390,320],'browser_errors':errors,'meta_calls':0,'generation_intercepted':True},indent=2))
    print('PASS: actual clip upload, preview bounds, draft restoration, mobile layouts; zero Meta requests.');browser.close()
