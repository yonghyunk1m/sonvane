import io,json,uuid,threading
from types import SimpleNamespace
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from app import studio,store,soundplan,video
from app.main import app

@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data')
    monkeypatch.delenv('MODEL_API_KEY',raising=False);monkeypatch.delenv('META_API_KEY',raising=False)
    p={'id':uuid.uuid4().hex,'profile_id':uuid.uuid4().hex,'context':'travel','brief':'Quiet piano','preserve_audio':True,
       'video':{'duration':12.,'frames':[],'has_audio':False},'name':'Test','status':'ready','message':'Ready','error':None,
       'tracks':[],'active_ids':[],'selected':None,'recommended':None,'selected_by':None,'plan':None,'round':0,'feedback':[],'events':[],'renders':{}}
    studio.write(p);return p

def cue(kind='music',start=1,end=5):
    return dict(id=uuid.uuid4().hex,kind=kind,start=start,end=end,description='Soft piano without vocals' if kind=='music' else 'Soft transition',reason='Test cue',effect='none' if kind=='music' else 'whoosh',bpm=90,gain=1 if kind=='music' else .2,enabled=True)
def draft(*cues):return {'summary':'Reviewed test plan','cues':list(cues)}
def save(project,plan):
    project['sound_plan']={**plan,'revision':uuid.uuid4().hex,'status':'draft','model':'test-muse'};studio.write(project);return project['sound_plan']['revision']


def test_proposal_is_draft_idempotent_and_never_generates(project,monkeypatch):
    calls=[]
    def propose(*args):calls.append(1);return draft(cue()),'test'
    monkeypatch.setattr(soundplan,'propose',propose)
    monkeypatch.setattr(studio,'generate',lambda *a:pytest.fail('Proposal must not generate'))
    c=TestClient(app);body={'request_id':uuid.uuid4().hex};url=f'/api/studio/projects/{project["id"]}/sound-plan'
    a=c.post(url,json=body);b=c.post(url,json=body)
    assert a.status_code==b.status_code==200 and len(calls)==1
    assert b.json()['sound_plan']['status']=='draft' and b.json()['round']==0 and b.json()['tracks']==[]


def test_invalid_proposal_preserves_prior_plan(project,monkeypatch):
    old=save(project,draft(cue()));calls=[]
    def fail(*a):calls.append(1);raise ValueError('Bad proposal')
    monkeypatch.setattr(soundplan,'propose',fail);c=TestClient(app);body={'request_id':uuid.uuid4().hex}
    assert c.post(f'/api/studio/projects/{project["id"]}/sound-plan',json=body).status_code==400
    again=c.post(f'/api/studio/projects/{project["id"]}/sound-plan',json=body).json()
    assert len(calls)==1 and again['sound_plan']['revision']==old and not again['cue_pending']

@pytest.mark.parametrize('cues',[ [cue(start=0,end=2)], [cue(start=10,end=14)], [cue(start=1,end=6),cue(start=5,end=9)], [cue('sfx',0,6)] ])
def test_invalid_cues_rejected(project,cues):
    with pytest.raises(ValueError):soundplan.validate_plan(draft(*cues),12)


def test_music_and_effect_overlap_is_valid(project):
    result=soundplan.validate_plan(draft(cue(start=0,end=6),cue('sfx',2,3)),12)
    assert len(result['cues'])==2


def test_approval_requires_current_revision_before_any_spending(project,monkeypatch):
    old=save(project,draft(cue()));c=TestClient(app);url=f'/api/studio/projects/{project["id"]}'
    monkeypatch.setattr(studio,'ready',lambda:True)
    monkeypatch.setattr(studio,'soundtrack_job',lambda *a:pytest.fail('Unapproved plan must not generate'))
    assert c.post(url+'/generate',json={}).status_code==409
    edited=c.put(url+'/sound-plan',json={**draft(cue(start=5,end=9)),'revision':old}).json()
    assert edited['sound_plan']['revision']!=old
    assert c.post(url+'/generate',json={'cue_revision':old}).status_code==409
    assert c.put(url+'/sound-plan',json={**draft(cue()),'revision':old}).status_code==409
    assert store.budget_status()['requests']==0


def test_approved_generation_reuses_reviewed_prompts_without_meta(project,monkeypatch):
    note='Exactly this instrumental direction';item=cue();item['description']=note;rev=save(project,draft(item));seen=[]
    monkeypatch.setattr(studio,'ready',lambda:True)
    def job(pid,feedback):
        p=studio.read(pid);seen.append(p['pending_sound_plan']);studio.CANCELLATIONS.pop(pid,None);studio.JOB_LOCK.release()
    monkeypatch.setattr(studio,'soundtrack_job',job)
    response=TestClient(app).post(f'/api/studio/projects/{project["id"]}/generate',json={'cue_revision':rev})
    assert response.status_code==200,response.text
    assert seen[0]['cues'][0]['description']==note and seen[0]['status']=='approved'
    assert store.budget_status()['requests']==0


def test_effects_are_finite_bounded_and_only_inside_their_interval():
    plan=draft(cue('sfx',2,2.5));wave=soundplan.effects_layer(plan,4)
    assert not np.any(wave[:2*44100]) and not np.any(wave[int(2.5*44100):])
    assert np.any(wave[2*44100:int(2.5*44100)]) and np.isfinite(wave).all() and np.max(np.abs(wave))<=.121
    for effect in soundplan.EFFECTS:
        a=soundplan.effect_audio(effect,.5);assert a.shape==(22050,2) and np.isfinite(a).all()


def test_effect_preview_uses_no_model(project):
    c=TestClient(app);r=c.post('/api/studio/sound-effects/preview',json={'effect':'chime','duration':.6,'gain':.2})
    assert r.status_code==200 and r.content[:4]==b'RIFF'
    assert c.post('/api/studio/sound-effects/preview',json={'effect':'dog','duration':.6}).status_code==422
    assert store.budget_status()['requests']==0


def test_evaluation_excludes_gaps_and_effects(tmp_path,monkeypatch):
    path=tmp_path/'music.wav';sr=16000;wave=np.zeros(sr*12,dtype='float32');wave[2*sr:5*sr]=.1;wave[8*sr:12*sr]=.2;sf.write(path,wave,sr)
    calls=[]
    def score(path,digest):
        a,rate=sf.read(path);calls.append((len(a)/rate,float(a.mean())));return {'score':len(calls),'embedding':[1.,0.]}
    monkeypatch.setattr(studio.audio,'score_path',score)
    result=studio.evaluate_track(path,[(2,5),(8,12)])
    assert result['windows']==[[2.,5.],[8.,12.]] and [x[0] for x in calls]==[3,4]
    assert all(x[1]>.09 for x in calls) and result['score']==1.5


def test_mix_contains_music_only_in_approved_cues_and_effect_only_in_its_cue(tmp_path):
    import subprocess
    folder=tmp_path/'mix';folder.mkdir();sr=44100
    sf.write(folder/'music.wav',.1*np.sin(2*np.pi*220*np.arange(sr*12)/sr),sr)
    subprocess.run([video.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=blue:s=128x96:r=24:d=12','-c:v','libx264',str(folder/'source.mp4')],capture_output=True,check=True)
    plan=draft(cue(start=2,end=5),cue('sfx',7,7.5))
    video.mix(folder,folder/'music.wav','result',12,False,.3,sound_plan=plan)
    bed,rate=sf.read(folder/'result-bed.wav',always_2d=True)
    assert not np.any(bed[:2*sr]) and not np.any(bed[5*sr:7*sr]) and not np.any(bed[int(7.5*sr):])
    assert np.any(bed[2*sr:5*sr]) and np.any(bed[7*sr:int(7.5*sr)])


def test_effect_only_plan_does_not_load_music_models(project,monkeypatch):
    rev=save(project,draft(cue('sfx',1,1.5)))
    monkeypatch.setattr(studio,'ready',lambda:False)
    monkeypatch.setattr(studio.audio,'scorer',lambda:pytest.fail('No music models should load'))
    def mix(folder,path,name,*a,**k):(folder/(name+'.mp4')).write_bytes(b'fixture')
    monkeypatch.setattr(studio.video,'mix',mix)
    r=TestClient(app).post(f'/api/studio/projects/{project["id"]}/generate',json={'cue_revision':rev});assert r.status_code==200,r.text
    p=studio.read(project['id']);assert p['status']=='complete',p.get('error')
    assert len(p['tracks'])==1 and p['tracks'][0]['evaluation_kind']=='not-rated' and p['tracks'][0]['windows']==[]
    assert store.budget_status()['requests']==0 and not studio.JOB_LOCK.locked()


def test_effect_only_render_failure_resumes_without_gpu_or_meta(project,monkeypatch):
    rev=save(project,draft(cue('sfx',1,1.5)))
    monkeypatch.setattr(studio,'ready',lambda:False)
    monkeypatch.setattr(studio.audio,'scorer',lambda:pytest.fail('Effects must not load music models'))
    def fail(*a,**k):raise ValueError('Injected render failure')
    monkeypatch.setattr(studio.video,'mix',fail)
    client=TestClient(app);url=f'/api/studio/projects/{project["id"]}'
    assert client.post(url+'/generate',json={'cue_revision':rev}).status_code==200
    p=client.get(url).json();assert p['status']=='error' and p['can_resume'] and not p['resume_requires_generator']
    def mix(folder,path,name,*a,**k):(folder/(name+'.mp4')).write_bytes(b'fixture')
    monkeypatch.setattr(studio.video,'mix',mix)
    assert client.post(url+'/resume').status_code==200
    p=client.get(url).json();assert p['status']=='complete' and p['round']==1 and len(p['tracks'])==1
    assert store.budget_status()['requests']==0 and not studio.JOB_LOCK.locked()


def test_concise_new_proposals_preserve_verbose_saved_plans():
    # Tightening new-model output must not invalidate a user's existing reviewed plan.
    old={'scene_description':'A'*500,'summary':'B'*900,'cues':[cue()]}
    assert soundplan.validate_plan(old,12)=={**old,'highlights':[],'scene_points':[],'sound_points':[]}
    short={'scene_description':'A robot approaches along a campus path.',
           'summary':'Warm, restrained piano follows the gentle movement.','highlights':['restrained piano'],'scene_points':['A robot approaches along a campus path.'],'sound_points':['Use restrained piano for the gentle movement.'],'cues':[]}
    assert soundplan.Proposal.model_validate(short).summary==short['summary']
    with pytest.raises(ValueError):
        soundplan.Proposal.model_validate({**short,'summary':'B'*281})


def test_highlights_are_verbatim_and_survive_editing(project):
    plan={**draft(cue()),'summary':'Warm piano follows the scene with no percussion.',
          'highlights':['Warm piano','not in the recommendation','Warm piano']}
    validated=soundplan.validate_plan(plan,12)
    assert validated['highlights']==['Warm piano']
    rev=save(project,validated)
    response=TestClient(app).put(f'/api/studio/projects/{project["id"]}/sound-plan',json={**validated,'revision':rev})
    assert response.status_code==200
    assert response.json()['sound_plan']['highlights']==['Warm piano']
    assert response.json()['sound_plan']['summary']==plan['summary']
    assert store.budget_status()['requests']==0


def test_plan_points_survive_save_without_changing_generation_prompt(project):
    plan={**draft(cue()),'scene_points':['A robot moves slowly toward the camera.'],
          'sound_points':['Soft piano follows the slow approach.'],'highlights':['Soft piano']}
    checked=soundplan.validate_plan(plan,12)
    assert checked['highlights']==['Soft piano']
    rev=save(project,checked)
    r=TestClient(app).put(f'/api/studio/projects/{project["id"]}/sound-plan',json={**checked,'revision':rev})
    assert r.status_code==200
    stored=r.json()['sound_plan']
    assert stored['scene_points']==plan['scene_points'] and stored['sound_points']==plan['sound_points']
    assert stored['cues']==plan['cues'] and store.budget_status()['requests']==0
    with pytest.raises(ValueError):soundplan.validate_plan({**plan,'sound_points':['x'*141]},12)
