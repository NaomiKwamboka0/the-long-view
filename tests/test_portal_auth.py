"""Checks for the two token kinds (ticket TP-1).

A human session may approve and save; an agent token may not. Every test here walks the
kind rule from the outside: mint, use, and assert the refusal, rather than inspecting the
session file's internals.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from hatua import auth, config, gate, store, summary
from hatua.summary import GateBlocked

PIN = '483920'
NAME = 'Mary Wambui'


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the store and the logs at a temporary folder."""
    for name, value in {'ROOT': tmp_path, 'STORE': tmp_path / 'store', 'LOGS': tmp_path / 'logs',
                        'AUDIT_LOG': tmp_path / 'logs' / 'audit.jsonl',
                        'APPROVALS_LOG': tmp_path / 'logs' / 'approvals.jsonl',
                        'PROFILES': tmp_path / 'profiles', 'DATA': tmp_path / 'data',
                        'INBOX': tmp_path / 'data' / 'inbox'}.items():
        monkeypatch.setattr(config, name, value)
    return tmp_path


@pytest.fixture
def learner(home):
    """One learner with a declining Mathematics record, so a real draft can be built."""
    store.save('learners', [{'learner_id': 'HT-0001', 'first_name': 'Example',
                             'current_grade': 9, 'stream': '9A'}])
    rows = []
    for i, points in enumerate([4, 4, 3, 2, 2]):
        rows.append({'record_id': f'R-{i:05d}', 'learner_id': 'HT-0001', 'family': 'Mathematics',
                     'ordinal': i, 'points': points, 'level': config.LEVELS[points - 1], 'flags': []})
    store.save('records', rows)
    return 'HT-0001'


def registered(teacher_id: str = 'mary') -> str:
    auth.register(teacher_id, NAME, PIN)
    return teacher_id


class Clock:
    """A hand-wound clock, so expiry can be tested without waiting."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch):
    wound = Clock()
    monkeypatch.setattr(auth, '_now', wound)
    return wound


def test_an_agent_token_cannot_approve(home, learner, monkeypatch):
    """The agent can never approve: only a human session may pass the gate."""
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    teacher_id = registered()
    draft = summary.draft(learner)
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)

    with pytest.raises(GateBlocked):
        gate.approve(draft['draft_id'], decision='approve', session=token)

    assert store.load('drafts')[0]['status'] == 'pending_teacher_review'


def test_an_agent_token_cannot_mint_another_token(home):
    """Only a human session can start an agent run; a token cannot extend its own life."""
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)

    with pytest.raises(GateBlocked, match='never approve'):
        auth.mint_agent_token(token)


def test_a_human_session_mints_an_agent_token_for_the_same_teacher(home):
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)

    who = auth.resolve(token, kind='agent')
    assert who == {'teacher_id': teacher_id, 'name': NAME, 'kind': 'agent'}


def test_sliding_expiry_extends_then_stops_at_the_absolute_maximum(home, clock):
    """A session that is used stays alive, but 8 hours after sign-in it is over."""
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    start = clock.now

    clock.advance(minutes=10)
    auth.resolve(session)
    clock.advance(minutes=10)  # 20 minutes in, past the original 15: the slide carried it
    auth.resolve(session)

    # Keep using it every 10 minutes: idle expiry never catches it, so only the absolute
    # limit can end it. The last request inside 8 hours must not extend past that limit.
    while clock.now < start + timedelta(hours=7, minutes=50):
        clock.advance(minutes=10)
        auth.resolve(session)
    record = next(iter(json.loads((config.STORE / 'sessions.json').read_text(encoding='utf-8')).values()))
    assert datetime.fromisoformat(record['expires']) == datetime.fromisoformat(record['absolute'])

    clock.advance(minutes=11)  # 8h01m: over, however often it was used
    with pytest.raises(GateBlocked, match='expired'):
        auth.resolve(session)


def test_logout_ends_the_session_and_its_agent_tokens(home, learner, monkeypatch):
    """Signing out is the off switch for a run that was started from that session."""
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)
    draft = summary.draft(learner)

    assert auth.logout(session) is True

    with pytest.raises(GateBlocked):
        auth.resolve(session)
    with pytest.raises(GateBlocked):
        auth.resolve(token, kind='agent')
    with pytest.raises(GateBlocked):
        gate.approve(draft['draft_id'], decision='approve', session=token)


def test_an_agent_token_cannot_save_a_profile(home, learner, monkeypatch):
    """Saving is a human act too, even for a draft a teacher already approved."""
    teacher_id = registered()
    draft = summary.draft(learner)
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)
    gate.approve(draft['draft_id'], decision='approve', session=session)

    with pytest.raises(GateBlocked):
        gate.update_profile(draft['draft_id'], session=token)


def test_no_pin_session_or_agent_token_reaches_the_audit_log(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    teacher_id = registered()
    draft = summary.draft(learner)
    session = auth.login(teacher_id, PIN)['session']
    token = auth.mint_agent_token(session)

    with pytest.raises(GateBlocked):
        gate.approve(draft['draft_id'], decision='approve', session=token)
    gate.approve(draft['draft_id'], decision='approve', session=session)

    raw = config.AUDIT_LOG.read_text(encoding='utf-8')
    assert PIN not in raw
    assert session not in raw
    assert token not in raw


def test_a_session_file_written_before_kinds_still_works(home):
    """Upgrading must not sign anyone out: a record without a kind is a human session."""
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    path = config.STORE / 'sessions.json'
    sessions = json.loads(path.read_text(encoding='utf-8'))
    for record in sessions.values():
        record.pop('kind', None)
        record.pop('absolute', None)
        record.pop('csrf', None)
    path.write_text(json.dumps(sessions), encoding='utf-8')

    who = auth.resolve(session)
    assert who == {'teacher_id': teacher_id, 'name': NAME, 'kind': 'human'}
