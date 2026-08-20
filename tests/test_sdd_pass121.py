"""
SDD Pass 121 — Module 3 BarStart v2: bar-level continuity repair and
oscillation damping on `committed_bar_starts`, before the fine-grained beat
grid is derived.

Stage 3 repairs the *beat* list (`BeatGridContinuityRepairNode` /
`TempoOscillationDampingNode`). v2's real unit of truth is the *bar* list, so
this pass ports the same insert/remove/dampen logic to operate on
`committed_bar_starts` directly, right before `MeterAwareBeatGridNode` turns
it into the final click grid.
"""

import unittest

from pgm_craft.workflow.module3_barstart_v2_bt import BarGridContinuityRepairNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass121BarGridContinuityRepair(unittest.TestCase):
    def test_missed_bar_gap_is_filled_at_median_interval(self):
        bb = Blackboard()
        # bars at 0,2,4 are regular (2s each); 6->10 skips a detection (should be ~8)
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0, 6.0, 10.0])
        status = BarGridContinuityRepairNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("bar_grid_repair_report")
        self.assertEqual(report["status"], "REPAIRED")
        self.assertEqual(report["inserted_bar_count"], 1)
        bars = bb.get_val("committed_bar_starts")
        self.assertIn(8.0, bars)
        self.assertEqual(bars, sorted(bars))

    def test_near_duplicate_bar_start_is_dropped(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0, 2.05, 4.0, 6.0])
        status = BarGridContinuityRepairNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("bar_grid_repair_report")
        self.assertEqual(report["status"], "REPAIRED")
        self.assertEqual(report["removed_bar_count"], 1)
        bars = bb.get_val("committed_bar_starts")
        self.assertNotIn(2.05, bars)

    def test_isolated_short_long_bar_oscillation_is_damped_toward_neighbors(self):
        bb = Blackboard()
        # bars 0,2,4,6,8 are regular except bar #3 (at index 2) sits too early at
        # 3.0 (short 1.0s bar followed by a compensating long 3.0s bar).
        bb.set_val("committed_bar_starts", [0.0, 2.0, 3.0, 6.0, 8.0])
        status = BarGridContinuityRepairNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("bar_grid_repair_report")
        self.assertEqual(report["status"], "REPAIRED")
        self.assertEqual(report["oscillation_damped_count"], 1)
        bars = bb.get_val("committed_bar_starts")
        self.assertAlmostEqual(bars[2], 4.0, delta=0.05)

    def test_regular_bar_list_is_left_untouched(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0, 6.0, 8.0])
        status = BarGridContinuityRepairNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = bb.get_val("bar_grid_repair_report")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(bb.get_val("committed_bar_starts"), [0.0, 2.0, 4.0, 6.0, 8.0])


if __name__ == "__main__":
    unittest.main()
