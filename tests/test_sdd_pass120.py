"""
SDD Pass 120 — Module 3 BarStart v2: madmom (2016) low-frequency downbeat
verification wired on top of the evidence-ladder grid.

The evidence ladder (drum/bass/chord/melody/Beat This! PK) can still be misled
by non-drum evidence (e.g. a strong bass overtone landing on the "wrong" beat).
`KickBassDownbeatVerifierNode` is an independent 40-120Hz acoustic check that
runs after the grid exists, as a second opinion the ladder doesn't have.

This pass also fixes a pre-existing contract gap in the reused Stage 3 node:
`downbeat_fix_report` was declared in `output_keys` but never written by
`execute()`, so it always came back as an empty dict downstream. That gap
existed on the Stage 3 main line too, so this fix benefits both lines.
"""

import unittest

import numpy as np

from pgm_craft.workflow.beat_tracking_bt import KickBassDownbeatVerifierNode
from pgm_craft.workflow.module3_barstart_v2_bt import MeterAwareBeatGridNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass120DownbeatVerifierInV2(unittest.TestCase):
    def setUp(self):
        self.sr = 22050
        duration = 4.0
        t = np.linspace(0, duration, int(self.sr * duration), False)
        y = np.zeros_like(t)

        def _impulse(center_sec, amplitude, freq=90.0):
            idx = int(center_sec * self.sr)
            n = 200
            y[idx:idx + n] += np.sin(2 * np.pi * freq * np.linspace(0, n / self.sr, n)) * amplitude

        # weak low-frequency energy at the (wrongly) labeled downbeats 0.0s/2.0s
        _impulse(0.0, 0.05)
        _impulse(2.0, 0.05)
        # strong low-frequency energy two beats later, at 1.0s/3.0s -> the real downbeats
        _impulse(1.0, 0.9)
        _impulse(3.0, 0.9)
        self.y = y

    def _grid_blackboard(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])
        bb.set_val("meter_profile", {"base_meter": "4/4", "beats_per_bar": 4, "beat_unit": 4})
        self.assertEqual(MeterAwareBeatGridNode().execute(bb), NodeStatus.SUCCESS)
        return bb

    def test_misplaced_downbeat_is_rotated_to_true_low_frequency_hit(self):
        bb = self._grid_blackboard()
        bb.set_val("y", self.y)
        bb.set_val("sr", self.sr)

        status = KickBassDownbeatVerifierNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        beats = bb.get_val("beats")
        # 1.0s and 3.0s were label=3 before the fix; the verifier should rotate
        # the downbeat label onto them since their low-freq energy dominates.
        rotated_times = beats[beats[:, 1] == 1][:, 0]
        np.testing.assert_allclose(sorted(rotated_times), [1.0, 3.0])

        report = bb.get_val("downbeat_fix_report")
        self.assertEqual(report["status"], "ROTATED")
        self.assertEqual(report["rotated_beat_count"], 2)
        np.testing.assert_array_equal(bb.get_val("refined_beats"), beats)


if __name__ == "__main__":
    unittest.main()
