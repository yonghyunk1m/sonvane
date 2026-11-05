"""Read-only saved fixture and browser-only state transitions; no model calls."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/studio-conversation-layout';OUT.mkdir(exist_ok=True)
state=json.loads((ROOT/'artifacts/sound-plan-check/state.json').read_text())
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1000});errors=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 def read_only(route):
  assert route.request.method=='GET',route.request.url
  route.continue_()
 p.route('**/api/**',read_only)
 p.goto('http://127.0.0.1:8765/studio/',wait_until='networkidle')
 p.evaluate('(s)=>{localStorage.clear();localStorage.setItem("sonvane-profile",s.profile);localStorage.setItem("sonvane-project",s.project)}',state)
 p.reload(wait_until='networkidle')
 expect(p.locator('#chat-input')).to_be_visible()
 assert p.locator('#muse-disclosure').evaluate('e=>e.tagName')=='DIV'
 assert p.evaluate('document.getElementById("result-panel").nextElementSibling.id')=='muse-disclosure'
 expect(p.locator('#chat-examples')).to_contain_text('Lower the music')
 expect(p.locator('#conversation-title')).to_have_text('Refine with Muse')
 expect(p.locator('#chat-listen-label')).to_have_text('Share selected track · Up to 10 seconds')
 expect(p.locator('#send-chat')).to_be_disabled()
 p.locator('#result-panel [data-talk-muse]').click();expect(p.locator('#chat-input')).to_be_focused()
 p.locator('#chat-examples button').last.click()
 expect(p.locator('#chat-input')).to_have_value('Lower the music level to 15 percent. Keep the same track.')
 expect(p.locator('#send-chat')).to_be_enabled()
 p.locator('#chat-input').fill('Keep this unsent direction.')
 p.evaluate('()=>setWorkspaceTab("plan")')
 assert p.evaluate('document.getElementById("sound-plan-panel").nextElementSibling.id')=='muse-disclosure'
 expect(p.locator('#chat-examples')).to_contain_text('Explore another mood')
 expect(p.locator('#conversation-title')).to_have_text('Plan with Muse')
 expect(p.locator('#chat-listen-label')).to_have_text('Share previously created track · Up to 10 seconds')
 expect(p.locator('#chat-input')).to_have_value('Keep this unsent direction.')
 expect(p.locator('#plan-choice-summary')).to_contain_text('3 versions')
 expect(p.locator('#plan-choice-summary')).to_contain_text('12.0 seconds')
 p.evaluate('()=>{document.getElementById("preserve-audio").checked=false;document.getElementById("preserve-audio").dispatchEvent(new Event("change"))}')
 expect(p.locator('#plan-choice-summary')).to_contain_text('Mute')
 p.locator('#sound-plan-panel [data-talk-muse]').click();expect(p.locator('#chat-input')).to_be_focused()
 # A pending conversation stays visible with its draft; inputs are disabled until it finishes.
 p.evaluate('()=>{project.chat_pending=true;render()}')
 expect(p.locator('#conversation-panel')).to_be_visible();expect(p.locator('#chat-input')).to_be_disabled()
 p.evaluate('()=>{project.chat_pending=false;render()}')
 expect(p.locator('#chat-input')).to_be_enabled()
 for view in ['plan','results']:
  p.evaluate('(v)=>setWorkspaceTab(v)',view)
  for width in [320,390,768,1024,1440]:
   p.set_viewport_size({'width':width,'height':1000})
   assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(view,width)
   expect(p.locator('#chat-input')).to_be_visible()
   if width in [390,1440]:
    p.locator('#conversation-panel').screenshot(path=str(OUT/f'{view}-chat-{width}.png'))
 p.set_viewport_size({'width':1440,'height':1000});p.evaluate('()=>setWorkspaceTab("plan")')
 p.locator('#sound-plan-panel').screenshot(path=str(OUT/'plan-review.png'))
 p.locator('#conversation-panel').scroll_into_view_if_needed()
 assert p.locator('.preview-column').evaluate('e=>getComputedStyle(e).position')=='sticky'
 assert abs(p.locator('.preview-column').bounding_box()['y']-p.locator('.sonvane-header').bounding_box()['height']-16)<2
 p.screenshot(path=str(OUT/'desktop-conversation-with-video.png'))
 # Draft survives a page reload without being sent or replaying any backend work.
 p.reload(wait_until='networkidle');expect(p.locator('#chat-input')).to_have_value('Keep this unsent direction.')
 # A new project can discuss a proposal, never imply an existing soundtrack.
 p.evaluate('()=>{project.tracks=[];project.selected=null;project.renders={};project.status="ready";project.video.has_audio=false;workspaceTab="plan";render()}')
 expect(p.locator('#chat-stage')).to_have_text('Before music creation')
 expect(p.locator('#conversation-title')).to_have_text('Plan with Muse')
 expect(p.locator('#chat-guidance')).to_contain_text('No music has been created yet.')
 expect(p.locator('#chat-listen-option')).to_be_hidden()
 expect(p.locator('#chat-examples')).not_to_contain_text('Lower the music')
 p.evaluate('()=>{project.video.has_audio=true;render()}')
 expect(p.locator('#chat-listen-option')).to_be_visible()
 expect(p.locator('#chat-listen-label')).to_have_text('Share original video audio · Up to 10 seconds')
 p.locator('#conversation-panel').screenshot(path=str(OUT/'before-creation.png'))
 p.evaluate('()=>{project.status="generating";render()}')
 expect(p.locator('#progress-panel')).to_be_visible();expect(p.locator('#conversation-panel')).to_be_hidden()
 assert not errors,errors
 (OUT/'report.json').write_text(json.dumps({'conversation_visible_without_disclosure':True,'follows_active_decision':True,'draft_and_pending_state_preserved':True,'review_summary_matches_controls':True,'widths':[320,390,768,1024,1440],'browser_errors':errors,'model_calls':0},indent=2))
 print('PASS: visible conversation, plan/result placement, keyboard focus, draft persistence, busy states, decision summary, five widths; no model calls.')
 b.close()
