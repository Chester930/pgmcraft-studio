"""
SDD Pass 119 — Module 3 BarStart v2: drum-fill / snap-exclusion zones wired
onto the bar-grid before onset realignment runs.

v2 does not have a `beats` array until `MeterAwareBeatGridNode` produces the
final bar-division grid, so `DrumFillDetectionNode` (reused from Stage 3) has
to run *after* the grid exists and *before* `OnsetPhaseRealignmentNode`, so a
decorative dense drum-fill cluster near a grid beat cannot drag that beat's
onset snap away from the true bar-aligned position.
"""

import unittest

import numpy as np

from pgm_craft.workflow.beat_tracking_bt import DrumFillDetectionNode, OnsetPhaseRealignmentNode
from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import MeterAwareBeatGridNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


class TestSDDPass119DrumFillExclusionInV2(unittest.TestCase):
    def setUp(self):
        self.sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(self.sr * duration), False)
        y = np.zeros_like(t)
        # decoy impulse sitting inside the drum-fill cluster window (should be ignored)
        for beat_time in [0.48, 0.98]:
            idx = int(beat_time * self.sr)
            y[idx:idx + 100] = np.sin(2 * np.pi * 100 * np.linspace(0, 0.01, 100)) * 0.8
        self.y = y

    def _grid_blackboard(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0])
        bb.set_val("meter_profile", {"base_meter": "2/4", "beats_per_bar": 2, "beat_unit": 4})
        self.assertEqual(MeterAwareBeatGridNode().execute(bb), NodeStatus.SUCCESS)
        return bb

    def test_v2_pipeline_places_drum_fill_detection_before_onset_realignment(self):
        names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
        self.assertIn("DrumFillDetectionNode", names)
        self.assertLess(names.index("MeterAwareBeatGridNode"), names.index("DrumFillDetectionNode"))
        self.assertLess(names.index("DrumFillDetectionNode"), names.index("OnsetPhaseRealignmentNode"))

    def test_dense_kick_cluster_produces_exclusion_zone_around_first_bar(self):
        bb = self._grid_blackboard()
        # dense sub-beat kick cluster inside [0.0, 0.5) -> should mark a fill region there
        bb.set_val("kick_anchors", [0.05, 0.15, 0.25, 0.35])
        status = DrumFillDetectionNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        regions = bb.get_val("drum_fill_regions")
        self.assertEqual(len(regions), 1)
        self.assertLessEqual(regions[0]["start_time"], 0.05)
        self.assertGreaterEqual(regions[0]["end_time"], 0.48)
        self.assertEqual(bb.get_val("drum_fill_report")["status"], "DETECTED")

    def test_beat_inside_fill_zone_ignores_decoy_onset_while_others_still_realign(self):
        bb = self._grid_blackboard()
        bb.set_val("kick_anchors", [0.05, 0.15, 0.25, 0.35])
        self.assertEqual(DrumFillDetectionNode().execute(bb), NodeStatus.SUCCESS)

        bb.set_val("y", self.y)
        bb.set_val("sr", self.sr)
        status = OnsetPhaseRealignmentNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        beats = bb.get_val("beats")
        # index 1 (t=0.5) sits inside the fill exclusion zone: must stay untouched
        # even though a decoy onset at 0.48s is within the +/-35ms search window.
        self.assertAlmostEqual(beats[1, 0], 0.5, delta=1e-6)
        # index 2 (t=1.0) is outside any fill zone: should still snap to the real
        # onset at 0.98s.
        self.assertLess(abs(beats[2, 0] - 0.98), 0.03)
        report = bb.get_val("phase_realignment_report")
        self.assertGreaterEqual(report["skipped_exclusion_count"], 1)


if __name__ == "__main__":
    unittest.main()
