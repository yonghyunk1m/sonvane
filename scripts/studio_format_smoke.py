"""Real media/trim uploads, intercepted analysis, and ratio-preserving export. No model calls."""
import json,uuid,subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright,expect
from app import video
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/studio-format-check';OUT.mkdir(parents=True,exist_ok=True)
fixtures={}
for name,size in [('portrait','180x320'),('square','240x240'),('landscape','320x180'),('ultrawide','420x180')]:
 path=OUT/(name+'.mp4')
 if not path.exists():video.run(['-f','lavfi','-i',f'testsrc2=s={size}:r=24:d=6','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',path])
 fixtures[name]=path
rotated=OUT/'rotated.mp4'
video.run(['-display_rotation','90','-i',fixtures['landscape'],'-c','copy',rotated])
fixtures['rotated']=rotated
fixtures['long']=ROOT/'artifacts/trim-check/long-source.mp4'
base='http://127.0.0.1:8765';records=[];errors=[];calls=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1440,'height':1000})
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('(id)=>{localStorage.clear();localStorage.setItem("sonvane-profile",id)}',uuid.uuid4().hex);p.reload(wait_until='networkidle')
 before=p.request.get(base+'/api/studio/status').json()['budget']['requests']
 def proposal(route):
  calls.append(route.request.url);data=p.request.get(route.request.url.removesuffix('/sound-plan')).json();duration=data['video']['duration']
  data['sound_plan']={'scene_description':'An original geometric motion test.','summary':'Soft instrumental music follows the movement.','revision':uuid.uuid4().hex,'status':'draft','model':'browser-fixture','cues':[{'id':uuid.uuid4().hex,'kind':'music','start':0,'end':duration,'description':'Soft piano, instrumental, no vocals.','reason':'Original test footage.','effect':'none','bpm':90,'gain':1,'enabled':True}]};route.fulfill(json=data)
 p.route('**/sound-plan',proposal)
 p.route('**/generate',lambda r:(_ for _ in ()).throw(AssertionError('Generation was not approved')))
 def geometry():
  return p.evaluate('''()=>{const v=document.getElementById('preview'),r=v.getBoundingClientRect();return {width:r.width,height:r.height,videoWidth:v.videoWidth,videoHeight:v.videoHeight,shape:document.body.dataset.videoShape,overflow:document.documentElement.scrollWidth>innerWidth,fit:getComputedStyle(v).objectFit,columns:getComputedStyle(document.querySelector('.result-column')).display}}''')
 for name,path in fixtures.items():
  p.locator('#video-file').set_input_files(str(path));expect(p.locator('#sound-plan-panel')).to_be_visible(timeout=30000)
  p.wait_for_function('()=>document.getElementById("preview").readyState>=2')
  pid=p.evaluate('project.id');actual=p.request.get(base+'/api/studio/projects/'+pid).json()
  for width in [320,390,768,1024,1440]:
   p.set_viewport_size({'width':width,'height':1000});g=geometry()
   assert not g['overflow'],(name,width,g)
   assert abs(g['width']/g['height']-g['videoWidth']/g['videoHeight'])<.01,(name,width,g)
   assert g['fit']=='contain'
   expected='portrait' if name in ['portrait','rotated'] else 'square' if name=='square' else 'landscape'
   assert g['shape']==expected,(name,g)
   assert g['columns']==('grid' if width>=1180 or width>=960 and expected!='landscape' else 'flex'),(name,width,g)
   records.append({'fixture':name,'viewport':width,**g})
   if width in [390,1440] and name in ['portrait','square','landscape','long']:p.screenshot(path=str(OUT/f'{name}-{width}.png'),full_page=True)
  if name=='portrait':
   # Render an original test tone into the prepared source without running any learned model.
   folder=ROOT/'.data/projects'/pid;tone=OUT/'original-tone.wav';wave=np.sin(2*np.pi*220*np.arange(6*44100)/44100)*.02;sf.write(tone,wave,44100)
   target=video.mix(folder,tone,'format-check',6,preserve_audio=False)
   p.route('**/format-test.mp4',lambda r:r.fulfill(path=str(target),content_type='video/mp4'))
   p.locator('#preview').evaluate('v=>{v.src="/format-test.mp4";v.load()}');p.wait_for_function('()=>document.getElementById("preview").readyState>=2');g=geometry();assert g['shape']=='portrait' and abs(g['videoWidth']/g['videoHeight']-9/16)<.01
  if name=='long':
   expect(p.locator('#source-overview')).to_be_visible();expect(p.locator('#source-length')).to_contain_text('0:45.0');expect(p.locator('#analysis-scope')).to_contain_text('0:00.0–0:30.0')
   assert actual['video']['duration']==30
   p.locator('#change-section').click();expect(p.locator('#trim-start')).to_be_visible()
   p.locator('#trim-start').fill('22.3');p.locator('#trim-end').fill('28.3');expect(p.locator('#source-range-label')).to_contain_text('6.0 seconds')
   marker=p.locator('#source-range-mark').evaluate('e=>({left:parseFloat(e.style.left),width:parseFloat(e.style.width)})');assert abs(marker['left']-100*22.3/45)<.01 and abs(marker['width']-100*6/45)<.01
  else:expect(p.locator('#source-overview')).to_be_hidden()
  if name=='rotated':
   count=len(calls);p.reload(wait_until='networkidle');p.wait_for_function('()=>document.body.dataset.videoShape==="portrait"');assert len(calls)==count
 assert p.request.get(base+'/api/studio/status').json()['budget']['requests']==before
 assert not errors,errors
 p.goto(base+'/demo/',wait_until='networkidle');expect(p.locator('#hero-title')).to_contain_text('Shape the sound')
 for width in [320,390,768,1440]:
  p.set_viewport_size({'width':width,'height':1000});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
 (OUT/'report.json').write_text(json.dumps({'media':records,'rotation_metadata_verified':True,'local_mix_keeps_portrait_ratio':True,'source_section_overview_verified':True,'browser_errors':errors,'model_calls':0},indent=2))
 print('PASS: six actual video formats/sources, uncropped media ratio, responsive layout, rotation, local mix, section overview; zero model calls.');b.close()
