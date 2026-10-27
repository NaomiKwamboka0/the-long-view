"""Checks the arithmetic behind the published model-run numbers (ticket T2)."""
from hatua import measure

RUNS = [
    {"crashed": False, "drafts": 3, "nudges": 0, "seconds": 10, "tool_calls": 8},
    {"crashed": False, "drafts": 3, "nudges": 0, "seconds": 12, "tool_calls": 8},
    {"crashed": False, "drafts": 3, "nudges": 0, "seconds": 14, "tool_calls": 9},
    {"crashed": False, "drafts": 3, "nudges": 0, "seconds": 16, "tool_calls": 9},
    {"crashed": False, "drafts": 3, "nudges": 1, "seconds": 18, "tool_calls": 10},
    {"crashed": False, "drafts": 3, "nudges": 2, "seconds": 20, "tool_calls": 12},
    {"crashed": False, "drafts": 3, "nudges": 1, "seconds": 22, "tool_calls": 11},
    {"crashed": False, "drafts": 1, "nudges": 0, "seconds": 24, "tool_calls": 4},
    {"crashed": True, "drafts": 0, "nudges": 0, "seconds": 5, "tool_calls": 0},
    {"crashed": True, "drafts": 0, "nudges": 0, "seconds": 6, "tool_calls": 0},
]


def test_unaided_means_every_target_learner_and_no_nudges():
    summary = measure.summarise(RUNS, target=3)
    assert summary["runs"] == 10
    assert summary["unaided"] == 4
    assert summary["unaided_rate"] == 0.4
    assert summary["crashed"] == 2


def test_a_short_run_counts_as_not_unaided():
    summary = measure.summarise([{"crashed": False, "drafts": 2, "nudges": 0, "seconds": 9}], target=3)
    assert summary["unaided"] == 0


def test_nudges_and_seconds_use_plain_counts_and_a_nearest_rank_p90():
    summary = measure.summarise(RUNS, target=3)
    assert summary["nudges"] == {"median": 0, "worst": 2, "total": 4}
    # sorted seconds: 5 6 10 12 14 16 18 20 22 24 -> median 15, p90 = 9th value
    assert summary["seconds"]["median"] == 15.0
    assert summary["seconds"]["p90"] == 22
    assert summary["seconds"]["worst"] == 24


def test_p90_never_lands_below_the_second_worst_run():
    for count in (2, 3, 5, 9, 10, 11):
        runs = [{"crashed": False, "drafts": 3, "nudges": 0, "seconds": float(i)}
                for i in range(1, count + 1)]
        summary = measure.summarise(runs, target=3)
        assert summary["seconds"]["p90"] >= sorted(float(i) for i in range(1, count + 1))[-2] \
            or count == 1


def test_an_empty_batch_does_not_divide_by_zero():
    summary = measure.summarise([], target=3)
    assert summary == {"runs": 0, "unaided": 0, "unaided_rate": 0.0, "crashed": 0,
                       "nudges": {"median": 0.0, "worst": 0, "total": 0},
                       "seconds": {"median": 0.0, "p90": 0.0, "worst": 0.0},
                       "tool_calls": 0, "blocked_calls": 0}


def test_the_table_states_counts_not_just_a_percentage():
    text = measure.table(measure.summarise(RUNS, target=3), 3)
    assert "4/10" in text
    assert "median 0" in text
    assert "worst 24" in text
