"""Local, explicitly remembered pairwise preferences over frozen audio embeddings.

This trains a regularized Bradley–Terry linear residual, not the TuneJury model.
Each video context has its own fit. Text memories are separate explicit instructions.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from . import store

CONTEXTS = ('general', 'narration', 'travel', 'product', 'cinematic')

def _path(pid):
    return store.DATA / 'profiles' / (store.identifier(pid) + '.json')

def load(pid):
    with store.LOCK:
        path = _path(pid)
        return json.loads(path.read_text()) if path.exists() else {'id':pid,'pairs':[],'notes':[],'version':0}

def save(profile):
    with store.LOCK:
        path = _path(profile['id']);path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(profile,allow_nan=False));tmp.replace(path)

def normalized(embedding):
    vector=np.asarray(embedding,dtype=float)
    if vector.ndim!=1 or not len(vector) or not np.isfinite(vector).all():
        raise ValueError('Invalid audio features.')
    return vector/max(float(np.linalg.norm(vector)),1e-8)

def fit(profile, context, dimension):
    rows=[p for p in profile['pairs'] if p['context'] in ('general',context) and len(p['difference'])==dimension]
    if not rows:return np.zeros(dimension),0
    x=np.asarray([r['difference'] for r in rows]);penalty=.25
    def objective(w):
        z=x@w
        return float(np.logaddexp(0,-z).sum()+penalty/2*(w@w)),x.T@(expit(z)-1)+penalty*w
    result=minimize(objective,np.zeros(dimension),jac=True,method='L-BFGS-B',options={'maxiter':150})
    if not np.isfinite(result.x).all():raise ValueError('Preference fitting failed.')
    return result.x,len(rows)

def annotate(tracks, profile_id, context):
    profile=load(profile_id)
    if not tracks:return {'pairs':0,'version':profile['version']}
    w,count=fit(profile,context,len(tracks[0]['embedding']))
    # Warm-up shrinks the learned residual; it is not a calibrated confidence.
    strength=min(.30,.30*count/8)
    for t in tracks:
        t['personal_signal']=round(float(w@normalized(t['embedding'])),6)
        t['personal_adjustment']=round(strength*float(np.tanh(t['personal_signal'])),6)
    return {'pairs':count,'version':profile['version'],'strength':strength,'method':'regularized pairwise logistic residual on frozen CLAP features'}

def remember_pair(pid,context,winner,loser,project_id):
    if context not in CONTEXTS:raise ValueError('Unknown preference context.')
    a,b=normalized(winner['embedding']),normalized(loser['embedding'])
    if winner['sha256']==loser['sha256']:raise ValueError('Choose two different recordings to learn a preference.')
    if len(a)!=len(b):raise ValueError('Audio feature dimensions do not match.')
    with store.LOCK:
        p=load(pid)
        # One direction per pair; repeating a click must not amplify the evidence.
        key=sorted([winner['sha256'],loser['sha256']])
        p['pairs']=[r for r in p['pairs'] if not(r['context']==context and r['key']==key)]
        if len(p['pairs'])>=200:raise ValueError('Preference memory is full. Remove earlier choices to continue.')
        item={'id':uuid.uuid4().hex,'context':context,'key':key,'difference':(a-b).tolist(),
              'winner':winner['name'],'loser':loser['name'],'project_id':project_id,
              'created_at':datetime.now(timezone.utc).isoformat()}
        p['pairs'].append(item);p['version']+=1;save(p)
        return item['id']

def remember_note(pid,context,text):
    text=text.strip()[:1000]
    if not text:return
    with store.LOCK:
        p=load(pid)
        if not any(n['context']==context and n['text']==text for n in p['notes']):
            if len(p['notes'])>=30:raise ValueError('Text memory is full. Remove an earlier note first.')
            p['notes'].append({'id':uuid.uuid4().hex,'context':context,'text':text});p['version']+=1;save(p)

def forget(pid,item_id=None):
    with store.LOCK:
        p=load(pid)
        p['pairs']=[x for x in p['pairs'] if item_id and x['id']!=item_id]
        p['notes']=[x for x in p['notes'] if item_id and x['id']!=item_id]
        p['version']+=1;save(p)

def summary(pid):
    p=load(pid)
    return {'id':pid,'version':p['version'],'pair_count':len(p['pairs']),
            'pairs':[{k:v for k,v in r.items() if k not in ('difference','key')} for r in p['pairs']],
            'notes':p['notes']}
