"""Original synthetic fixtures; results are functional checks, not human quality evidence."""
import argparse,json,time,uuid,subprocess
import imageio_ffmpeg
from pathlib import Path
import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser(description='Real conversation, voice and region-edit integration check; seven bounded Meta requests.')
parser.add_argument('--live',action='store_true');args=parser.parse_args()
if not args.live:raise SystemExit('Pass --live to permit real Meta requests and local model generation.')
root=Path(__file__).resolve().parents[1];out=root/'artifacts/conversation-check';out.mkdir(parents=True,exist_ok=True);profile=uuid.uuid4().hex
source=root/'artifacts/studio-check/source.mp4'
if not source.exists():
 source=out/'synthetic-video.mp4'
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=12','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
voice=out/'voice-fixture.wav'
if not voice.exists():
 job=out/'voice-job.json';job.write_text(json.dumps({'text':'Please lower the music level to fifteen percent. Keep the same track.','output':str(voice)}))
 subprocess.run([str(root/'.models/speech-env/bin/python'),str(root/'scripts/synthesize_speech.py'),str(job)],check=True,cwd=root)
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',f'--use-file-for-fake-audio-capture={out/"voice-fixture.wav"}'])
 p=b.new_page(viewport={'width':1440,'height':1100},permissions=['microphone']);errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto('http://127.0.0.1:8765/studio/',wait_until='networkidle');p.evaluate('(id)=>{localStorage.clear();localStorage.setItem("sonvane-profile",id)}',profile);p.reload(wait_until='networkidle')
 before=p.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget'];pid=None
 def state():return p.request.get(f'http://127.0.0.1:8765/api/studio/projects/{pid}').json()
 def chat(message,expected,remember=False):
  global pid
  p.locator('#chat-input').fill(message);p.locator('#chat-memory').set_checked(remember);p.locator('#send-chat').click()
  deadline=time.monotonic()+180;data=None
  while time.monotonic()<deadline:
   pid=p.evaluate('localStorage.getItem("sonvane-project")')
   if pid:
    data=state();turns=[t for t in data.get('conversation',[]) if t['role']=='assistant']
    if turns and turns[-1].get('id')!=chat.last and not data.get('chat_pending'):
     turn=turns[-1];chat.last=turn['id'];print('CHAT',turn,flush=True)
     assert turn['action']==expected and turn['action_status']!='error',turn
     break
    if data.get('conversation',[]) and data['conversation'][-1]['role']=='system':raise AssertionError(data['conversation'][-1])
   p.wait_for_timeout(500)
  else:raise AssertionError('Chat timed out')
  for _ in range(30):
   if not p.locator('#chat-input').is_disabled():break
   p.wait_for_timeout(200)
  return data
 chat.last=None
 def await_music(round):
  deadline=time.monotonic()+900;last=None
  while time.monotonic()<deadline:
   data=state()
   if data['message']!=last:print(data['status'],data['message'],flush=True);last=data['message']
   if data['round']>=round and data['status'] in ('complete','error','cancelled'):break
   p.wait_for_timeout(1200)
  assert data['status']=='complete',data.get('error');p.wait_for_timeout(2300);return data
 p.evaluate('document.body.classList.add(\"has-video\");document.getElementById(\"video-tools\").classList.remove(\"hidden\");document.getElementById(\"video-settings\").open=true');p.locator('.input-preferences').evaluate('e=>e.open=true');p.locator('#context').select_option('travel');p.evaluate('nextFileManual=true');p.locator('#video-file').set_input_files(str(source))
 chat('Create a quiet instrumental soundtrack for this synthetic video. Warm piano and soft strings, no vocals.', 'generate')
 first=await_music(1);assert len(first['tracks'])==3
 (out/'state.json').write_text(json.dumps({'project':pid,'profile':profile,'before':before},indent=2))
 # Browser captures a known locally synthesized sentence, encodes WAV, sends to real Muse transcription.
 p.locator('#record-voice').click();p.wait_for_timeout(min(29000,int(sf.info(voice).duration*1000)+200));p.locator('#record-voice').click()
 for _ in range(180):
  if 'Review your words' in p.locator('#voice-status').inner_text():break
  p.wait_for_timeout(500)
 transcript=p.locator('#chat-input').input_value();print('VOICE TRANSCRIPT',transcript,flush=True)
 assert 'fifteen' in transcript.lower() or '15' in transcript,transcript
 chat(transcript,'mix');mixed=state();assert mixed['round']==1 and len(mixed['tracks'])==3
 assert abs(mixed['mix_settings']['level']-.15)<.001
 parent=mixed['selected'];original=next(t for t in json.loads((root/f'.data/projects/{pid}/project.json').read_text())['tracks'] if t['id']==parent)
 chat('Keep the exact same music before 8 seconds and after 11 seconds. Change only the section from 8 to 11 seconds: quieter warm piano, no percussion. Please make this section edit now.','edit_region')
 edited=await_music(2);assert len(edited['tracks'])==6
 on_disk=json.loads((root/f'.data/projects/{pid}/project.json').read_text());source,sr=sf.read(original['path'],always_2d=True,dtype='int16')
 for track in on_disk['tracks']:
  if track['id'] not in edited['active_ids']:continue
  new,rate=sf.read(track['path'],always_2d=True,dtype='int16');assert rate==sr
  assert track['edit_region']=={'source_id':parent,'start':8.,'end':11.}
  assert np.array_equal(new[:8*sr],source[:8*sr]) and np.array_equal(new[11*sr:],source[11*sr:])
  assert not np.array_equal(new[8*sr:11*sr],source[8*sr:11*sr])
 chat('Remember this direction for my travel videos: warm piano, no heavy percussion. Save the direction only; do not generate more music.','remember',True)
 assert len(state()['profile']['notes'])==1
 p.get_by_role('navigation').get_by_text('Overview',exact=True).click();p.wait_for_url('**/demo/');p.get_by_role('navigation').get_by_text('Studio',exact=True).click();p.wait_for_url('**/studio/');p.wait_for_timeout(700)
 assert p.locator('.chat-message.assistant').count()==4
 p.locator('[data-speak]').last.click();p.locator('#voice-output').wait_for(state='visible',timeout=100000)
 p.locator('#reply-audio').evaluate('async a=>{a.muted=true;await a.play()}');p.wait_for_timeout(600);assert p.locator('#reply-audio').evaluate('a=>a.currentTime>0')
 p.locator('#stop-speaking').click();assert p.locator('#reply-audio').evaluate('a=>a.paused')
 p.screenshot(path=str(out/'desktop.png'),full_page=True)
 for width in [390,320]:
  p.set_viewport_size({'width':width,'height':844});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth');p.screenshot(path=str(out/f'mobile-{width}.png'),full_page=True)
 p.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}');p.wait_for_timeout(600);assert p.locator('#preview').evaluate('v=>v.currentTime')>0
 after=p.request.get('http://127.0.0.1:8765/api/studio/status').json()['budget'];assert after['requests']==before['requests']+7,(before,after)
 assert not errors,errors
 (out/'report.json').write_text(json.dumps({'project':pid,'profile':profile,'voice_transcript':transcript,'conversation_actions':['generate','mix','edit_region','remember'],'unchanged_pcm_outside_edit':True,'generated_candidates':6,'browser_errors':errors,'before':before,'after':after,'fixture':'Original synthetic video and locally synthesized voice; not a human quality study.'},indent=2))
 print('CONVERSATION CHECK PASSED',after,flush=True);b.close()
