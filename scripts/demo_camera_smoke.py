"""Real local face inference on a synthetic camera stream, plus camera lifecycle checks."""
import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('SONVANE_TEST_URL','http://127.0.0.1:8765')
PORTRAIT=Path(os.environ.get('SONVANE_FACE_FIXTURE','/tmp/sonvane-face-portrait.jpg'))
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1100});errors=[];remote=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.on('request',lambda r:remote.append(r.url) if not r.url.startswith(BASE) else None)
 p.route('**/test-face.jpg',lambda route:route.fulfill(body=PORTRAIT.read_bytes(),content_type='image/jpeg'))
 p.goto(BASE+'/demo/',wait_until='networkidle')
 p.evaluate("""async()=>{
  window.cameraCalls=[];window.cameraTest=document.createElement('canvas');cameraTest.width=640;cameraTest.height=480;
  const img=new Image();img.src='/test-face.jpg';await img.decode();
  window.drawFace=scale=>{const ctx=cameraTest.getContext('2d');ctx.fillStyle='#ddd';ctx.fillRect(0,0,640,480);if(scale){const h=480*scale,w=460/500*h;ctx.drawImage(img,180,0,460,500,(640-w)/2,(480-h)/2,w,h)}};
  drawFace(.75);
  window.testStreams=[];navigator.mediaDevices.getUserMedia=async constraints=>{cameraCalls.push(constraints);const stream=cameraTest.captureStream(15);testStreams.push(stream);return stream};
  window.cameraRefresh=setInterval(()=>{const ctx=cameraTest.getContext('2d');ctx.fillStyle='#ddd';ctx.fillRect(0,0,1,1)},60);
 }""")
 assert p.evaluate('cameraCalls.length')==0
 assert p.evaluate('heroSound.context===null')
 toggle=p.locator('#face-volume-toggle');toggle.click()
 p.wait_for_function('()=>faceVolume.reference!==null',timeout=30000)
 assert p.evaluate('cameraCalls.length===1 && cameraCalls[0].audio===false')
 assert p.evaluate('heroSound.context===null'), 'Camera implicitly started music'
 p.locator('#hero-sound-toggle').click();p.wait_for_timeout(900)
 base=p.evaluate('heroSound.graph.distance.gain.value');assert .8<base<1.2,base
 p.evaluate('drawFace(1)');p.wait_for_timeout(1800)
 near=p.evaluate('heroSound.graph.distance.gain.value');assert near>base*1.15,('Closer face not louder',base,near)
 p.evaluate('drawFace(.5)');p.wait_for_timeout(1800)
 far=p.evaluate('heroSound.graph.distance.gain.value');assert far<base*.8,('Farther face not quieter',base,far)
 p.evaluate('drawFace(0)');p.wait_for_timeout(2000)
 assert abs(p.evaluate('heroSound.graph.distance.gain.value')-1)<.1, 'No-face recovery failed'
 toggle.click();assert p.evaluate('testStreams.every(s=>s.getTracks().every(t=>t.readyState==="ended")) && faceVolume.worker===null')
 # A permission denial is visible and does not leave a camera or altered volume behind.
 p.evaluate("()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError')}}")
 toggle.click();p.wait_for_function('()=>!faceVolume.wanted')
 assert 'declined' in p.locator('#face-volume-state').inner_text()
 # Turning off before a permission request resolves must close a late stream.
 p.evaluate('()=>{navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>window.resolveCamera=resolve)}')
 toggle.click();toggle.click()
 p.evaluate('window.lateStream=cameraTest.captureStream(15);resolveCamera(lateStream)');p.wait_for_timeout(100)
 assert p.evaluate('lateStream.getTracks().every(t=>t.readyState==="ended") && faceVolume.worker===null')
 # Tab hiding must release actual acquired tracks and cancel model initialization.
 p.evaluate('()=>{navigator.mediaDevices.getUserMedia=async()=>{const s=cameraTest.captureStream(15);testStreams.push(s);return s}}')
 toggle.click();p.wait_for_function('()=>faceVolume.stream!==null')
 p.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
 assert p.evaluate('!faceVolume.wanted && !faceVolume.worker && testStreams.every(s=>s.getTracks().every(t=>t.readyState==="ended"))')
 assert not remote,remote
 assert not errors,errors
 out=ROOT/'artifacts/sculpture-check';out.mkdir(parents=True,exist_ok=True)
 (out/'camera-report.json').write_text(json.dumps({'real_local_face_inference':True,'base_gain':base,'near_gain':near,'far_gain':far,'no_face_recovery':True,'permission_denial':True,'late_stream_cleanup':True,'hidden_tab_cleanup':True,'external_requests':remote,'page_errors':errors},indent=2))
 print(f'PASS: real face detection, distance volume {far:.2f} < {base:.2f} < {near:.2f}, no-face recovery, opt-in and camera cleanup; no external requests.')
 b.close()
