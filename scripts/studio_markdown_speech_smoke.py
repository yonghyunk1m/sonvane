"""Browser checks using saved replies and locally cached speech. No Meta calls."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/markdown-speech-check'
state=json.loads((OUT/'state.json').read_text());base='http://127.0.0.1:8765'
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1100});errors=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto(base+'/studio/',wait_until='networkidle')
 p.evaluate('(s)=>{localStorage.clear();localStorage.setItem("sonvane-profile",s.profile);localStorage.setItem("sonvane-project",s.project)}',state)
 p.reload(wait_until='networkidle')
 article=p.locator(f'[data-turn="{state["turn"]}"]');body=article.locator('.chat-markdown')
 assert body.locator('strong').count()>0 and body.locator('li').count()==3
 assert '**' not in body.inner_text()
 dom_words=body.evaluate('e=>{const words=[];for(const w of e.querySelectorAll("[data-word]")){const i=Number(w.dataset.word);words[i]=(words[i]||"")+w.textContent;}return words}')
 assert dom_words==[w['text'] for w in state['speech']['words']],(len(dom_words),len(state['speech']['words']))
 body.screenshot(path=str(OUT/'markdown-desktop.png'))
 # Actual waveform: click a word and seek to its model-derived time.
 word_index=24;target=state['speech']['words'][word_index]['start']
 body.locator(f'[data-word="{word_index}"]').first.click()
 expect(p.locator('#reply-audio')).to_have_js_property('paused',False)
 time=p.locator('#reply-audio').evaluate('a=>a.currentTime');assert target<=time<target+1,(target,time)
 p.locator('#reply-audio').evaluate('(a,t)=>{a.pause();a.currentTime=t}',target+.02)
 expect(body.locator('.is-speaking')).to_have_count(1)
 expect(body.locator('.is-speaking')).to_have_text(state['speech']['words'][word_index]['text'])
 body.screenshot(path=str(OUT/'word-highlight.png'))
 # A second word reuses the same cached waveform and supports keyboard access.
 later=35;word=body.locator(f'[data-word="{later}"]').first;word.focus();word.press('Enter')
 expect(p.locator('#reply-audio')).to_have_js_property('paused',False)
 assert p.locator('#reply-audio').evaluate('a=>a.currentTime')>=state['speech']['words'][later]['start']-.01
 # Starting the video stops narration, and clears word highlighting.
 p.locator('#preview').evaluate('async v=>{v.muted=true;v.currentTime=0;await v.play()}')
 expect(p.locator('#reply-audio')).to_have_js_property('paused',True)
 expect(body.locator('.is-speaking')).to_have_count(0)
 # Delayed speech cannot hijack a video that the user started in the meantime.
 pending=[];speech_url=f'**/speech/{state["turn"]}'
 p.route(speech_url,lambda route:pending.append(route))
 p.evaluate('speechCache.clear()');article.locator('[data-speak]').click()
 p.wait_for_timeout(150);assert pending
 p.locator('#preview').evaluate('async v=>{v.pause();v.currentTime=0;await v.play()}')
 pending[0].fulfill(json=state['speech']);p.wait_for_timeout(400)
 assert not p.locator('#preview').evaluate('v=>v.paused')
 assert p.locator('#reply-audio').evaluate('v=>v.paused')
 p.unroute(speech_url)
 # A background generation finishing must not replace a currently playing source video.
 p.evaluate('()=>{window.completedFixture=structuredClone(project);project.selected=null;project.renders={};project.tracks=[];project.status="generating";mixSignature="";previewMode="mix";render()}')
 p.locator('#preview').evaluate('async v=>{v.muted=true;await v.play()}')
 p.evaluate('()=>{project=window.completedFixture;render()}')
 assert p.locator('#preview').get_attribute('src').endswith('/source')
 assert not p.locator('#preview').evaluate('v=>v.paused')
 # Raw HTML and unsafe links cannot execute or load remote images.
 malicious='**Bold**\n\n- One\n- Two\n\n<img src=x onerror=alert(1)> [bad](javascript:alert(1)) ![alt](https://invalid.example/image.png)\n\n`<script>alert(1)</script>`'
 safe=p.evaluate('(text)=>{const d=document.createElement("div");d.innerHTML=chatMarkdown.render(text);return {strong:d.querySelectorAll("strong").length,items:d.querySelectorAll("li").length,images:d.querySelectorAll("img").length,scripts:d.querySelectorAll("script").length,unsafe:Array.from(d.querySelectorAll("a")).some(a=>a.protocol==="javascript:")}}',malicious)
 assert safe=={'strong':1,'items':2,'images':0,'scripts':0,'unsafe':False},safe
 # Inline emphasis boundaries share a single word index, including trailing punctuation.
 inline=p.evaluate('()=>{const d=document.createElement("div");d.innerHTML=chatMarkdown.render("**direction**: stay calm.");speechWords(d);return Array.from(d.querySelectorAll("[data-word=\\"0\\"]"),e=>e.textContent).join("")}')
 assert inline=='direction:'
 for width in [320,390,768,1024,1440]:
  p.set_viewport_size({'width':width,'height':1100});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  if width==390:article.screenshot(path=str(OUT/'markdown-mobile.png'))
 assert not errors,errors
 (OUT/'browser-report.json').write_text(json.dumps({'markdown_rendered':True,'word_count':len(dom_words),'actual_word_seek_and_highlight':True,'keyboard_word_seek':True,'delayed_speech_does_not_interrupt_video':True,'completed_generation_preserves_video_playback':True,'unsafe_markup_blocked':True,'widths':[320,390,768,1024,1440],'browser_errors':errors,'meta_calls':0},indent=2))
 print('PASS: Markdown, actual timed speech, word seeking, playback races, safe markup and five widths; no Meta calls.')
 b.close()
