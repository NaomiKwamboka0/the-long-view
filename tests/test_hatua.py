"""Fast checks. The full evaluation set is scripts/run_evals.py."""
from hatua import guard, normalize


def test_level_spellings():
    assert normalize.level("Meeting Expectations") == "ME"
    assert normalize.level(" e.e ") == "EE"
    assert normalize.level("2") == "AE"
    assert normalize.level("great") is None


def test_learner_id_repair():
    assert normalize.learner_id("ht0007") == "HT-0007"
    assert normalize.learner_id("HT 0024") == "HT-0024"
    assert normalize.learner_id("X-12") is None


def test_score_bands():
    assert normalize.level_from_score(80) == "EE"
    assert normalize.level_from_score(50) == "ME"
    assert normalize.level_from_score(24) == "BE"


def test_guard_blocks_labels_and_comparisons():
    found = guard.labels_in("She is gifted and should take the STEM pathway, better than her classmates.")
    assert len(found) >= 3


def test_citation_parsing():
    assert guard.citations("- Fell [R-00012, R-00013] (Ref: A-HT-0018-G8T2)") == ["R-00012", "R-00013", "A-HT-0018-G8T2"]
