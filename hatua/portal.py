"""The teacher portal: a small web server that runs on the teacher's own laptop.

    python -m hatua portal            ->  http://127.0.0.1:8765

Standard library only. It listens on 127.0.0.1, so nothing outside this computer can
reach it, and it makes no outgoing calls except to Ollama on this same computer.

Every request after sign-in carries:
* the session in an HttpOnly, SameSite=Strict cookie (page scripts cannot read it), and
* for anything that changes data, a CSRF value in the X-Hatua-CSRF header.

What a teacher can see is decided by hatua.scope only: their own learners, with the
full Grade 4 to 9 history of each one. Earlier grades are read-only: there is no
endpoint that edits a record. Approving a drive file, opening pathway ideas, rating a
comment and marking that the parent was told all need a signed-in teacher (a human
session, never an agent token).

Sign-in: a one-time PIN opens nothing but the "choose your own PIN" step; signing in
ends the same member number's sign-in anywhere else; and every sign-in, failed PIN,
sign-out and PIN change is written to the audit log, where the teacher can see their own.
"""
from __future__ import annotations

import json
import re
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import (
    assistant,
    audit,
    auth,
    comments,
    config,
    drive,
    notify,
    pathways,
    patterns,
    school,
    school_calendar,
    scope,
    store,
)
from .summary import GateBlocked

PAGE = Path(__file__).resolve().parent.parent / "ui" / "portal.html"
COOKIE = "hatua_session"
LOCK = threading.Lock()  # one request at a time touches the JSON store
MAX_BODY = 6 * 1024 * 1024
HEADERS = {
    # Nothing may load from, or be sent to, anywhere but this computer: no web font, no image, no call.
    "Content-Security-Policy": ("default-src 'none'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY", "Cache-Control": "no-store",
}


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _demo() -> dict | None:
    p = config.ROOT / "demo.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _auth_event(what: str, actor: str, ok: bool, **output) -> None:
    audit.write_event({"tool": f"auth.{what}", "actor": actor, "ok": ok, "output": output})


AUTH_WORDS = {"auth.sign_in": ("Signed in", "Wrong PIN tried"), "auth.sign_out": ("Signed out", "Signed out"),
              "auth.pin_change": ("PIN changed", "PIN change refused")}


def _did(e: dict) -> str | None:
    """One audit-log line in a teacher's words, or None for lines that are not worth showing."""
    tool, out = e.get("tool", ""), e.get("output") or {}
    kwargs = (e.get("inputs") or {}).get("kwargs") or {}
    name = str(kwargs.get("file", "")).rsplit("/", 1)[-1]
    learner = store.learner(kwargs.get("learner_id", "")) or {}
    child = f"{learner.get('first_name', '')} ({kwargs.get('learner_id', '')})"
    if tool == "drive.approve":
        return f"Approved the file '{name}': {out.get('added', 0)} results added to Hatua"
    if tool == "drive.reject":
        return f"Rejected the file '{name}'"
    if tool == "drive.upload":
        return f"Uploaded the file '{name}' to the school drive"
    if tool == "pathways.open":
        return f"Opened pathway ideas for {child}"
    if tool == "parent.told":
        return f"Recorded that the parent of {child} was told ({str(out.get('how', '')).lower()})"
    if tool == "comment.rate":
        return f"Gave a report comment a thumbs {out.get('rating', '')}"
    if tool == "assistant.ask" and out.get("step") == "answer":
        return "Asked the assistant a question" + (" (refused: no rankings)" if out.get("refused") else "")
    return None


def _account(teacher_id: str) -> dict:
    """The teacher's own account: sign-ins, wrong PINs tried on their number, and what they did."""
    mine = [e for e in audit.read_events() if e.get("actor") == teacher_id]
    events = [e for e in mine if e.get("tool") in AUTH_WORDS]
    did = [{"when": e.get("ts"), "what": w} for e in mine if (w := _did(e))][-15:][::-1]
    recent = [{"when": e.get("ts"), "ok": bool(e.get("ok")),
               "what": ("Sign-in locked for 15 minutes" if (e.get("output") or {}).get("reason") == "locked"
                        else AUTH_WORDS[e["tool"]][0 if e.get("ok") else 1])}
              for e in events[-12:]][::-1]
    return {**auth.account(teacher_id), "recent": recent, "did": did}


def _states(teacher_id: str, today) -> list[dict]:
    return [{"term": s["term"], "label": s["label"], "state": s["state"], "folder": s["folder"],
             "closes": s["closes"].isoformat(), "due": s["due"].isoformat(), "files": s["files"]}
            for s in notify.term_states(teacher_id, today)]


def _learner_card(l: dict, notices: list[dict]) -> dict:
    found = patterns.find(l["learner_id"])
    mine = [n for n in notices if n.get("learner_id") == l["learner_id"]]
    return {"id": l["learner_id"], "name": l["first_name"], "stream": l["stream"], "grade": int(l["current_grade"]),
            "kinds": sorted({p["type"] for p in found["patterns"] if p["current"]}),
            "families": sorted({p["family"] for p in found["patterns"] if p["family"]}),
            "alerts": len([n for n in mine if not n.get("told_parent")]),
            "told": len([n for n in mine if n.get("told_parent")])}


def _learner_detail(teacher_id: str, learner_id: str) -> dict:
    if not scope.can_view(teacher_id, learner_id):
        raise Refused(403, "This learner is not in your class.")
    l = store.learner(learner_id)
    found = patterns.find(learner_id)
    recs = store.records_for(learner_id)
    current = int(l["current_grade"])
    return {
        "id": learner_id, "name": l["first_name"], "stream": l["stream"], "grade": current,
        "span": found["span"], "reviewed": found["records_reviewed"],
        "patterns": [{k: p[k] for k in ("pattern_id", "type", "family", "statement", "trail", "evidence",
                                         "caveats", "current", "terms")} for p in found["patterns"]],
        "record_notes": found["record_notes"],
        "records": [[r["record_id"], r["ordinal"], r["family"], r["level"], r["grade"], r["year"], r["term"],
                     r["learning_area"], r["task"], r["score"], r["teacher"], r["task_date"], r["flags"]]
                    for r in recs],
        "attendance": [[a["attendance_id"], a["ordinal"], a["days_present"], a["days_open"]]
                       for a in store.load("attendance") if a["learner_id"] == learner_id],
        "notes": [[n["note_id"], n["ordinal"], n["family"] or "", n["text"]]
                  for n in store.load("notes") if n["learner_id"] == learner_id],
        "families": sorted({r["family"] for r in recs}),
        "grades": [{"grade": g, "read_only": g < current,
                    "who": "Your class this year" if g == current else "Earlier teachers' records (read only)"}
                   for g in range(4, current + 1)],
        "notices": [n for n in notify.for_teacher(teacher_id, include_resolved=True)
                    if n.get("learner_id") == learner_id],
        "comments": comments.for_learner(learner_id, teacher_id),
        "pathways": pathways.for_teacher(teacher_id, learner_id),
        "model": comments.model_name(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Hatua"
    sys_version = ""

    def log_message(self, fmt, *args):  # keep the terminal quiet; the audit log has the record
        return

    # ---------------------------------------------------------------- plumbing
    def _send(self, status: int, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in {**HEADERS, **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _session(self) -> str | None:
        jar = cookies.SimpleCookie(self.headers.get("Cookie") or "")
        return jar[COOKIE].value if COOKIE in jar else None

    def _who(self, allow_limited: bool = False) -> dict:
        try:
            who = auth.resolve(self._session(), kind="human", allow_limited=True)
        except GateBlocked as exc:
            raise Refused(401, str(exc)) from None
        if who.get("limited") and not allow_limited:
            raise Refused(403, "Choose your own PIN first.")
        return who

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise Refused(413, "That is too large.")
        return self.rfile.read(n) if n else b""

    def _json(self) -> dict:
        try:
            return json.loads(self._body() or b"{}")
        except ValueError:
            raise Refused(400, "That request was not readable.") from None

    def _check_post(self, need_csrf=True) -> None:
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            raise Refused(403, "Requests must come from the Hatua page on this computer.")
        if need_csrf and not auth.csrf_ok(self._session(), self.headers.get("X-Hatua-CSRF")):
            raise Refused(403, "This page is out of date. Reload it and try again.")

    def _route(self, method: str):
        if not self._host_ok():
            raise Refused(421, "Open Hatua at http://127.0.0.1 on this computer.")
        url = urlsplit(self.path)
        path, q = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
        if method == "GET" and path in ("/", "/index.html"):
            return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            raise Refused(404, "Not found.")
        if method == "POST" and path == "/api/assistant":
            return self._assistant()
        with LOCK:
            return self._api(method, path[5:], q)

    def _assistant(self):
        """Read the store under the lock, then ask the model WITHOUT the lock, so the rest of
        the portal keeps working while Qwen thinks."""
        with LOCK:
            who = self._who()
            self._check_post()
            body = self._json()
            tid, history = who["teacher_id"], body.get("history") or []
            if body.get("ask_id"):
                # Step 2: the teacher answered Hatua's follow-up question. Now it may answer.
                try:
                    item = assistant.take_follow_up(tid, str(body["ask_id"]), str(body.get("reply", "")))
                except ValueError as exc:
                    raise Refused(400, str(exc)) from None
                ctx = assistant.prepare(tid, item["question"], history, {"asked": item["asked"], "reply": item["reply"]})
            else:
                # Step 1: every new question gets a follow-up question first. Only a refusal
                # (a ranking question) is given at once, and it tells the teacher nothing new.
                ctx = assistant.prepare(tid, str(body.get("question", "")), history)
                if ctx["question"] and not assistant.refusal(ctx["question"], ctx):
                    out = assistant.open_follow_up(tid, ctx)
                    assistant.log(tid, out)
                    return self._send(200, out)
        out = assistant.answer(ctx)
        out["kind"] = "answer"
        with LOCK:
            assistant.log(who["teacher_id"], out)
        return self._send(200, out)

    # ---------------------------------------------------------------- API
    def _api(self, method: str, path: str, q: dict):  # noqa: C901 - one flat table of routes
        today = config.today()
        if method == "GET" and path == "public":
            demo = _demo()
            learners = store.load("learners")
            return self._send(200, {"school": (learners[0]["school"] if learners else ""),
                                    "calendar": school_calendar.term_on(today)["text"], "today": today.isoformat(),
                                    "practice": ({"pin": demo["pin"], "teachers": demo["teachers"],
                                                  "one_time": demo.get("first_sign_in", [])} if demo else None)})
        if method == "POST" and path == "login":
            self._check_post(need_csrf=False)
            body = self._json()
            typed = str(body.get("teacher_id", "")).strip().upper()
            try:
                out = auth.login(typed, str(body.get("pin", "")))
            except GateBlocked as exc:
                known = any(t["teacher_id"] == typed for t in auth.teachers())
                _auth_event("sign_in", typed if known else "unknown", False,
                            reason="locked" if "locked" in str(exc) else "wrong PIN or member number")
                raise Refused(401, str(exc)) from None
            if not school.streams_of(out["teacher_id"]):
                auth.logout(out["session"])
                raise Refused(403, "You are registered, but no class is assigned to you yet. Ask the school's Hatua admin.")
            ended = auth.end_other_sessions(out["session"])
            _auth_event("sign_in", out["teacher_id"], True, one_time_pin=out["must_change"], other_sign_ins_ended=ended)
            cookie = f"{COOKIE}={out['session']}; HttpOnly; SameSite=Strict; Path=/; Max-Age={8 * 3600}"
            if out["must_change"]:
                return self._send(200, {"csrf": out["csrf"], "must_change": True, "name": out["name"],
                                        "teacher_id": out["teacher_id"]}, extra={"Set-Cookie": cookie})
            notify.check_missing(today)
            return self._send(200, {"csrf": out["csrf"], "me": school.profile(out["teacher_id"]),
                                    "previous_login": out["previous_login"], "failed_since": out["failed_since"],
                                    "ended_other": ended}, extra={"Set-Cookie": cookie})
        if method == "POST" and path == "logout":
            self._check_post()
            try:
                _auth_event("sign_out", self._who(allow_limited=True)["teacher_id"], True)
            except Refused:
                pass
            auth.logout(self._session())
            return self._send(200, {"ok": True},
                              extra={"Set-Cookie": f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
        if method == "POST" and path == "pin":
            who = self._who(allow_limited=True)
            self._check_post()
            body = self._json()
            try:
                auth.change_pin(self._session(), str(body.get("current", "")), str(body.get("new", "")))
            except GateBlocked as exc:
                _auth_event("pin_change", who["teacher_id"], False, reason="current PIN wrong")
                raise Refused(403, str(exc)) from None
            except ValueError as exc:
                raise Refused(400, str(exc)) from None
            _auth_event("pin_change", who["teacher_id"], True)
            notify.check_missing(today)
            return self._send(200, {"ok": True, "me": school.profile(who["teacher_id"])})

        who = self._who()
        tid = who["teacher_id"]
        if method == "GET" and path == "me":
            return self._send(200, {"me": school.profile(tid), "csrf": auth.new_csrf(self._session()),
                                    "calendar": school_calendar.summary(today), "model": comments.model_name(),
                                    "idle_minutes": auth.SESSION_MINUTES})
        if method == "GET" and path == "account":
            return self._send(200, _account(tid))
        if method == "GET" and path == "notices":
            notify.check_missing(today)  # a file deleted from the drive is noticed here
            return self._send(200, {"notices": notify.for_teacher(tid, include_resolved=q.get("all") == "1")})
        m = re.fullmatch(r"notices/(NT-\d+)/parent", path)
        if method == "GET" and m:
            n = next((x for x in notify.for_teacher(tid, True) if x["notice_id"] == m.group(1)), None)
            if not n or not n.get("learner_id"):
                raise Refused(404, "Notice not found.")
            return self._send(200, {"en": notify.parent_message(n, "en"), "sw": notify.parent_message(n, "sw")})
        m = re.fullmatch(r"notices/(NT-\d+)", path)
        if method == "POST" and m:
            self._check_post()
            body = self._json()
            try:
                n = notify.mark(m.group(1), tid, read=body.get("read"), told_parent=body.get("told_parent"))
            except ValueError as exc:
                raise Refused(404, str(exc)) from None
            if body.get("told_parent") and n.get("learner_id"):
                audit.write_event({"tool": "parent.told", "actor": tid, "ok": True,
                                   "inputs": {"kwargs": {"learner_id": n["learner_id"], "notice": n["notice_id"]}},
                                   "output": {"how": n["told_parent"]["how"], "recorded_by": who["name"]}})
            return self._send(200, {"notice": n})
        if method == "GET" and path == "class":
            notices = notify.for_teacher(tid, include_resolved=True)
            return self._send(200, {"learners": [_learner_card(l, notices) for l in school.learners_of(tid)]})
        m = re.fullmatch(r"learner/(HT-\d{4})", path)
        if method == "GET" and m:
            return self._send(200, _learner_detail(tid, m.group(1)))
        m = re.fullmatch(r"learner/(HT-\d{4})/pathways/open", path)
        if method == "POST" and m:
            self._check_post()
            try:
                pathways.open_ideas(self._session(), m.group(1))
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
            return self._send(200, {"pathways": pathways.for_teacher(tid, m.group(1))})
        m = re.fullmatch(r"learner/(HT-\d{4})/comment", path)
        if method == "POST" and m:
            self._check_post()
            try:
                return self._send(200, {"comment": comments.write(m.group(1), tid)})
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
        m = re.fullmatch(r"comment/(C-\d+)/rate", path)
        if method == "POST" and m:
            self._check_post()
            body = self._json()
            try:
                return self._send(200, comments.rate(m.group(1), self._session(), body.get("rating", ""),
                                                     body.get("reasons") or [], body.get("note", ""),
                                                     body.get("edited_text")))
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
            except ValueError as exc:
                raise Refused(400, str(exc)) from None
        if method == "GET" and path == "drive":
            notify.check_missing(today)
            return self._send(200, {"folders": drive.folders(tid, today.year), "terms": _states(tid, today),
                                    "on_this_computer": str(drive.root())})
        if method == "GET" and path == "drive/preview":
            try:
                return self._send(200, drive.preview(q.get("path", ""), tid))
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
            except ValueError as exc:
                raise Refused(404, str(exc)) from None
        if method == "POST" and path == "drive/decide":
            self._check_post()
            body = self._json()
            try:
                return self._send(200, drive.decide(body.get("path", ""), self._session(),
                                                    body.get("decision", ""), body.get("reason", "")))
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
            except ValueError as exc:
                raise Refused(400, str(exc)) from None
        if method == "POST" and path == "drive/upload":
            self._check_post()
            try:
                year, term = int(q.get("year", today.year)), int(q.get("term", 0))
                out = drive.upload(self._session(), q.get("name", "results"), self._body(), year, term)
                notify.check_missing(today)
                return self._send(200, out)
            except GateBlocked as exc:
                raise Refused(403, str(exc)) from None
            except ValueError as exc:
                raise Refused(400, str(exc)) from None
        m = re.fullmatch(r"evidence/([RNA]-[A-Za-z0-9-]{1,40})", path)
        if method == "GET" and m:
            rec = store.get_record(m.group(1))
            if not rec or not scope.can_view(tid, rec.get("learner_id", "")):
                raise Refused(404, "That record is not in your class.")
            learner = store.learner(rec["learner_id"]) or {}
            keep = ("record_id", "note_id", "attendance_id", "learner_id", "grade", "year", "term", "learning_area",
                    "task", "level", "score", "task_date", "teacher", "flags", "text", "days_present", "days_open")
            return self._send(200, {**{k: rec[k] for k in keep if k in rec}, "name": learner.get("first_name", ""),
                                    "read_only": int(rec.get("grade", 0) or 0) < int(learner.get("current_grade", 0) or 0)})
        if method == "GET" and path == "calendar":
            return self._send(200, school_calendar.summary(today))
        raise Refused(404, "Not found.")

    def _run(self, method: str):
        try:
            self._route(method)
        except Refused as exc:
            self._send(exc.status, {"error": str(exc)})
        except Exception:  # never show a stack trace to the browser
            self._send(500, {"error": "Something went wrong on this computer. The details are not shown here."})

    def do_GET(self):
        self._run("GET")

    def do_POST(self):
        self._run("POST")


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = 8765) -> None:
    httpd = make_server(port)
    print(f"Hatua portal: open http://127.0.0.1:{port} in your browser. Press Ctrl+C to stop.")
    print(f"Data folder: {config.ROOT}   Today (school calendar): {config.today()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
