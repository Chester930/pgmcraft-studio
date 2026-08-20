"""
SDD Pass 129 — Module 3 BarStart v2: wire real future drum evidence into
`lookahead_drum_events`, activating the Pass 116-117 bidirectional
re-anchoring machinery that had no real data source in production.

`kick_anchors`/`snare_anchors` are a full-song array (Stage 3's
`KickSnarePulseNode`, shared into v2's blackboard when running through
`Module3BarStartV2MergeNode`). Nothing ever filtered them down into
`lookahead_drum_events` -- `LookaheadDrumAnchorSearchNode` only ever saw real
data in unit tests that set the key by hand. User-reported symptoms this
targets: tempo drift and wrong downbeat phase across no-drum spans.
"""

import unittest

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import (
    LookaheadDrumAnchorSearchNode,
    LookaheadDrumEventScanNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass129LookaheadDrumEventScan(unittest.TestCase):
    def test_future_kick_and_snare_anchors_become_lookahead_events(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("kick_anchors", np.array([1.0, 8.0, 12.0]))  # 1.0 is in the past
        bb.set_val("snare_anchors", np.array([9.0]))
        status = LookaheadDrumEventScanNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        events = bb.get_val("lookahead_drum_events")
        times = sorted(e["time"] for e in events)
        self.assertEqual(times, [8.0, 9.0, 12.0])
        self.assertNotIn(1.0, times)  # past events excluded

    def test_events_beyond_the_lookahead_horizon_are_excluded(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("kick_anchors", np.array([5.0, 50.0]))
        status = LookaheadDrumEventScanNode(horizon_sec=10.0).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        events = bb.get_val("lookahead_drum_events")
        self.assertEqual([e["time"] for e in events], [5.0])

    def test_near_duplicate_kick_and_snare_hit_dedupes_to_higher_confidence(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("kick_anchors", np.array([8.0]))
        bb.set_val("snare_anchors", np.array([8.01]))  # same hit, different stem
        status = LookaheadDrumEventScanNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        events = bb.get_val("lookahead_drum_events")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["time"], 8.0)  # kick's higher confidence wins

    def test_lookahead_search_now_finds_real_candidates_from_the_scan(self):
        """End-to-end: previously LookaheadDrumAnchorSearchNode always saw
        event_count=0 in real runs; this confirms the wiring now produces
        real candidates from real anchor data."""
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("kick_anchors", np.array([10.0]))

        self.assertEqual(LookaheadDrumEventScanNode().execute(bb), NodeStatus.SUCCESS)
        self.assertEqual(LookaheadDrumAnchorSearchNode().execute(bb), NodeStatus.SUCCESS)

        report = bb.get_val("lookahead_anchor_report")
        self.assertEqual(report["status"], "READY")
        self.assertGreater(report["event_count"], 0)
        self.assertGreater(report["candidate_count"], 0)
        candidates = bb.get_val("lookahead_bar_candidates")
        self.assertTrue(any(abs(c["event_time"] - 10.0) < 1e-6 for c in candidates))


if __name__ == "__main__":
    unittest.main()
