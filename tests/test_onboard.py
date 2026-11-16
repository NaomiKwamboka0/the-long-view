"""A new school starts empty: the head teacher sets it up and creates the class teachers' logins.

No practice data anywhere. Each test works in its own empty Hatua folder.
"""
import http.client
import json
import threading

import pytest

from hatua import audit, auth, config, onboard, store, xlsx
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
    assert onboard.first_run() and store.load("learners") == []
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


def test_nobody_else_can_create_their_own_account(empty):
    make()
    with pytest.raises(ValueError, match="Ask your head teacher"):
        make(name="Other Person", member_no="TSC-9", stream="7B")
    assert not onboard.first_run()


def test_the_head_teacher_may_teach_no_class(empty):
    out = make(stream="")
    assert out["class"] == "" and onboard.is_head("TSC-4471")
    from hatua import school
    assert school.streams_of("TSC-4471") == [] and school.learners_of("TSC-4471") == []
    with pytest.raises(GateBlocked):
        onboard.add_learners("TSC-4471", "Wanjiku")      # no class: nothing to add learners to


def test_the_head_teacher_creates_logins_and_each_teacher_sees_only_their_class(empty):
    from hatua import school
    make(stream="")
    head = auth.login("TSC-4471", PIN)["session"]
    out = onboard.add_teacher(head, "Mary Njeri", "tsc-6001", "6a")
    assert out["teacher_id"] == "TSC-6001" and out["class"] == "6A" and len(out["one_time_pin"]) == 8 and out["school"] == "Kibera Primary"
    stored = json.dumps(auth._read(auth._path("teachers"), {}))
    assert out["one_time_pin"] not in stored, "the PIN is never stored"
    first = auth.login("TSC-6001", out["one_time_pin"])
    assert first["must_change"], "the teacher must choose their own PIN before anything opens"
    out7 = onboard.add_teacher(head, "Peter Otieno", "TSC-7001", "7B")
    onboard.add_learners("TSC-6001", "Wanjiku\nKamau")
    onboard.add_learners("TSC-7001", "Otieno")
    assert [l["first_name"] for l in school.learners_of("TSC-6001")] == ["Wanjiku", "Kamau"]
    assert [l["first_name"] for l in school.learners_of("TSC-7001")] == ["Otieno"]
    assert school.learners_of("TSC-4471") == [], "the head teacher manages accounts: no class, no learners"
    rows = {t["teacher_id"]: t for t in onboard.teachers("TSC-4471")}
    assert rows["TSC-4471"]["head"] and rows["TSC-6001"]["classes"] == ["6A"] and rows["TSC-6001"]["learners"] == 2
    assert rows["TSC-6001"]["waiting_first_sign_in"] and out7["one_time_pin"] not in json.dumps(onboard.teachers("TSC-4471"))
    ev = [e for e in audit.read_events() if e["tool"] == "teacher.add"]
    assert [e["output"]["added_by"] for e in ev] == ["Jane Wanjiku", "Jane Wanjiku"]
    assert out["one_time_pin"] not in json.dumps(audit.read_events()), "PINs are never logged"


def test_account_rules_for_the_head_teacher(empty):
    make()
    head = auth.login("TSC-4471", PIN)["session"]
    with pytest.raises(ValueError, match="already has a class teacher"):
        onboard.add_teacher(head, "Other Person", "TSC-9", "6A")          # the head teacher teaches 6A
    made = onboard.add_teacher(head, "Mary Njeri", "TSC-6001", "6B")
    with pytest.raises(ValueError, match="already has a class teacher"):
        onboard.add_teacher(head, "Other Person", "TSC-9", "6b")
    with pytest.raises(ValueError, match="already has an account"):
        onboard.add_teacher(head, "Mary Again", "tsc-6001", "7A")
    with pytest.raises(ValueError, match="grade from 4 to 9"):
        onboard.add_teacher(head, "Other Person", "TSC-9", "")
    with pytest.raises(ValueError, match="full name"):
        onboard.add_teacher(head, "Jo", "TSC-9", "7A")
    limited = auth.login("TSC-6001", made["one_time_pin"])["session"]
    auth.change_pin(limited, made["one_time_pin"], "mary-6B-pin")
    teacher = auth.login("TSC-6001", "mary-6B-pin")["session"]
    with pytest.raises(GateBlocked, match="head teacher"):
        onboard.add_teacher(teacher, "Sneaky Person", "TSC-8", "8A")
    with pytest.raises(GateBlocked, match="head teacher"):
        onboard.teachers("TSC-6001")


def test_new_pin_and_removing_a_teacher(empty):
    from hatua import school
    make(stream="")
    head = auth.login("TSC-4471", PIN)["session"]
    first = onboard.add_teacher(head, "Mary Njeri", "TSC-6001", "6A")
    onboard.add_learners("TSC-6001", "Wanjiku")
    s1 = auth.login("TSC-6001", first["one_time_pin"])["session"]
    again = onboard.new_pin(head, "TSC-6001")
    assert again["one_time_pin"] != first["one_time_pin"] and again["class"] == "6A"
    with pytest.raises(GateBlocked):
        auth.login("TSC-6001", first["one_time_pin"])                   # the old PIN no longer works
    with pytest.raises(GateBlocked):
        auth.resolve(s1, kind="human")                                    # and the old sign-in ended
    with pytest.raises(ValueError, match="Change your own PIN"):
        onboard.new_pin(head, "TSC-4471")
    with pytest.raises(ValueError, match="cannot be removed"):
        onboard.remove_teacher(head, "TSC-4471")
    out = onboard.remove_teacher(head, "TSC-6001")
    assert out["classes_now_without_teacher"] == ["6A"] and auth.role_of("TSC-6001") is None
    assert [l["first_name"] for l in store.load("learners")] == ["Wanjiku"], "the class and its learners stay"
    waiting = [t for t in onboard.teachers("TSC-4471") if t["teacher_id"] is None]
    assert waiting == [{"teacher_id": None, "name": None, "head": False, "classes": ["6A"], "waiting_first_sign_in": False,
                        "last_login": None, "learners": 1}]
    onboard.add_teacher(head, "Grace Atieno", "TSC-6002", "6A")          # a new teacher takes the class, with its learners
    assert [l["first_name"] for l in school.learners_of("TSC-6002")] == ["Wanjiku"]
    tools = [e["tool"] for e in audit.read_events() if e["tool"].startswith("teacher.")]
    assert tools.count("teacher.new_pin") == 1 and tools.count("teacher.remove") == 1


def test_a_practice_school_never_opens_accounts(empty):
    (config.ROOT / "demo.json").write_text("{}")
    assert not onboard.first_run()
    with pytest.raises(ValueError, match="practice school"):
        make()


def test_adding_learners(empty):
    make()
    out = onboard.add_learners("TSC-4471", "Wanjiku, 1042\n  Kamau ,1043\n\nAchieng\nBad<script>, 1\nKamau, 1043")
    assert [a["learner_id"] for a in out["added"]] == ["HT-0001", "HT-0002", "HT-0003"]
    assert out["skipped"] == ["Kamau"] and len(out["refused"]) == 1 and out["total"] == 3
    rows = store.load("learners")
    assert rows[0] == {"learner_id": "HT-0001", "first_name": "Wanjiku", "sex": "", "current_grade": "6", "stream": "6A",
                       "joined": "", "school": "Kibera Primary", "admission_no": "1042"}
    onboard.add_teacher(auth.login("TSC-4471", PIN)["session"], "Peter Otieno", "TSC-5000", "7B")
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
        onboard.add_teacher(auth.login("TSC-4471", PIN)["session"], "Peter Otieno", "TSC-5000", "7B")
        onboard.results_template("TSC-5000", 2026, 1)
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
        assert pub["setup"] is False and "signup" not in pub and pub["school"] == "Kibera Primary"
        assert call("POST", "/api/signup", {"school": "x", "name": "Other Person", "member_no": "TSC-9", "class": "7A",
                                            "pin": PIN, "pin_again": PIN})[0] == 400, "nobody else can sign themselves up"
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
        assert me["me"]["learners"] == 2 and me["me"]["class_label"] == "Grade 6A" and me["me"]["head"] is True
        csrf = me["csrf"]      # /api/me issues a fresh CSRF value
        # the head teacher creates a class teacher over HTTP; that teacher cannot use the head routes
        assert call("GET", "/api/head/teachers", cookie=cookie)[0] == 200
        assert call("POST", "/api/head/teachers", {"name": "Peter Otieno", "member_no": "TSC-7001", "class": "7A"}, cookie=cookie)[0] == 403, "CSRF needed"
        st, _, made = call("POST", "/api/head/teachers", {"name": "Peter Otieno", "member_no": "TSC-7001", "class": "7A"}, cookie=cookie, csrf=csrf)
        assert st == 200 and len(made["one_time_pin"]) == 8, made
        assert call("POST", "/api/head/teachers", {"name": "Dup Person", "member_no": "TSC-7002", "class": "7a"}, cookie=cookie, csrf=csrf)[0] == 400
        st, h3, t_login = call("POST", "/api/login", {"teacher_id": "TSC-7001", "pin": made["one_time_pin"]})
        assert st == 200 and t_login["must_change"]
        t_cookie, t_csrf = h3["Set-Cookie"].split(";")[0], t_login["csrf"]
        assert call("POST", "/api/pin", {"current": made["one_time_pin"], "new": "otieno-7A-pin"}, cookie=t_cookie, csrf=t_csrf)[0] == 200
        assert call("POST", "/api/privacy", {"agree": True}, cookie=t_cookie, csrf=t_csrf)[0] == 200
        assert call("GET", "/api/head/teachers", cookie=t_cookie)[0] == 403, "a class teacher is not the head teacher"
        assert call("POST", "/api/head/teachers/TSC-4471/remove", {}, cookie=t_cookie, csrf=t_csrf)[0] == 403
        assert call("GET", "/api/class", cookie=t_cookie)[2] == {"learners": []}, "a new class teacher sees only their own, empty class"
        assert call("POST", "/api/head/teachers/TSC-7001/remove", {}, cookie=cookie, csrf=csrf)[0] == 200
        assert call("GET", "/api/me", cookie=t_cookie)[0] == 401, "removing a teacher ends their sign-in"
    finally:
        srv.shutdown()


def test_a_head_teacher_with_no_class_can_sign_in_but_a_classless_teacher_cannot(empty):
    from hatua import portal
    srv = portal.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def login(tid, pin):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.request("POST", "/api/login", body=json.dumps({"teacher_id": tid, "pin": pin}),
                  headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read())
    try:
        make(stream="")
        assert login("TSC-4471", PIN)[0] == 200, "the head teacher manages accounts and needs no class"
        from hatua import school
        store.save("assignments", {})
        auth.register("TSC-7000", "Some Teacher", PIN)                     # an account with no class (made by the CLI, say)
        st, body = login("TSC-7000", PIN)
        assert st == 403 and "head teacher" in body["error"] and school.streams_of("TSC-7000") == []
    finally:
        srv.shutdown()


SCHOOL = """class, name, admission
6A, Wanjiku, 1042
6A, Kamau, 1043
Grade 6B\tAchieng\t1101
7a;Otieno
7A, Otieno
9C, Njeri, 1300
2A, TooYoung
no class here
8B, Bad<b>
"""


def test_the_head_teacher_adds_the_whole_school_at_once_and_then_gives_each_class_a_teacher(empty):
    from hatua import school
    make(stream="")
    head = auth.login("TSC-4471", PIN)["session"]
    out = onboard.import_school(head, SCHOOL)
    assert out["added"] == 5 and out["skipped"] == 1 and len(out["refused"]) == 3
    assert out["classes"] == {"6A": {"added": 2, "skipped": 0}, "6B": {"added": 1, "skipped": 0},
                              "7A": {"added": 1, "skipped": 1}, "9C": {"added": 1, "skipped": 0}}
    rows = store.load("learners")
    assert [r["learner_id"] for r in rows] == ["HT-0001", "HT-0002", "HT-0003", "HT-0004", "HT-0005"]
    assert {(r["stream"], r["current_grade"]) for r in rows} == {("6A", "6"), ("6B", "6"), ("7A", "7"), ("9C", "9")}
    again = onboard.import_school(head, "6A, Wanjiku, 1042")
    assert again["added"] == 0 and again["skipped"] == 1, "importing the same list twice adds nobody twice"
    waiting = {t["classes"][0]: t["learners"] for t in onboard.teachers("TSC-4471") if t["teacher_id"] is None}
    assert waiting == {"6A": 2, "6B": 1, "7A": 1, "9C": 1}, "every class with learners but no teacher is listed"
    onboard.add_teacher(head, "Mary Njeri", "TSC-6001", "6A")
    onboard.add_teacher(head, "Peter Otieno", "TSC-7001", "7A")
    assert [l["first_name"] for l in school.learners_of("TSC-6001")] == ["Wanjiku", "Kamau"]
    assert [l["first_name"] for l in school.learners_of("TSC-7001")] == ["Otieno"]
    assert school.learners_of("TSC-4471") == [], "the head teacher who teaches no class sees no learners"
    still = {t["classes"][0] for t in onboard.teachers("TSC-4471") if t["teacher_id"] is None}
    assert still == {"6B", "9C"}
    ev = [e for e in audit.read_events() if e["tool"] == "school.import"]
    assert ev[0]["output"]["imported_by"] == "Jane Wanjiku" and "Achieng" not in json.dumps(ev) and "Kamau" not in json.dumps(ev), "learners' names are not logged"
    mary = onboard.new_pin(head, "TSC-6001")
    limited = auth.login("TSC-6001", mary["one_time_pin"])["session"]
    auth.change_pin(limited, mary["one_time_pin"], "mary-6A-pin")
    with pytest.raises(GateBlocked, match="head teacher"):
        onboard.import_school(auth.login("TSC-6001", "mary-6A-pin")["session"], "6A, Sneaky")
    with pytest.raises(ValueError, match="Paste the learners"):
        onboard.import_school(head, "  \n")
    with pytest.raises(ValueError, match="at most 60 classes"):
        onboard.import_school(head, "\n".join(f"{g}{chr(65 + i)}{chr(65 + j)}, N{g}{i}{j}" for g in "456789" for i in range(5) for j in range(3)))
