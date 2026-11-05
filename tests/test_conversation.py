import io,json,uuid
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from app import conversation as talk, studio, store, personalization as prefs
from app.main import app

@pytest.fixture
def project(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'DATA',tmp_path);monkeypatch.delenv('MODEL_API_KEY',raising=False);monkeypatch.delenv('META_API_KEY',raising=False)
 p={'id':uuid.uuid4().hex,'profile_id':uuid.uuid4().hex,'context':'travel','brief':'Gentle piano','preserve_audio':True,'status':'complete','round':1,
 'events':[],'tracks':[{'id':uuid.uuid4().hex,'name':'Piano','path':'private.wav','embedding':[1.,0.],'score':.1,'alignment':.1,'mix_level':.3,'sha256':'first'}],
 'active_ids':[],'renders':{},'selected':None,'recommended':None,'selected_by':None,'error':None,'feedback':[],
 'video':{'duration':12,'frames':[],'has_audio':False},'plan':{'scene_summary':'Sunset','music_direction':'Piano'}}
 p['selected']=p['tracks'][0]['id'];p['active_ids']=[p['selected']];p['renders'][p['selected']]='existing.mp4';studio.rerank(p);studio.write(p)
 return p

def decision(action='answer',**kw):
 return talk.Decision(reply='I can help with that.',action=action,instruction='',track_id='',compared_with='',memory_id='',remember_choice=False,
     level=None,preserve_audio=None,duck=None,start=None,end=None,**kw)

def body(**kw):return {'message':'Explain the recommendation','request_id':uuid.uuid4().hex,**kw}

def test_duplicate_request_does_not_repeat_model_or_action(project,monkeypatch):
 calls=[]
 def decide(*args):calls.append(1);return decision(),'test-model'
 monkeypatch.setattr(talk,'decide',decide);c=TestClient(app);request=body()
 a=c.post(f'/api/studio/projects/{project["id"]}/chat',json=request)
 b=c.post(f'/api/studio/projects/{project["id"]}/chat',json=request)
 assert a.status_code==b.status_code==200 and len(calls)==1
 assert len(b.json()['conversation'])==2 and not b.json()['chat_pending']


def test_memory_cannot_be_modified_without_explicit_ui_permission(project,monkeypatch):
 monkeypatch.setattr(talk,'decide',lambda *a:(decision('remember'),'test'))
 result=TestClient(app).post(f'/api/studio/projects/{project["id"]}/chat',json=body(message='Remember soft piano')).json()
 assert result['conversation'][-1]['action_status']=='error'
 assert prefs.summary(project['profile_id'])['notes']==[]


def test_empty_remember_extraction_preserves_authorized_user_words(project,monkeypatch):
 monkeypatch.setattr(talk,'decide',lambda *a:(decision('remember'),'test'))
 request=body(message='Remember warm piano and no drums.',allow_memory=True)
 result=TestClient(app).post(f'/api/studio/projects/{project["id"]}/chat',json=request).json()
 assert result['conversation'][-1]['action_status']=='complete'
 assert prefs.summary(project['profile_id'])['notes'][0]['text']==request['message']


def test_invalid_model_track_id_cannot_change_selection(project,monkeypatch):
 d=decision('select');d.track_id=uuid.uuid4().hex
 monkeypatch.setattr(talk,'decide',lambda *a:(d,'test'))
 result=TestClient(app).post(f'/api/studio/projects/{project["id"]}/chat',json=body(message='Use another track')).json()
 assert result['selected']==project['selected'] and result['conversation'][-1]['action_status']=='error'


def test_mix_dispatch_does_not_call_generation(project,monkeypatch):
 d=decision('mix');d.level=.15;calls=[]
 monkeypatch.setattr(talk,'decide',lambda *a:(d,'test'))
 monkeypatch.setattr(studio,'change_mix',lambda pid,options:calls.append(options.model_dump()))
 monkeypatch.setattr(studio,'start',lambda *a:pytest.fail('Volume change must not generate music'))
 result=TestClient(app).post(f'/api/studio/projects/{project["id"]}/chat',json=body(message='Lower music to fifteen percent')).json()
 assert calls==[{'level':.15,'preserve_audio':True,'duck':True}]
 assert result['conversation'][-1]['action_status']=='complete'


def test_failed_paid_turn_is_not_automatically_replayed(project,monkeypatch):
 calls=[]
 def fail(*a):calls.append(1);raise ValueError('Provider failure')
 monkeypatch.setattr(talk,'decide',fail);c=TestClient(app);request=body()
 assert c.post(f'/api/studio/projects/{project["id"]}/chat',json=request).status_code==400
 retry=c.post(f'/api/studio/projects/{project["id"]}/chat',json=request)
 assert retry.status_code==200 and len(calls)==1 and not retry.json()['chat_pending']
 assert retry.json()['conversation'][-1]['role']=='system'


def test_pending_chat_blocks_concurrent_mutation(project):
 project['chat_pending']=uuid.uuid4().hex;studio.write(project)
 c=TestClient(app)
 assert c.post(f'/api/studio/projects/{project["id"]}/chat',json=body()).status_code==409
 assert c.put(f'/api/studio/projects/{project["id"]}/direction',json={'brief':'Changed'}).status_code==409


def test_voice_validation_rejects_silence_and_oversize_without_api(project,monkeypatch):
 monkeypatch.setattr(talk,'call_muse',lambda *a,**k:pytest.fail('Invalid recording must not spend API budget'))
 c=TestClient(app);buf=io.BytesIO();sf.write(buf,np.zeros(16000),16000,format='WAV')
 assert c.post('/api/studio/voice/transcribe',files={'file':('silent.wav',buf.getvalue(),'audio/wav')}).status_code==400
 assert c.post('/api/studio/voice/transcribe',files={'file':('bad.wav',b'not wave','audio/wav')}).status_code==400
 assert store.budget_status()['requests']==0


def test_splice_changes_only_requested_interval_including_crossfades():
 sr=16000;original=np.tile(np.linspace(-.2,.2,sr*12,dtype='float32')[:,None],(1,2));replacement=np.ones_like(original)*.4
 result,rate=studio.splice_region(original,sr,replacement,sr,8,11)
 assert rate==sr and np.array_equal(result[:8*sr],original[:8*sr]) and np.array_equal(result[11*sr:],original[11*sr:])
 assert np.allclose(result[9*sr:10*sr],.4)
 assert np.array_equal(result[8*sr],original[8*sr]) and np.array_equal(result[11*sr-1],original[11*sr-1])


def test_region_bounds_rejected_before_planning(project):
 c=TestClient(app)
 for start,end in [(10,9),(11.5,12),(9,13)]:
  result=c.post(f'/api/studio/projects/{project["id"]}/generate',json={'feedback':'Quiet','edit_start':start,'edit_end':end})
  assert result.status_code==400 and 'interval' in result.json()['detail']
 assert studio.read(project['id'])['round']==1 and store.budget_status()['requests']==0


def test_speech_cache_reuses_local_audio_without_model_call(project,monkeypatch):
 import hashlib
 turn={'id':uuid.uuid4().hex,'role':'assistant','text':'This is the current recommendation.','action':'answer','action_status':'complete'}
 project['conversation']=[turn];studio.write(project)
 key=hashlib.sha256(('kokoro-v2-timed-af_heart-'+turn['text']).encode()).hexdigest()[:20]
 cached=studio.folder(project['id'])/f'voice-{turn["id"]}-{key}.wav';cached.write_bytes(b'cached speech fixture');cached.with_suffix('.timing.json').write_text(json.dumps({'words':[{'text':'This','start':0,'end':.3}]}))
 monkeypatch.setattr(talk.subprocess,'run',lambda *a,**k:pytest.fail('Cached speech should not synthesize again'))
 c=TestClient(app);response=c.post(f'/api/studio/projects/{project["id"]}/speech/{turn["id"]}')
 assert response.status_code==200 and c.get(response.json()['url']).content==b'cached speech fixture'
 assert store.budget_status()['requests']==0


def test_speech_cannot_read_arbitrary_text_or_another_reply(project):
 c=TestClient(app)
 assert c.post(f'/api/studio/projects/{project["id"]}/speech/{uuid.uuid4().hex}').status_code==404
 assert c.get(f'/api/studio/projects/{project["id"]}/speech/{uuid.uuid4().hex}/invalid-key').status_code==404


def test_explanation_command_needs_no_editing_arguments():
 wire=talk.MuseReply.model_validate({'reply':'Piano suits the slow scene.','command':{'action':'answer'}})
 d=wire.to_decision()
 assert d.action=='answer' and d.end is None and d.start is None and d.level is None
 assert set(talk.MuseReply.model_json_schema()['$defs']['AnswerCommand']['properties'])=={'action'}
 with pytest.raises(ValueError):
  talk.MuseReply.model_validate({'reply':'Answer','command':{'action':'answer','end':0}})


@pytest.mark.parametrize('command,expected',[
 ({'action':'generate','instruction':'Soft piano'},'generate'),
 ({'action':'mix','level':.15,'preserve_audio':None,'duck':None},'mix'),
 ({'action':'select','track_id':'a'*32,'remember_choice':False,'compared_with':''},'select'),
 ({'action':'remember','instruction':'Warm piano'},'remember'),
 ({'action':'forget','memory_id':'all'},'forget'),
 ({'action':'edit_region','instruction':'Gentle ending','start':8,'end':11},'edit_region'),
])
def test_action_specific_reply_preserves_dispatch_arguments(command,expected):
 d=talk.MuseReply.model_validate({'reply':'I can do that.','command':command}).to_decision()
 assert d.action==expected
 assert all(getattr(d,k)==v for k,v in command.items())


@pytest.mark.parametrize('command',[
 {'action':'mix','level':1.1,'preserve_audio':None,'duck':None},
 {'action':'edit_region','instruction':'Piano','start':-1,'end':2},
 {'action':'edit_region','instruction':'Piano','start':0,'end':0},
])
def test_action_specific_reply_retains_local_numeric_bounds(command):
 with pytest.raises(ValueError):
  talk.MuseReply.model_validate({'reply':'Proposed action','command':command}).to_decision()


def test_truncated_provider_reply_is_not_parsed_or_retried(project,monkeypatch,tmp_path):
 calls=[]
 class Response:
  status_code=200
  def json(self):return {'choices':[{'finish_reason':'length','message':{'content':'{"action":"answer","end":0.'+'0'*1000}}],'usage':{}}
 monkeypatch.setenv('MODEL_API_KEY','test-only')
 monkeypatch.setattr(talk.httpx,'post',lambda *a,**kw:(calls.append(1) or Response()))
 with pytest.raises(ValueError,match='cut short'):
  talk.call_muse([],talk.MuseReply,talk.SYSTEM,'test',tmp_path/'raw.json')
 assert calls==[1]
 assert (tmp_path/'raw.json').exists()
