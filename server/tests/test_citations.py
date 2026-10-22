"""Unit tests for citation marker validation."""

from civic.citations import validate


def test_valid_markers_are_kept_and_collected():
    cleaned, used = validate("Yes [1], under conditions [2].", 2)
    assert used == [1, 2]
    assert cleaned == "Yes [1], under conditions [2]."


def test_out_of_range_markers_are_stripped():
    cleaned, used = validate("Rule applies [1] everywhere [7].", 5)
    assert used == [1]
    assert "[7]" not in cleaned
    assert "everywhere." in cleaned


def test_duplicate_markers_dedupe():
    _, used = validate("Same rule [2] again [2] and [1].", 3)
    assert used == [1, 2]


def test_fully_ungrounded_answer_yields_no_markers():
    cleaned, used = validate("You may build up to two metres.", 8)
    assert used == []
    assert "two metres" in cleaned


def test_spacing_before_punctuation_is_repaired():
    cleaned, _ = validate("Permitted [1] .", 1)
    assert " ." not in cleaned
