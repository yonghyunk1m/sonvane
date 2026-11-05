"""Real decoding checks for clip selection; no model calls or paid requests."""
import uuid
import subprocess
import numpy as np
import pytest
import soundfile as sf
from PIL import Image
from fastapi.testclient import TestClient
from app import video, store, studio
from app.main import app

@pytest.fixture(scope='module')
def long_video(tmp_path_factory):
    path=tmp_path_factory.mktemp('trim-source')/'two-scenes.mp4'
    # Red/220 Hz until 20 s, then blue/880 Hz. Seek must move both streams.
    subprocess.run([video.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=red:s=128x96:r=24:d=20',
        '-f','lavfi','-i','color=blue:s=128x96:r=24:d=25','-f','lavfi','-i',
        "aevalsrc=if(lt(t\\,20)\\,0.1*sin(2*PI*220*t)\\,0.1*sin(2*PI*880*t)):s=16000:d=45",
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a',
        '-c:v','libx264','-threads','2','-c:a','aac',str(path)],check=True,capture_output=True)
    return path

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data')
    monkeypatch.delenv('MODEL_API_KEY',raising=False);monkeypatch.delenv('META_API_KEY',raising=False)
    return TestClient(app)

def upload(client,path,**fields):
    with path.open('rb') as file:
        return client.post('/api/studio/projects',data={'profile_id':uuid.uuid4().hex,**fields},files={'file':('scenes.mp4',file,'video/mp4')})

def test_long_video_requires_explicit_section_and_cleans_failed_upload(client,long_video):
    response=upload(client,long_video)
    assert response.status_code==400 and 'Choose a 3–30 second section' in response.json()['detail']
    assert not list((store.DATA/'projects').glob('*'))
    assert store.budget_status()['requests']==0

def test_selected_section_seeks_both_video_and_audio_and_keeps_provenance(client,long_video):
    response=upload(client,long_video,trim_start=22.3,trim_end=28.3)
    assert response.status_code==200,response.text
    data=response.json();root=studio.folder(data['id']);details=data['video']
    assert details['duration']==6
    assert details['selection']=={'start':22.3,'end':28.3,'source_duration':45.0}
    for frame in details['frames']:
        rgb=np.array(Image.open(root/frame['file']).convert('RGB')).mean(axis=(0,1))
        assert rgb[2]>rgb[0]+100  # blue, not the first red scene
        assert 0<=frame['at']<6
    wave,sr=sf.read(root/'source.wav');sample=wave[sr:2*sr]
    peak=np.fft.rfftfreq(len(sample),1/sr)[np.abs(np.fft.rfft(sample)).argmax()]
    assert abs(peak-880)<2 and abs(len(wave)/sr-6)<.1
    assert not (root/'upload.mp4').exists()
    assert store.budget_status()['requests']==0
    assert client.get(f'/api/studio/projects/{data["id"]}/source').status_code==200

@pytest.mark.parametrize('start,end',[(-1,5),(0,31),(22,24),(44,48),(5,4),('nan',10),('inf',10)])
def test_invalid_sections_rejected_without_spend(client,long_video,start,end):
    result=upload(client,long_video,trim_start=start,trim_end=end)
    assert result.status_code in (400,422)
    assert not list((store.DATA/'projects').glob('*'))
    assert store.budget_status()['requests']==0

def test_partial_interval_rejected(client,long_video):
    assert upload(client,long_video,trim_start=10).status_code==400

def test_short_video_still_works_without_selection(client,long_video,tmp_path):
    short=tmp_path/'short.mp4';video.run(['-i',long_video,'-t',4,'-c','copy',short])
    response=upload(client,short)
    assert response.status_code==200,response.text
    assert 3.9<=response.json()['video']['duration']<=4.2

def test_upload_size_cap_cleans_partial_file(client,long_video,monkeypatch):
    monkeypatch.setattr(video,'MAX_UPLOAD_BYTES',8)
    assert upload(client,long_video,trim_start=0,trim_end=10).status_code==400
    assert not list((store.DATA/'projects').glob('*'))
