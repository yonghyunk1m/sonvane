"""CPU speech worker; reads only the requested reply text, never API keys."""
import json,sys
from pathlib import Path
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro
from speech_alignment import prepare_words,align_words
ROOT=Path(__file__).resolve().parents[1]
job=json.loads(Path(sys.argv[1]).read_text())
settings=ort.SessionOptions();settings.intra_op_num_threads=2;settings.inter_op_num_threads=1
session=ort.InferenceSession(str(ROOT/'.models/speech/kokoro-v1.0.onnx'),sess_options=settings,providers=['CPUExecutionProvider'])
engine=Kokoro.from_session(session,str(ROOT/'.models/speech/voices-v1.0.bin'))
phonemes,owners,words=prepare_words(job['text'],lambda word:engine.tokenizer.phonemize(word,'en-us'))
audio,sr,timings=engine.create_timed(phonemes,voice='af_heart',speed=1.0,lang='en-us',is_phonemes=True)
words=align_words(phonemes,owners,words,timings)
target=Path(job['output']);temp=target.with_suffix('.tmp.wav');sf.write(temp,audio,sr,subtype='PCM_16');temp.replace(target)
metadata=target.with_suffix('.timing.json');pending=metadata.with_suffix('.tmp');pending.write_text(json.dumps({'words':words,'duration':len(audio)/sr,'timing_source':'Kokoro phoneme durations'}));pending.replace(metadata)
print('Speech ready with word timings.',flush=True)
