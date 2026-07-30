"""
SDD Pass 118 — Module 3 BarStart v2: Ellis (2007) onset-phase realignment
wired onto the bar-start-first grid.

`MeterAwareBeatGridNode` only produces a geometrically even split inside each
committed bar; it never looks at the waveform. This pass wires the existing
Stage 3 `OnsetPhaseRealignmentNode` into the v2 export tree so every beat gets
snapped (+/-35ms) onto the nearest real onset before click synthesis reads it.
"""

import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import OnsetPhaseRealignmentNode
from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import MeterAwareBeatGridNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


class TestSDDPass118OnsetPhaseRealignmentInV2(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(self.sr * duration), False)
        y = np.zeros_like(t)
        # true onset impulses at 0.5s and 1.5s
        for beat_time in [0.5, 1.5]:
            idx = int(beat_time * self.sr)
            y[idx:idx + 100] = np.sin(2 * np.pi * 100 * np.linspace(0, 0.01, 100)) * 0.8
        self.y = y
        self.audio_path = os.path.join(self.test_dir, "synth_bar.wav")
        sf.write(self.audio_path, y, self.sr)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_v2_pipeline_places_onset_realignment_before_click_synthesis(self):
        names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
        self.assertIn("OnsetPhaseRealignmentNode", names)
        self.assertLess(names.index("MeterAwareBeatGridNode"), names.index("OnsetPhaseRealignmentNode"))
        self.assertLess(names.index("OnsetPhaseRealignmentNode"), names.index("ClickSynthesisNode"))

    def test_grid_beat_snaps_onto_real_onset(self):
        bb = Blackboard()
        # committed bar starts deliberately offset by 20ms from the real onsets;
        # beats_per_bar=2 puts a mid-bar beat exactly on the (offset) 0.52s/1.52s marks
        bb.set_val("committed_bar_starts", [0.02, 1.02, 2.02])
        bb.set_val("meter_profile", {"base_meter": "2/4", "beats_per_bar": 2, "beat_unit": 4})
        self.assertEqual(MeterAwareBeatGridNode().execute(bb), NodeStatus.SUCCESS)

        bb.set_val("y", self.y)
        bb.set_val("sr", self.sr)
        status = OnsetPhaseRealignmentNode().execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        realigned = bb.get_val("beats")
        # index 1 == the 0.52s grid beat, should snap back near the true 0.5s onset
        self.assertLess(abs(realigned[1, 0] - 0.5), 0.02)
        report = bb.get_val("phase_realignment_report")
        self.assertGreaterEqual(report["realigned_count"], 1)
        np.testing.assert_array_equal(bb.get_val("refined_beats"), realigned)


if __name__ == "__main__":
    unittest.main()
