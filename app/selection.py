"""Deterministic, inspectable ranking. No claim of learned personal preference."""
from __future__ import annotations

import itertools
import random

from .audio import cosine


def eligible(session):
    return [t for t in session["tracks"] if t.get("score") is not None
            and session["min_duration"] <= t["duration"] <= session["max_duration"]]


def ranks(values):
    ordered = sorted(set(values))
    return {v: ordered.index(v) / max(1, len(ordered) - 1) for v in ordered}


def shortlist(session, count=3):
    tracks = eligible(session)
    if not tracks:
        session["shortlist"] = []
        return []
    quality = ranks([t["score"] for t in tracks])
    alignment = ranks([t["alignment"] for t in tracks if t.get("alignment") is not None])
    wins = {t["id"]: 0 for t in tracks}
    losses = dict(wins)
    for vote in session["votes"]:
        if vote["winner"] in wins:
            wins[vote["winner"]] += 1
        if vote.get("loser") in losses:
            losses[vote["loser"]] += 1
    def utility(t):
        # This is an explicit heuristic, NOT a personalized reward model.
        preference = 0.15 * (wins[t["id"]] - losses[t["id"]])
        if t.get("alignment") is None:
            return quality[t["score"]] + preference
        return 0.6 * quality[t["score"]] + 0.4 * alignment[t["alignment"]] + preference
    chosen = []
    remaining = list(tracks)
    while remaining and len(chosen) < count:
        def criterion(t):
            redundancy = max((max(0, cosine(t["embedding"], c["embedding"])) for c in chosen), default=0)
            return utility(t) - session["diversity"] * redundancy
        best = max(remaining, key=lambda t: (criterion(t), t["id"]))
        chosen.append(best)
        remaining.remove(best)
    session["shortlist"] = [t["id"] for t in chosen]
    return chosen


def next_pair(session, requested=None):
    tracks = eligible(session)
    seen = {frozenset((v["a"], v["b"])) for v in session["votes"]}
    valid = {t["id"] for t in tracks}
    pairs = [(a, b) for a, b in itertools.combinations(tracks, 2)
             if frozenset((a["id"], b["id"])) not in seen]
    if requested:
        a, b = requested
        if a == b or a not in valid or b not in valid or frozenset((a, b)) in seen:
            raise ValueError("These candidates cannot be compared.")
        ids = [a, b]
    elif pairs:
        preferred = set(session["shortlist"])
        a, b = min(pairs, key=lambda pair: (
            -sum(t["id"] in preferred for t in pair),
            abs(pair[0]["score"] - pair[1]["score"])))
        ids = [a["id"], b["id"]]
    else:
        session["pair"] = None
        return None
    random.SystemRandom().shuffle(ids)
    session["pair"] = {"a": ids[0], "b": ids[1], "revealed": False}
    return session["pair"]


def export_report(session):
    tracks = sorted(eligible(session), key=lambda t: t["score"], reverse=True)
    return {
        "project": "Sonvane", "brief": session["brief"], "query_en": session["query_en"],
        "model": "TuneJury A1 (CLAP audio-only), first 10 seconds, empty text branch",
        "baseline_score_order": [t["id"] for t in tracks], "shortlist": session["shortlist"],
        "selected_by_user": session["selected"], "votes": session["votes"],
        "tracks": [{k: v for k, v in t.items() if k not in ("embedding", "waveform", "path")}
                   for t in session["tracks"]],
        "activity": session["activity"],
        "limits": ["Scores are not personal preference probabilities.",
                   "CLAP similarity does not certify that a request was satisfied.",
                   "Ranking and diversity are heuristics, not a trained personal model.",
                   "Synthetic examples test operation, not musical or human preference quality."],
    }
