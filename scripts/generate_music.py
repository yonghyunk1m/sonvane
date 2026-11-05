"""Isolated ACE-Step worker. Run with .models/generator-env/bin/python.

The parent passes a local JSON job; no credentials are required or read here.
"""
import json
import os
import math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.models/ace-step-runtime'
sys.path.insert(0,str(RUNTIME))
os.environ['ACESTEP_CHECKPOINTS_DIR']=str(RUNTIME/'checkpoints')
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['ACESTEP_DISABLE_TQDM']='1'
from acestep.handler import AceStepHandler
from acestep.inference import GenerationParams,GenerationConfig,generate_music

job=json.loads(Path(sys.argv[1]).read_text())
out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
handler=AceStepHandler()
message,ok=handler.initialize_service(project_root=str(RUNTIME),config_path='acestep-v15-turbo',device='cuda',use_flash_attention=False,compile_model=False,offload_to_cpu=False)
if not ok:raise RuntimeError(message)
result_file=out/'result.json'
outputs=json.loads(result_file.read_text()) if result_file.exists() else []
for item in outputs:
    if not Path(item['path']).is_file():raise RuntimeError('A saved candidate is missing.')
for i,candidate in enumerate(job['candidates']):
    if i<len(outputs):continue
    seed=job['seed']+i*107
    music_cues=[c for c in job.get('sound_plan',{}).get('cues',[]) if c['enabled'] and c['kind']=='music']
    if music_cues and not job.get('edit'):
        rate=44100;assembled=np.zeros((int(round(job['duration']*rate)),2),dtype='float32')
        for ci,cue in enumerate(music_cues):
            # Decoder lengths are quantized; generate a margin, then trim to exact timeline samples.
            required_frames=int(round(cue['end']*rate))-int(round(cue['start']*rate))
            piece=out/f'variation-{i}-cue-{cue["id"]}.wav'
            cue_seed=seed+ci*1009
            if not piece.exists():
                params=GenerationParams(caption=cue['description'],lyrics='[Instrumental]',instrumental=True,
                    duration=max(10,math.ceil(cue['end']-cue['start'])+1),bpm=cue['bpm'],seed=cue_seed,
                    thinking=False,use_cot_metas=False,use_cot_caption=False,use_cot_language=False,
                    inference_steps=8,shift=3.0,fade_in_duration=.08,fade_out_duration=0)
                config=GenerationConfig(batch_size=1,use_random_seed=False,seeds=[cue_seed],audio_format='wav')
                result=generate_music(handler,None,params,config,save_dir=str(out))
                if not result.success:raise RuntimeError(result.error)
                raw,sr=sf.read(result.audios[0]['path'],always_2d=True,dtype='float32')
                if sr!=rate:
                    divisor=math.gcd(sr,rate);raw=resample_poly(raw,rate//divisor,sr//divisor)
                if raw.shape[1]==1:raw=np.repeat(raw,2,axis=1)
                raw=raw[:required_frames,:2]
                if len(raw)<required_frames:
                    raise RuntimeError(f'A music cue was too short: expected {required_frames} samples, received {len(raw)}.')
                if not np.isfinite(raw).all() or np.sqrt(np.mean(raw.astype(float)**2))<1e-5:
                    raise RuntimeError('A music cue was invalid or silent.')
                temp=piece.with_suffix('.tmp.wav');sf.write(temp,raw,rate,subtype='PCM_16');temp.replace(piece)
            raw,sr=sf.read(piece,always_2d=True,dtype='float32')
            a,b=int(round(cue['start']*rate)),int(round(cue['end']*rate))
            if sr!=rate or len(raw)<b-a:raise RuntimeError('A saved cue is incomplete.')
            assembled[a:b]=raw[:b-a]
            (out/'progress.json').write_text(json.dumps({'completed':i,'total':len(job['candidates']),'cue_completed':ci+1,'cue_total':len(music_cues)}))
        path=out/f'variation-{i}.wav';sf.write(path,assembled,rate,subtype='PCM_16')
        outputs.append({'path':str(path),'seed':seed,'cue_seeds':{c['id']:seed+j*1009 for j,c in enumerate(music_cues)},**candidate})
        temp=out/'result.tmp';temp.write_text(json.dumps(outputs));temp.replace(result_file)
        (out/'progress.json').write_text(json.dumps({'completed':i+1,'total':len(job['candidates'])}))
        continue
    edit=job.get('edit')
    editing={'task_type':'repaint','src_audio':edit['source'],'repainting_start':edit['start'],'repainting_end':edit['end'],'chunk_mask_mode':'explicit','enable_normalization':False} if edit else {}
    params=GenerationParams(**editing,caption=candidate['prompt'],lyrics='[Instrumental]',instrumental=True,
        duration=max(10,job['duration']),bpm=candidate['bpm'],seed=seed,
        thinking=False,use_cot_metas=False,use_cot_caption=False,use_cot_language=False,
        inference_steps=8,shift=3.0,fade_in_duration=0 if edit else .15,fade_out_duration=0 if edit else .4)
    config=GenerationConfig(batch_size=1,use_random_seed=False,seeds=[seed],audio_format='wav')
    result=generate_music(handler,None,params,config,save_dir=str(out))
    if not result.success:raise RuntimeError(result.error)
    outputs.append({'path':result.audios[0]['path'],'seed':seed,**candidate})
    temp=out/'result.tmp';temp.write_text(json.dumps(outputs));temp.replace(result_file)
    (out/'progress.json').write_text(json.dumps({'completed':i+1,'total':len(job['candidates'])}))
(out/'result.json').write_text(json.dumps(outputs))
print('Completed',len(outputs),'real ACE-Step generations.',flush=True)
