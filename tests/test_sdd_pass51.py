"""
SDD Pass 51 — 變拍子動態感應與 REAPER .RPP 原生工程導出單元測試
"""

import os
import tempfile
import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import DownbeatRefineNode
from pgm_craft.daw_exporter import DAWExporter


class TestSDDPass51MeterAndREAPERExport(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_downbeat_refine_waltz_3_4_time_signature_detection(self):
        """驗證 DownbeatRefineNode 動態識別 3/4 拍號（華爾滋拍）」"""
        node = DownbeatRefineNode()
        bb = Blackboard()
        # 每 3 拍一循環
        timestamps = np.linspace(0, 60 * 0.5, 60)
        beat_numbers = (np.arange(60) % 3) + 1
        beats = np.column_stack([timestamps, beat_numbers])
        bb.set_val("beats", beats)

        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        time_sig = bb.get_val("time_signature")
        self.assertEqual(time_sig, "3/4")

    def test_reaper_rpp_project_export(self):
        """驗證 DAWExporter 能正確產出包含 Bus, Markers, Click Track 的 .RPP 專案檔」"""
        exporter = DAWExporter()
        report = {
            "average_bpm": 128.0,
            "chord_progression": [{"measure": 1, "start_time": 0.0, "chord": "C Major"}],
            "sections": [{"measure": 1, "name": "Intro"}],
            "outputs": {"click_track": os.path.join(self.test_dir, "click.wav")}
        }
        rpp_path = exporter.export_reaper_project(report, output_dir=self.test_dir)
        self.assertTrue(os.path.exists(rpp_path))

        with open(rpp_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("REAPER_PROJECT", content)
        self.assertIn("RHYTHM BUS", content)
        self.assertIn("TEMPO 128.0", content)


if __name__ == "__main__":
    unittest.main()
