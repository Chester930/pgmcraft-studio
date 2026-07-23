"""
Unit tests for RetryFallbackNode decorator with retry & fallback protection.
"""

import pytest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, RetryFallbackNode, BaseNode


class AlwaysFailNode(BaseNode):
    def __init__(self):
        super().__init__("AlwaysFailNode")
        self.call_count = 0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        self.call_count += 1
        return NodeStatus.FAILURE


class AlwaysSucceedNode(BaseNode):
    def __init__(self):
        super().__init__("AlwaysSucceedNode")
        self.call_count = 0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        self.call_count += 1
        return NodeStatus.SUCCESS


class FailThenSucceedNode(BaseNode):
    def __init__(self, fail_times=1):
        super().__init__("FailThenSucceedNode")
        self.fail_times = fail_times
        self.call_count = 0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            return NodeStatus.FAILURE
        return NodeStatus.SUCCESS


def test_retry_succeeds_on_retry():
    """Node fails once then succeeds on retry."""
    bb = Blackboard()
    child = FailThenSucceedNode(fail_times=1)
    node = RetryFallbackNode("RetryTest", child=child, max_retries=2)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert child.call_count == 2


def test_retry_exhausted_falls_back():
    """Child always fails → fallback node runs."""
    bb = Blackboard()
    child = AlwaysFailNode()
    fallback = AlwaysSucceedNode()
    node = RetryFallbackNode("RetryFallbackTest", child=child, max_retries=2, fallback=fallback)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert child.call_count == 3  # 1 original + 2 retries
    assert fallback.call_count == 1


def test_retry_exhausted_no_fallback_returns_failure():
    """Child always fails, no fallback → return FAILURE."""
    bb = Blackboard()
    child = AlwaysFailNode()
    node = RetryFallbackNode("RetryNoFallback", child=child, max_retries=1)
    status = node.run(bb)
    assert status == NodeStatus.FAILURE
    assert child.call_count == 2  # 1 original + 1 retry


def test_retry_first_attempt_success():
    """Node succeeds immediately → no retries."""
    bb = Blackboard()
    child = AlwaysSucceedNode()
    node = RetryFallbackNode("RetryEarlySuccess", child=child, max_retries=3)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert child.call_count == 1
