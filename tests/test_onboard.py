"""A new school starts empty: create an account, add learners, fill the results sheet, approve it.

No practice data anywhere. Each test works in its own empty Hatua folder.
"""
import http.client
import json
import threading

import pytest

from hatua import auth, config, onboard, store, xlsx
from hatua.summary import GateBlocked

PIN = "wanjiku-6A"


@pytest.fixture
def empty(tmp_path, monkeypatch):
    root = tmp_path / "My school"
    for name, value in {"ROOT": root, "STORE": root / "store", "LOGS": root / "logs", "AUDIT_LOG": root / "logs" / "audit.jsonl",
                        "APPROVALS_LOG": root / "logs" / "approvals.jsonl", "PROFILES": root / "profiles", "DATA": root / "data",
                        "RAW": root / "data" / "raw", "INBOX": root / "data" / "inbox", "UI": root / "ui"}.items():
        monkeypatch.setattr(config, name, value)
    (root / "store").mkdir(parents=True)
    monkeypatch.setenv("HATUA_TODAY", "2026-11-16")
    monkeypatch.setenv("HATUA_LLM", "off")
    monkeypatch.delenv("HATUA_DRIVE", raising=False)
    from hatua import privacy
    monkeypatch.setattr(privacy, "accepted", lambda person_id: True)
    return root


def make(**k):
    a = {"school": "Kibera Primary", "name": "Jane Wanjiku", "member_no": "tsc-4471", "stream": "6a", "pin": PIN, "pin_again": PIN}
    a.update(k)
    return onboard.create_account(a["school"], a["name"], a["member_no"], a["stream"], a["pin"], a["pin_again"])


def test_the_first_person_names_the_school_and_makes_their_own_account(empty):
    assert onboard.first_run() and onboard.signup_open() and store.load("learners") == []
    out = make()
    assert out == {"teacher_id": "TSC-4471", "name": "Jane Wanjiku", "class": "6A", "school": "Kibera Primary"}
    assert not onboard.first_run() and onboard.school_name() == "Kibera Primary"
    session = auth.login("TSC-4471", PIN)           # the PIN is theirs: no one-time PIN step
    assert not session.get("must_change")
    from hatua import school
    assert school.streams_of("TSC-4471") == ["6A"] and school.learners_of("TSC-4471") == []


def test_account_mistakes_are_refused_in_plain_words(empty):
    cases = [({"school": "x"}, "school's name"), ({"name": "Jo"}, "full name"), ({"member_no": "a b"}, "member number"),
             ({"stream": "3A"}, "grade from 4 to 9"), ({"stream": "10"}, "grade from 4 to 9"),
             ({"pin_again": "other-pin"}, "not the same"), ({"pin": "123456", "pin_again": "123456"}, "first that people try"),
             ({"pin": "tsc-4471-x", "pin_again": "tsc-4471-x"}, "member number")]
    for bad, words in cases:
        with pytest.raises(ValueError, match=words):
            make(**bad)
    assert onboard.first_run(), "nothing was created by the refused attempts"


def test_a_second_teacher_makes_their_own_class_and_cannot_take_another_teachers(empty):
    make()
    onboard.add_learners("TSC-4471", "Wanjiku\nKamau")
    with pytest.raises(ValueError, match="already has a class teacher"):
        make(name="Other Person", member_no="TSC-9", stream="6A")
    with pytest.raises(ValueError, match="already has an account"):
        make(stream="7A")
    out = make(name="Peter Otieno", member_no="TSC-5000", stream="7B", school="ignored")
    assert out["school"] == "Kibera Primary", "the school's name stays the first person's"
    from hatua import school
    assert school.learners_of("TSC-5000") == [] and len(school.learners_of("TSC-4471")) == 2, "each sees only their own class"


def test_a_practice_school_never_opens_accounts(empty):
    (config.ROOT / "demo.json").write_text("{}")
    assert not onboard.signup_open() and not onboard.first_run()
    with pytest.raises(ValueError, match="not opened"):
        make()


def test_adding_learners(empty):
    make()
    out = onboard.add_learners("TSC-4471", "Wanjiku, 1042\n  Kamau ,1043\n\nAchieng\nBad<script>, 1\nKamau, 1043")
    assert [a["learner_id"] for a in out["added"]] == ["HT-0001", "HT-0002", "HT-0003"]
    assert out["skipped"] == ["Kamau"] and len(out["refused"]) == 1 and out["total"] == 3
    rows = store.load("learners")
    assert rows[0] == {"learner_id": "HT-0001", "first_name": "Wanjiku", "sex": "", "current_grade": "6", "stream": "6A",
                       "joined": "", "school": "Kibera Primary", "admission_no": "1042"}
    make(name="Peter Otieno", member_no="TSC-5000", stream="7B")
    nxt = onboard.add_learners("TSC-5000", "Otieno")
    assert nxt["added"][0]["learner_id"] == "HT-0004", "numbers continue across classes"
    with pytest.raises(ValueError, match="at least one name"):
        onboard.add_learners("TSC-4471", "  \n ")
    with pytest.raises(ValueError, match="at most"):
        onboard.add_learners("TSC-4471", "\n".join(f"Name{chr(65 + i % 26)}{'x' * (i // 26)}" for i in range(101)))
    with pytest.raises(GateBlocked):
        onboard.add_learners("NOBODY", "Wanjiku")


def test_results_sheet_filled_in_uploaded_and_approved_end_to_end(empty):
    from hatua import drive
    make()
    onboard.add_learners("TSC-4471", "Wanjiku\nKamau")
    with pytest.raises(ValueError, match="Add your learners"):
        make(name="Peter Otieno", member_no="TSC-5000", stream="7B") and onboard.results_template("TSC-5000", 2026, 1)
    sheet = onboard.results_template("TSC-4471", 2026, 3)
    header, rows = xlsx.read_bytes(sheet)
    assert header[:3] == ["learner_id", "name", "grade"] and len(rows) == 2 * 7, "a row for each learner and each Grade 6 area"
    assert {r["learning_area"] for r in rows} >= {"Mathematics", "Science and Technology", "Creative Arts"}
    for r in rows:
        r["level"] = "ME"
    filled = xlsx.to_bytes(rows, "Results", header)
    session = auth.login("TSC-4471", PIN)["session"]
    drive.upload(session, "term3.xlsx", filled, 2026, 3)
    path = next(f["path"] for g in drive.folders("TSC-4471", 2026) for t in g["terms"] for f in t["files"])
    pre = drive.preview(path, "TSC-4471")
    assert not pre.get("problems"), pre
    done = drive.decide(path, session, "approve")
    assert done["added"] == 14
    assert {r["learner_id"] for r in store.load("records")} == {"HT-0001", "HT-0002"}


def test_the_portal_flow_from_an_empty_folder(empty):
    from hatua import portal
    srv = portal.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def call(method, path, body=None, cookie=None, csrf=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        h = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        if csrf:
            h["X-Hatua-CSRF"] = csrf
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        return r.status, dict(r.getheaders()), json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data
    try:
        pub = call("GET", "/api/public")[2]
        assert pub["setup"] is True and pub["practice"] is None and pub["school"] == ""
        st, _, body = call("POST", "/api/signup", {"school": "Kibera Primary", "name": "Jane Wanjiku", "member_no": "TSC-4471",
                                                   "class": "6A", "pin": PIN, "pin_again": PIN})
        assert st == 200, body
        pub = call("GET", "/api/public")[2]
        assert pub["setup"] is False and pub["signup"] is True and pub["school"] == "Kibera Primary"
        assert call("POST", "/api/signup", {"school": "x", "name": "Jane Wanjiku", "member_no": "TSC-4471", "class": "7A",
                                            "pin": PIN, "pin_again": PIN})[0] == 400
        st, h, login = call("POST", "/api/login", {"teacher_id": "TSC-4471", "pin": PIN})
        assert st == 200 and not login.get("must_change")
        cookie, csrf = h["Set-Cookie"].split(";")[0], login["csrf"]
        assert call("GET", "/api/class", cookie=cookie)[2] == {"learners": []}
        assert call("POST", "/api/class/learners", {"names": "Wanjiku"}, cookie=cookie)[0] == 403, "CSRF needed"
        st, _, out = call("POST", "/api/class/learners", {"names": "Wanjiku, 1042\nKamau"}, cookie=cookie, csrf=csrf)
        assert st == 200 and out["total"] == 2
        cards = call("GET", "/api/class", cookie=cookie)[2]["learners"]
        assert [c["id"] for c in cards] == ["HT-0001", "HT-0002"]
        st, h2, sheet = call("GET", "/api/drive/template?term=2&year=2026", cookie=cookie)
        assert st == 200 and sheet[:2] == b"PK" and "results-term-2.xlsx" in h2["Content-Disposition"]
        assert call("GET", "/api/drive/template?term=x", cookie=cookie)[0] == 400
        me = call("GET", "/api/me", cookie=cookie)[2]
        assert me["me"]["learners"] == 2 and me["me"]["class_label"] == "Grade 6A"
    finally:
        srv.shutdown()
