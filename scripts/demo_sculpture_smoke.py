"""Browser checks for continuous motion, local pointer response and direct rotation."""
import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/sculpture-check';OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1100});errors=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto(os.environ.get('SONVANE_TEST_URL','http://127.0.0.1:8765')+'/demo/',wait_until='networkidle')
 assert p.locator('#listening,[data-play],[data-choose],#brief-link').count()==0
 assert p.locator('.closing-cta').get_attribute('href')=='/studio/'
 canvas=p.locator('#sound-sculpture')
 assert p.evaluate('heroSound.context===null'), 'Audio started without a gesture'
 assert p.locator('#motion-toggle,#sculpture-flip,#sculpture-reset,#motion-state').count()==0
 snapshot=lambda:canvas.evaluate('c=>c.toDataURL()')
 moving=snapshot();p.wait_for_timeout(180);assert moving!=snapshot(),'Automatic motion missing'
 box=canvas.bounding_box();x=min(box['x']+box['width']*.55,1300);y=box['y']+box['height']*.45
 canvas.focus();p.keyboard.press('ArrowRight')
 assert canvas.evaluate('c=>getComputedStyle(c).outlineStyle')!='none'
 p.mouse.move(x,y);p.mouse.down();before=p.evaluate('visualTime')
 assert canvas.evaluate('c=>getComputedStyle(c).outlineStyle')=='none', 'Pointer drag shows focus rectangle'
 p.mouse.move(x+100,y+65,steps=10);p.wait_for_timeout(100)
 assert p.evaluate('visualTime')>before,'Dragging stopped automatic motion'
 assert p.evaluate('rotation.x!==0 && rotation.y!==0')
 p.mouse.up();p.mouse.move(5,5);released=snapshot();p.wait_for_timeout(180)
 assert released!=snapshot(),'Releasing stopped automatic motion'
 # Hover over the projected ribbon, then check a local response and smooth return.
 for fraction in [.3,.4,.5,.6,.7]:
  p.mouse.move(min(box['x']+box['width']*fraction,1380),box['y']+box['height']*.49)
  p.wait_for_timeout(150)
  if p.evaluate('points.some(p=>Math.hypot(p.offsetX,p.offsetY)>2)'):break
 assert p.evaluate('points.some(p=>Math.hypot(p.offsetX,p.offsetY)>2)'), 'Hover has no particle response'
 assert p.evaluate('points.some(p=>Math.hypot(p.offsetX,p.offsetY)<.01)'), 'Hover moved the whole sculpture'
 p.mouse.move(5,5);p.wait_for_timeout(1200)
 assert p.evaluate('points.every(p=>p.offsetX===0 && p.offsetY===0)'), 'Particles did not settle'
 before=p.evaluate('rotation.y');canvas.focus();p.keyboard.press('ArrowRight');assert p.evaluate('rotation.y')!=before
 p.keyboard.press('Shift+ArrowRight');assert p.evaluate('rotation.z')!=0
 p.keyboard.press('Home');assert p.evaluate('rotation.x===0 && rotation.y===0 && rotation.z===0')
 # Verify the real audio graph produces samples and responds without stopping playback.
 sound=p.locator('#hero-sound-toggle');sound.click();p.wait_for_timeout(650)
 assert sound.get_attribute('aria-pressed')=='true'
 assert p.evaluate('heroSound.context.state==="running" && heroSound.level>.001'), 'No audio output'
 assert p.evaluate('heroSound.voices.size>0')
 p.mouse.move(5,5);p.wait_for_timeout(700)
 baseline=p.evaluate('({pan:heroSound.graph.pan.pan.value,tone:heroSound.graph.filter.frequency.value,echo:heroSound.graph.wet.gain.value,time:heroSound.context.currentTime,step:heroSound.step})')
 # Aim at a real visible particle rather than an arbitrary position in the canvas.
 target=p.evaluate("""()=>{const c=document.querySelector('#sound-sculpture'),r=c.getBoundingClientRect();return points.map(p=>({x:p.screenX+r.x,y:p.screenY+r.y})).find(p=>p.x>innerWidth*.65&&p.x<innerWidth-40&&p.y>r.y+80&&p.y<r.bottom-120&&document.elementFromPoint(p.x,p.y)===c)}""")
 assert target, 'No visible particle to hover'
 p.mouse.move(target['x'],target['y']);p.wait_for_timeout(350)
 assert p.evaluate('pointer.proximity')>.6, 'Hover did not reach particles'
 assert p.evaluate('heroSound.graph.presence.type')=='peaking'
 assert p.evaluate('heroSound.graph.presence.gain.value')>5, 'Hover presence boost missing'
 # Sample distant intrinsic positions on the ribbon with motion temporarily reduced.
 p.emulate_media(reduced_motion='reduce');p.wait_for_timeout(100)
 targets=p.evaluate("""()=>{const c=document.querySelector('#sound-sculpture'),r=c.getBoundingClientRect();const ps=points.map(p=>({x:p.screenX+r.x,y:p.screenY+r.y,tone:(1-Math.cos(p.u))/2})).filter(p=>p.x>0&&p.x<innerWidth-20&&p.y>r.y+30&&p.y<r.bottom-130&&document.elementFromPoint(p.x,p.y)===c).sort((a,b)=>a.tone-b.tone);return [ps[0],ps[ps.length-1]]}""")
 frequencies=[]
 for target in targets:
  p.mouse.move(target['x'],target['y']);p.wait_for_timeout(650)
  frequencies.append(p.evaluate('heroSound.graph.presence.frequency.value'))
  response=p.evaluate("""()=>{const f=heroSound.graph.presence,frequencies=new Float32Array([f.frequency.value/3,f.frequency.value,f.frequency.value*3]),m=new Float32Array(3),phase=new Float32Array(3);f.getFrequencyResponse(frequencies,m,phase);return [...m]}""")
  assert response[1]>max(response[0],response[2])*1.5, 'Selected frequency band is not emphasized'
 assert frequencies[1]>frequencies[0]*3, ('Curve did not select different frequency bands',frequencies)
 p.emulate_media(reduced_motion='no-preference')
 p.mouse.move(5,5);p.wait_for_timeout(800)
 assert p.evaluate('heroSound.graph.presence.gain.value')<.1, 'Hover boost did not settle'
 assert abs(p.evaluate('heroSound.graph.filter.frequency.value')-baseline['tone'])<25, 'Tone did not settle after leaving'
 # Read actual left/right output samples, including the echo path.
 p.evaluate("""()=>{const c=heroSound.context,s=c.createChannelSplitter(2);window.stereoMeters=[c.createAnalyser(),c.createAnalyser()];heroSound.graph.analyser.connect(s);stereoMeters.forEach((a,i)=>{a.fftSize=2048;s.connect(a,i)});window.stereoEnergy=()=>stereoMeters.map(a=>{const data=new Float32Array(a.fftSize);a.getFloatTimeDomainData(data);return data.reduce((sum,v)=>sum+v*v,0)/data.length})}""")
 p.wait_for_timeout(200);left,right=p.evaluate('stereoEnergy()')
 assert left>right*1.4, ('Front stereo emphasis missing',left,right)
 # Exercise exact half turns: the old sine-only panning was identical at 0 and pi.
 canvas.focus();p.keyboard.press('Home')
 for _ in range(18):p.keyboard.press('ArrowRight')
 p.wait_for_timeout(800)
 assert p.evaluate('heroSound.graph.pan.pan.value')>.3 and baseline['pan']<-.3, 'Half turn did not swap stereo position'
 left,right=p.evaluate('stereoEnergy()');assert right>left*1.4, ('Back stereo emphasis missing',left,right)
 assert p.evaluate('heroSound.graph.filter.frequency.value')<baseline['tone']*.7, 'Horizontal flip did not change timbre'
 assert p.evaluate('heroSound.graph.wet.gain.value')>baseline['echo']+.1, 'Flip did not change echo'
 for _ in range(18):p.keyboard.press('ArrowRight')
 p.wait_for_timeout(800)
 assert abs(p.evaluate('heroSound.graph.pan.pan.value')-baseline['pan'])<.03, 'Full turn did not restore stereo position'
 assert abs(p.evaluate('heroSound.graph.filter.frequency.value')-baseline['tone'])<25, 'Full turn did not restore timbre'
 p.keyboard.press('Home')
 for _ in range(18):p.keyboard.press('ArrowDown')
 p.wait_for_timeout(800)
 assert p.evaluate('heroSound.graph.pan.pan.value')>.3, 'Vertical flip did not swap stereo position'
 assert p.evaluate('heroSound.graph.filter.frequency.value')<baseline['tone']*.7, 'Vertical flip did not change timbre'
 assert p.evaluate('heroSound.context.currentTime')>baseline['time']+3
 assert p.evaluate('heroSound.step')>baseline['step'], 'Interaction restarted the music'
 p.keyboard.press('Home')
 p.locator('[data-mood="night"]').click();p.wait_for_timeout(350)
 assert p.evaluate('heroSound.mood==="night" && heroSound.graph!==null && heroSound.level>.001')
 sound.click();p.wait_for_timeout(350)
 assert p.evaluate('heroSound.graph===null && heroSound.voices.size===0 && !heroSound.wanted')
 # A late audio start must not survive immediate cancellation.
 p.evaluate('heroSound.stop();heroSound.start(mood);heroSound.stop()');p.wait_for_timeout(250)
 assert p.evaluate('heroSound.graph===null && !heroSound.wanted')
 sound.click();p.wait_for_timeout(200)
 p.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
 assert p.evaluate('heroSound.graph===null && !heroSound.wanted')
 p.evaluate("delete document.hidden")
 p.locator('[data-mood="focus"]').click();p.mouse.move(5,5)
 p.locator('.hero').screenshot(path=str(OUT/'desktop.png'))
 for width in [320,390,768,1024,1440]:
  p.set_viewport_size({'width':width,'height':1100});p.wait_for_timeout(80)
  assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  if width==390:p.locator('.hero').screenshot(path=str(OUT/'mobile.png'))
 p.emulate_media(reduced_motion='reduce');p.reload(wait_until='networkidle');p.wait_for_timeout(100)
 frozen=snapshot();p.wait_for_timeout(180);assert snapshot()==frozen
 canvas.focus();p.keyboard.press('ArrowRight');p.wait_for_timeout(80);assert snapshot()!=frozen
 touch=b.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
 touch.on('pageerror',lambda e:errors.append(str(e)));touch.goto(os.environ.get('SONVANE_TEST_URL','http://127.0.0.1:8765')+'/demo/',wait_until='networkidle')
 c=touch.locator('#sound-sculpture');c.scroll_into_view_if_needed();r=c.bounding_box();tx=195;ty=r['y']+r['height']/2
 session=touch.context.new_cdp_session(touch)
 session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':tx,'y':ty}]})
 session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':tx+65,'y':ty-45}]})
 session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
 touch.wait_for_timeout(100);assert touch.evaluate('rotation.x!==0 && rotation.y!==0 && drag===null && !pointer.active')
 moving=c.evaluate('c=>c.toDataURL()');touch.wait_for_timeout(150);assert c.evaluate('c=>c.toDataURL()')!=moving
 assert not errors,errors
 (OUT/'report.json').write_text(json.dumps({'continuous_motion_during_and_after_drag':True,'local_pointer_response_and_return':True,'keyboard':True,'reduced_motion':True,'real_touch_drag':True,'audible_signal_and_interactive_tone':True,'particle_proximity_and_return':True,'horizontal_and_vertical_flip_timbre':True,'full_turn_restores_tone':True,'actual_stereo_output_swaps_on_flip':True,'stronger_hover_and_release':True,'curve_frequency_sweep_and_eq_response':True,'audio_stop_and_cancellation':True,'widths':[320,390,768,1024,1440],'browser_errors':errors},indent=2))
 print('PASS: continuous motion, local pointer response and return, keyboard, reduced motion, touch, responsive layout, audio output, particle proximity, horizontal/vertical flip timbre, actual stereo swap, stronger hover, full-turn recovery and audio lifecycle.')
 b.close()
