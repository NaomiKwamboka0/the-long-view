"""Whole-school portal: calendar, school drive, notices, comments and the HTTP portal.

Each test works on a fresh copy of the synthetic school demo (Grades 4-9), so nothing
here touches the Grade 9 data the other tests and the evaluations use.
"""
import http.client
import json
import runpy
import shutil
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hatua import (
    assistant,
    audit,
    auth,
    comments,
    config,
    drive,
    notify,
    pathways,
    school,
    school_calendar,
    school_demo,
    store,
    xlsx,
)
from hatua.summary import GateBlocked

REPO = Path(__file__).resolve().parent.parent
PIN = "246810"
G6 = "Grade 6/2026 Term 3/Grade 6 Term 3 2026 results.xlsx"
G6_T1 = "Grade 6/2026 Term 1/Grade 6 Term 1 2026 results.xlsx"
G9 = "Grade 9/2026 Term 3/Grade 9 Term 3 2026 results.xlsx"


def _point(monkeypatch, root: Path):
    for name, value in {"ROOT": root, "STORE": root / "store", "LOGS": root / "logs",
                        "AUDIT_LOG": root / "logs" / "audit.jsonl",
                        "APPROVALS_LOG": root / "logs" / "approvals.jsonl", "PROFILES": root / "profiles",
                        "DATA": root / "data", "RAW": root / "data" / "raw", "INBOX": root / "data" / "inbox",
                        "UI": root / "ui"}.items():
        monkeypatch.setattr(config, name, value)
    monkeypatch.setenv("HATUA_TODAY", "2026-11-04")
    monkeypatch.setenv("HATUA_LLM", "off")
    monkeypatch.delenv("HATUA_DRIVE", raising=False)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Generate and load the demo once; each test gets its own copy."""
    root = tmp_path_factory.mktemp("school") / "home"
    runpy.run_path(str(REPO / "scripts" / "make_school_demo.py"), run_name="x")["main"](root)
    with pytest.MonkeyPatch.context() as mp:
        _point(mp, root)
        school_demo.setup()
    return root


@pytest.fixture
def school_home(built, tmp_path, monkeypatch):
    root = tmp_path / "home"
    shutil.copytree(built, root)
    _point(monkeypatch, root)
    return root


def login(teacher_id):
    return auth.login(teacher_id, PIN)["session"]


def term3(teacher_id):
    return [f["status"] for g in drive.folders(teacher_id) for t in g["terms"] if t["term"] == 3 for f in t["files"]]


def ask2(teacher_id, question, reply="Everything the records show", history=None):
    """A full turn: the question, Hatua's follow-up, the teacher's reply, then the answer."""
    first = assistant.ask(teacher_id, question, history)
    if first["kind"] != "follow_up":
        return first
    return assistant.ask(teacher_id, question, history, ask_id=first["ask_id"], reply=reply)


# ---------------------------------------------------------------- calendar
def test_kenya_2026_calendar_terms_and_due_dates(school_home):
    assert school_calendar.term_on(date(2026, 2, 26))["state"] == "half_term"
    assert school_calendar.term_on(date(2026, 9, 7)) == {"year": 2026, "term": 3, "state": "in_term", "week": 3,
                                                         "text": "Term 3, week 3"}
    assert school_calendar.term_on(date(2026, 4, 15))["text"].startswith("School holiday after Term 1. Term 2 opens 27 Apr")
    due = school_calendar.due_terms(date(2026, 10, 29))
    assert [d["term"] for d in due] == [1, 2], "Term 3 results are due 7 days after it closes on 23 Oct"
    assert [d["term"] for d in school_calendar.due_terms(date(2026, 10, 30))] == [1, 2, 3]


# ---------------------------------------------------------------- Excel sheets
def test_excel_sheets_are_read_without_any_extra_package(tmp_path):
    rows = [{"learner_id": "HT-0601", "grade": 6, "year": 2026, "term": 1, "learning_area": "Kiswahili",
             "level": "ME", "score": "07", "task": "Insha & <ufahamu>"},
            {"learner_id": "HT-0602", "grade": 6, "year": 2026, "term": 1, "learning_area": "Mathematics",
             "level": "EE", "score": "", "task": "Fractions"}]
    path = tmp_path / "sheet.xlsx"
    xlsx.write(path, rows)
    header, back = xlsx.read(path)
    assert header == list(rows[0]) and back == [{k: str(v) for k, v in r.items()} for r in rows]
    assert xlsx.to_bytes(rows) == path.read_bytes(), "the same rows always give the same file"


def test_excel_from_real_excel_shared_strings_and_dates(tmp_path):
    """Excel itself stores text in a shared table and dates as day numbers."""
    import zipfile
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    parts = {
        "xl/workbook.xml": f'<workbook {ns} {rel}><sheets><sheet name="T1" sheetId="1" r:id="rId7"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                       '<Relationship Id="rId7" Target="worksheets/sheet1.xml"/></Relationships>'),
        "xl/sharedStrings.xml": f'<sst {ns}><si><t>learner_id</t></si><si><t>task_date</t></si><si><r><t>HT-</t></r><r><t>0601</t></r></si></sst>',
        "xl/styles.xml": f'<styleSheet {ns}><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": (f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                                     '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" s="1"><v>46063</v></c></row>'
                                     '<row r="3"></row></sheetData></worksheet>'),
    }
    path = tmp_path / "from_excel.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        for name, text in parts.items():
            z.writestr(name, text)
    assert xlsx.read(path) == (["learner_id", "task_date"], [{"learner_id": "HT-0601", "task_date": "2026-02-10"}])


def test_unsafe_or_wrong_excel_files_are_refused(tmp_path):
    import zipfile
    with pytest.raises(xlsx.BadSheet):
        xlsx.read_bytes(b"this is not a zip")
    bomb = tmp_path / "entities.xlsx"
    with zipfile.ZipFile(bomb, "w") as z:
        z.writestr("xl/workbook.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><workbook/>')
        z.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
    with pytest.raises(xlsx.BadSheet):
        xlsx.read(bomb)


# ---------------------------------------------------------------- notices at sign-in
def test_each_teacher_hears_only_about_their_own_class(school_home):
    kinds = {t: sorted(n["kind"] for n in notify.for_teacher(t)) for t in
             ["M-4001", "M-5001", "M-6001", "M-7001", "M-8001", "M-9001", "M-9002"]}
    assert kinds["M-7001"] == ["missing_upload"], "Grade 7 has no Term 3 file on the drive"
    assert kinds["M-4001"] == ["sharp_drop"], "Grade 4 was approved at setup; Wanjiku dropped in Kiswahili"
    for t in ["M-5001", "M-6001", "M-8001", "M-9001", "M-9002"]:
        assert kinds[t] == ["waiting_approval"]
    wanjiku = notify.for_teacher("M-4001")[0]
    assert wanjiku["learner_id"] == "HT-0405" and "early sign, not a pattern" in wanjiku["text"]


def test_every_class_has_an_excel_sheet_for_each_term(school_home):
    states = {t: [s["state"] for s in notify.term_states(t)] for t in ["M-4001", "M-6001", "M-7001", "M-9002"]}
    assert states["M-4001"] == ["in_hatua", "in_hatua", "in_hatua"]
    assert states["M-6001"] == ["in_hatua", "in_hatua", "waiting"]
    assert states["M-7001"] == ["in_hatua", "in_hatua", "missing"]
    assert states["M-9002"] == ["in_hatua", "in_hatua", "waiting"]
    names = [f["name"] for g in drive.folders("M-6001") for t in g["terms"] for f in t["files"]]
    assert len(names) == 3 and all(n.endswith(".xlsx") for n in names)


# ---------------------------------------------------------------- a deleted file
def test_deleting_an_approved_sheet_tells_only_that_class_teacher(school_home):
    (drive.root() / G6_T1).unlink()
    new = notify.check_missing()
    assert [(n["kind"], n["teacher_id"], n["term"]) for n in new] == [("file_removed", "M-6001", 1)]
    n = new[0]
    assert "gone from the school drive" in n["title"] and "still safe in Hatua" in n["text"]
    assert "Grade 6 Term 1 2026 results.xlsx" in n["text"], "it names the file the teacher approved"
    for other in ["M-4001", "M-5001", "M-7001", "M-8001", "M-9001", "M-9002"]:
        assert "file_removed" not in {x["kind"] for x in notify.for_teacher(other)}
    assert notify.check_missing() == [], "the same notice is not sent twice"
    raised = [e for e in audit.read_events() if e["tool"] == "notice.raise"]
    assert raised[-1]["output"] == {"kind": "file_removed", "term": 1}
    assert [s["state"] for s in notify.term_states("M-6001")][0] == "file_removed"


def test_putting_the_sheet_back_closes_the_notice_and_deleting_again_reopens_it(school_home):
    path = drive.root() / G6_T1
    content = path.read_bytes()
    path.unlink()
    first = notify.check_missing()[0]
    up = drive.upload(login("M-6001"), path.name, content, 2026, 1)
    assert up == {"path": G6_T1, "status": "approve"}, "the same file is still approved; no second approval"
    notify.check_missing()
    assert "file_removed" not in {n["kind"] for n in notify.for_teacher("M-6001")}
    path.unlink()
    again = notify.check_missing()
    assert [n["notice_id"] for n in again] == [first["notice_id"]] and not again[0]["resolved"]


def test_deleting_a_waiting_sheet_or_the_whole_folder_says_missing(school_home):
    (drive.root() / G6).unlink()
    new = notify.check_missing()
    assert [(n["kind"], n["teacher_id"], n["term"]) for n in new] == [("missing_upload", "M-6001", 3)]
    assert {n["kind"] for n in notify.for_teacher("M-6001")} == {"missing_upload"}, "the waiting notice closed itself"
    shutil.rmtree(drive.root() / "Grade 8" / "2026 Term 2")
    new = notify.check_missing()
    assert [(n["kind"], n["teacher_id"], n["term"]) for n in new] == [("file_removed", "M-8001", 2)]
    assert [t["label"] for g in drive.folders("M-8001") for t in g["terms"]] == ["2026 Term 3", "2026 Term 2", "2026 Term 1"]


# ---------------------------------------------------------------- drive gate
def test_approving_adds_only_my_rows_and_alerts_at_once(school_home):
    before = len(store.load("records"))
    result = drive.decide(G6, login("M-6001"), "approve")
    assert result["added"] == 70 and len(store.load("records")) == before + 70
    alerts = {(n["learner_id"], n["kind"], n["family"]) for n in result["notices"]}
    assert ("HT-0603", "sharp_drop", "Mathematics") in alerts
    assert ("HT-0607", "decline", "English") in alerts
    assert all(n["teacher_id"] == "M-6001" for n in result["notices"])
    left = {n["kind"] for n in notify.for_teacher("M-6001")}
    assert "waiting_approval" not in left, "the waiting notice is resolved once results are in"


def test_shared_grade_file_is_split_by_stream(school_home):
    a = drive.decide(G9, login("M-9001"), "approve")
    mine = {l["learner_id"] for l in school.learners_of("M-9001")}
    added = [r for r in store.load("records") if r.get("file") == a["inbox_file"]]
    assert added and {r["learner_id"] for r in added} <= mine
    assert drive.preview(G9, "M-9002")["counts"]["yours"] == 156  # 9B's rows wait for 9B's teacher
    assert term3("M-9002") == ["waiting"] and term3("M-9001") == ["approve"]


def test_drive_refuses_other_grades_paths_and_agent_tokens(school_home):
    with pytest.raises(GateBlocked):
        drive.preview(G6, "M-8001")
    with pytest.raises(ValueError):
        drive.preview("../store/teachers.json", "M-6001")
    with pytest.raises(ValueError):
        drive.preview("Grade 6/../../demo.json", "M-6001")
    session = login("M-6001")
    agent = auth.mint_agent_token(session)
    with pytest.raises(GateBlocked):
        drive.decide(G6, agent, "approve")
    with pytest.raises(GateBlocked):
        drive.decide(G6, None, "approve")
    drive.decide(G6, session, "approve")
    with pytest.raises(GateBlocked):
        drive.decide(G6, session, "approve")  # one decision per version of a file


def test_a_changed_file_needs_approval_again(school_home):
    drive.decide(G6, login("M-6001"), "approve")
    path = drive.root() / G6
    _, rows = xlsx.read(path)
    rows[0]["score"] = "1"
    xlsx.write(path, rows)
    assert term3("M-6001") == ["waiting"]


def test_upload_then_approve_clears_the_missing_notice(school_home):
    session = login("M-7001")
    sample = school_home / "samples" / "Grade 7 Term 3 2026 results.xlsx"
    up = drive.upload(session, "../../evil name?.xlsx", sample.read_bytes(), 2026, 3)
    assert up["path"] == "Grade 7/2026 Term 3/evil name.xlsx"
    with pytest.raises(ValueError):
        drive.upload(session, "x.csv", b"name,score\nA,3\n", 2026, 3)  # missing Hatua's columns
    with pytest.raises(ValueError):
        drive.upload(session, "x.xlsx", xlsx.to_bytes([{"name": "A", "score": 3}]), 2026, 3)
    with pytest.raises(ValueError):
        drive.upload(session, "x.xlsx", b"PK\x03\x04 not really a zip", 2026, 3)
    csv_up = drive.upload(session, "old style.csv", b"learner_id,grade,year,term,learning_area,level\n", 2026, 2)
    assert csv_up["path"].endswith("old style.csv"), "CSV still works"
    result = drive.decide(up["path"], session, "approve")
    assert result["added"] > 0
    assert ("HT-0704", "sharp_drop") in {(n["learner_id"], n["kind"]) for n in result["notices"]}
    assert "missing_upload" not in {n["kind"] for n in notify.for_teacher("M-7001")}


def test_parent_message_and_told_parent(school_home):
    drive.decide(G6, login("M-6001"), "approve")
    kamau = next(n for n in notify.for_teacher("M-6001") if n.get("learner_id") == "HT-0603")
    sw = notify.parent_message(kamau, "sw")
    assert "Hisabati" in sw and "Kufikia Matarajio" in sw and "Tumsaidie Kamau" in sw
    assert "Mathematics" in notify.parent_message(kamau, "en")
    with pytest.raises(ValueError):
        notify.mark(kamau["notice_id"], "M-5001", told_parent="By SMS")  # not their notice
    marked = notify.mark(kamau["notice_id"], "M-6001", told_parent="By SMS")
    assert marked["told_parent"]["how"] == "By SMS"


# ---------------------------------------------------------------- comments
def test_comments_scope_template_and_thumbs(school_home):
    with pytest.raises(GateBlocked):
        comments.write("HT-0401", "M-6001")
    drive.decide(G6, login("M-6001"), "approve")
    first = comments.write("HT-0603", "M-6001")
    assert first["writer"] == "template" and "Kamau" in first["text"] and not comments.problems(first["text"], "Kamau")
    session = login("M-6001")
    out = comments.rate(first["comment_id"], session, "down", ["harsh"])
    assert out["next"]["feedback_used"] == ["harsh"] and out["next"]["replaces"] == first["comment_id"]
    with pytest.raises(ValueError):
        comments.rate(out["next"]["comment_id"], session, "up", edited_text="Kamau is weaker than his classmates.")
    saved = comments.rate(out["next"]["comment_id"], session, "up", edited_text="Kamau works hard. Well done, Kamau.")
    assert saved["comment"]["rating"] == "up" and saved["comment"]["teacher_edit"].startswith("Kamau works hard")
    with pytest.raises(GateBlocked):
        comments.rate(out["next"]["comment_id"], session, "up")  # already rated
    with pytest.raises(GateBlocked):
        comments.rate(out["next"]["comment_id"], login("M-8001"), "up")  # not their comment


class _FakeOllama(BaseHTTPRequestHandler):
    reply = ""

    def log_message(self, *a):
        pass

    def _out(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._out({"models": [{"name": "qwen2.5:7b"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._out({"response": type(self).reply})


@pytest.fixture
def fake_qwen(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("HATUA_OLLAMA_HOST", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setenv("HATUA_LLM", "")
    yield _FakeOllama
    srv.shutdown()


def test_qwen_words_the_comment_and_the_guard_still_decides(school_home, fake_qwen):
    fake_qwen.reply = "Kamau has grown in Science this year. A little daily practice will help him in Mathematics."
    c = comments.write("HT-0603", "M-6001")
    assert c["writer"] == "qwen2.5:7b" and c["text"] == fake_qwen.reply
    fake_qwen.reply = "Kamau is weaker than his classmates and should take the STEM pathway."
    c = comments.write("HT-0603", "M-6001")
    assert c["writer"] == "template", "a comment that labels or compares is never shown"


# ---------------------------------------------------------------- sign-in security
def test_easy_pins_are_refused():
    for weak in ["12345", "123456", "654321", "111111", "121212", "246810", "135790", "abcabc", "pin6001x", "password"]:
        assert auth.pin_problem(weak, "M-6001"), weak
    for fine in ["739152", "kibera-41", "50 mango trees"]:
        assert auth.pin_problem(fine, "M-6001") is None, fine


def test_a_one_time_pin_opens_nothing_until_the_teacher_chooses_their_own(school_home):
    out = auth.login("M-5001", PIN)
    assert out["must_change"] is True
    with pytest.raises(GateBlocked, match="Choose your own PIN first"):
        auth.resolve(out["session"])
    with pytest.raises(GateBlocked):
        auth.mint_agent_token(out["session"])
    with pytest.raises(GateBlocked):
        drive.decide("Grade 5/2026 Term 3/Grade 5 Term 3 2026 results.xlsx", out["session"], "approve")
    with pytest.raises(GateBlocked, match="current PIN"):
        auth.change_pin(out["session"], "000000", "739152")
    with pytest.raises(ValueError, match="in order"):
        auth.change_pin(out["session"], PIN, "345678")
    auth.change_pin(out["session"], PIN, "739152")
    with pytest.raises(ValueError, match="different"):
        auth.change_pin(out["session"], "739152", "739152")
    assert auth.resolve(out["session"])["teacher_id"] == "M-5001", "the same sign-in is now a full one"
    with pytest.raises(GateBlocked):
        auth.login("M-5001", PIN)  # the one-time PIN is dead
    again = auth.login("M-5001", "739152")
    assert again["must_change"] is False and again["failed_since"] == 1 and again["previous_login"]
    teachers = json.loads((config.STORE / "teachers.json").read_text())
    assert "739152" not in json.dumps(teachers) and "must_change" not in teachers["M-5001"]


def test_changing_a_pin_ends_the_teacher_s_other_sign_ins(school_home):
    one, two = login("M-6001"), login("M-6001")
    agent = auth.mint_agent_token(two)
    auth.change_pin(one, PIN, "408 kisumu road")
    assert auth.resolve(one)["teacher_id"] == "M-6001"
    for dead in (two,):
        with pytest.raises(GateBlocked):
            auth.resolve(dead)
    with pytest.raises(GateBlocked):
        auth.resolve(agent, kind="agent")
    three = login("M-8001")
    assert auth.end_other_sessions(three) == 0 and auth.resolve(one), "another teacher's sign-in is untouched"


# ---------------------------------------------------------------- the HTTP portal
@pytest.fixture
def portal(school_home):
    from hatua import portal as p
    srv = p.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def call(port, method, path, body=None, cookie=None, csrf=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Host": host or f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Hatua-CSRF"] = csrf
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = c.getresponse()
    data = r.read()
    return r.status, dict(r.getheaders()), (json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data)


def sign_in(port, teacher_id, pin=PIN):
    st, headers, body = call(port, "POST", "/api/login", {"teacher_id": teacher_id, "pin": pin})
    assert st == 200, body
    return headers["Set-Cookie"].split(";")[0], body["csrf"], body


def test_portal_sign_in_scope_and_csrf(portal):
    assert call(portal, "GET", "/api/public", host="evil.example")[0] == 421
    assert call(portal, "GET", "/api/class")[0] == 401
    st, _, body = call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": "000000"})
    assert st == 401 and "Sign-in failed" in body["error"]
    st, headers, body = call(portal, "POST", "/api/login", {"teacher_id": "m-6001", "pin": PIN})
    assert st == 200
    set_cookie = headers["Set-Cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
    cookie, csrf = set_cookie.split(";")[0], body["csrf"]
    st, _, cls = call(portal, "GET", "/api/class", cookie=cookie)
    assert st == 200 and {l["grade"] for l in cls["learners"]} == {6} and len(cls["learners"]) == 12
    assert call(portal, "GET", "/api/learner/HT-0401", cookie=cookie)[0] == 403
    detail = call(portal, "GET", "/api/learner/HT-0603", cookie=cookie)[2]
    assert [g["read_only"] for g in detail["grades"]] == [True, True, False]
    assert call(portal, "POST", "/api/drive/decide", {"path": G6, "decision": "approve"}, cookie=cookie)[0] == 403
    st, _, out = call(portal, "POST", "/api/drive/decide", {"path": G6, "decision": "approve"}, cookie=cookie, csrf=csrf)
    assert st == 200 and out["added"] == 70
    assert call(portal, "POST", "/api/logout", {}, cookie=cookie, csrf=csrf)[0] == 200
    assert call(portal, "GET", "/api/class", cookie=cookie)[0] == 401


def test_portal_sign_in_history_one_place_only_and_the_log(portal):
    assert call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": "nope-1"})[0] == 401
    assert call(portal, "POST", "/api/login", {"teacher_id": "M-0000", "pin": "nope-2"})[0] == 401
    first, _, body = sign_in(portal, "M-6001")
    assert body["failed_since"] == 1 and body["previous_login"] is None and body["ended_other"] == 0
    second, csrf, body = sign_in(portal, "M-6001")
    assert body["ended_other"] == 1 and body["previous_login"] and body["failed_since"] == 0
    assert call(portal, "GET", "/api/class", cookie=first)[0] == 401, "one member number, one place"
    acct = call(portal, "GET", "/api/account", cookie=second)[2]
    assert [e["what"] for e in acct["recent"]] == ["Signed in", "Signed in", "Wrong PIN tried"]
    assert acct["idle_minutes"] == 15 and acct["lock_failures"] == 5
    log = (config.LOGS / "audit.jsonl").read_text()
    assert "nope-1" not in log and "nope-2" not in log and PIN not in log, "no PIN is ever written to the log"
    assert '"actor": "unknown"' in log and "M-0000" not in log, "a made-up member number is not kept"


def test_portal_one_time_pin_must_be_changed_before_anything_opens(portal):
    cookie, csrf, body = sign_in(portal, "M-5001")
    assert body["must_change"] is True and "me" not in body
    for path in ["/api/class", "/api/me", "/api/notices", "/api/drive", "/api/learner/HT-0501", "/api/account"]:
        assert call(portal, "GET", path, cookie=cookie)[0] == 403, path
    assert call(portal, "POST", "/api/assistant", {"question": "Who needs attention?"}, cookie=cookie, csrf=csrf)[0] == 403
    assert call(portal, "POST", "/api/pin", {"current": PIN, "new": "739152"}, cookie=cookie)[0] == 403, "CSRF still needed"
    st, _, out = call(portal, "POST", "/api/pin", {"current": PIN, "new": "111111"}, cookie=cookie, csrf=csrf)
    assert st == 400 and "repeat" in out["error"]
    st, _, out = call(portal, "POST", "/api/pin", {"current": PIN, "new": "739152"}, cookie=cookie, csrf=csrf)
    assert st == 200 and out["me"]["teacher_id"] == "M-5001"
    assert call(portal, "GET", "/api/class", cookie=cookie)[0] == 200
    assert call(portal, "POST", "/api/login", {"teacher_id": "M-5001", "pin": PIN})[0] == 401


def test_portal_shows_a_deleted_sheet_the_next_time_the_teacher_looks(portal):
    cookie, csrf, _ = sign_in(portal, "M-6001")
    d = call(portal, "GET", "/api/drive", cookie=cookie)[2]
    assert [t["state"] for t in d["terms"]] == ["in_hatua", "in_hatua", "waiting"] and d["on_this_computer"].endswith("school_drive")
    (drive.root() / G6_T1).unlink()
    notices = call(portal, "GET", "/api/notices", cookie=cookie)[2]["notices"]
    assert [n["kind"] for n in notices if n["term"] == 1] == ["file_removed"]
    assert call(portal, "GET", "/api/drive", cookie=cookie)[2]["terms"][0]["state"] == "file_removed"
    other, _, _ = sign_in(portal, "M-8001")
    assert "file_removed" not in {n["kind"] for n in call(portal, "GET", "/api/notices", cookie=other)[2]["notices"]}


# ---------------------------------------------------------------- the Hatua assistant
def test_assistant_always_asks_one_question_first(school_home):
    for q in ["hello", "When does Term 1 open?", "How is Kamau doing?", "How do I approve a file?",
              "Give me ideas to teach fractions", "Who needs my attention?", "What is 2 + 2?"]:
        first = assistant.ask("M-6001", q)
        assert first["kind"] == "follow_up" and "answer" not in first, q
        assert first["question"].endswith(("?", ".")) and 2 <= len(first["options"]) <= 4, q
    kamau = assistant.ask("M-6001", "How is Kamau doing?")
    assert kamau["question"] == "What do you want to know about Kamau?" and "Pathway ideas" not in kamau["options"]
    assert "Pathway ideas" in assistant.ask("M-9001", "How is Kiprono doing?")["options"]
    with pytest.raises(ValueError):
        assistant.ask("M-8001", "x", ask_id=kamau["ask_id"], reply="Everything")  # another teacher's question
    with pytest.raises(ValueError):
        assistant.ask("M-6001", "x", ask_id=kamau["ask_id"], reply="   ")  # no reply
    out = assistant.ask("M-6001", "ignored", ask_id=kamau["ask_id"], reply="Everything the records show")
    assert out["kind"] == "answer" and "Kamau" in out["answer"]
    with pytest.raises(ValueError):
        assistant.ask("M-6001", "x", ask_id=kamau["ask_id"], reply="Everything")  # each follow-up works once


def test_the_reply_shapes_the_answer(school_home):
    drive.decide(G6, login("M-6001"), "approve")
    everything = ask2("M-6001", "How is Kamau doing?")["answer"]
    down = ask2("M-6001", "How is Kamau doing?", "Only what is going down")["answer"]
    parent = ask2("M-6001", "How is Kamau doing?", "What to tell the parent")["answer"]
    assert "what is going down" in down and "Mathematics" in down and down != everything
    assert "I would like to talk with you about Kamau" in parent
    files = ask2("M-7001", "Who needs my attention?", "Results files that are missing or waiting")["answer"]
    assert "Term 3 results file for 7A is missing" in files
    assert "KJSEA" in ask2("M-6001", "When are exams?", "KPSEA and KJSEA dates")["answer"]


def test_assistant_refuses_rankings_without_the_model(school_home):
    for q in ["Who is the best in Maths?", "Rank my class in English", "Compare Kamau with the class",
              "Nani ni mwanafunzi bora?"]:
        out = assistant.ask("M-6001", q)
        assert out["kind"] == "answer" and out.get("refused") and "does not rank" in out["answer"], q
    assert ask2("M-6001", "How is Kamau doing?", "Is he the best in the class?").get("refused"), "a reply cannot sneak a ranking in"
    assert not ask2("M-6001", "What is the best way to teach fractions?", "A full lesson").get("refused")
    out = ask2("M-6001", "Which pathway should Atieno take?", "Only to understand the strengths")
    assert not out.get("refused") and "chosen in Grade 9" in out["answer"], "Grade 6: too early for pathways"


def test_assistant_knows_only_my_class(school_home):
    drive.decide(G6, login("M-6001"), "approve")
    ctx = assistant.prepare("M-6001", "How is Kamau doing?")
    six = {l["learner_id"] for l in school.learners_of("M-6001")}
    others = [l for l in store.load("learners") if l["learner_id"] not in six]
    assert all(l["first_name"] not in ctx["data"] and l["learner_id"] not in ctx["data"] for l in others)
    assert {store.get_record(i)["learner_id"] for i in ctx["allowed"]} <= six
    out = ask2("M-6001", "How is Kamau doing?")
    assert out["writer"] == "hatua" and out["citations"]
    assert {store.get_record(c)["learner_id"] for c in out["citations"]} == {"HT-0603"}
    assert "can't find Amani" in ask2("M-6001", "Tell me about Amani", "A learner in my class")["answer"]
    att = ask2("M-6001", "Who needs my attention?", "Learners with an alert")["answer"]
    assert "Kamau" in att and "Atieno" in att


def test_assistant_with_qwen_checks_every_answer(school_home, fake_qwen, monkeypatch):
    drive.decide(G6, login("M-6001"), "approve")
    ctx = assistant.prepare("M-6001", "How is Kamau doing?")
    good_id = sorted(ctx["allowed"])[0]
    other_class = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0401")
    replies = iter([f"Kamau went down in Mathematics this term [{good_id}].",
                    f"Kamau is weaker than his classmates [{good_id}].",
                    f"Kamau is doing fine [{other_class}].",
                    f"Kamau's Mathematics fell this term [{good_id}]."])
    seen = []
    monkeypatch.setattr(assistant, "_chat", lambda model, system, history, question, extra="": (seen.append(question), next(replies))[1])
    out = ask2("M-6001", "How is Kamau doing?", "Only what is going down")
    assert out["writer"] == "qwen2.5:7b" and out["citations"] == [good_id]
    assert "Hatua asked: What do you want to know about Kamau?" in seen[0] and "The teacher answered: Only what is going down" in seen[0]
    out = ask2("M-6001", "How is Kamau doing?")  # a label, then another class's record: both refused
    assert out["writer"] == "hatua", "neither bad answer is shown; the built-in answer is used instead"
    out = ask2("M-6001", "How is Kamau doing?")
    assert out["writer"] == "qwen2.5:7b"
    events = [e for e in audit.read_events() if e["tool"] == "assistant.ask"]
    assert {e["output"]["step"] for e in events} == {"follow_up", "answer"}
    assert all("How is" not in json.dumps(e) and "going down" not in json.dumps(e) for e in events), "questions and replies are not logged"


def test_assistant_and_evidence_endpoints(portal):
    cookie, csrf, _ = sign_in(portal, "M-6001")
    assert call(portal, "POST", "/api/assistant", {"question": "Who needs my attention?"}, cookie=cookie)[0] == 403
    st, _, first = call(portal, "POST", "/api/assistant", {"question": "When were Term 3 results due?"},
                        cookie=cookie, csrf=csrf)
    assert st == 200 and first["kind"] == "follow_up" and "answer" not in first
    assert call(portal, "POST", "/api/assistant", {"ask_id": "made-up", "reply": "Term dates"}, cookie=cookie, csrf=csrf)[0] == 400
    st, _, out = call(portal, "POST", "/api/assistant", {"ask_id": first["ask_id"], "reply": "When results are due"},
                      cookie=cookie, csrf=csrf)
    assert st == 200 and out["kind"] == "answer" and "2026-10-30" in out["answer"]
    st, _, out = call(portal, "POST", "/api/assistant", {"question": "Rank my class"}, cookie=cookie, csrf=csrf)
    assert st == 200 and out["refused"]
    mine = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0603")
    theirs = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0401")
    assert call(portal, "GET", f"/api/evidence/{mine}", cookie=cookie)[2]["learner_id"] == "HT-0603"
    assert call(portal, "GET", f"/api/evidence/{theirs}", cookie=cookie)[0] == 404


# ---------------------------------------------------------------- pathways
def test_pathway_ideas_by_grade_and_never_a_pick(school_home):
    assert pathways.for_learner("HT-0603")["stage"] == "too_early"
    assert pathways.for_learner("HT-0805")["stage"] == "explore"
    nine = pathways.for_learner("HT-0007")
    assert nine["stage"] == "suggest"
    assert [p["name"] for p in nine["pathways"]] == ["STEM", "Social Sciences", "Arts and Sports Science"]
    for pw in nine["pathways"]:
        assert all(store.get_record(e)["learner_id"] == "HT-0007" for e in pw["evidence"])
    arts = nine["pathways"][2]
    assert arts["strengths"] >= 1 and any("Creative Arts" in x["text"] for x in arts["lines"])
    text = pathways.text("HT-0007")
    assert not assistant.problems(text, {"allowed": set(assistant.guard.citations(text)), "learners": []})
    assert "learner chooses" in text


def test_pathway_ideas_stay_closed_until_the_named_teacher_opens_them(portal):
    cookie, csrf, _ = sign_in(portal, "M-9001")
    closed = call(portal, "GET", "/api/learner/HT-0007", cookie=cookie)[2]["pathways"]
    assert closed == {"stage": "suggest", "grade": 9, "locked": True, "pathways": []}
    assert "Pathway ideas: NOT OPENED" in assistant.prepare("M-9001", "Kiprono")["data"]
    kiprono = assistant.prepare("M-9001", "Kiprono")["data"].split("Kiprono (HT-0007)")[1].split("\n  - ")[0]
    assert "STEM:" not in kiprono  # HT-0001's ideas were opened at setup; Kiprono's were not
    gated = ask2("M-9001", "What pathways could Kiprono explore?", "My talk with Kiprono and the guardian")
    assert gated.get("gated") and "Open pathway ideas" in gated["answer"] and "STEM" not in gated["answer"]
    assert call(portal, "POST", "/api/learner/HT-0007/pathways/open", {}, cookie=cookie)[0] == 403, "CSRF needed"
    st, _, out = call(portal, "POST", "/api/learner/HT-0007/pathways/open", {}, cookie=cookie, csrf=csrf)
    assert st == 200 and out["pathways"]["opened"]["by"] == "Daniel Mutiso" and len(out["pathways"]["pathways"]) == 3
    event = [e for e in audit.read_events() if e["tool"] == "pathways.open"][-1]
    assert event["actor"] == "M-9001" and event["output"]["approved_by"] == "Daniel Mutiso"
    assert event["inputs"]["kwargs"]["learner_id"] == "HT-0007"
    assert call(portal, "GET", "/api/learner/HT-0008", cookie=cookie)[2]["pathways"]["locked"], "one learner at a time"
    other, other_csrf, _ = sign_in(portal, "M-9002")
    assert call(portal, "POST", "/api/learner/HT-0007/pathways/open", {}, cookie=other, csrf=other_csrf)[0] == 403
    six, six_csrf, _ = sign_in(portal, "M-6001")
    assert call(portal, "POST", "/api/learner/HT-0603/pathways/open", {}, cookie=six, csrf=six_csrf)[0] == 403
    with pytest.raises(GateBlocked):
        pathways.open_ideas(auth.mint_agent_token(login("M-9001")), "HT-0008")  # an agent cannot open them


def test_assistant_suggests_pathways_but_never_prescribes(school_home, monkeypatch):
    pathways.open_ideas(login("M-9001"), "HT-0007")
    out = ask2("M-9001", "What pathways could Kiprono explore?", "My talk with Kiprono and the guardian")
    assert not out.get("refused") and "STEM" in out["answer"] and "Arts and Sports Science" in out["answer"]
    assert {store.get_record(c)["learner_id"] for c in out["citations"]} == {"HT-0007"}
    none = {"allowed": set(), "learners": []}
    ok = "Kiprono could explore STEM, for example Technical and Engineering, and Arts and Sports Science."
    assert assistant.problems(ok, none) == []
    for bad in ["Kiprono should take STEM.", "Kiprono is a STEM learner.", "The best pathway for him is STEM.",
                "Arts and Sports Science is the right choice for her.", "He is destined for engineering."]:
        assert assistant.problems(bad, none), bad
    ctx = assistant.prepare("M-9001", "What pathways could Kiprono explore?")
    good_id = sorted(ctx["allowed"] & set(pathways.for_learner("HT-0007")["pathways"][2]["evidence"]))[0]
    replies = iter([f"Kiprono should take the Arts and Sports Science pathway [{good_id}].",
                    f"Kiprono could explore Arts and Sports Science: Creative Arts has held at EE [{good_id}]. "
                    "Ask what he enjoys; he and his family choose.",
                    "Kiprono and Brian could both explore STEM."])
    monkeypatch.setattr(assistant, "_chat", lambda *a, **k: next(replies, None))
    monkeypatch.setattr(assistant.comments, "model_name", lambda: "qwen2.5:7b")
    out = ask2("M-9001", "What pathways could Kiprono explore?", "Only to understand the strengths")
    assert out["writer"] == "qwen2.5:7b" and "could explore" in out["answer"], "the prescriptive answer was not shown"
    out = ask2("M-9001", "Tell me about Kiprono", "Everything the records show")
    assert out["writer"] == "hatua", "pathway ideas for Brian, whose ideas are still closed, are not shown"


def test_assistant_knows_every_pupil_in_the_class(school_home):
    session = login("M-9002")
    mine = school.learners_of("M-9002")
    pathways.open_ideas(session, mine[0]["learner_id"])
    ctx = assistant.prepare("M-9002", "Which of my learners have a held strength in Science?")
    assert len(mine) == 20 and all(l["learner_id"] in ctx["data"] for l in mine)
    assert ctx["data"].count("Pathway evidence (Grade 9 pathway ideas)") == 1
    assert ctx["data"].count("Pathway ideas: NOT OPENED") == 19
    nine_a = {l["learner_id"] for l in school.learners_of("M-9001")}
    assert not any(lid in ctx["data"] for lid in nine_a), "the other Grade 9 stream stays private"
    assert {store.get_record(i)["learner_id"] for i in ctx["allowed"]} <= {l["learner_id"] for l in mine}


# ---------------------------------------------------------------- parents
def ask_parent(parent_id, question, reply_index=0):
    from hatua import family
    first = family.ask(parent_id, question)
    if first["kind"] != "follow_up":
        return first
    return family.ask(parent_id, question, ask_id=first["ask_id"], reply=first["options"][reply_index])


def test_a_parent_sees_only_their_own_child(portal):
    cookie, csrf, out = sign_in(portal, "P-100001")
    assert out["role"] == "parent" and "me" not in out
    me = call(portal, "GET", "/api/me", cookie=cookie)[2]
    assert me["role"] == "parent" and [c["id"] for c in me["family"]["children"]] == ["HT-0001"]
    st, _, child = call(portal, "GET", "/api/family/child/HT-0001", cookie=cookie)
    assert st == 200 and child["name"] == "Achieng" and child["teacher"] == "Daniel Mutiso"
    assert {r[0] for r in child["records"]} == {r["record_id"] for r in store.records_for("HT-0001")}
    assert "notes" not in child, "teacher notes never reach a parent"
    assert call(portal, "GET", "/api/family/child/HT-0002", cookie=cookie)[0] == 403
    for path in ("/api/class", "/api/learner/HT-0001", "/api/notices", "/api/drive", "/api/calendar"):
        assert call(portal, "GET", path, cookie=cookie)[0] == 403, path
    note = next(n["note_id"] for n in store.load("notes") if n["learner_id"] == "HT-0001")
    assert call(portal, "GET", f"/api/evidence/{note}", cookie=cookie)[0] == 403
    other = next(r["record_id"] for r in store.records_for("HT-0002"))
    assert call(portal, "GET", f"/api/evidence/{other}", cookie=cookie)[0] == 404
    mine = store.records_for("HT-0001")[0]["record_id"]
    assert call(portal, "GET", f"/api/evidence/{mine}", cookie=cookie)[2]["learner_id"] == "HT-0001"
    st, _, _ = call(portal, "POST", "/api/learner/HT-0001/pathways/open", {}, cookie=cookie, csrf=csrf)
    assert st == 403, "a parent can never act as a teacher"
    with pytest.raises(GateBlocked):
        auth.mint_agent_token(auth.login("P-100001", PIN)["session"])


def test_a_parent_with_two_children_and_a_one_time_pin(portal):
    _, _, out = sign_in(portal, "P-100002")
    from hatua import family
    assert [c["id"] for c in family.profile("P-100002")["children"]] == ["HT-0405", "HT-0805"]
    cookie, csrf, out = sign_in(portal, "P-100003")
    assert out["must_change"] and out["role"] == "parent"
    assert call(portal, "GET", "/api/family/child/HT-0603", cookie=cookie)[0] == 403, "nothing opens before a new PIN"
    st, _, _ = call(portal, "POST", "/api/pin", {"current": PIN, "new": "kamau2468"}, cookie=cookie, csrf=csrf)
    assert st == 200
    assert call(portal, "GET", "/api/family/child/HT-0603", cookie=cookie)[0] == 200


def test_pathway_ideas_reach_a_parent_only_after_the_teacher_opens_them(school_home):
    from hatua import family
    assert family.child_view("P-100001", "HT-0001")["pathways"]["opened"]["by"] == "Daniel Mutiso"
    closed = family.child_view("P-100002", "HT-0805")["pathways"]
    assert closed["locked"] and closed["pathways"] == [] and "has not shared" in closed["intro"]
    assert family.child_view("P-100002", "HT-0405")["pathways"]["stage"] == "too_early"
    gated = ask_parent("P-100002", "What pathways could Nyokabi explore?", 1)
    assert gated.get("gated") and "STEM" not in gated["answer"]
    shared = ask_parent("P-100001", "What pathways could Achieng explore?", 1)
    assert "STEM" in shared["answer"] and {store.get_record(c)["learner_id"] for c in shared["citations"]} == {"HT-0001"}


def test_the_teacher_gives_and_removes_parent_access(portal):
    cookie, csrf, _ = sign_in(portal, "M-9001")
    st, _, out = call(portal, "POST", "/api/learner/HT-0002/parents", {"name": "Mercy Atieno", "relation": "Mother"},
                      cookie=cookie, csrf=csrf)
    assert st == 200 and out["parent_id"].startswith("P-") and len(out["one_time_pin"]) == 8
    assert out["parents"][0]["waiting_first_sign_in"]
    stored = json.dumps(auth._read(auth._path("teachers"), {}))
    assert out["one_time_pin"] not in stored and out["one_time_pin"] not in json.dumps(store.load("guardians"))
    assert call(portal, "POST", "/api/learner/HT-0405/parents", {"name": "X Y Z"}, cookie=cookie, csrf=csrf)[0] == 403
    assert call(portal, "POST", "/api/learner/HT-0002/parents", {"name": "Q"}, cookie=cookie)[0] == 403, "CSRF needed"
    parent, pcsrf, first = sign_in(portal, out["parent_id"], out["one_time_pin"])
    assert first["must_change"]
    call(portal, "POST", "/api/pin", {"current": out["one_time_pin"], "new": "mercy2468"}, cookie=parent, csrf=pcsrf)
    assert call(portal, "GET", "/api/family/child/HT-0002", cookie=parent)[0] == 200
    # a brother or sister: the same parent number, linked by the other class teacher
    other, ocsrf, _ = sign_in(portal, "M-9002")
    nine_b = next(l["learner_id"] for l in school.learners_of("M-9002"))
    st, _, linked = call(portal, "POST", f"/api/learner/{nine_b}/parents", {"existing_id": out["parent_id"]},
                         cookie=other, csrf=ocsrf)
    assert st == 200 and linked["one_time_pin"] is None
    st, _, _ = call(portal, "POST", f"/api/learner/HT-0002/parents/{out['parent_id']}/remove", {}, cookie=cookie, csrf=csrf)
    assert st == 200
    assert call(portal, "GET", "/api/family/child/HT-0002", cookie=parent)[0] == 403
    assert call(portal, "GET", f"/api/family/child/{nine_b}", cookie=parent)[0] == 200, "the other child stays"
    call(portal, "POST", f"/api/learner/{nine_b}/parents/{out['parent_id']}/remove", {}, cookie=other, csrf=ocsrf)
    assert auth.role_of(out["parent_id"]) is None and call(portal, "GET", "/api/me", cookie=parent)[0] == 401
    tools = [e["tool"] for e in audit.read_events() if e["tool"].startswith("parent.")]
    assert tools.count("parent.add") == 2 and tools.count("parent.remove") == 2


def test_the_parent_assistant_asks_first_and_never_compares(school_home):
    from hatua import family
    first = family.ask("P-100001", "How is Achieng doing?")
    assert first["kind"] == "follow_up" and len(first["options"]) >= 3
    out = family.ask("P-100001", "How is Achieng doing?", ask_id=first["ask_id"], reply=first["options"][0])
    assert out["kind"] == "answer" and out["citations"]
    assert {store.get_record(c)["learner_id"] for c in out["citations"]} == {"HT-0001"}
    with pytest.raises(ValueError):  # each follow-up is used once
        family.ask("P-100001", "x", ask_id=first["ask_id"], reply="again")
    with pytest.raises(ValueError):  # and only by the parent it was asked of
        f2 = family.ask("P-100001", "How is Achieng doing?")
        family.ask("P-100002", "x", ask_id=f2["ask_id"], reply="steal")
    for q in ("Is Achieng the best in her class?", "Compare Achieng with the others", "How is Brian doing?"):
        out = family.ask("P-100001", q)
        assert out["kind"] == "answer" and out.get("refused"), q
        assert "Brian" not in out["answer"] and not out.get("citations")
    ctx = family.prepare("P-100001", "How is Achieng doing?")
    assert all(store.get_record(i)["learner_id"] == "HT-0001" for i in ctx["allowed"])
    assert "Teacher note" not in ctx["data"] and "Brian" not in ctx["data"]
    two = family.ask("P-100002", "How can I help at home?")
    assert two["question"] == "Which child do you mean?" and two["options"] == ["Wanjiku", "Nyokabi"]


# ---------------------------------------------------------------- getting Qwen from the sign-in page
def test_qwen_setup_talks_only_to_ollama_on_this_computer(monkeypatch):
    from hatua import ai_setup
    have = set()

    class FakeOllama(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def do_GET(self):
            body = json.dumps({"models": [{"name": n} for n in sorted(have)]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            assert self.path == "/api/pull"
            want = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["model"]
            self.send_response(200)
            self.end_headers()
            for done in (0, 50, 100):
                self.wfile.write(json.dumps({"status": "pulling", "total": 100, "completed": done}).encode() + b"\n")
            have.add(want)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("HATUA_OLLAMA_HOST", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(ai_setup, "_STATE", {"state": "idle", "percent": 0, "message": ""})
    st = ai_setup.status()
    assert st["ollama"] == "running" and not st["ready"]
    ai_setup.get_qwen()
    for _ in range(100):
        if ai_setup.status()["ready"]:
            break
        threading.Event().wait(0.05)
    st = ai_setup.status()
    assert st["ready"] and st["pull"]["percent"] == 100
    srv.shutdown()
    monkeypatch.setenv("HATUA_OLLAMA_HOST", "http://example.com:11434")  # never anywhere but this computer
    assert ai_setup.status()["ollama"] in ("not_running", "not_installed")
    with pytest.raises(RuntimeError):
        ai_setup.get_qwen()
