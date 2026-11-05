"""Render repository artwork from Sonvane's original brand and approved illustrations."""
from pathlib import Path
import base64
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1];OUT=R/'docs/assets';OUT.mkdir(exist_ok=True)
def data(path,mime):return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
font=data(R/'app/static/assets/inter.woff2','font/woff2')
mark=data(R/'app/static/assets/sonvane.svg','image/svg+xml')
def art(name):return data(R/'app/static/demo'/name,'image/png')
base=f'''@font-face{{font-family:Inter;src:url({font});font-weight:100 900}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Arial,sans-serif;color:#192630}}'''
hero='''<main class="banner"><div class="brand"><img src="MARK"><b>sonvane<span>.</span></b></div><div class="copy"><h1>A sound director<br>for <em>your video.</em></h1><p>Review Muse’s plan. Create the music.<br>Choose what works for your scene.</p></div><img class="hero-art" src="ART" alt="The original creator, planning companion and TuneJury character keeping a finished soundtrack"><footer><span>Muse Spark <i>planning</i></span><span>ACE-Step <i>generation</i></span><span>TuneJury <i>evaluation</i></span></footer></main>'''.replace('MARK',mark).replace('ART',art('situation-record-v1.png'))
hero_css=base+'''body{background:#f7f5ef}.banner{position:relative;width:1600px;height:590px;overflow:hidden}.brand{position:absolute;left:48px;top:36px;display:flex;align-items:center;gap:16px}.brand img{width:66px;height:66px}.brand b{font-size:64px;font-weight:750;letter-spacing:-.07em}.brand span{color:#075ee8}.copy{position:absolute;left:52px;top:164px;z-index:1}h1{font-size:90px;line-height:1.04;letter-spacing:-4.3px;font-weight:600;margin:0 0 26px}em{font-style:normal;color:#075ee8}.copy p{font-size:32px;line-height:1.4;margin:0;color:#475661;letter-spacing:-.5px}.hero-art{position:absolute;width:760px;height:490px;right:18px;top:30px;object-fit:contain}footer{position:absolute;bottom:0;left:52px;right:52px;height:70px;border-top:1px solid #cbd1d2;display:flex;align-items:center;gap:35px;font-size:23px}footer i{font-style:normal;font-size:21px;margin-left:8px;color:#65747c}@media(max-width:900px){.banner{width:800px;height:1020px}.brand{left:38px;top:30px}.brand img{width:49px;height:49px}.brand b{font-size:47px}.copy{left:40px;top:144px}h1{font-size:76px;line-height:1.05}.copy p{font-size:28px}.hero-art{width:740px;height:490px;right:20px;top:450px}footer{left:40px;right:40px;height:70px;gap:25px;font-size:19px}footer i{display:block;font-size:16px;margin:3px 0 0}}'''
steps=[('01','Plan with Muse','situation-brief-v1.png','Show your scene.','Get a music and effects plan.'),('02','Make it yours','situation-clarify-v1.png','Adjust the timing and sound.','Approve before generation.'),('03','Listen and compare','situation-compare-v2.png','Hear three music variations.','Use TuneJury to compare.'),('04','Keep your mix','situation-record-v1.png','Choose, refine and export.','Remember preferences by choice.')]
flow='<main class="flow">'+''.join(f'<section><div class="number">{n}</div><h2>{title}</h2><img src="{art(image)}"><p>{a}<br>{b}</p></section>' for n,title,image,a,b in steps)+'</main>'
flow_css=base+'''body{background:#fff}.flow{display:grid;grid-template-columns:repeat(4,1fr);width:1600px;padding:16px 0 20px;gap:0}.flow section{min-width:0;padding:0 12px;border-right:1px solid #dbe1e3}.flow section:last-child{border:0}.number{font-size:22px;color:#075ee8;margin:5px 12px 10px}h2{font-size:31px;letter-spacing:-1.3px;font-weight:600;margin:0 12px 9px}img{display:block;width:100%;height:255px;object-fit:contain}p{font-size:23px;line-height:1.5;letter-spacing:-.4px;margin:10px 12px 0;color:#41515d}@media(max-width:900px){.flow{width:800px;grid-template-columns:1fr 1fr;row-gap:25px;padding:16px 0}.flow section:nth-child(2n){border-right:0}.flow section{padding-bottom:18px;border-bottom:1px solid #dbe1e3!important}.number{font-size:25px}h2{font-size:33px}p{font-size:25px}img{height:240px}}'''
with sync_playwright() as pw:
 b=pw.chromium.launch()
 for name,body,css in [('sonvane-banner',hero,hero_css),('sonvane-illustrated-flow',flow,flow_css)]:
  for width,suffix in [(1600,''),(800,'-mobile')]:
   p=b.new_page(viewport={'width':width,'height':1200},device_scale_factor=1)
   p.set_content(f'<html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>')
   p.evaluate('document.fonts.ready');p.wait_for_function('()=>[...document.images].every(i=>i.complete&&i.naturalWidth)')
   p.locator('main').screenshot(path=str(OUT/f'{name}{suffix}.png'));p.close()
 b.close()
print('Rendered original Sonvane brand + approved character artwork, desktop and mobile.')
