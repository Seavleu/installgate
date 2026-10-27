"""Attribution must separate "a rule fired" from "a rule decided", without inventing
a winner when two rules of the same severity both apply."""

from __future__ import annotations

import pytest
from eval.runner import deciding_rule


@pytest.mark.parametrize(
    "matched,expected",
    [
        ([], "(none)"),
        (["P9"], "P9"),
        # BLOCK outranks REVIEW: P2 decides, P6 is only coverage.
        (["P2", "P6"], "P2"),
        (["P5", "P6"], "P5+P6"),
        # P4 and P5 and P6 all fire on a young typosquat; only P4 is BLOCK.
        (["P4", "P5", "P6"], "P4"),
    ],
)
def test_strictest_verdict_decides(matched, expected):
    assert deciding_rule(matched) == expected


def test_two_rules_of_the_same_severity_are_reported_as_a_tie():
    # P2 and P4 are both BLOCK. Neither is stricter, and the verdict is the same
    # either way, so naming one would be an arbitrary tiebreak presented as fact.
    assert deciding_rule(["P2", "P4"]) == "P2+P4"
    assert deciding_rule(["P4", "P2"]) == "P2+P4"


def test_tie_is_ordered_by_rule_number_not_alphabetically():
    assert deciding_rule(["P4", "P2", "P1", "P3"]) == "P1+P2+P3+P4"


def test_tie_output_does_not_depend_on_input_order():
    import itertools

    for permutation in itertools.permutations(["P2", "P4", "P6"]):
        assert deciding_rule(list(permutation)) == "P2+P4"


def test_duplicate_matches_are_collapsed():
    assert deciding_rule(["P2", "P2"]) == "P2"
