"""Adversarial checks for the draft guard (ticket T1).

Two directions matter: phrases that should never reach a teacher must be blocked, and
the sentences our own templates write must never be blocked.
"""
import runpy
import shutil
from pathlib import Path

import pytest

from hatua import cli, config, gate, guard, store, summary

REPO = Path(__file__).resolve().parent.parent

# Every phrase named in the ticket as one that used to pass, plus the older favourites.
FORBIDDEN_PHRASES = [
    "STEM-pathway candidate",
    "stem  pathway",
    "would do well in the sciences track",
    "excellent fit for engineering",
    "should consider medicine",
    "outperforms the rest of the class",
    "among the top performers",
    "a natural leader",
    "top 5 in the class",
    "rest of the class",
    "gifted and talented",
    "she is a slow learner",
    "better than her classmates",
    "weaker than the others in class",
    "he is a natural genius",
    "should take the arts track",
    "kuliko wenzake",
    "kuliko wanafunzi wengine",
    "kipanga",
    "mwerevu",
]

LEGITIMATE = [
    "Mathematics stayed at Meeting Expectations for 4 terms [R-00001].",
    "Results rose from Meeting Expectations to Exceeding Expectations [R-00002].",
    "Attendance was under 75% for 3 terms in a row [A-HT-0001-G8T2].",
    "The teacher noted steady effort in class [N-00001].",
    "Creative Arts held at Exceeding Expectations from Grade 5 [R-00003].",
    "Results fell from Approaching Expectations to Below Expectations [R-00001].",
    "There is no record for Grade 7 Term 2 [R-00002].",
    "Kiswahili improved across a missing term [R-00003].",
    "The learner joined in Grade 7, so earlier years are not in Hatua [R-00001].",
    "Please check the late-logged records before relying on this [N-00001].",
    "Mathematics: 6 recorded terms, Grade 8 Term 1 to Grade 9 Term 3 [R-00002].",
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    for name, value in {'ROOT': tmp_path, 'DATA': tmp_path / 'data', 'STORE': tmp_path / 'store',
                        'PROFILES': tmp_path / 'profiles', 'LOGS': tmp_path / 'logs',
                        'AUDIT_LOG': tmp_path / 'logs' / 'audit.jsonl',
                        'APPROVALS_LOG': tmp_path / 'logs' / 'approvals.jsonl'}.items():
        monkeypatch.setattr(config, name, value)
    store.save('learners', [{'learner_id': 'HT-0001', 'first_name': 'Achieng',
                             'current_grade': 9, 'stream': '9A'}])
    store.save('records', [{'record_id': 'R-00001', 'learner_id': 'HT-0001', 'family': 'Mathematics',
                            'ordinal': 0, 'points': 3, 'level': 'ME', 'flags': []},
                           {'record_id': 'R-00002', 'learner_id': 'HT-0001', 'family': 'Mathematics',
                            'ordinal': 1, 'points': 2, 'level': 'AE', 'flags': []},
                           {'record_id': 'R-00003', 'learner_id': 'HT-0001', 'family': 'Creative Arts',
                            'ordinal': 2, 'points': 4, 'level': 'EE', 'flags': []}])
    store.save('attendance', [{'attendance_id': 'A-HT-0001-G8T2', 'learner_id': 'HT-0001',
                               'ordinal': 1, 'grade': 8, 'term': 2, 'rate': 0.5,
                               'days_present': 30, 'days_open': 60}])
    store.save('notes', [{'note_id': 'N-00001', 'learner_id': 'HT-0001', 'text': 'Steady effort.'}])
    return tmp_path


@pytest.mark.parametrize('phrase', FORBIDDEN_PHRASES)
def test_every_known_label_or_pathway_phrase_is_blocked(phrase):
    assert guard.labels_in(phrase), f"not blocked: {phrase}"
    assert guard.check(f"- {phrase} [R-00001]", 'HT-0001'), f"check() let through: {phrase}"


@pytest.mark.parametrize('sentence', LEGITIMATE)
def test_legitimate_sentences_are_not_blocked(home, sentence):
    assert guard.labels_in(sentence) == [], f"false positive: {sentence}"
    assert guard.check(sentence, 'HT-0001') == [], f"check() blocked: {sentence}"


def test_an_uncited_sentence_is_blocked_with_or_without_a_bullet(home):
    plain = "Mathematics is going well.\n"
    bullet = "- Mathematics is going well.\n"
    assert guard.check(plain, 'HT-0001')
    assert guard.check(bullet, 'HT-0001')
    assert "Claim has no citation" in guard.check(plain, 'HT-0001')[0]


def test_a_cited_sentence_then_an_uncited_one_is_blocked(home):
    text = "- Mathematics fell over six terms [R-00001]. The teacher is pleased.\n"
    assert any('teacher is pleased' in p for p in guard.check(text, 'HT-0001'))


def test_leading_spaces_and_double_spaces_do_not_help(home):
    assert guard.check("   - should   take   the   stem   pathway [R-00001]", 'HT-0001')
    assert guard.check("- STEM_pathway candidate [R-00001]", 'HT-0001')


# ---------------------------------------------------------------- the templates must pass
@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    """A fresh synthetic class, built in a temporary home exactly as `demo` does."""
    parts = {'ROOT': '', 'DATA': 'data', 'RAW': 'data/raw', 'INBOX': 'data/inbox',
             'STORE': 'store', 'PROFILES': 'profiles', 'LOGS': 'logs', 'UI': 'ui'}
    for name, part in parts.items():
        monkeypatch.setattr(config, name, tmp_path / part if part else tmp_path)
    monkeypatch.setattr(config, 'AUDIT_LOG', tmp_path / 'logs' / 'audit.jsonl')
    monkeypatch.setattr(config, 'APPROVALS_LOG', tmp_path / 'logs' / 'approvals.jsonl')
    (tmp_path / 'scripts').mkdir()
    shutil.copy2(REPO / 'scripts' / 'make_dummy_data.py', tmp_path / 'scripts')
    runpy.run_path(str(tmp_path / 'scripts' / 'make_dummy_data.py'), run_name='__main__')
    cli.main(['setup'])
    return tmp_path


def test_no_learner_draft_in_any_language_or_audience_is_blocked(synthetic):
    problems, checked = [], 0
    for learner in store.load('learners'):
        lid = learner['learner_id']
        teacher = summary.draft(lid, 'teacher', 'en')
        problems += guard.check(teacher['text'], lid)
        checked += 1
        gate.approve(teacher['draft_id'], 'Test Teacher')
        for language in ('en', 'sw'):
            guardian = summary.draft(lid, 'guardian', language)
            problems += guard.check(guardian['text'], lid)
            checked += 1
    assert checked == 120, f"expected 40 learners x 3 drafts, got {checked}"
    assert problems == [], f"{len(problems)} problem(s), first: {problems[:3]}"


# ---------------------------------------------------------------- teacher edits
def test_a_teacher_edit_without_a_citation_is_blocked(home):
    """The guard runs on teacher edits too, so an uncited addition cannot be saved."""
    draft = summary.draft('HT-0001')
    with pytest.raises(summary.GateBlocked, match='no citation'):
        gate.approve(draft['draft_id'], 'Test Teacher',
                     edited_text=draft['text'] + '\nThe learner is doing well.')


def test_a_teacher_edit_with_a_citation_is_accepted(home):
    draft = summary.draft('HT-0001')
    entry = gate.approve(draft['draft_id'], 'Test Teacher',
                         edited_text=draft['text'] + '\nParent meeting agreed [R-00001].')
    assert entry['decision'] == 'approve'


# ---------------------------------------------------------------- the optional rewrite
def test_a_rewrite_that_adds_a_line_is_discarded(home, monkeypatch):
    monkeypatch.setattr(summary.llm, 'polish', lambda text, language='en': text + "\n- Extra claim.\n")
    draft = summary.draft('HT-0001')
    assert draft['writer'] == 'template'


def test_a_rewrite_that_moves_a_citation_is_discarded(home, monkeypatch):
    def mover(text, language='en'):
        lines = text.splitlines()
        lines.append('[R-00001]')
        return "\n".join(lines)

    monkeypatch.setattr(summary.llm, 'polish', mover)
    draft = summary.draft('HT-0001')
    assert draft['writer'] == 'template'


def test_a_faithful_rewrite_is_kept(home, monkeypatch):
    def reword(text, language='en'):
        return text.replace('Hatua draft for the class teacher: ',
                            'Hatua draft for the class teacher: learner ')

    monkeypatch.setattr(summary.llm, 'polish', reword)
    monkeypatch.setattr(summary.llm, 'model_name', lambda: 'ollama:stub')
    draft = summary.draft('HT-0001')
    assert draft['writer'] == 'ollama:stub'
    assert 'learner Achieng' in draft['text']
