"""Scope checks for TP-2: teacher assignments and the one visibility rule."""
from pathlib import Path

import pytest

from hatua import config, scope, store

REPO = Path(__file__).resolve().parent.parent

CLASS_LIST = [
    {'learner_id': 'HT-0001', 'first_name': 'Achieng', 'stream': '9A', 'current_grade': 9},
    {'learner_id': 'HT-0002', 'first_name': 'Brian', 'stream': '9A', 'current_grade': 9},
    {'learner_id': 'HT-0003', 'first_name': 'Cynthia', 'stream': '9B', 'current_grade': 9},
    {'learner_id': 'HT-0004', 'first_name': 'Dennis', 'stream': '9B', 'current_grade': 9},
]

ASSIGNMENTS = ('teacher_id,role,streams,subjects\n'
               'T-9A,class_teacher,9A,\n'
               'T-9B,class_teacher,9B,\n')


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the store and the logs at a temporary folder."""
    for name, value in {'ROOT': tmp_path, 'STORE': tmp_path / 'store', 'LOGS': tmp_path / 'logs',
                        'AUDIT_LOG': tmp_path / 'logs' / 'audit.jsonl',
                        'APPROVALS_LOG': tmp_path / 'logs' / 'approvals.jsonl',
                        'PROFILES': tmp_path / 'profiles', 'DATA': tmp_path / 'data',
                        'RAW': tmp_path / 'data' / 'raw',
                        'INBOX': tmp_path / 'data' / 'inbox'}.items():
        monkeypatch.setattr(config, name, value)
    return tmp_path


def write_assignments(text):
    config.RAW.mkdir(parents=True, exist_ok=True)
    path = config.RAW / 'teacher_assignments.csv'
    path.write_text(text, encoding='utf-8')
    return path


@pytest.fixture
def loaded(home):
    """One Grade 9 class in two streams, with the T-9A and T-9B assignments loaded."""
    store.save('learners', CLASS_LIST)
    store.load_assignments(write_assignments(ASSIGNMENTS))
    return home


def test_each_class_teacher_sees_only_their_own_stream(loaded):
    assert scope.visible_learner_ids('T-9A') == {'HT-0001', 'HT-0002'}
    assert scope.visible_learner_ids('T-9B') == {'HT-0003', 'HT-0004'}
    assert store.load('assignments')['T-9A'] == {
        'role': 'class_teacher', 'streams': ['9A'], 'subjects': []}


def test_a_teacher_assigned_to_two_streams_sees_both(home):
    """The assignment carries a list of streams, and every one of them counts."""
    store.save('learners', CLASS_LIST)
    store.load_assignments(write_assignments('teacher_id,role,streams,subjects\n'
                                             'T-9AB,class_teacher,9A;9B,\n'))

    assert scope.visible_learner_ids('T-9AB') == {'HT-0001', 'HT-0002', 'HT-0003', 'HT-0004'}


def test_together_the_two_class_teachers_cover_the_class_list(loaded):
    nine_a = scope.visible_learner_ids('T-9A')
    nine_b = scope.visible_learner_ids('T-9B')
    classroom = {learner['learner_id'] for learner in store.load('learners')}
    assert nine_a | nine_b == classroom


def test_a_learner_with_records_but_no_class_list_row_is_not_viewable(loaded):
    """Records mentioning a learner do not put them in anyone's class."""
    store.save('records', [{'record_id': 'R-99999', 'learner_id': 'HT-0099', 'family': 'Mathematics',
                            'ordinal': 0, 'points': 3, 'level': 'ME', 'flags': []}])

    assert scope.can_view('T-9A', 'HT-0099') is False
    assert 'HT-0099' not in scope.visible_learner_ids('T-9A')


def test_unknown_teacher_sees_nothing(loaded):
    assert scope.visible_learner_ids('T-UNKNOWN') == set()
    assert scope.can_view('T-UNKNOWN', 'HT-0001') is False


def test_learner_outside_the_loaded_class_list_is_never_viewable(loaded):
    assert scope.can_view('T-9A', 'HT-0001') is True
    assert scope.can_view('T-9A', 'HT-0003') is False
    assert scope.can_view('T-9A', 'HT-0099') is False
    assert scope.can_view('T-9A', 'HT-9999') is False


@pytest.mark.parametrize('row,message', [
    ('T-9C,admin,9A,', 'class_teacher'),
    ('T-9C,class_teacher,,', 'streams'),
    (',class_teacher,9A,', 'teacher_id'),
    ('T 9C,class_teacher,9A,', 'valid teacher ID'),
])
def test_malformed_assignment_row_is_rejected(home, row, message):
    path = write_assignments('teacher_id,role,streams,subjects\n' + row + '\n')
    with pytest.raises(ValueError, match=f'row 2.*{message}'):
        store.load_assignments(path)
    assert store.load('assignments') == {}


def test_a_second_row_for_the_same_teacher_is_rejected(home):
    """Two rows and no way to choose between them is ambiguous data, not a last-wins."""
    path = write_assignments('teacher_id,role,streams,subjects\n'
                             'T-9A,class_teacher,9A,\nT-9A,class_teacher,9B,\n')

    with pytest.raises(ValueError, match='row 3.*already has a row'):
        store.load_assignments(path)


def test_the_committed_assignment_file_names_one_teacher_per_stream(home):
    """Guards the data file itself against a silent edit: T-9A sees 9A, T-9B sees 9B."""
    store.load_assignments(REPO / 'data' / 'raw' / 'teacher_assignments.csv')

    assert store.load('assignments') == {
        'T-9A': {'role': 'class_teacher', 'streams': ['9A'], 'subjects': []},
        'T-9B': {'role': 'class_teacher', 'streams': ['9B'], 'subjects': []},
    }


def test_teacher_without_a_row_sees_nothing(loaded):
    assert scope.visible_learner_ids('T-9C') == set()
    assert scope.can_view('T-9C', 'HT-0001') is False
