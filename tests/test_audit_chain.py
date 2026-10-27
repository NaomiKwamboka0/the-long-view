"""Checks the tamper-evident log chain (ticket T7)."""
import hashlib
import json

import pytest

from hatua import audit, cli, config, gate, store, summary

EVENTS = [{"tool": "one"}, {"tool": "two"}, {"tool": "three"}]


@pytest.fixture
def logs(tmp_path, monkeypatch):
    for name, value in {'ROOT': tmp_path, 'LOGS': tmp_path / 'logs', 'STORE': tmp_path / 'store',
                        'PROFILES': tmp_path / 'profiles',
                        'AUDIT_LOG': tmp_path / 'logs' / 'audit.jsonl',
                        'APPROVALS_LOG': tmp_path / 'logs' / 'approvals.jsonl'}.items():
        monkeypatch.setattr(config, name, value)
    return tmp_path / 'logs'


def write_log(count: int = 3):
    for event in EVENTS[:count]:
        audit.write_event(dict(event))
    return config.AUDIT_LOG


def lines() -> list[str]:
    return config.AUDIT_LOG.read_text(encoding='utf-8').splitlines()


def rewrite(text_lines: list[str]) -> None:
    config.AUDIT_LOG.write_text("\n".join(text_lines) + "\n", encoding='utf-8')


def test_an_untouched_log_verifies_and_reports_its_tip(logs):
    path = write_log()
    result = audit.verify_jsonl(path)
    assert result["ok"] is True and result["chained"] is True
    assert result["lines"] == 3
    assert result["tip"] == hashlib.sha256(lines()[-1].encode()).hexdigest()


def test_the_first_line_links_to_the_genesis_hash(logs):
    write_log()
    first = json.loads(lines()[0])
    assert first["prev"] == audit.GENESIS


def test_an_edited_line_is_detected(logs):
    write_log()
    parts = lines()
    event = json.loads(parts[1])
    event["tool"] = "something else"
    parts[1] = json.dumps(event)
    rewrite(parts)
    result = audit.verify_jsonl(config.AUDIT_LOG)
    assert result["ok"] is False
    assert "edited, deleted or reordered" in result["message"]


def test_a_deleted_line_is_detected(logs):
    write_log()
    rewrite([lines()[0], lines()[2]])
    assert audit.verify_jsonl(config.AUDIT_LOG)["ok"] is False


def test_a_reordered_line_is_detected(logs):
    write_log()
    parts = lines()
    rewrite([parts[0], parts[2], parts[1]])
    assert audit.verify_jsonl(config.AUDIT_LOG)["ok"] is False


def test_a_legacy_log_is_unchained_not_broken(logs):
    config.LOGS.mkdir(parents=True, exist_ok=True)
    config.AUDIT_LOG.write_text('{"tool": "old", "ok": true}\n{"tool": "older"}\n', encoding='utf-8')
    result = audit.verify_jsonl(config.AUDIT_LOG)
    assert result["ok"] is True
    assert result["chained"] is False
    assert "not chained" in result["message"]


def test_a_line_that_is_not_json_is_reported_as_broken(logs):
    write_log()
    parts = lines()
    parts[1] = "{not json"
    rewrite(parts)
    result = audit.verify_jsonl(config.AUDIT_LOG)
    assert result["ok"] is False and result["line"] == 2


def test_an_empty_log_verifies(logs):
    result = audit.verify_jsonl(config.AUDIT_LOG)
    assert result["ok"] is True and result["lines"] == 0


def test_approval_ids_cannot_collide_between_approvers(logs, monkeypatch):
    """Two approvals recorded at the same second still get different ids."""
    store.save('learners', [{'learner_id': 'HT-0001', 'first_name': 'One', 'current_grade': 9, 'stream': '9A'},
                            {'learner_id': 'HT-0002', 'first_name': 'Two', 'current_grade': 9, 'stream': '9A'}])
    store.save('records', [{'record_id': f'R-{lid[-1]}{i:03d}', 'learner_id': lid, 'family': 'Mathematics',
                            'ordinal': i, 'points': p, 'level': config.LEVELS[p - 1], 'flags': []}
                           for lid in ('HT-0001', 'HT-0002')
                           for i, p in enumerate([4, 4, 3, 2, 2])])
    monkeypatch.setattr(gate, '_now', lambda: '2026-10-27T10:00:00+00:00')

    first = gate.approve(summary.draft('HT-0001')['draft_id'], 'Teacher One')
    second = gate.approve(summary.draft('HT-0002')['draft_id'], 'Teacher Two')
    assert first["approval_id"] != second["approval_id"]
    assert first["approval_id"].startswith("AP-")
    entries = [json.loads(line) for line in config.APPROVALS_LOG.read_text(encoding='utf-8').splitlines()]
    assert entries[0]["prev"] == audit.GENESIS
    assert entries[1]["prev"] == hashlib.sha256(
        config.APPROVALS_LOG.read_text(encoding='utf-8').splitlines()[0].encode()).hexdigest()


def test_verify_log_command_exit_codes(logs, capsys):
    write_log()
    assert cli.main(['verify-log']) == 0
    output = capsys.readouterr().out
    assert "OK" in output and "chain intact" in output

    parts = lines()
    parts[1] = json.dumps({**json.loads(parts[1]), "tool": "tampered"})
    rewrite(parts)
    assert cli.main(['verify-log']) == 1
    assert "BROKEN" in capsys.readouterr().out
