"""Checks for the audit redaction, optional sign-in and the export mapper (tickets A1-A3)."""
import json

import pytest

from hatua import audit, config, store


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


def log_lines() -> list[dict]:
    text = config.AUDIT_LOG.read_text(encoding='utf-8')
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------- A1: no secrets in the log
def test_scrub_redacts_secret_named_arguments():
    scrubbed = audit.scrub({'pin': '483920', 'Session': 'tok_abc', 'learner_id': 'HT-0001'})
    assert scrubbed['pin'] == audit.REDACTED
    assert scrubbed['Session'] == audit.REDACTED
    assert scrubbed['learner_id'] == 'HT-0001'


def test_audit_log_never_contains_a_secret(home):
    pin, session = '771234', 'sess_token_value_do_not_log'

    @audit.audited('example_tool')
    def example_tool(learner_id: str, *, pin: str = '', session: str = '') -> dict:
        return {'ok': True}

    example_tool('HT-0001', pin=pin, session=session)

    raw = config.AUDIT_LOG.read_text(encoding='utf-8')
    assert pin not in raw
    assert session not in raw
    assert audit.REDACTED in raw
    logged = log_lines()[0]
    assert logged['inputs']['kwargs']['pin'] == audit.REDACTED
    assert logged['inputs']['kwargs']['session'] == audit.REDACTED
    assert logged['inputs']['args'] == ['HT-0001']


def test_store_reset_keeps_the_private_store_files(home):
    """setup/store.reset must not wipe sign-in credentials, sessions or lockout state."""
    config.STORE.mkdir(parents=True, exist_ok=True)
    for name in ('teachers', 'sessions', 'auth_state'):
        (config.STORE / f'{name}.json').write_text('{}', encoding='utf-8')
    store.save('learners', [])
    store.reset()
    assert not (config.STORE / 'learners.json').exists()
    for name in ('teachers', 'sessions', 'auth_state'):
        assert (config.STORE / f'{name}.json').exists()
