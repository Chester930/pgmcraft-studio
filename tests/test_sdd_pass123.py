"""
SDD Pass 123 — Module 3 BarStart v2: onset syncopation/anticipation
classification, ported from Module 3 v1's `SyncopationClassificationNode`.

v1 relies on a `subdivision_grid` produced elsewhere in its pipeline; v2 has
no equivalent, so this node derives a lightweight half-beat subdivision grid
directly from `click_grid` and reuses v1's classification thresholds. This
covers general off-grid onsets (any instrument), which is broader than
Pass 119's drum-fill-only exclusion detector.
"""

import unittest

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartV2SyncopationClassificationNode,
    MeterAwareBeatGridNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


class TestSDDPass123SyncopationClassificationInV2(unittest.TestCase):
    def _grid_blackboard(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])
        bb.set_val("meter_profile", {"base_meter": "4/4", "beats_per_bar": 4, "beat_unit": 4})
        self.assertEqual(MeterAwareBeatGridNode().execute(bb), NodeStatus.SUCCESS)
        return bb

    def test_v2_pipeline_places_syncopation_classification_before_drum_fill_detection(self):
        names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
        self.assertIn("BarStartV2SyncopationClassificationNode", names)
        self.assertLess(
            names.index("MeterAwareBeatGridNode"),
            names.index("BarStartV2SyncopationClassificationNode"),
        )
        self.assertLess(
            names.index("BarStartV2SyncopationClassificationNode"),
            names.index("DrumFillDetectionNode"),
        )

    def test_onset_on_grid_is_true_beat_and_not_excluded(self):
        bb = self._grid_blackboard()
        # bar 1 beat 3 sits at 1.0s (0.0 + 2*0.5); land an onset right on it
        bb.set_val("onset_events", [1.0])
        status = BarStartV2SyncopationClassificationNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        events = bb.get_val("syncopation_events")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["classification"], "true_beat")
        self.assertTrue(events[0]["snap_click"])
        self.assertEqual(bb.get_val("snap_exclusion_zones", []), [])

    def test_offbeat_syncopated_onset_produces_exclusion_zone(self):
        bb = self._grid_blackboard()
        # beats land at 0.0/0.5/1.0/1.5/2.0...; the "and" of beat 1 sits at 0.25s
        bb.set_val("onset_events", [{"time": 0.25}])
        status = BarStartV2SyncopationClassificationNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        events = bb.get_val("syncopation_events")
        self.assertEqual(events[0]["classification"], "syncopation")
        self.assertFalse(events[0]["snap_click"])
        zones = bb.get_val("snap_exclusion_zones")
        self.assertEqual(len(zones), 1)
        self.assertLessEqual(zones[0]["start_time"], 0.25)
        self.assertGreaterEqual(zones[0]["end_time"], 0.25)

    def test_existing_exclusion_zones_are_preserved_not_overwritten(self):
        bb = self._grid_blackboard()
        bb.set_val("snap_exclusion_zones", [{"start_time": 10.0, "end_time": 10.5, "reason": "prior"}])
        bb.set_val("onset_events", [{"time": 0.25}])
        self.assertEqual(BarStartV2SyncopationClassificationNode().execute(bb), NodeStatus.SUCCESS)

        zones = bb.get_val("snap_exclusion_zones")
        self.assertEqual(len(zones), 2)
        self.assertTrue(any(z["reason"] == "prior" for z in zones))

    def test_falls_back_to_drum_anchors_when_no_explicit_onset_events(self):
        bb = self._grid_blackboard()
        bb.set_val("kick_anchors", [1.0])
        status = BarStartV2SyncopationClassificationNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        events = bb.get_val("syncopation_events")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["classification"], "true_beat")


if __name__ == "__main__":
    unittest.main()
