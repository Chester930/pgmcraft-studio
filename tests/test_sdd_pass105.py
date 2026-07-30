"""
SDD Pass 105 — Module 3 BarStart v2 skeleton and meter-aware grid tests.
"""

import numpy as np

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    ManualCommittedBarStartsSeedNode,
    MeterAwareBeatGridNode,
    MeterProfileNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_meter_profile_supports_user_meter_and_temporary_extensions():
    bb = Blackboard()
    bb.set_val("user_meter_selection", "4/4")
    bb.set_val("allow_temporary_bar_delta", "+2")

    assert MeterProfileNode().execute(bb) == NodeStatus.SUCCESS

    profile = bb.get_val("meter_profile")
    assert profile["base_meter"] == "4/4"
    assert profile["meter"] == "4/4"
    assert profile["beats_per_bar"] == 4
    assert profile["clicks_per_bar"] == 4
    assert bb.get_val("allowed_bar_lengths") == [4, 5, 6]
    assert bb.get_val("temporary_bar_policy") == "allow_temporary_delta"


def test_meter_aware_grid_divides_committed_bar_starts_by_meter():
    bb = Blackboard()
    bb.set_val("manual_bar_starts", [0.0, 3.0, 6.0])
    bb.set_val("user_meter_selection", "3/4")

    assert MeterProfileNode().execute(bb) == NodeStatus.SUCCESS
    assert ManualCommittedBarStartsSeedNode().execute(bb) == NodeStatus.SUCCESS
    assert MeterAwareBeatGridNode().execute(bb) == NodeStatus.SUCCESS

    beats = bb.get_val("beats")
    click_grid = bb.get_val("click_grid")
    measure_map = bb.get_val("measure_map")

    assert beats.shape == (6, 2)
    np.testing.assert_allclose(beats[:, 0], [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    np.testing.assert_allclose(beats[:, 1], [1, 2, 3, 1, 2, 3])
    assert len(click_grid) == 6
    assert len(measure_map) == 2
    assert measure_map[0]["meter"] == "3/4"
    assert measure_map[0]["beat_count"] == 3
    assert bb.get_val("bar_length_report")["strategy"] == "meter_aware_bar_division"


def test_module3_barstart_v2_tree_is_isolated_from_existing_module3():
    v2_tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    old_tree = build_master_pipeline_tree(target_stage="module3")
    v2_names = _node_names(v2_tree)
    old_names = _node_names(old_tree)

    assert v2_tree.name == "Module3BarStartClickRoot"
    assert "MeterProfileNode" in v2_names
    assert "ManualCommittedBarStartsSeedNode" in v2_names
    assert "MeterAwareBeatGridNode" in v2_names
    assert "Module3BarStartV2ExportRoot" in v2_names
    assert v2_names.index("Module3BarStartV2SummaryNode") < v2_names.index("Module3OutputSummaryNode")

    assert old_tree.name == "Module3BeatClickRoot"
    assert "MeterAwareBeatGridNode" not in old_names
