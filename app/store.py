"""Local-only persistent sessions and conservative API request reservations."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("TUNEJURY_DATA_DIR", str(ROOT / ".data")))
LOCK = threading.RLock()


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid identifier")
    return value


def directory(sid: str) -> Path:
    return DATA / "sessions" / identifier(sid)


def read(sid: str) -> dict:
    with LOCK:
        return json.loads((directory(sid) / "session.json").read_text())


def write(session: dict) -> None:
    with LOCK:
        folder = directory(session["id"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "session.json"
        temp = folder / "session.tmp"
        temp.write_text(json.dumps(session, ensure_ascii=False, allow_nan=False))
        temp.replace(target)


def update(sid: str, function) -> dict:
    with LOCK:
        session = read(sid)
        function(session)
        write(session)
        return session


def create() -> dict:
    session = {
        "id": uuid.uuid4().hex, "tracks": [], "brief": "", "query_en": "",
        "min_duration": 0, "max_duration": 180, "diversity": 0.35,
        "votes": [], "pair": None, "selected": None, "shortlist": [],
        "score_status": "idle", "score_error": None, "agent_status": "idle",
        "agent_error": None, "activity": [], "revision": 0,
    }
    write(session)
    return session


def database() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / "cache.sqlite", timeout=15)
    conn.execute("CREATE TABLE IF NOT EXISTS scores (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, reserved REAL NOT NULL, actual REAL, status TEXT NOT NULL)")
    return conn


def cache_get(key: str):
    with database() as conn:
        row = conn.execute("SELECT value FROM scores WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def cache_set(key: str, result: dict):
    with database() as conn:
        conn.execute("INSERT OR REPLACE INTO scores VALUES (?, ?)", (key, json.dumps(result)))


def budget_status() -> dict:
    with database() as conn:
        count, reserved, actual = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(reserved),0), COALESCE(SUM(actual),0) FROM requests"
        ).fetchone()
    return {"requests": count, "reserved_usd": round(reserved, 4),
            "reported_usd": round(actual, 6), "limit_usd": float(os.getenv("META_BUDGET_USD", "5")),
            "max_requests": int(os.getenv("META_MAX_REQUESTS", "40"))}


def reserve_request(reserved_usd: float = 0.10) -> str:
    # Reserve BEFORE sending. Failed/uncertain requests retain their reservation.
    if not 0.10 <= reserved_usd <= 5.0:
        raise ValueError("Invalid request reservation.")
    with database() as conn:
        conn.execute("BEGIN IMMEDIATE")
        count, total = conn.execute("SELECT COUNT(*), COALESCE(SUM(reserved),0) FROM requests").fetchone()
        limit = min(float(os.getenv("META_BUDGET_USD", "5")), 150.0)
        if count >= int(os.getenv("META_MAX_REQUESTS", "40")) or total + reserved_usd > limit + 1e-9:
            raise ValueError("This app has reached its Meta request budget. Further calls are blocked.")
        rid = uuid.uuid4().hex
        conn.execute("INSERT INTO requests VALUES (?, ?, NULL, 'reserved')", (rid, reserved_usd))
    return rid


def finish_request(rid: str, usage: dict):
    actual = (usage.get("prompt_tokens", 0) * 1.25 + usage.get("completion_tokens", 0) * 4.25) / 1_000_000
    with database() as conn:
        conn.execute("UPDATE requests SET actual=?, status='complete' WHERE id=?", (actual, rid))


def event(session: dict, kind: str, message: str, details=None):
    session["activity"].append({"kind": kind, "message": message, "details": details})
    session["activity"] = session["activity"][-60:]
