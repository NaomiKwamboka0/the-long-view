"""Regression checks for teacher-review boundaries and local data handling."""
import argparse
import json
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError

import pytest
from hatua import cli, config, gate, guard, patterns, store, summary
from hatua.local_model import local_host, open_local


@pytest.mark.parametrize('url', [
    'https://127.0.0.1:11434', 'http://localhost.attacker.example',
    'http://127.0.0.1.attacker.example', 'http://localhost@attacker.example',
    'http://localhost:11434@attacker.example', 'http://127.0.0.10:11434',
    'http://localhost/path', 'http://localhost?next=remote', 'http://localhost#remote',
    'http://[::1]:bad', 'http://192.168.1.2:11434', 'http://localhost:0',
])
def test_remote_or_ambiguous_model_endpoint_rejected(url):
    assert local_host(url) is None


@pytest.mark.parametrize('url,expected', [
    ('http://localhost:11434/', 'http://127.0.0.1:11434'),
    ('http://127.0.0.1:12345', 'http://127.0.0.1:12345'),
    ('http://[::1]:11434', 'http://[::1]:11434'),
])
def test_literal_loopback_endpoints(url, expected):
    assert local_host(url) == expected


def test_model_requests_do_not_follow_redirects(monkeypatch):
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/redirected')
            self.end_headers()
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    try:
        with pytest.raises(HTTPError):
            open_local(f'http://127.0.0.1:{server.server_port}/original', timeout=2)
        assert hits == ['/original']
    finally:
        server.shutdown(); thread.join(); server.server_close()


def rows(levels, conflict=None):
    return [dict(record_id=f'R-{i:05}', learner_id='HT-0001', family='Mathematics',
                 ordinal=i, points=p, flags=['score_level_conflict'] if i==conflict else [])
            for i,p in enumerate(levels)]


def test_conflict_breaks_runs_and_cannot_anchor_trend():
    series = patterns.term_series(rows([4,4,4,4,4,4], conflict=3))['Mathematics']
    assert [len(x) for x in patterns._runs(series, lambda t:t['points']>=3.5)] == [3,2]
    trimmed = patterns._trend(patterns.term_series(rows([4,4,3,2,2], conflict=0))['Mathematics'])
    assert trimmed[0] == 'decline' and trimmed[1][0]['ordinal'] == 1
    assert patterns._trend(patterns.term_series(rows([4,4,3,2,2], conflict=4))['Mathematics']) is None


def test_clean_trend_is_preserved():
    assert patterns._trend(patterns.term_series(rows([4,4,3,2,2]))['Mathematics'])[0] == 'decline'


def test_empty_approval_text_is_blocked():
    assert guard.check(' \n ', 'HT-0001')


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    for name, value in {'ROOT':tmp_path, 'STORE':tmp_path/'store', 'PROFILES':tmp_path/'profiles',
                        'LOGS':tmp_path/'logs', 'AUDIT_LOG':tmp_path/'logs/audit.jsonl',
                        'APPROVALS_LOG':tmp_path/'logs/approvals.jsonl'}.items():
        monkeypatch.setattr(config, name, value)
    store.save('learners', [dict(learner_id='HT-0001', first_name='Example', current_grade=9, stream='9A')])
    r = rows([4,4,3,2,2])
    for row in r: row.update(level=config.LEVELS[row['points']-1])
    store.save('records', r)
    return tmp_path


def test_family_message_cannot_restore_edited_teacher_text(local_store):
    draft = summary.draft('HT-0001')
    # The guard now requires a citation on every sentence a teacher adds, so the note
    # carries one. What this test checks is unchanged: an edited teacher draft locks the
    # template family message.
    gate.approve(draft['draft_id'], 'Test Teacher', edited_text=draft['text']+'\nTeacher review note [R-00000].')
    with pytest.raises(summary.GateBlocked, match='edited'):
        summary.draft('HT-0001', 'guardian')


def test_changed_patterns_require_new_teacher_review(local_store):
    draft = summary.draft('HT-0001')
    gate.approve(draft['draft_id'], 'Test Teacher')
    store.save('records', rows([3,3,3,3,3]))
    with pytest.raises(summary.GateBlocked, match='patterns changed'):
        summary.draft('HT-0001', 'guardian')


def test_import_rejects_missing_hash_and_guardian_share(local_store, capsys):
    draft = summary.draft('HT-0001')
    file = local_store/'approval.json'
    file.write_text(json.dumps([{'draft_id':draft['draft_id'], 'audience':'teacher',
                                'decision':'approve', 'teacher':'Test Teacher'}]))
    cli.cmd_import(argparse.Namespace(file=str(file)))
    assert store.load('drafts')[0]['status'] == 'pending_teacher_review'
    assert 'NOT applied' in capsys.readouterr().out


def test_import_good_approval_saves_only_matching_text(local_store):
    draft = summary.draft('HT-0001')
    file = local_store/'approval.json'
    file.write_text(json.dumps([{'draft_id':draft['draft_id'], 'audience':'teacher',
        'decision':'approve', 'teacher':'Test Teacher', 'hash':draft['hash']}]))
    cli.cmd_import(argparse.Namespace(file=str(file)))
    profile = json.loads((config.PROFILES/'HT-0001.json').read_text())
    assert profile['entries'][0]['text'] == draft['text']
