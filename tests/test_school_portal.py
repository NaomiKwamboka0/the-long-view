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

from hatua import audit, auth, comments, config, drive, notify, school, school_calendar, school_demo, store
from hatua.summary import GateBlocked

REPO = Path(__file__).resolve().parent.parent
PIN = "246810"
G6 = "Grade 6/2026 Term 3/grade6_2026_term3_results.csv"


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


# ---------------------------------------------------------------- calendar
def test_kenya_2026_calendar_terms_and_due_dates(school_home):
    assert school_calendar.term_on(date(2026, 2, 26))["state"] == "half_term"
    assert school_calendar.term_on(date(2026, 9, 7)) == {"year": 2026, "term": 3, "state": "in_term", "week": 3,
                                                         "text": "Term 3, week 3"}
    assert school_calendar.term_on(date(2026, 4, 15))["text"].startswith("School holiday after Term 1. Term 2 opens 27 Apr")
    due = school_calendar.due_terms(date(2026, 10, 29))
    assert [d["term"] for d in due] == [1, 2], "Term 3 results are due 7 days after it closes on 23 Oct"
    assert [d["term"] for d in school_calendar.due_terms(date(2026, 10, 30))] == [1, 2, 3]


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
    rel = "Grade 9/2026 Term 3/grade9_2026_term3_results.csv"
    a = drive.decide(rel, login("M-9001"), "approve")
    mine = {l["learner_id"] for l in school.learners_of("M-9001")}
    added = [r for r in store.load("records") if r.get("file") == a["inbox_file"]]
    assert added and {r["learner_id"] for r in added} <= mine
    assert drive.preview(rel, "M-9002")["counts"]["yours"] == 156  # 9B's rows wait for 9B's teacher
    assert [f["status"] for g in drive.folders("M-9002") for t in g["terms"] for f in t["files"]] == ["waiting"]


def test_drive_refuses_other_grades_paths_and_agent_tokens(school_home):
    with pytest.raises(GateBlocked):
        drive.preview(G6, "M-5001")
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
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    statuses = [f["status"] for g in drive.folders("M-6001") for t in g["terms"] for f in t["files"]]
    assert statuses == ["waiting"]


def test_upload_then_approve_clears_the_missing_notice(school_home):
    session = login("M-7001")
    sample = school_home / "samples" / "grade7_2026_term3_results.csv"
    up = drive.upload(session, "../../evil name?.csv", sample.read_bytes(), 2026, 3)
    assert up["path"] == "Grade 7/2026 Term 3/evil name.csv"
    with pytest.raises(ValueError):
        drive.upload(session, "x.csv", b"name,score\nA,3\n", 2026, 3)  # missing Hatua's columns
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
        comments.rate(out["next"]["comment_id"], login("M-5001"), "up")  # not their comment


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


# ---------------------------------------------------------------- the HTTP portal
@pytest.fixture
def portal(school_home):
    from hatua import portal as p
    srv = p.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def call(port, method, path, body=None, cookie=None, csrf=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    headers = {"Host": host or f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Hatua-CSRF"] = csrf
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = c.getresponse()
    data = r.read()
    return r.status, dict(r.getheaders()), (json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data)


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


# ---------------------------------------------------------------- the Hatua assistant
from hatua import assistant  # noqa: E402


def test_assistant_refuses_rankings_without_the_model(school_home):
    for q in ["Who is the best in Maths?", "Rank my class in English", "Compare Kamau with the class",
              "Nani ni mwanafunzi bora?"]:
        out = assistant.ask("M-6001", q)
        assert out.get("refused") and "does not rank" in out["answer"], q
    assert not assistant.ask("M-6001", "What is the best way to teach fractions?").get("refused")
    out = assistant.ask("M-6001", "Which pathway should Atieno take?")
    assert not out.get("refused") and "chosen in Grade 9" in out["answer"], "Grade 6: too early for pathways"


def test_assistant_knows_only_my_class(school_home):
    drive.decide(G6, login("M-6001"), "approve")
    ctx = assistant.prepare("M-6001", "How is Kamau doing?")
    six = {l["learner_id"] for l in school.learners_of("M-6001")}
    others = [l for l in store.load("learners") if l["learner_id"] not in six]
    assert all(l["first_name"] not in ctx["data"] and l["learner_id"] not in ctx["data"] for l in others)
    assert {store.get_record(i)["learner_id"] for i in ctx["allowed"]} <= six
    out = assistant.ask("M-6001", "How is Kamau doing?")
    assert out["writer"] == "hatua" and out["citations"]
    assert {store.get_record(c)["learner_id"] for c in out["citations"]} == {"HT-0603"}
    assert "can't find Amani" in assistant.ask("M-6001", "Tell me about Amani")["answer"]
    att = assistant.ask("M-6001", "Who needs my attention?")["answer"]
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
    monkeypatch.setattr(assistant, "_chat", lambda *a, **k: next(replies))
    out = assistant.ask("M-6001", "How is Kamau doing?")
    assert out["writer"] == "qwen2.5:7b" and out["citations"] == [good_id]
    out = assistant.ask("M-6001", "How is Kamau doing?")  # a label, then another class's record: both refused
    assert out["writer"] == "hatua", "neither bad answer is shown; the built-in answer is used instead"
    out = assistant.ask("M-6001", "How is Kamau doing?")
    assert out["writer"] == "qwen2.5:7b"
    events = [e for e in __import__("hatua.audit", fromlist=["x"]).read_events() if e["tool"] == "assistant.ask"]
    assert events and all("How is" not in json.dumps(e) for e in events), "questions are not written to the log"


def test_assistant_and_evidence_endpoints(portal):
    st, headers, body = call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": PIN})
    cookie, csrf = headers["Set-Cookie"].split(";")[0], body["csrf"]
    assert call(portal, "POST", "/api/assistant", {"question": "Who needs my attention?"}, cookie=cookie)[0] == 403
    st, _, out = call(portal, "POST", "/api/assistant", {"question": "When were Term 3 results due?"},
                      cookie=cookie, csrf=csrf)
    assert st == 200 and "2026-10-30" in out["answer"]
    mine = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0603")
    theirs = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0401")
    assert call(portal, "GET", f"/api/evidence/{mine}", cookie=cookie)[2]["learner_id"] == "HT-0603"
    assert call(portal, "GET", f"/api/evidence/{theirs}", cookie=cookie)[0] == 404


# ---------------------------------------------------------------- pathways
from hatua import pathways  # noqa: E402


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
    assert not assistant.problems(text, {"allowed": set(assistant.guard.citations(text))})
    assert "learner chooses" in text


def test_assistant_suggests_pathways_but_never_prescribes(school_home, monkeypatch):
    out = assistant.ask("M-9001", "What pathways could Kiprono explore?")
    assert not out.get("refused") and "STEM" in out["answer"] and "Arts and Sports Science" in out["answer"]
    assert {store.get_record(c)["learner_id"] for c in out["citations"]} == {"HT-0007"}
    ok = "Kiprono could explore STEM, for example Technical and Engineering, and Arts and Sports Science."
    assert assistant.problems(ok, {"allowed": set()}) == []
    for bad in ["Kiprono should take STEM.", "Kiprono is a STEM learner.", "The best pathway for him is STEM.",
                "Arts and Sports Science is the right choice for her.", "He is destined for engineering."]:
        assert assistant.problems(bad, {"allowed": set()}), bad
    # WP-P (P1): Pathway questions never reach the model; they return deterministic builtin text
    model_called = []
    monkeypatch.setattr(assistant, "_chat", lambda *a, **k: model_called.append(True) or "mock reply")
    monkeypatch.setattr(assistant.comments, "model_name", lambda: "qwen2.5:7b")
    out = assistant.ask("M-9001", "What pathways could Kiprono explore?")
    assert out["writer"] == "hatua" and len(model_called) == 0, "pathway questions skip the model completely"


def test_assistant_knows_every_pupil_in_the_class(school_home):
    ctx = assistant.prepare("M-9002", "Which of my learners have a held strength in Science?")
    mine = school.learners_of("M-9002")
    assert len(mine) == 20 and all(l["learner_id"] in ctx["data"] for l in mine)
    # WP1.8: Non-pathway question produces a context with no pathway evidence
    assert "Pathway evidence" not in ctx["data"]
    # ... but a pathway question includes it
    ctx_pw = assistant.prepare("M-9002", "What pathways could Kiprono explore?")
    assert "Pathway evidence (Grade 9 pathway ideas)" in ctx_pw["data"]
    nine_a = {l["learner_id"] for l in school.learners_of("M-9001")}
    assert not any(lid in ctx["data"] for lid in nine_a), "the other Grade 9 stream stays private"
    assert {store.get_record(i)["learner_id"] for i in ctx["allowed"]} <= {l["learner_id"] for l in mine}


# ---------------------------------------------------------------- WP1 hardening tests

def test_assistant_rejects_uncited_result_claims(school_home):
    ctx = {"allowed": {"R-0001", "R-0002"}}
    # Sentences with results and no citation are rejected (WP1.1)
    uncited_cases = [
        "Amina is at Exceeding Expectations in Mathematics.",
        "Her Mathematics results fell from Meeting Expectations.",
        "Attendance dropped to 44/70 days last term.",
        "She scored 85% in Science.",
        "He needs support in Kiswahili.",
        "Kamau got EE in Creative Arts.",
        "Results declined over the last two terms.",
    ]
    for sentence in uncited_cases:
        probs = assistant.problems(sentence, ctx)
        assert probs, f"Expected uncited claim to be rejected: {sentence}"
        assert any("states a result without a citation" in p for p in probs)

    # Valid citations pass
    valid = "Amina is at Exceeding Expectations in Mathematics [R-0001]."
    assert assistant.problems(valid, ctx) == []

    # Citation not in ctx["allowed"] is rejected
    alien = "Amina is at Exceeding Expectations in Mathematics [R-9999]."
    probs = assistant.problems(alien, ctx)
    assert any("cites records that were not given" in p for p in probs)

    # General statements with no result claim pass without citations
    assert assistant.problems("Open the My class tab to see the long view.", ctx) == []
    assert assistant.problems("Today is Friday and Term 3 closes next week.", ctx) == []


def test_assistant_blocks_probe_phrases_and_allows_legitimate_suggestions(school_home):
    ctx = {"allowed": {"R-1", "R-2"}}
    # 7 probe sentences from WP1.7 + class ranking sentence
    probes = [
        "Amina should consider STEM",
        "would thrive in the Social Sciences pathway",
        "STEM looks like the right direction for Amina",
        "I'd encourage Amina to go for Arts and Sports Science",
        "Amina is a natural at STEM",
        "STEM is a better choice than Arts for Amina",
        "STEM it is",
        "Amina is the strongest in the class at maths",
    ]
    for probe in probes:
        with_cite = f"{probe} [R-1]"
        probs = assistant.problems(with_cite, ctx)
        assert probs, f"Expected probe to be blocked: '{probe}'"

    # At least 10 legitimate suggestion sentences that must pass
    legit = [
        "Her strengths point to STEM and Arts and Sports Science [R-1].",
        "She could explore STEM and Social Sciences [R-1].",
        "The records show strengths in Creative Arts and Integrated Science [R-1].",
        "Options for the family to explore include STEM and Arts and Sports Science [R-1].",
        "Kiprono could explore Arts and Sports Science: Creative Arts has held at EE [R-1].",
        "Her evidence relates to all three pathways [R-1].",
        "These are ideas for your conversation with the learner and family [R-1].",
        "The learner and family choose based on interests and KJSEA results [R-1].",
        "Strengths the records show now include Technical Studies and Mathematics [R-1].",
        "Areas to explore further include Social Sciences and STEM [R-1].",
    ]
    for sentence in legit:
        probs = assistant.problems(sentence, ctx)
        assert probs == [], f"Legitimate suggestion was wrongly blocked: '{sentence}', issues: {probs}"


def test_pathway_views_logged_and_omitted_for_grades_4_to_6(portal):
    st, headers, body = call(portal, "POST", "/api/login", {"teacher_id": "M-9001", "pin": PIN})
    cookie, csrf = headers["Set-Cookie"].split(";")[0], body["csrf"]

    # View Grade 9 learner -> writes portal.view_pathways (WP1.2)
    st, _, out = call(portal, "GET", "/api/learner/HT-0007", cookie=cookie)
    assert st == 200 and out["grade"] == 9
    events = [e for e in audit.read_events() if e.get("action") == "portal.view_pathways" and e.get("via") != "assistant"]
    assert any(e.get("learner_id") == "HT-0007" and e.get("actor") == "M-9001" for e in events)

    # View Grade 6 learner with Grade 6 teacher -> NO portal.view_pathways event
    st6, h6, b6 = call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": PIN})
    cookie6 = h6["Set-Cookie"].split(";")[0]
    st, _, out6 = call(portal, "GET", "/api/learner/HT-0603", cookie=cookie6)
    assert st == 200 and out6["grade"] == 6
    g6_events = [e for e in audit.read_events() if e.get("action") == "portal.view_pathways" and e.get("learner_id") == "HT-0603"]
    assert len(g6_events) == 0, "Grades 4-6 must never write portal.view_pathways"

    # Assistant pathway question for Grade 9 learner logs portal.view_pathways with via: assistant
    st, _, out_as = call(portal, "POST", "/api/assistant", {"question": "What pathways could Kiprono explore?"},
                          cookie=cookie, csrf=csrf)
    assert st == 200
    as_events = [e for e in audit.read_events() if e.get("action") == "portal.view_pathways" and e.get("via") == "assistant"]
    assert any(e.get("learner_id") == "HT-0007" for e in as_events)


def test_portal_audit_coverage_and_chain_integrity(portal):
    # 1. Login success
    st, headers, body = call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": PIN})
    assert st == 200
    cookie, csrf = headers["Set-Cookie"].split(";")[0], body["csrf"]

    # 2. Login failure with registered teacher
    st_fail, _, _ = call(portal, "POST", "/api/login", {"teacher_id": "M-6001", "pin": "000000"})
    assert st_fail == 401

    # 3. Login failure with unknown teacher ID
    st_unk, _, _ = call(portal, "POST", "/api/login", {"teacher_id": "UNKNOWN_TEACHER", "pin": "000000"})
    assert st_unk == 401

    # 4. View class
    st_cls, _, _ = call(portal, "GET", "/api/class", cookie=cookie)
    assert st_cls == 200

    # 5. View learner
    st_lrn, _, _ = call(portal, "GET", "/api/learner/HT-0603", cookie=cookie)
    assert st_lrn == 200

    # 6. View evidence
    rec_id = next(r["record_id"] for r in store.load("records") if r["learner_id"] == "HT-0603")
    st_ev, _, _ = call(portal, "GET", f"/api/evidence/{rec_id}", cookie=cookie)
    assert st_ev == 200

    # 7. Logout
    st_out, _, _ = call(portal, "POST", "/api/logout", {}, cookie=cookie, csrf=csrf)
    assert st_out == 200

    # Verify audit events and chain
    events = audit.read_events()
    actions = {e.get("action") for e in events}
    assert "portal.login" in actions
    assert "portal.logout" in actions
    assert "portal.view_class" in actions
    assert "portal.view_learner" in actions
    assert "portal.view_evidence" in actions

    # Check unknown ID did not leak in failure event
    unk_logins = [e for e in events if e.get("action") == "portal.login" and e.get("actor") == "unknown_id"]
    assert len(unk_logins) >= 1
    assert all("UNKNOWN_TEACHER" not in json.dumps(e) for e in unk_logins)

    # Check no PIN, session, or csrf values leaked anywhere in audit.jsonl
    raw_log = config.AUDIT_LOG.read_text(encoding="utf-8")
    assert PIN not in raw_log
    assert csrf not in raw_log

    # Verify log chain is intact
    chain_check = audit.verify_jsonl(config.AUDIT_LOG)
    assert chain_check["ok"] is True and chain_check["chained"] is True


def test_drive_file_safety(school_home):
    session = auth.login("M-6001", PIN)["session"]

    # 1. Traversal and HTML in filename are stripped and bounded (WP1.5)
    csv_data = b"learner_id,grade,year,term,learning_area,level\nHT-0603,6,2026,3,Mathematics,ME\n"
    up = drive.upload(session, "../../<script>alert(1)</script>very_long_file_name_that_should_be_bounded_properly.csv",
                      csv_data, 2026, 3)
    assert ".." not in up["path"]
    assert "<" not in up["path"]
    assert up["path"].endswith(".csv")

    # 2. File with rows for another class/stream is not applied by the wrong teacher
    # Create CSV where rows belong to Grade 4 (HT-0401), not Grade 6 stream A (M-6001)
    other_stream_row = b"learner_id,grade,year,term,learning_area,level\nHT-0401,6,2026,3,Mathematics,ME\n"
    up_other = drive.upload(session, "other_stream.csv", other_stream_row, 2026, 3)
    prev = drive.preview(up_other["path"], "M-6001")
    assert prev["counts"]["yours"] == 0
    assert prev["counts"]["other_class"] == 1
    with pytest.raises(GateBlocked, match="No rows in this file are for your class"):
        drive.decide(up_other["path"], session, "approve")

