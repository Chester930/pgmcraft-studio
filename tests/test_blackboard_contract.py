"""
Unit tests for Blackboard typed contract validation and workflow tracing.
"""

import pytest
from pgm_craft.workflow.nodes import Blackboard, BaseNode, NodeStatus, SequenceNode


class DummyContractNode(BaseNode):
    required_keys = ["audio_path"]
    optional_keys = ["output_dir"]
    output_keys = ["beats"]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        blackboard.set_val("beats", [(0.0, 1), (0.5, 2)])
        return NodeStatus.SUCCESS


def test_blackboard_get_typed():
    bb = Blackboard()
    bb.set_val("audio_path", "test.wav")
    bb.set_val("enable_stem", True)

    assert bb.get_typed("audio_path", str) == "test.wav"
    assert bb.get_typed("enable_stem", bool) is True
    assert bb.get_typed("missing_key", str, default="fallback") == "fallback"


def test_blackboard_contract_validation_pass():
    bb = Blackboard()
    bb.set_val("audio_path", "test.wav")
    bb.set_val("validate_contracts", True)

    node = DummyContractNode("TestNode")
    status = node.run(bb)

    assert status == NodeStatus.SUCCESS
    assert "contract_validation" in bb
    assert len(bb["contract_validation"]) == 1

    val = bb["contract_validation"][0]
    assert val["status"] == "PASS"
    assert val["missing_required_keys"] == []


def test_blackboard_contract_validation_warn_missing_key():
    bb = Blackboard()
    bb.set_val("validate_contracts", True)

    node = DummyContractNode("TestNode")
    status = node.run(bb)

    assert status == NodeStatus.SUCCESS
    assert "contract_validation" in bb
    val = bb["contract_validation"][0]
    assert val["status"] == "WARN"
    assert "audio_path" in val["missing_required_keys"]


def test_blackboard_contract_validation_strict_mode():
    bb = Blackboard()

    node = DummyContractNode("TestNode")
    missing = bb.validate_strict(node)
    assert "audio_path" in missing

    bb.set_val("audio_path", "test.wav")
    missing_after = bb.validate_strict(node)
    assert len(missing_after) == 0
