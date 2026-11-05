"""Bounded local video decoding, sampled frames, and soundtrack mixing."""
from __future__ import annotations
import re
import math
import subprocess
from pathlib import Path
import imageio_ffmpeg
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
MAX_SOURCE_SECONDS=600
MAX_UPLOAD_BYTES=250*1024*1024

def run(args, timeout=90):
    try:r=subprocess.run([FFMPEG,'-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired:raise ValueError('Video processing timed out.') from None
    if r.returncode:raise ValueError('Could not process this video. Use an ordinary MP4 or MOV file with a video track.')
    return r

def prepare(upload:Path, folder:Path, trim_start:float|None=None, trim_end:float|None=None):
    with upload.open('rb') as f:header=f.read(32)
    if len(header)<12 or header[4:8]!=b'ftyp':raise ValueError('Use an MP4 or MOV video container.')
    try:info=subprocess.run([FFMPEG,'-nostdin','-hide_banner','-f','mov','-i',str(upload)],capture_output=True,timeout=15).stderr.decode(errors='replace')
    except subprocess.TimeoutExpired:raise ValueError('Video inspection timed out. Try a shorter or smaller file.') from None
    match=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',info)
    if not match:raise ValueError('Could not determine video length.')
    h,m,s=map(float,match.groups());original_duration=h*3600+m*60+s
    if not 3<=original_duration<=MAX_SOURCE_SECONDS:raise ValueError('Choose a source video between 3 seconds and 10 minutes.')
    if trim_start is None and trim_end is None:
        if original_duration>30:raise ValueError('Choose a 3–30 second section before uploading this longer video.')
        start,end=0.,original_duration
    else:
        if trim_start is None or trim_end is None or not all(math.isfinite(n) for n in (trim_start,trim_end)):
            raise ValueError('Specify finite start and end times for the section.')
        start,end=trim_start,trim_end
        # Container and browser metadata may round the source endpoint differently.
        if start<0 or end>original_duration+.05 or end<=start:raise ValueError('Choose a section inside the source video.')
        end=min(end,original_duration)
    duration=round(end-start,6)
    if not 3<=duration<=30:raise ValueError('Choose a section between 3 and 30 seconds long.')
    if 'Video:' not in info:raise ValueError('The file has no video track.')
    has_audio='Audio:' in info
    source=folder/'source.mp4'
    run(['-ss',start,'-f','mov','-i',upload,'-map','0:v:0','-map','0:a:0?','-t',duration,'-vf',"scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",'-r','24','-c:v','libx264','-threads','2','-preset','fast','-crf','22','-c:a','aac','-ac','2','-ar','44100','-movflags','+faststart',source])
    frames=[]
    for index,fraction in enumerate((.08,.35,.65,.92)):
        at=round(duration*fraction,3);dest=folder/f'frame-{index}.jpg'
        run(['-ss',at,'-i',source,'-frames:v','1','-vf','scale=512:-2','-q:v','4',dest]);frames.append({'file':dest.name,'at':at})
    if has_audio:run(['-i',source,'-vn','-ac','1','-ar','16000',folder/'source.wav'])
    return {'duration':duration,'has_audio':has_audio,'frames':frames,'filename':source.name,
            'selection':{'start':start,'end':end,'source_duration':original_duration}}

def mix(folder, track_path, name, duration, preserve_audio=True, level=.22, duck=True,sound_plan=None):
    # Duck music against original audio energy, not a claimed speech detector.
    sr=44100;count=int(duration*sr)
    music,rate=sf.read(track_path,always_2d=True,dtype='float32')
    import math
    if rate!=sr:
        divisor=math.gcd(rate,sr);music=resample_poly(music,sr//divisor,rate//divisor)
    if music.shape[1]==1:music=np.repeat(music,2,axis=1)
    music=music[:count,:2]
    if len(music)<count:music=np.pad(music,((0,count-len(music)),(0,0)))
    music*=min(2,.13/max(float(np.sqrt(np.mean(music.astype(float)**2))),1e-6))
    envelope=np.ones(count,dtype=np.float32)*level
    source=folder/'source.wav'
    if preserve_audio and duck and source.exists():
        original,rate=sf.read(source,dtype='float32');chunk=max(1,int(rate*.05))
        values=np.array([np.sqrt(np.mean(original[i:i+chunk]**2)) for i in range(0,len(original),chunk)])
        duck=1-.72*np.clip(values/.08,0,1)
        # Release ducking after the source audio ends; do not extend its last
        # energy measurement over the rest of a longer video.
        times=np.append(np.arange(len(duck))*.05,len(original)/rate+.2)
        envelope*=np.interp(np.arange(count)/sr,times,np.append(duck,1.),right=1.).astype('float32')
    if sound_plan:
        placement=np.zeros(count,dtype='float32')
        for cue in sound_plan['cues']:
            if not cue['enabled'] or cue['kind']!='music':continue
            a,b=int(round(cue['start']*sr)),min(count,int(round(cue['end']*sr)));shape=np.ones(b-a,dtype='float32')*cue['gain']
            fade=min(int(.08*sr),(b-a)//2)
            if fade:shape[:fade]*=np.linspace(0,1,fade);shape[-fade:]*=np.linspace(1,0,fade)
            placement[a:b]=shape
        envelope*=placement
    else:
        fade=min(int(.35*sr),count//2);envelope[:fade]*=np.linspace(0,1,fade);envelope[-fade:]*=np.linspace(1,0,fade)
    combined=music*envelope[:,None]
    if sound_plan:
        from .soundplan import effects_layer
        combined+=effects_layer(sound_plan,duration,sr)[:count]
    bed=folder/(name+'-bed.wav');sf.write(bed,np.clip(combined,-.98,.98),sr,subtype='PCM_16')
    target=folder/(name+'.mp4');temp=folder/(name+'.rendering.mp4')
    args=['-i',folder/'source.mp4','-i',bed]
    if preserve_audio and source.exists():args+=['-filter_complex','[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]','-map','0:v:0','-map','[a]']
    else:args+=['-map','0:v:0','-map','1:a:0']
    run(args+['-c:v','copy','-c:a','aac','-b:a','192k','-t',duration,'-movflags','+faststart',temp]);temp.replace(target)
    return target
