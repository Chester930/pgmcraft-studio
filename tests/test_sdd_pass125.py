"""
SDD Pass 125 — Module 3 BarStart v2: bounded fallback interpolation for
no-drum spans with no future anchor at all, ported from Module 3 v1's
`_inertia_fill`.

`NoDrumPhaseCarryNode` only ever carried bars up to a *known* future anchor
found by lookahead. When lookahead genuinely found nothing (e.g. a long
ambient outro past the lookahead range), `provisional_bar_starts` stayed
empty and that whole span produced no click coverage at all. This pass adds a
capped constant-tempo extrapolation for that specific case, tagged with a
distinct status (`CARRIED_FALLBACK_NO_LOOKAHEAD`) so it is never confused with
an anchor-confirmed carry.
"""

import unittest

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import NoDrumPhaseCarryNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass125NoLookaheadFallback(unittest.TestCase):
    def test_no_future_anchor_previously_produced_zero_coverage(self):
        # sanity-check the bug this pass fixes: with no lookahead candidates at
        # all and no duration cap, count must be bounded, not empty and not infinite.
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("bar_duration_sec", 2.0)
        status = NoDrumPhaseCarryNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        provisional = bb.get_val("provisional_bar_starts")
        self.assertTrue(provisional)
        report = bb.get_val("no_drum_phase_report")
        self.assertEqual(report["status"], "CARRIED_FALLBACK_NO_LOOKAHEAD")
        self.assertTrue(report["used_no_lookahead_fallback"])

    def test_fallback_is_capped_at_max_fallback_bars(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("bar_duration_sec", 2.0)
        node = NoDrumPhaseCarryNode(max_fallback_bars=3)
        self.assertEqual(node.execute(bb), NodeStatus.SUCCESS)

        provisional = bb.get_val("provisional_bar_starts")
        self.assertEqual(provisional, [2.0, 4.0, 6.0])

    def test_fallback_is_further_capped_by_known_audio_duration(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("bar_duration_sec", 2.0)
        bb.set_val("audio_duration_sec", 5.5)
        node = NoDrumPhaseCarryNode(max_fallback_bars=8)
        self.assertEqual(node.execute(bb), NodeStatus.SUCCESS)

        provisional = bb.get_val("provisional_bar_starts")
        # bars at 2.0 and 4.0 fit inside 5.5s; 6.0 would not
        self.assertEqual(provisional, [2.0, 4.0])

    def test_fallback_duration_cap_derived_from_waveform_when_no_explicit_duration(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("bar_duration_sec", 2.0)
        sr = 22050
        bb.set_val("y", np.zeros(int(4.2 * sr)))
        bb.set_val("sr", sr)
        node = NoDrumPhaseCarryNode(max_fallback_bars=8)
        self.assertEqual(node.execute(bb), NodeStatus.SUCCESS)

        provisional = bb.get_val("provisional_bar_starts")
        self.assertEqual(provisional, [2.0, 4.0])

    def test_known_future_anchor_still_uses_the_original_carried_path(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("bar_duration_sec", 2.0)
        bb.set_val("lookahead_bar_candidates", [{"time": 8.0, "confidence": 0.9}])
        status = NoDrumPhaseCarryNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        provisional = bb.get_val("provisional_bar_starts")
        self.assertEqual(provisional, [2.0, 4.0, 6.0])
        report = bb.get_val("no_drum_phase_report")
        self.assertEqual(report["status"], "CARRIED")
        self.assertFalse(report["used_no_lookahead_fallback"])


if __name__ == "__main__":
    unittest.main()
