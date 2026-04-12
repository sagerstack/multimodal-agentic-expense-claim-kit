"""Unit tests for Phase 13 state reducers.

Reducer behavior is load-bearing: an incorrect union for
unsupportedCurrencies would cause directive injection to miss currencies
accumulated across turns, defeating the purpose of the flag.
"""

from agentic_claims.core.state import _unionSet


def test_unionSetMergesTwoSets():
    assert _unionSet({"VND"}, {"THB"}) == {"VND", "THB"}


def test_unionSetHandlesNoneExisting():
    assert _unionSet(None, {"VND"}) == {"VND"}


def test_unionSetHandlesNoneUpdate():
    assert _unionSet({"VND"}, None) == {"VND"}


def test_unionSetHandlesBothNone():
    assert _unionSet(None, None) == set()


def test_unionSetIsIdempotentOnDuplicateCurrency():
    assert _unionSet({"VND"}, {"VND"}) == {"VND"}


def test_unionSetAccumulatesAcrossMultipleCalls():
    """Simulates multi-turn accumulation as LangGraph would apply it."""
    state = set()
    state = _unionSet(state, {"VND"})
    state = _unionSet(state, {"THB"})
    state = _unionSet(state, {"IDR"})
    assert state == {"VND", "THB", "IDR"}
