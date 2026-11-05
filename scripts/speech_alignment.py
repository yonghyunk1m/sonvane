"""Map source words to the phoneme durations returned by the local TTS model."""
import re

def prepare_words(text,phonemize):
    words=[];phonemes=[];owners=[]
    for match in re.finditer(r'\S+',text):
        word=match.group();pronunciation=phonemize(word).strip()
        index=len(words);words.append({'text':word})
        if phonemes:phonemes.append(' ')
        phonemes.append(pronunciation)
        owners.extend([index for char in pronunciation if not char.isspace()])
    return ' '.join(''.join(phonemes).split()),owners,words

def align_words(phonemes,owners,words,timings):
    expected=''.join(char for char in phonemes if not char.isspace())
    spoken=[t for t in timings if not t.phoneme.isspace()]
    # Do not invent word timings if a runtime/model does not return matching durations.
    if ''.join(t.phoneme for t in spoken)!=expected or len(owners)!=len(spoken):
        raise ValueError('The local voice did not return aligned word timings.')
    for owner,timing in zip(owners,spoken):
        word=words[owner];word.setdefault('start',timing.start);word['end']=timing.end
    last=0.0
    for word in words:
        word.setdefault('start',last);word.setdefault('end',word['start']);last=word['end']
    return words
