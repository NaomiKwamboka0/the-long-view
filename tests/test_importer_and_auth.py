"""Checks for the audit redaction, optional sign-in and the export mapper (tickets A1-A3)."""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hatua import audit, auth, cli, config, gate, importer, store, summary
from hatua.summary import GateBlocked

REPO = Path(__file__).resolve().parent.parent


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


def example_rows(levels):
    return [dict(record_id=f'R-{i:05d}', learner_id='HT-0001', family='Mathematics',
                 ordinal=i, points=p, flags=[]) for i, p in enumerate(levels)]


@pytest.fixture
def learner(home):
    """One learner with a declining Mathematics record, so a real draft can be built."""
    store.save('learners', [dict(learner_id='HT-0001', first_name='Example', current_grade=9, stream='9A')])
    rows = example_rows([4, 4, 3, 2, 2])
    for row in rows:
        row.update(level=config.LEVELS[row['points'] - 1])
    store.save('records', rows)
    return 'HT-0001'


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


# ---------------------------------------------------------------- A2: sign-in
PIN = '483920'
NAME = 'Mary Wambui'


def registered(teacher_id='mary'):
    auth.register(teacher_id, NAME, PIN)
    return teacher_id


def test_registry_stores_the_name_but_never_the_pin(home):
    registered()
    raw = (config.STORE / 'teachers.json').read_text(encoding='utf-8')
    assert NAME in raw
    assert PIN not in raw
    assert auth.teachers() == [{'teacher_id': 'mary', 'name': NAME}]


def test_five_wrong_pins_lock_the_id_even_for_the_right_pin(home):
    teacher_id = registered()
    for _ in range(5):
        with pytest.raises(GateBlocked):
            auth.login(teacher_id, '000000')
    with pytest.raises(GateBlocked, match='locked'):
        auth.login(teacher_id, PIN)


def test_unknown_id_fails_with_the_same_message_as_a_wrong_pin(home):
    teacher_id = registered()
    with pytest.raises(GateBlocked) as wrong_pin:
        auth.login(teacher_id, '000000')
    with pytest.raises(GateBlocked) as unknown:
        auth.login('nobody', PIN)
    assert str(wrong_pin.value) == str(unknown.value)
    assert 'Sign-in failed' in str(unknown.value)


def test_sign_in_required_blocks_a_typed_name(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    registered()
    draft = summary.draft(learner)
    with pytest.raises(GateBlocked, match='Sign-in required'):
        gate.approve(draft['draft_id'], 'Typed Name Here')


def test_signed_in_approval_uses_the_registry_name(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    teacher_id = registered()
    draft = summary.draft(learner)
    session = auth.login(teacher_id, PIN)['session']
    entry = gate.approve(draft['draft_id'], 'Typed Name Here', session=session)
    assert entry['teacher'] == NAME
    assert entry['teacher_id'] == teacher_id
    assert entry['authenticated'] is True
    assert 'Typed Name Here' not in json.dumps(entry)


def test_approval_made_without_sign_in_cannot_be_saved_once_sign_in_is_on(home, learner, monkeypatch):
    monkeypatch.delenv('HATUA_REQUIRE_AUTH', raising=False)
    registered()
    draft = summary.draft(learner)
    gate.approve(draft['draft_id'], 'Test Teacher')
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    with pytest.raises(GateBlocked, match='not made by a signed-in teacher'):
        gate.update_profile(draft['draft_id'])


def test_expired_session_is_refused(home, learner, monkeypatch):
    teacher_id = registered()
    session = auth.login(teacher_id, PIN)['session']
    later = datetime.now(timezone.utc) + timedelta(minutes=auth.SESSION_MINUTES + 1)
    monkeypatch.setattr(auth, '_now', lambda: later)
    with pytest.raises(GateBlocked, match='expired'):
        auth.resolve(session)


def test_signed_in_approval_leaves_no_pin_or_token_in_the_audit_log(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    teacher_id = registered()
    draft = summary.draft(learner)
    session = auth.login(teacher_id, PIN)['session']
    gate.approve(draft['draft_id'], decision='approve', session=session)

    raw = config.AUDIT_LOG.read_text(encoding='utf-8')
    assert PIN not in raw
    assert session not in raw
    assert audit.REDACTED in raw
    approve_events = [e for e in log_lines() if e.get('tool') == 'approve']
    assert approve_events and approve_events[0]['inputs']['kwargs']['session'] == audit.REDACTED


# ---------------------------------------------------------------- A2: command line
def stub_pin(monkeypatch, *answers):
    prompt = iter(answers)
    monkeypatch.setattr('getpass.getpass', lambda text='': next(prompt))


def approvals() -> list[dict]:
    return [json.loads(line) for line in config.APPROVALS_LOG.read_text(encoding='utf-8').splitlines()]


def test_cli_registers_a_teacher_and_approves_with_a_session(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    stub_pin(monkeypatch, PIN, PIN)
    assert cli.main(['teacher-add', '--id', 'mary', '--name', NAME]) == 0

    draft = summary.draft(learner)
    stub_pin(monkeypatch, PIN)
    assert cli.main(['approve', draft['draft_id'], '--teacher-id', 'mary']) == 0

    entry = approvals()[0]
    assert entry['teacher'] == NAME
    assert entry['teacher_id'] == 'mary'
    assert entry['authenticated'] is True


def test_cli_returns_2_when_sign_in_is_required(home, learner, monkeypatch):
    monkeypatch.setenv('HATUA_REQUIRE_AUTH', '1')
    registered()
    draft = summary.draft(learner)
    assert cli.main(['approve', draft['draft_id'], '--teacher', 'Typed Name Here']) == 2


def test_cli_returns_1_for_a_bad_teacher_id(home, monkeypatch):
    stub_pin(monkeypatch, PIN, PIN)
    assert cli.main(['teacher-add', '--id', 'x', '--name', NAME]) == 1


# ---------------------------------------------------------------- A3: mapping a school sheet
SCHOOL_HEADINGS = ['Adm No', 'Full Name', 'Class', 'Year', 'Term', 'Learning Area', 'Assessment',
                   'Rubric Level', 'Marks %', 'Date Done', 'Date Entered', 'Teacher No', 'Parent Phone']
MAPPING = {
    'columns': {'Adm No': 'learner_id', 'Class': 'grade', 'Year': 'year', 'Term': 'term',
                'Learning Area': 'learning_area', 'Assessment': 'task', 'Rubric Level': 'level',
                'Marks %': 'score', 'Date Done': 'task_date', 'Date Entered': 'logged_date',
                'Teacher No': 'teacher'},
    'constants': {'source': 'school_sheet'},
}


def school_sheet(path, rows=None):
    rows = rows or [
        ['HT-0001', 'Achieng O', 'Grade 7', '2026', 'Term 2', 'Mathematics', 'Algebra check',
         'ME', '68', '2026-06-12', '2026-06-19', 'T-004', '0712 000 000'],
        ['HT-0001', 'Achieng O', 'Grade 7', '2026', 'Term 2', 'Mathematics', 'Fractions',
         'EE', '82', '2026-07-02', '2026-07-09', 'T-004', '0712 000 000'],
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(SCHOOL_HEADINGS)
        writer.writerows(rows)
    return path


def write_mapping(path, mapping=None):
    path.write_text(json.dumps(mapping or MAPPING), encoding='utf-8')
    return path


@pytest.fixture
def sheet(home, tmp_path):
    config.INBOX.mkdir(parents=True, exist_ok=True)
    return school_sheet(tmp_path / 'school.csv')


def test_only_mapped_columns_are_copied_and_drops_are_reported(home, tmp_path, sheet):
    report = importer.map_export(sheet, write_mapping(tmp_path / 'mapping.json'), 'july.csv')
    raw = (config.INBOX / 'july.csv').read_text(encoding='utf-8')
    assert 'Full Name' not in raw and 'Achieng' not in raw
    assert 'Parent Phone' not in raw and '0712 000 000' not in raw
    assert report['dropped_but_look_personal'] == ['Full Name', 'Parent Phone']
    assert report['dropped_columns'] == ['Full Name', 'Parent Phone']
    assert 'Adm No' not in report['dropped_columns']

    first = next(csv.DictReader(raw.splitlines()))
    assert first['learner_id'] == 'HT-0001'
    assert first['grade'] == '7' and first['term'] == '2'
    assert 'source' in first and first['source'] == 'school_sheet'
    assert report['rows_in'] == 2 and report['rows_out'] == 2
    assert report['skipped'] == {'no_id_match': 0, 'blank': 0}
    assert report['next'] == 'python -m hatua ingest july.csv'


def test_two_imports_of_the_same_sheet_are_identical(home, tmp_path, sheet):
    mapping = write_mapping(tmp_path / 'mapping.json')
    importer.map_export(sheet, mapping, 'first.csv')
    first = (config.INBOX / 'first.csv').read_text(encoding='utf-8')
    importer.map_export(sheet, mapping, 'second.csv')
    second = (config.INBOX / 'second.csv').read_text(encoding='utf-8')
    assert first == second
    assert first.splitlines()[1].startswith('R-')


def test_unmapped_real_ids_are_skipped_never_passed_through(home, tmp_path):
    config.INBOX.mkdir(parents=True, exist_ok=True)
    config.DATA.joinpath('private').mkdir(parents=True, exist_ok=True)
    config.DATA.joinpath('private', 'id_map.csv').write_text(
        'real_id,hatua_id\nSCH-1,HT-0001\n', encoding='utf-8')
    source = school_sheet(tmp_path / 'school.csv', rows=[
        ['SCH-1', 'Known Child', 'Grade 7', '2026', 'Term 2', 'Mathematics', 'Algebra', 'ME', '68',
         '2026-06-12', '2026-06-19', 'T-004', '0712 000 000'],
        ['SCH-2', 'Other Child', 'Grade 7', '2026', 'Term 2', 'Mathematics', 'Algebra', 'ME', '60',
         '2026-06-12', '2026-06-19', 'T-004', '0713 000 000'],
    ])
    mapping = write_mapping(tmp_path / 'm.json', {**MAPPING, 'id_map': 'private/id_map.csv'})
    report = importer.map_export(source, mapping, 'mapped.csv')

    raw = (config.INBOX / 'mapped.csv').read_text(encoding='utf-8')
    assert 'SCH-2' not in raw and 'Other Child' not in raw
    assert report['skipped']['no_id_match'] == 1
    assert report['rows_out'] == 1
    assert next(csv.DictReader(raw.splitlines()))['learner_id'] == 'HT-0001'


def test_bad_mappings_and_unsafe_output_names_are_refused(home, tmp_path, sheet):
    with pytest.raises(importer.MappingError, match='Unknown Hatua column'):
        importer.map_export(sheet, write_mapping(tmp_path / 'bad.json',
                                                 {'columns': {'Adm No': 'not_a_column'}}), 'a.csv')
    with pytest.raises(importer.MappingError, match='Heading'):
        importer.map_export(sheet, write_mapping(tmp_path / 'missing.json',
                                                 {'columns': {'Not There': 'learner_id',
                                                              'Class': 'grade', 'Year': 'year',
                                                              'Term': 'term',
                                                              'Learning Area': 'learning_area',
                                                              'Rubric Level': 'level'}}), 'a.csv')
    mapping = write_mapping(tmp_path / 'ok.json')
    with pytest.raises(importer.MappingError, match='inside data/inbox'):
        importer.map_export(sheet, mapping, '../escape.csv')
    importer.map_export(sheet, mapping, 'taken.csv')
    with pytest.raises(importer.MappingError, match='already exists'):
        importer.map_export(sheet, mapping, 'taken.csv')


def test_mapped_file_still_gets_the_normal_cleaner_repairs(home, tmp_path):
    store.save('learners', [{'learner_id': 'HT-0001', 'first_name': 'Achieng', 'stream': '7A',
                             'current_grade': 7}])
    config.INBOX.mkdir(parents=True, exist_ok=True)
    source = school_sheet(tmp_path / 'school.csv', rows=[
        ['ht 1', 'Achieng O', 'Grade 7', '2026', 'Term 2', 'maths', 'Algebra', 'me', '68',
         '2026-06-12', '2026-06-19', 'T-004', '0712 000 000'],
    ])
    importer.map_export(source, write_mapping(tmp_path / 'm.json'), 'cleaned.csv')
    result = store.ingest_records(config.INBOX / 'cleaned.csv')

    assert result['added'] == 1 and result['rejected'] == 0
    record = store.load('records')[0]
    assert record['learner_id'] == 'HT-0001'
    assert record['learning_area'] == 'Mathematics'
    assert record['level'] == 'ME'
    flagged = {f['type'] for f in store.load('flags')}
    assert {'id_repaired', 'area_repaired', 'level_repaired'} <= flagged


def test_example_mapping_and_template_work_together(home, tmp_path):
    """Smoke test: the shipped template, mapped with the shipped example mapping, then ingested."""
    mapping = json.loads((REPO / 'data' / 'mappings' / 'example_school_export.json')
                         .read_text(encoding='utf-8'))
    mapping.pop('id_map', None)  # the private ID map is never shipped
    map_file = tmp_path / 'example.json'
    map_file.write_text(json.dumps(mapping), encoding='utf-8')
    config.INBOX.mkdir(parents=True, exist_ok=True)
    store.save('learners', [{'learner_id': 'HT-0001', 'first_name': 'Achieng', 'stream': '7A',
                             'current_grade': 7},
                            {'learner_id': 'HT-0002', 'first_name': 'Brian', 'stream': '7A',
                             'current_grade': 7}])
    report = importer.map_export(REPO / 'docs' / 'templates' / 'records_template.csv',
                                map_file, 'template.csv')
    assert report['rows_in'] == 2 and report['rows_out'] == 2
    assert report['dropped_but_look_personal'] == []
    result = store.ingest_records(config.INBOX / 'template.csv')
    assert result['added'] == 2 and result['rejected'] == 0


