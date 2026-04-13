"""Tests for checkpointer-based interrupt detection.

Covers the isPausedAtInterrupt utility used by the HTTP layer to decide
whether an incoming POST /chat/message should be routed as Command(resume=...).
"""

from dataclasses import dataclass, field
from typing import Any

from agentic_claims.web.interruptDetection import isPausedAtInterrupt


@dataclass
class FakeInterrupt:
    value: Any = "Confirm?"


@dataclass
class FakeTask:
    name: str = "intake"
    interrupts: tuple = ()


@dataclass
class FakeSnapshot:
    tasks: tuple = field(default_factory=tuple)


def testReturnsFalseWhenSnapshotIsNone():
    assert isPausedAtInterrupt(None) is False


def testReturnsFalseWhenTasksEmpty():
    snapshot = FakeSnapshot(tasks=())
    assert isPausedAtInterrupt(snapshot) is False


def testReturnsFalseWhenTasksHaveNoInterrupts():
    snapshot = FakeSnapshot(tasks=(FakeTask(name="intake", interrupts=()),))
    assert isPausedAtInterrupt(snapshot) is False


def testReturnsTrueWhenTaskHasInterrupt():
    snapshot = FakeSnapshot(
        tasks=(FakeTask(name="intake", interrupts=(FakeInterrupt(),)),)
    )
    assert isPausedAtInterrupt(snapshot) is True


def testReturnsTrueWhenOneOfManyTasksHasInterrupt():
    snapshot = FakeSnapshot(
        tasks=(
            FakeTask(name="a", interrupts=()),
            FakeTask(name="b", interrupts=(FakeInterrupt(),)),
            FakeTask(name="c", interrupts=()),
        )
    )
    assert isPausedAtInterrupt(snapshot) is True


def testReturnsFalseWhenInterruptsAttributeIsNone():
    @dataclass
    class LooseTask:
        interrupts: Any = None

    snapshot = FakeSnapshot(tasks=(LooseTask(),))
    assert isPausedAtInterrupt(snapshot) is False


def testReturnsFalseWhenSnapshotHasNoTasksAttribute():
    class BareSnapshot:
        pass

    assert isPausedAtInterrupt(BareSnapshot()) is False
