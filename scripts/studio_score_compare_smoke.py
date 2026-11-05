"""Real saved music auditions; selection response intercepted to preserve the user's project."""
import copy,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/score-compare-check';OUT.mkdir(exist_ok=True)
base='http://127.0.0.1:8765';pid='d80c807fe61d4624967c304eed982b98'
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1100});errors=[];writes=[]
 p.on('pageerror',lambda e:errors.append(str(e)))
 data=p.request.get(base+'/api/studio/projects/'+pid).json();original_selected=data['selected']
 selected=next(t for t in data['tracks'] if t['id']==original_selected)
 current=[t for t in data['tracks'] if t['round']==selected['round']];other=[t for t in data['tracks'] if t['round']!=selected['round']]
 assert len(current)==3 and len(other)==3
 def guard(route):
  if route.request.method!='GET':writes.append(route.request.post_data_json);raise AssertionError('Unexpected write')
  route.continue_()
 p.route('**/api/**',guard)
 p.goto(base+'/studio/',wait_until='networkidle');p.evaluate('(d)=>{localStorage.clear();localStorage.setItem("sonvane-profile",d.profile_id);localStorage.setItem("sonvane-project",d.id)}',data);p.reload(wait_until='networkidle')
 expect(p.locator('[data-listen]')).to_have_count(3)
 expect(p.locator('#jury-compare-title')).to_have_text(f'Compare 3 versions · Round {selected["round"]}')
 expect(p.locator('#generation-history')).not_to_have_attribute('open','')
 expect(p.locator('#alternatives .track')).to_have_count(3)
 expect(p.locator('#generation-history-label')).to_contain_text('3 saved versions')
 p.locator(f'[data-listen="{current[0]["id"]}"] .jury-number').click()
 audio=p.locator('#jury-audio');expect(audio).to_have_js_property('paused',False)
 expect(audio).to_have_attribute('src',f'/api/studio/projects/{pid}/audio/{current[0]["id"]}')
 audio.evaluate('a=>{a.pause();a.currentTime=5}')
 alternate=next(t for t in current if t['id']!=current[0]['id'])
 p.locator(f'[data-listen="{alternate["id"]}"]').click();expect(audio).to_have_js_property('paused',False)
 assert 4.99<=audio.evaluate('a=>a.currentTime')<6
 assert p.evaluate('project.selected')==original_selected
 assert not writes
 expect(p.locator('#jury-preview-name')).to_contain_text(alternate['name'])
 p.locator(f'[data-listen="{alternate["id"]}"]').click();expect(audio).to_have_js_property('paused',True)
 p.locator(f'[data-listen="{alternate["id"]}"]').focus();p.keyboard.press('Enter');expect(audio).to_have_js_property('paused',False)
 p.locator('#jury-verdict').screenshot(path=str(OUT/'desktop.png'))
 # Observe the selection request without changing the user's stored choice or learning a preference.
 chosen=next(t for t in current if t['id']!=original_selected)
 if chosen['id']!=alternate['id']:
  p.locator(f'[data-listen="{chosen["id"]}"]').click();expect(audio).to_have_js_property('paused',False)
 picks=[]
 def pick(route):
  picks.append(route.request.post_data_json)
  fixture=copy.deepcopy(data);fixture['selected']=chosen['id'];fixture['selected_by']='listener';fixture['renders'][chosen['id']]=fixture['renders'][original_selected]
  route.fulfill(json=fixture)
 p.route('**/select',pick)
 # An existing local render is used only for this intercepted UI selection fixture.
 p.route('**/preview?*',lambda route:route.fulfill(path=str(ROOT/'.data/projects'/pid/data['renders'][original_selected]),content_type='video/mp4'))
 p.locator('#jury-use-track').click();expect(p.locator('#selected-name')).to_contain_text(chosen['name'])
 assert picks==[{'track_id':chosen['id'],'remember':False,'compared_with':None}],picks
 expect(p.locator('#jury-use-track')).to_be_disabled()
 for width in [320,390,768,1024,1440]:
  p.set_viewport_size({'width':width,'height':1100});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  if width==390:p.locator('#jury-verdict').screenshot(path=str(OUT/'mobile.png'))
 # Revisiting an older choice compares only its own round and puts the other round into history.
 old=other[0]
 p.evaluate('(id)=>{project.selected=id;project.renders[id]=Object.values(project.renders)[0];render()}',old['id'])
 expect(p.locator('#jury-compare-title')).to_have_text(f'Compare 3 versions · Round {old["round"]}')
 assert set(p.locator('[data-listen]').evaluate_all('es=>es.map(e=>e.dataset.listen)'))=={t['id'] for t in other}
 expect(p.locator('#jury-preview')).to_be_hidden()
 expect(p.locator('#alternatives .track')).to_have_count(3)
 p.evaluate('()=>{setWorkspaceTab("plan")}');expect(p.locator('#approve-sound-plan')).to_have_text('Make 3 more versions')
 assert p.request.get(base+'/api/studio/projects/'+pid).json()['selected']==original_selected
 assert not errors,errors
 (OUT/'report.json').write_text(json.dumps({'actual_audio_audition':True,'same_position_switch':True,'audition_does_not_select':True,'explicit_apply_request_verified':True,'selection_intercepted':True,'three_current_three_archived':True,'old_round_isolation':True,'browser_errors':errors,'meta_calls':0},indent=2))
 print('PASS: score-click auditions, aligned switching, explicit selection wiring, grouped history, round isolation and five widths; user selection unchanged, no Meta calls.')
 b.close()
