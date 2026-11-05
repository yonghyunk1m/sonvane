import json
import uuid
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import personalization as prefs, studio, store
from app.main import app

REAL_PLAN_MUSIC = studio.plan_music

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    monkeypatch.delenv('MODEL_API_KEY',raising=False);monkeypatch.delenv('META_API_KEY',raising=False)
    monkeypatch.setenv('META_BUDGET_USD','5');monkeypatch.setenv('META_MAX_REQUESTS','40')

def track(name,vector):return {'name':name,'sha256':name,'embedding':vector}

def test_learning_generalizes_to_unseen_audio_features_and_is_reversible():
    pid=uuid.uuid4().hex
    a,b=track('A',[1.,0.,0.]),track('B',[0.,1.,0.])
    prefs.remember_pair(pid,'narration',a,b,'project')
    new=[track('unseen C',[.9,.1,.1]),track('unseen D',[.1,.9,.1])]
    details=prefs.annotate(new,pid,'narration')
    assert details['pairs']==1 and new[0]['personal_adjustment']>new[1]['personal_adjustment']
    prefs.annotate(new,pid,'travel');assert all(t['personal_adjustment']==0 for t in new)
    prefs.forget(pid);prefs.annotate(new,pid,'narration');assert all(t['personal_adjustment']==0 for t in new)

def test_repeated_pair_is_not_extra_evidence_and_reversal_replaces_it():
    pid=uuid.uuid4().hex;a,b=track('A',[1.,0.]),track('B',[0.,1.])
    prefs.remember_pair(pid,'general',a,b,'p');prefs.remember_pair(pid,'general',a,b,'p')
    assert prefs.summary(pid)['pair_count']==1
    prefs.remember_pair(pid,'general',b,a,'p')
    new=[dict(a),dict(b)];prefs.annotate(new,pid,'general')
    assert new[1]['personal_signal']>new[0]['personal_signal']

def test_text_memory_does_not_pretend_to_train_audio_model():
    pid=uuid.uuid4().hex;prefs.remember_note(pid,'narration','Less percussion')
    new=[track('A',[1.,0.])];details=prefs.annotate(new,pid,'narration')
    assert details['pairs']==0 and new[0]['personal_adjustment']==0
    note=prefs.summary(pid)['notes'][0];prefs.forget(pid,note['id'])
    assert prefs.summary(pid)['notes']==[]

def test_profile_api_hides_features_and_is_separated():
    client=TestClient(app);p1,p2=uuid.uuid4().hex,uuid.uuid4().hex
    prefs.remember_pair(p1,'general',track('A',[1,0]),track('B',[0,1]),'p')
    result=client.get('/api/studio/profiles/'+p1).json()
    assert 'difference' not in result['pairs'][0]
    assert client.get('/api/studio/profiles/'+p2).json()['pair_count']==0
    assert client.get('/api/studio/profiles/not-an-id').status_code==400
    assert client.delete('/api/studio/profiles/'+p1).json()['pair_count']==0

def test_multimodal_budget_reserves_before_call():
    for _ in range(20):store.reserve_request(.25)
    with pytest.raises(ValueError):store.reserve_request(.25)
    assert store.budget_status()['reserved_usd']==5

def test_upload_rejects_non_video_and_does_not_call_meta():
    client=TestClient(app)
    result=client.post('/api/studio/projects',data={'profile_id':uuid.uuid4().hex},files={'file':('fake.mp4',b'#EXTM3U\nfile:///etc/passwd','video/mp4')})
    assert result.status_code==400 and store.budget_status()['requests']==0

def test_rank_uses_personalization_without_overwriting_explicit_selection():
    pid=uuid.uuid4().hex
    p={'profile_id':pid,'context':'general','active_ids':['a','b'],'selected':'a','tracks':[
        {'id':'a',**track('A',[1.,0.]),'score':0.,'alignment':.1},
        {'id':'b',**track('B',[0.,1.]),'score':0.,'alignment':.1}]}
    prefs.remember_pair(pid,'general',p['tracks'][1],p['tracks'][0],'p')
    studio.rerank(p)
    assert p['recommended']=='b' and p['selected']=='a'

def test_generator_failure_is_visible_without_fake_output(monkeypatch):
    pid=uuid.uuid4().hex
    p={'id':pid,'profile_id':uuid.uuid4().hex,'status':'planning','round':0,'events':[],'tracks':[],'error':None}
    studio.write(p);studio.JOB_LOCK.acquire()
    monkeypatch.setattr(studio,'plan_music',lambda *args:(_ for _ in ()).throw(ValueError('Provider rejected request')))
    studio.soundtrack_job(pid)
    result=studio.read(pid)
    assert result['status']=='error' and result['tracks']==[] and not studio.JOB_LOCK.locked()

def test_home_opens_video_studio():
    client=TestClient(app)
    result=client.get('/',follow_redirects=False)
    assert result.headers['location']=='/studio/'

@pytest.fixture
def pipeline(tmp_path,monkeypatch):
    """Small local media with fake model inference, testing orchestration not model quality."""
    from types import SimpleNamespace
    import soundfile as sf
    root=tmp_path/'application';provenance=root/'.models/ace-step-runtime/checkpoints'
    provenance.mkdir(parents=True);(provenance/'sonvane-provenance.json').write_text('{"license":"MIT","revision":"test"}')
    monkeypatch.setattr(store,'ROOT',root);monkeypatch.setattr(studio,'ready',lambda:True)
    monkeypatch.setenv('MODEL_API_KEY','unit-test-placeholder')
    pid,profile=uuid.uuid4().hex,uuid.uuid4().hex
    p={'id':pid,'profile_id':profile,'status':'ready','round':0,'context':'travel','brief':'Quiet','preserve_audio':True,
       'events':[],'tracks':[],'error':None,'active_ids':[],'renders':{},'plan':None,'selected':None,'recommended':None,'selected_by':None,
       'video':{'duration':3,'has_audio':False,'frames':[]},'feedback':[],'name':'Test.mp4','created_at':'2026-11-03T10:00:00Z'}
    studio.write(p)
    plan={'scene_summary':'Test scene','music_direction':'Soft piano','query_en':'soft piano','mix_level':.3,'speech_present':False,
          'candidates':[{'name':f'Track {i}','prompt':f'Soft piano and strings variation {i}','bpm':70+i} for i in range(3)]}
    generated=[]
    for i,c in enumerate(plan['candidates']):
        path=tmp_path/f'candidate-{i}.wav';sf.write(path,.1*np.sin(np.arange(24000*3)*2*np.pi*(220+i*50)/24000),24000)
        generated.append({**c,'path':str(path),'seed':i})
    calls={'plan':0,'generate':0,'evaluate':0,'mix':0}
    def planner(project,feedback=''):
        calls['plan']+=1;project['meta_model']='test-muse';return plan
    def generator(project):calls['generate']+=1;return generated
    def evaluate(path):
        calls['evaluate']+=1;return {'score':.1,'embedding':[1.,.1*calls['evaluate']],'windows':[[0,3]],'window_scores':[.1]}
    def mix(folder,path,name,*args,**kwargs):
        calls['mix']+=1;target=folder/(name+'.mp4');target.write_bytes(b'test-render');return target
    monkeypatch.setattr(studio,'plan_music',planner);monkeypatch.setattr(studio,'generate',generator)
    monkeypatch.setattr(studio,'evaluate_track',evaluate);monkeypatch.setattr(studio.video,'mix',mix)
    monkeypatch.setattr(studio.audio,'scorer',lambda:SimpleNamespace(text=lambda q:[1.,0.]))
    return p,plan,calls,evaluate


def test_resume_reuses_plan_generation_and_completed_scores(pipeline,monkeypatch):
    p,plan,calls,evaluate=pipeline;client=TestClient(app)
    def interrupted(path):
        if calls['evaluate']==1:
            calls['evaluate']+=1;raise ValueError('Injected scoring failure')
        return evaluate(path)
    monkeypatch.setattr(studio,'evaluate_track',interrupted)
    assert client.post(f'/api/studio/projects/{p["id"]}/generate',json={}).status_code==200
    failed=studio.read(p['id']);first=failed['tracks'][0]['id']
    assert failed['status']=='error' and len(failed['checkpoint']['track_ids'])==1
    assert studio.clean(failed)['can_resume']
    monkeypatch.setattr(studio,'evaluate_track',evaluate)
    assert client.post(f'/api/studio/projects/{p["id"]}/resume').status_code==200
    result=studio.read(p['id'])
    assert result['status']=='complete' and result['round']==1 and len(result['tracks'])==3
    assert first in result['active_ids'] and calls['plan']==1 and calls['generate']==1
    assert not studio.JOB_LOCK.locked() and 'checkpoint' not in studio.clean(result)
    assert client.post(f'/api/studio/projects/{p["id"]}/resume').status_code==409


def test_failed_revision_keeps_last_playable_selection(pipeline,monkeypatch):
    p,plan,calls,evaluate=pipeline;client=TestClient(app)
    client.post(f'/api/studio/projects/{p["id"]}/generate',json={})
    before=studio.read(p['id']);selected=before['selected'];render=before['renders'][selected]
    monkeypatch.setattr(studio.video,'mix',lambda *a,**k:(_ for _ in ()).throw(ValueError('Injected render failure')))
    client.post(f'/api/studio/projects/{p["id"]}/generate',json={'feedback':'Change the rhythm'})
    after=studio.read(p['id'])
    assert after['status']=='error' and after['selected']==selected and after['renders'][selected]==render
    assert after['active_ids']==before['active_ids'] and studio.clean(after)['can_resume']
    assert (studio.folder(p['id'])/render).read_bytes()==b'test-render'


def test_cancel_after_planning_then_resume_without_new_muse_call(pipeline,monkeypatch):
    p,plan,calls,evaluate=pipeline;client=TestClient(app);original=studio.plan_music
    def cancel_during_plan(project,feedback=''):
        result=original(project,feedback)
        response=client.post(f'/api/studio/projects/{p["id"]}/cancel')
        assert response.status_code==200 and response.json()['cancellation_requested']
        return result
    monkeypatch.setattr(studio,'plan_music',cancel_during_plan)
    client.post(f'/api/studio/projects/{p["id"]}/generate',json={})
    stopped=studio.read(p['id'])
    assert stopped['status']=='cancelled' and calls['generate']==0 and studio.clean(stopped)['can_resume']
    monkeypatch.setattr(studio,'plan_music',original)
    client.post(f'/api/studio/projects/{p["id"]}/resume')
    assert studio.read(p['id'])['status']=='complete' and calls['plan']==1


def test_mix_changes_do_not_generate_and_have_new_render_urls(pipeline):
    p,plan,calls,evaluate=pipeline;client=TestClient(app)
    client.post(f'/api/studio/projects/{p["id"]}/generate',json={})
    before=studio.read(p['id']);selected=before['selected'];old=before['renders'][selected]
    result=client.post(f'/api/studio/projects/{p["id"]}/mix',json={'level':.1,'preserve_audio':False,'duck':False})
    assert result.status_code==200;after=result.json()
    assert after['selected']==selected and after['renders'][selected]!=old
    assert after['render_settings'][selected]=={'level':.1,'preserve_audio':False,'duck':False}
    assert calls['plan']==1 and calls['generate']==1 and calls['mix']==2
    assert client.post(f'/api/studio/projects/{p["id"]}/mix',json={'level':2}).status_code==422


def test_memory_deletion_refreshes_scores_without_changing_selected_audio(pipeline):
    p,plan,calls,evaluate=pipeline;client=TestClient(app)
    client.post(f'/api/studio/projects/{p["id"]}/generate',json={});p=studio.read(p['id'])
    prefs.remember_pair(p['profile_id'],'travel',p['tracks'][1],p['tracks'][0],p['id'])
    with_memory=client.get(f'/api/studio/projects/{p["id"]}').json();assert with_memory['personalization']['pairs']==1
    client.delete('/api/studio/profiles/'+p['profile_id'])
    after=client.get(f'/api/studio/projects/{p["id"]}').json()
    assert after['personalization']['pairs']==0 and all(t['personal_adjustment']==0 for t in after['tracks'])
    assert after['selected']==p['selected'] and after['renders']==p['renders']


def test_history_filters_profile_and_does_not_expose_private_state(pipeline):
    p,plan,calls,evaluate=pipeline;client=TestClient(app)
    rows=client.get('/api/studio/projects',params={'profile_id':p['profile_id']}).json()['projects']
    assert len(rows)==1 and rows[0]['id']==p['id'] and 'brief' not in rows[0] and 'checkpoint' not in rows[0]
    assert client.get('/api/studio/projects',params={'profile_id':uuid.uuid4().hex}).json()['projects']==[]


@pytest.mark.parametrize('samples', [np.zeros((72000,1)),np.full((72000,1),np.nan),np.ones((24000,1))])
def test_invalid_generated_audio_is_rejected(samples):
    with pytest.raises(ValueError):studio.validate_generated(samples,24000,3)


def test_job_releases_lock_if_project_disappears():
    studio.JOB_LOCK.acquire();studio.soundtrack_job(uuid.uuid4().hex)
    assert not studio.JOB_LOCK.locked()


def test_muse_revision_receives_selected_track_and_matching_memory(pipeline,monkeypatch):
    from types import SimpleNamespace
    p,plan,calls,evaluate=pipeline
    # Exercise the real request construction, replacing only HTTP transport.
    original=REAL_PLAN_MUSIC
    p['tracks']=[{'id':'chosen','name':'Selected strings','prompt':'Quiet strings without percussion','direction':'Gentle strings','score':.3,'alignment':.2}]
    p['selected']='chosen';p['round']=1;p['feedback']=[{'text':'Keep the strings'}]
    prefs.remember_note(p['profile_id'],'travel','No heavy drums')
    prefs.remember_note(p['profile_id'],'narration','Voice first')
    captured={}
    def post(url,**kwargs):
        captured.update(kwargs['json'])
        return SimpleNamespace(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps(plan)}}],'usage':{}})
    monkeypatch.setattr(studio.httpx,'post',post)
    result=original(p,'A little more space')
    text=json.loads(captured['messages'][1]['content'][0]['text'])
    assert text['selected_track']['name']=='Selected strings'
    assert text['remembered_instructions']==['No heavy drums']
    assert text['recent_feedback']==['Keep the strings'] and text['revision_request']=='A little more space'
    assert captured['response_format']['json_schema']['strict'] and result['candidates']==plan['candidates']
    assert store.budget_status()['requests']==1


def test_ducking_preserves_full_video_when_original_audio_is_short(tmp_path):
    import subprocess
    import soundfile as sf
    from app import video
    folder=tmp_path/'mix';folder.mkdir();sr=24000
    original=.2*np.sin(np.arange(sr)*2*np.pi*220/sr);sf.write(folder/'source.wav',original,sr)
    music=.1*np.sin(np.arange(sr*3)*2*np.pi*440/sr);sf.write(folder/'music.wav',music,sr)
    subprocess.run([video.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=c=blue:s=128x128:r=24:d=3','-i',str(folder/'source.wav'),'-map','0:v','-map','1:a','-c:v','libx264','-c:a','aac',str(folder/'source.mp4')],check=True,capture_output=True)
    video.mix(folder,folder/'music.wav','ducked',3,True,.3,duck=True)
    video.mix(folder,folder/'music.wav','steady',3,True,.3,duck=False)
    ducked,_=sf.read(folder/'ducked-bed.wav');steady,_=sf.read(folder/'steady-bed.wav')
    assert np.sqrt(np.mean(ducked[22050:33075]**2)) < np.sqrt(np.mean(steady[22050:33075]**2))*.5
    assert np.allclose(ducked[88200:110250],steady[88200:110250],atol=1e-4)
    # The output audio must continue to the end of the three-second video.
    video.run(['-i',folder/'ducked.mp4','-vn','-ac','1','-ar','24000',folder/'decoded.wav'])
    decoded,rate=sf.read(folder/'decoded.wav');assert len(decoded)/rate>=2.9


def test_exhausted_budget_does_not_consume_round_or_save_feedback(pipeline):
    p,plan,calls,evaluate=pipeline
    for _ in range(20):store.reserve_request(.25)
    result=TestClient(app).post(f'/api/studio/projects/{p["id"]}/generate',json={'feedback':'More drums','remember':True})
    assert result.status_code==400
    assert studio.read(p['id'])['round']==0 and calls['plan']==0
    assert prefs.summary(p['profile_id'])['notes']==[] and not studio.JOB_LOCK.locked()
