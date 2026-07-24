"""
Unit tests for Pass 5 Architectural Optimizations:
Module 1: BaseNode BT Self-Healing Guard (Catching Exception & failing safely)
Module 2: CLI main.py batch processing helper logic
"""

import pytest
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus


class ExceptionTestNode(BaseNode):
    def __init__(self):
        super().__init__("ExceptionTestNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raise ValueError("Simulated unexpected exception for Self-Healing test")


def test_bt_self_healing_guard():
    node = ExceptionTestNode()
    blackboard = Blackboard()

    # The node should NOT raise exception, but catch it and return FAILURE safely
    status = node.run(blackboard)
    assert status == NodeStatus.FAILURE

    # Verify trace entry recorded error
    trace = blackboard.get_val("workflow_trace", [])
    assert len(trace) == 1
    assert trace[0]["status"] == "FAILURE"
    assert "Simulated unexpected exception" in trace[0]["error"]
