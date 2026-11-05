from types import SimpleNamespace
import pytest
from app.speech_text import markdown_to_speech
from scripts.speech_alignment import prepare_words,align_words


def test_markdown_is_spoken_as_visible_words():
 text='## Scene\n\n**Warm piano** and *soft strings*.\n\n* **Pace:** 78 BPM.\n* Keep `volume` low.\n\n[Reference](https://example.org) ![A scene](image.png)'
 assert markdown_to_speech(text)=='Scene Warm piano and soft strings. Pace: 78 BPM. Keep volume low. Reference A scene'
 assert markdown_to_speech('**direction**: Keep it calm.')=='direction: Keep it calm.'
 assert markdown_to_speech('1. First\n2. Second')=='First Second'


def test_word_times_follow_model_durations_including_expanded_numbers():
 pronunciations={'78':'seven eight','BPM.':'bee pee em.'}
 phonemes,owners,words=prepare_words('78 BPM.',pronunciations.get)
 times=[SimpleNamespace(phoneme=c,start=i*.03,end=(i+1)*.03) for i,c in enumerate(phonemes)]
 result=align_words(phonemes,owners,words,times)
 assert result[0]['text']=='78' and result[0]['start']==0 and result[0]['end']==pytest.approx(.33)
 assert result[1]['text']=='BPM.' and result[1]['start']==pytest.approx(.36)
 assert result[1]['end']==len(phonemes)*.03


def test_missing_tts_timings_are_not_faked():
 phonemes,owners,words=prepare_words('hello',lambda x:x)
 with pytest.raises(ValueError,match='aligned word timings'):
  align_words(phonemes,owners,words,[])
