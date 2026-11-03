"""Scope checks for TP-2: teacher assignments and the one visibility rule."""
import pytest

from hatua import config, scope, store

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


def test_stream_sets_are_disjoint_and_cover_the_whole_class_list(loaded):
    nine_a = scope.visible_learner_ids('T-9A')
    nine_b = scope.visible_learner_ids('T-9B')
    classroom = {learner['learner_id'] for learner in store.load('learners')}
    assert nine_a.isdisjoint(nine_b)
    assert nine_a | nine_b == classroom


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
])
def test_malformed_assignment_row_is_rejected(home, row, message):
    path = write_assignments('teacher_id,role,streams,subjects\n' + row + '\n')
    with pytest.raises(ValueError, match=f'row 2.*{message}'):
        store.load_assignments(path)
    assert store.load('assignments') == {}


def test_teacher_without_a_row_sees_nothing(loaded):
    assert scope.visible_learner_ids('T-9C') == set()
    assert scope.can_view('T-9C', 'HT-0001') is False
