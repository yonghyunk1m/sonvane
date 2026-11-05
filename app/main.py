from __future__ import annotations

import io
import json
import os
from pathlib import Path
import uuid
import zipfile
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import numpy as np
import soundfile as sf
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, audio, selection, store, studio, conversation, soundplan

@asynccontextmanager
async def lifespan(app):
    # A stopped process cannot finish its old background jobs. Make this visible
    # and allow the user to resume; do not automatically repeat any paid calls.
    for path in (store.DATA / "sessions").glob("*/session.json"):
        try:
            session = store.read(path.parent.name)
            changed = False
            for prefix in ("score", "agent"):
                if session[prefix + "_status"] == "running":
                    session[prefix + "_status"] = "error"
                    session[prefix + "_error"] = "The server restarted and interrupted this job. Run it again to continue."
                    changed = True
            if changed:
                store.write(session)
        except (ValueError, KeyError, OSError):
            continue
    for path in (store.DATA / "projects").glob("*/project.json"):
        try:
            project = studio.read(path.parent.name)
            if project.get('cue_pending'):
                rid=project.pop('cue_pending');project.setdefault('cue_requests',{})[rid]='error'
                project['cue_error']='The server restarted during sound planning. No request was automatically retried.';studio.write(project)
            if project.get("chat_pending"):
                rid=project.pop("chat_pending")
                project.setdefault("chat_requests",{})[rid]="error"
                project.setdefault("conversation",[]).append({"id":uuid.uuid4().hex,"role":"system","text":"The server restarted during the conversation. No message was automatically retried.","request_id":rid})
                studio.write(project)
            if project["status"] in studio.RUNNING:
                project["error"] = "The server restarted. Resume saved work, or start a new generation if no plan was saved."
                studio.log(project, "error", project["error"])
        except (ValueError, KeyError, OSError):
            continue
    yield


app = FastAPI(title="Sonvane", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Local preview only"}, status_code=403)
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD") and origin:
        from urllib.parse import urlparse
        if urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Origin mismatch"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    wasm = " 'wasm-unsafe-eval'" if request.url.path.startswith('/demo/') else ""
    response.headers["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'{wasm}; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def get_session(sid):
    try:
        return store.read(sid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Session not found.") from None


def writable(session):
    if session["score_status"] == "running" or session["agent_status"] == "running":
        raise HTTPException(409, "Wait for the current job to finish, then try again.")


def public(session):
    result = json.loads(json.dumps(session))
    for track in result["tracks"]:
        track.pop("embedding", None)
        track.pop("path", None)
    return result


def find_track(session, tid):
    for track in session["tracks"]:
        if track["id"] == tid:
            return track
    raise HTTPException(404, "Audio not found.")


@app.get("/api/status")
def status():
    return {"meta_ready": bool(os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY")),
            "model_files_ready": all((audio.MODELS / n).exists() for n in
                ("A1_clap_audio_only.pt", "music_audioset_epoch_15_esc_90.14.pt")),
            "scorer": audio.MODEL_LABEL, "budget": store.budget_status()}


@app.post("/api/sessions")
def create():
    return public(store.create())


@app.get("/api/sessions/{sid}")
def read(sid: str):
    return public(get_session(sid))


class Brief(agent.Policy):
    brief: str = Field(default="", max_length=2000)


@app.put("/api/sessions/{sid}/brief")
def brief(sid: str, body: Brief):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        if body.min_duration > body.max_duration:
            raise ValueError("Minimum length must not exceed maximum length.")
        query_changed = body.query_en != session["query_en"]
        session.update(body.model_dump())
        if query_changed:
            for t in session["tracks"]:
                t["alignment"] = None
        session["pair"] = None
        selection.shortlist(session)
        session["revision"] += 1
        store.write(session)
        return public(session)


@app.post("/api/sessions/{sid}/tracks")
def upload(sid: str, file: UploadFile = File(...)):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        if len(session["tracks"]) >= 12:
            raise ValueError("This version supports up to 12 candidates per session.")
        name = Path(file.filename or "audio.wav").name[:120]
        if Path(name).suffix.lower() not in (".wav", ".flac", ".ogg", ".mp3"):
            raise ValueError("Use WAV, FLAC, OGG, or MP3 files.")
        tid = uuid.uuid4().hex
        path = store.directory(sid) / (tid + ".upload")
        total = 0
        try:
            with path.open("wb") as target:
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 24 * 1024 * 1024:
                        raise ValueError("Each file must be 24 MB or smaller.")
                    target.write(chunk)
            try:
                details = audio.inspect_audio(path)
            except (RuntimeError, sf.LibsndfileError):
                raise ValueError("Could not read this audio. Convert it to WAV or FLAC and try again.") from None
            # Normalize container only; preserve samples, channels and amplitude.
            wav, sr = sf.read(path, dtype="float32", always_2d=True)
            final = store.directory(sid) / (tid + ".wav")
            sf.write(final, wav, sr, subtype="FLOAT")
            track = {"id": tid, "name": name, "path": str(final), **details,
                     "score": None, "alignment": None, "source": "uploaded", "embedding": None}
            session["tracks"].append(track)
            session["pair"] = None
            session["revision"] += 1
            store.write(session)
        finally:
            path.unlink(missing_ok=True)
        return public(session)


@app.post("/api/sessions/{sid}/demo")
def demo(sid: str):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        if session["tracks"]:
            raise ValueError("Test clips can only be added to an empty session.")
        # Original deterministic synthesis for plumbing tests, not external recordings.
        sr = 24000
        for index, (name, tempo, brightness) in enumerate([
            ("Test 01 · Soft keys", 80, .1), ("Test 02 · Open keys", 80, .3),
            ("Test 03 · Moving pulse", 120, .15), ("Test 04 · Sparse notes", 60, .08)]):
            duration = 12
            wave = np.zeros(sr * duration, dtype=np.float32)
            notes = [60, 64, 67, 71, 69, 67, 64, 62]
            beat = 60 / tempo
            for j in range(int(duration / beat)):
                start = int(j * beat * sr)
                length = min(int(sr * 1.5), len(wave) - start)
                time = np.arange(length) / sr
                freq = 440 * 2 ** ((notes[j % len(notes)] - 69) / 12)
                attack = np.minimum(time / .02, 1)
                sound = (np.sin(2 * np.pi * freq * time) + brightness * np.sin(4 * np.pi * freq * time))
                wave[start:start + length] += (.18 * sound * attack * np.exp(-time * 3)).astype(np.float32)
            tid = uuid.uuid4().hex
            path = store.directory(sid) / (tid + ".wav")
            sf.write(path, wave, sr, subtype="PCM_16")
            session["tracks"].append({"id": tid, "name": name, "path": str(path),
                **audio.inspect_audio(path), "score": None, "alignment": None,
                "embedding": None, "source": "synthetic-test"})
        store.event(session, "local", "Created four synthetic test clips. These are not music-quality evaluation data.")
        store.write(session)
        return public(session)


def score_job(sid):
    session = store.read(sid)
    try:
        for t in session["tracks"]:
            if t.get("score") is None:
                t.update(audio.score_path(Path(t["path"]), t["sha256"]))
                store.event(session, "score", f"{t['name']} · A1 inference completed", {"cached": t["cached"]})
                store.write(session)
        audio.apply_alignment(session, session["query_en"])
        selection.shortlist(session)
        selection.next_pair(session)
        session["score_status"] = "complete"
    except Exception as exc:
        import traceback
        traceback.print_exc()
        session["score_status"] = "error"
        session["score_error"] = str(exc)[:300]
    finally:
        store.write(session)


@app.post("/api/sessions/{sid}/score")
def score(sid: str, background: BackgroundTasks):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        if len(session["tracks"]) < 2:
            raise ValueError("Add at least two candidates.")
        session["score_status"], session["score_error"] = "running", None
        store.write(session)
    background.add_task(score_job, sid)
    return public(session)


@app.post("/api/sessions/{sid}/agent")
def run_agent(sid: str, background: BackgroundTasks):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        if not (os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY")):
            raise HTTPException(409, "No Meta API key is configured. Local comparisons remain available.")
        if len(selection.eligible(session)) < 2:
            raise ValueError("At least two scored candidates must meet the current criteria.")
        if not session["brief"].strip():
            raise ValueError("Describe what you need in the brief first.")
        session["agent_status"], session["agent_error"] = "running", None
        store.write(session)
    background.add_task(agent.run, sid)
    return public(session)


class Vote(BaseModel):
    winner: str
    reason: str = Field(default="", max_length=500)


@app.post("/api/sessions/{sid}/vote")
def vote(sid: str, body: Vote):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        pair = session["pair"]
        if not pair or pair["revealed"]:
            raise ValueError("Start a new comparison first.")
        if body.winner not in ("a", "b", "tie"):
            raise ValueError("Choose A, B, or no preference.")
        winner = pair[body.winner] if body.winner != "tie" else None
        loser = pair["b" if body.winner == "a" else "a"] if winner else None
        a, b = find_track(session, pair["a"]), find_track(session, pair["b"])
        model_winner = a["id"] if a["score"] > b["score"] else b["id"] if b["score"] > a["score"] else None
        session["votes"].append({"a": a["id"], "b": b["id"], "winner": winner, "loser": loser,
                                 "reason": body.reason, "model_winner": model_winner,
                                 "disagreement": bool(winner and model_winner and winner != model_winner)})
        pair["revealed"] = True
        selection.shortlist(session)
        store.event(session, "human", "Recorded the listening choice and updated the shortlist.")
        store.write(session)
        return public(session)


@app.post("/api/sessions/{sid}/next")
def next_comparison(sid: str):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        selection.next_pair(session)
        store.write(session)
        return public(session)


class Choice(BaseModel):
    track_id: str


@app.post("/api/sessions/{sid}/select")
def choose(sid: str, body: Choice):
    with store.LOCK:
        session = get_session(sid)
        writable(session)
        find_track(session, body.track_id)
        session["selected"] = body.track_id
        store.event(session, "human", "The listener selected the final candidate.")
        store.write(session)
        return public(session)


@app.get("/api/sessions/{sid}/audio/{tid}")
def audio_file(sid: str, tid: str, download: bool = False):
    track = find_track(get_session(sid), tid)
    return FileResponse(track["path"], media_type="audio/wav",
                        filename=f"{Path(track["name"]).stem}.wav" if download else None)


@app.get("/api/sessions/{sid}/record")
def decision_record(sid: str):
    session = get_session(sid)
    if not session["selected"]:
        raise ValueError("Select a final candidate first.")
    return Response(json.dumps(selection.export_report(session), ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="decision-record.json"'})


@app.get("/api/sessions/{sid}/export")
def export(sid: str):
    session = get_session(sid)
    if not session["selected"]:
        raise ValueError("Select a final candidate first.")
    selected = find_track(session, session["selected"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(selected["path"], "selected.wav")
        archive.writestr("selection.json", json.dumps(selection.export_report(session), ensure_ascii=False, indent=2))
    return Response(out.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="sonvane-selection.zip"'})


@app.get("/")
def home(request: Request):
    query = "?" + request.url.query if request.url.query else ""
    return RedirectResponse("/studio/" + query)

app.include_router(studio.router)
app.include_router(conversation.router)
app.include_router(soundplan.router)

app.mount("/", StaticFiles(directory=store.ROOT / "app" / "static", html=True), name="static")
