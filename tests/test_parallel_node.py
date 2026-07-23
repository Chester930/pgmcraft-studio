"""
Unit tests for ParallelNode concurrent execution.
"""

import time
import pytest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, ParallelNode, BaseNode


class SlowNode(BaseNode):
    """Simulates a slow node by sleeping."""
    def __init__(self, name, sleep_sec=0.05, result=NodeStatus.SUCCESS):
        super().__init__(name)
        self.sleep_sec = sleep_sec
        self.result = result
        self.call_count = 0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        self.call_count += 1
        time.sleep(self.sleep_sec)
        blackboard.set_val(f"result_{self.name}", True)
        return self.result


def test_parallel_all_succeed():
    """All children succeed → ParallelNode returns SUCCESS."""
    bb = Blackboard()
    node = ParallelNode("ParallelAll", children=[
        SlowNode("A", sleep_sec=0.05),
        SlowNode("B", sleep_sec=0.05),
        SlowNode("C", sleep_sec=0.05),
    ])
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert bb.get_val("result_A") is True
    assert bb.get_val("result_B") is True
    assert bb.get_val("result_C") is True


def test_parallel_one_fails_default_policy():
    """Default policy ANY_SUCCESS: if any child fails, overall FAILURE when all fail."""
    bb = Blackboard()
    node = ParallelNode("ParallelFail", children=[
        SlowNode("A", result=NodeStatus.SUCCESS),
        SlowNode("B", result=NodeStatus.FAILURE),
    ], success_threshold=2)  # require ALL to succeed
    status = node.run(bb)
    assert status == NodeStatus.FAILURE


def test_parallel_is_faster_than_sequential():
    """Parallel execution should be noticeably faster than sequential."""
    SLEEP = 0.1
    N = 3

    # Sequential timing
    start = time.perf_counter()
    bb_seq = Blackboard()
    for i in range(N):
        SlowNode(f"seq_{i}", sleep_sec=SLEEP).run(bb_seq)
    seq_time = time.perf_counter() - start

    # Parallel timing
    start = time.perf_counter()
    bb_par = Blackboard()
    ParallelNode("Parallel", children=[
        SlowNode(f"par_{i}", sleep_sec=SLEEP) for i in range(N)
    ]).run(bb_par)
    par_time = time.perf_counter() - start

    # Parallel should be substantially faster (at least 1.5× speedup)
    assert par_time < seq_time * 0.8, (
        f"Parallel ({par_time:.3f}s) not faster than sequential ({seq_time:.3f}s)"
    )


def test_parallel_success_threshold():
    """With success_threshold=1, node succeeds as soon as any child succeeds."""
    bb = Blackboard()
    node = ParallelNode("Partial", children=[
        SlowNode("ok", result=NodeStatus.SUCCESS),
        SlowNode("fail", result=NodeStatus.FAILURE),
    ], success_threshold=1)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS


def test_parallel_empty_children():
    """Empty children list → SUCCESS (nothing to fail)."""
    bb = Blackboard()
    node = ParallelNode("Empty", children=[])
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
