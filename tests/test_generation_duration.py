"""Exercise the real worker with a quantized-duration backend, without loading a GPU model."""
import json,runpy,sys,types
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

@pytest.mark.parametrize('start,end',[(0,18.43),(.123,3.456)])
def test_music_cue_is_generated_with_margin_and_trimmed_to_timeline(tmp_path,monkeypatch,start,end):
 calls=[]
 class Handler:
  def initialize_service(self,**kwargs):return 'ready',True
 def generate(handler,lm,params,config,save_dir):
  calls.append(params.duration)
  rate=48000;length=int((params.duration-.07)*rate)
  raw=np.tile((.1*np.sin(np.arange(length)*.03))[:,None],(1,2))
  path=Path(save_dir)/f'raw-{len(calls)}.wav';sf.write(path,raw,rate)
  return types.SimpleNamespace(success=True,audios=[{'path':str(path)}])
 parent=types.ModuleType('acestep');parent.__path__=[]
 handler=types.ModuleType('acestep.handler');handler.AceStepHandler=Handler
 infer=types.ModuleType('acestep.inference');infer.GenerationParams=types.SimpleNamespace;infer.GenerationConfig=types.SimpleNamespace;infer.generate_music=generate
 for name,module in [('acestep',parent),('acestep.handler',handler),('acestep.inference',infer)]:monkeypatch.setitem(sys.modules,name,module)
 out=tmp_path/'out';job=tmp_path/'job.json'
 job.write_text(json.dumps({'output':str(out),'duration':18.43,'seed':123,'candidates':[{'name':'test'}]*3,'sound_plan':{'cues':[{'enabled':True,'kind':'music','start':start,'end':end,'id':'cue','description':'Piano','bpm':78}]}}))
 monkeypatch.setattr(sys,'argv',['generate_music.py',str(job)]);monkeypatch.setattr(sys,'path',sys.path.copy())
 runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/generate_music.py'),run_name='__main__')
 assert len(calls)==3 and all(duration>end-start for duration in calls)
 a,b=round(start*44100),round(end*44100)
 for index in range(3):
  raw,sr=sf.read(out/f'variation-{index}.wav',always_2d=True)
  assert sr==44100 and len(raw)==round(18.43*44100)
  assert np.any(raw[a:b][-100:]!=0)
  assert not np.any(raw[:a]) and not np.any(raw[b:])
