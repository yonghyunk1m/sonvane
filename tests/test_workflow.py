import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import agent, audio, selection, store
from app.main import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setenv("META_MAX_REQUESTS", "40")
    monkeypatch.setenv("META_BUDGET_USD", "5")


@pytest.fixture
def client():
    return TestClient(app)


def fixture_session():
    s = store.create()
    s["tracks"] = [{"id": f"{i:032x}", "name": f"fixture-{i}.wav", "duration": duration,
                     "score": score, "alignment": None, "embedding": emb,
                     "waveform": [], "source": "test-only"}
                    for i, duration, score, emb in [(1, 12, 1.0, [1., 0.]),
                                                   (2, 12, .99, [1., 0.]),
                                                   (3, 12, .98, [0., 1.]),
                                                   (4, 100, 5., [0., 1.])]]
    store.write(s)
    return s


def test_duration_constraints_and_diversity():
    s = fixture_session()
    s["max_duration"] = 20
    s["diversity"] = 1
    chosen = selection.shortlist(s, count=2)
    assert [t["id"] for t in chosen] == [f"{1:032x}", f"{3:032x}"]
    s["max_duration"] = 2
    assert selection.shortlist(s) == []


def test_unknown_scores_never_become_zero_scores():
    s = fixture_session()
    s["tracks"][0]["score"] = None
    assert s["tracks"][0] not in selection.shortlist(s, count=4)


def test_rejected_pairs_and_no_repeat():
    s = fixture_session()
    selection.shortlist(s)
    pair = selection.next_pair(s)
    s["votes"].append({**pair, "winner": None, "loser": None})
    again = selection.next_pair(s)
    assert set(again[k] for k in ("a", "b")) != set(pair[k] for k in ("a", "b"))
    with pytest.raises(ValueError):
        selection.next_pair(s, [pair["a"], pair["b"]])
    with pytest.raises(ValueError):
        selection.next_pair(s, [pair["a"], "made-up-id"])


def test_user_choice_is_not_overwritten_by_model_ranking(client):
    s = fixture_session()
    selection.next_pair(s, [s["tracks"][0]["id"], s["tracks"][2]["id"]])
    store.write(s)
    prefix = f"/api/sessions/{s['id']}"
    winner = 'a' if s['pair']['a'] == s['tracks'][2]['id'] else 'b'
    result = client.post(prefix + '/vote', json={"winner": winner, "reason": "my actual choice"})
    assert result.status_code == 200
    assert result.json()["votes"][-1]["disagreement"] is True
    assert client.post(prefix + '/vote', json={"winner": winner}).status_code == 400
    choice = s['tracks'][2]['id']
    assert client.post(prefix + '/select', json={"track_id": choice}).json()['selected'] == choice
    current = store.read(s['id'])
    selection.shortlist(current)
    assert current['selected'] == choice


def test_real_upload_download_and_export(client):
    s = client.post('/api/sessions').json()
    prefix = f"/api/sessions/{s['id']}"
    data = io.BytesIO()
    sr = 16000
    wave = .1 * np.sin(2 * np.pi * 440 * np.arange(sr * 2) / sr)
    sf.write(data, wave, sr, format='WAV')
    result = client.post(prefix + '/tracks', files={'file': ('../../fixture.wav', data.getvalue(), 'audio/wav')})
    assert result.status_code == 200
    t = result.json()['tracks'][0]
    assert t['name'] == 'fixture.wav'
    assert 'path' not in t and 'embedding' not in t
    assert t['score'] is None
    assert t['duration'] == 2
    assert client.get(prefix+'/audio/'+t['id']).status_code == 200
    assert client.get(prefix+'/export').status_code == 400
    assert client.get(prefix+'/record').status_code == 400
    client.post(prefix+'/select', json={'track_id': t['id']})
    exported = client.get(prefix+'/export')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        assert set(z.namelist()) == {'selected.wav', 'selection.json'}
        report = json.loads(z.read('selection.json'))
        assert report['selected_by_user'] == t['id']
        assert 'path' not in report['tracks'][0]
        assert report['tracks'][0]['score'] is None
    record = client.get(prefix+'/record')
    assert record.json() == report
    assert 'attachment;' in record.headers['content-disposition']
    download = client.get(prefix+'/audio/'+t['id']+'?download=true')
    assert 'attachment;' in download.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        assert download.content == z.read('selected.wav')
    assert client.get(prefix+'/audio/missing?download=true').status_code == 404



def test_invalid_audio_and_missing_key(client):
    s = client.post('/api/sessions').json()
    prefix = f"/api/sessions/{s['id']}"
    assert client.post(prefix+'/tracks',files={'file':('bad.wav',b'not audio')}).status_code == 400
    assert client.post(prefix+'/tracks',files={'file':('bad.txt',b'not audio')}).status_code == 400
    assert client.post(prefix+'/agent').status_code == 409
    assert store.budget_status()['requests'] == 0
    assert client.get('/api/sessions/not-a-real-id').status_code == 404


def test_running_job_cannot_be_overwritten(client):
    s = fixture_session()
    s['agent_status'] = 'running'
    store.write(s)
    assert client.put(f"/api/sessions/{s['id']}/brief",json={'brief':'new'}).status_code == 409
    assert client.post(f"/api/sessions/{s['id']}/next").status_code == 409


def test_origin_and_host_protection(client):
    assert client.post('/api/sessions',headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code == 403


def test_concurrent_budget_reservations_are_bounded(monkeypatch):
    monkeypatch.setenv('META_BUDGET_USD','0.30')
    # Initialize schema before concurrent writers.
    store.budget_status()
    def reserve(_):
        try: return store.reserve_request()
        except ValueError: return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(12)))
    assert len([r for r in results if r]) == 3
    assert store.budget_status()['reserved_usd'] == .3


def test_meta_loop_executes_tools_and_never_chooses_final(monkeypatch):
    s = fixture_session()
    s['agent_status'] = 'running'
    s['brief'] = 'Choose varied candidates'
    store.write(s)
    outputs = iter([
        {'role':'assistant','content':None,'tool_calls':[
            {'id':'1','type':'function','function':{'name':'get_candidates','arguments':'{}'}},
            {'id':'2','type':'function','function':{'name':'build_shortlist','arguments':'{}'}}]},
        {'role':'assistant','content':'I organized the candidates using the measured tool results.'}])
    messages = []
    def mocked_request(m):
        messages.append(json.loads(json.dumps(m)))
        return next(outputs)
    monkeypatch.setattr(agent,'request',mocked_request)
    agent.run(s['id'])
    final = store.read(s['id'])
    assert final['agent_status'] == 'complete'
    assert len(final['shortlist']) == 3
    assert final['selected'] is None
    assert any(m['role']=='tool' for m in messages[1])
    assert final['activity'][-1]['kind'] == 'meta'


def test_meta_failure_is_explicit(monkeypatch):
    s = fixture_session()
    def fail(_): raise ValueError('controlled error')
    monkeypatch.setattr(agent,'request',fail)
    agent.run(s['id'])
    final = store.read(s['id'])
    assert final['agent_status'] == 'error'
    assert final['agent_error'] == 'controlled error'
    assert not any(e['kind']=='meta' for e in final['activity'])


def test_meta_finishes_when_valid_comparison_is_ready(monkeypatch):
    s = fixture_session()
    s['agent_status'] = 'running'
    selection.shortlist(s)
    store.write(s)
    calls = []
    def mocked_request(_):
        calls.append(1)
        return {'role':'assistant','content':None,'tool_calls':[
            {'id':'pair','type':'function','function':{'name':'propose_comparison',
             'arguments':json.dumps({'a':s['tracks'][0]['id'],'b':s['tracks'][1]['id']})}}]}
    monkeypatch.setattr(agent,'request',mocked_request)
    agent.run(s['id'])
    result = store.read(s['id'])
    assert len(calls) == 1
    assert result['agent_status'] == 'complete'
    assert result['pair'] is not None
    assert result['activity'][-1]['kind'] == 'meta_result'


def test_score_cache_keeps_model_provenance():
    result = {'score': -0.2, 'model': audio.MODEL_LABEL, 'window':[0,10], 'embedding':[1,0]}
    store.cache_set('unit-test-version:content-hash',result)
    assert store.cache_get('unit-test-version:content-hash') == result
    assert store.cache_get('different-version:content-hash') is None
