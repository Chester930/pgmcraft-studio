import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import HarmonicSilenceGateNode

class TestSDDPass43(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        
        # 建立測試和聲音軌：前 2 秒完全靜音 (0.0)，後 2 秒有聲音
        sr = 22050
        y_harm = np.zeros(sr * 4, dtype=np.float32)
        y_harm[sr * 2:] = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2))
        
        harm_path = os.path.join(self.test_dir, "track_stage4_harmonic.wav")
        sf.write(harm_path, y_harm, sr)
        
        # 模擬原本在靜音區誤判的 Ghost Chords
        chords = [
            {"measure": 1, "start_time": 0.0, "end_time": 1.0, "chord": "C#m"},
            {"measure": 2, "start_time": 1.0, "end_time": 2.0, "chord": "D#dim"},
            {"measure": 3, "start_time": 2.0, "end_time": 3.0, "chord": "C Major"},
            {"measure": 4, "start_time": 3.0, "end_time": 4.0, "chord": "G Major"}
        ]
        
        self.blackboard.set_val("harmonic_track_path", harm_path)
        self.blackboard.set_val("chord_progression", chords)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_harmonic_silence_gate_removes_ghost_chords(self):
        """驗證 HarmonicSilenceGateNode 能在靜音區間將 Ghost Chords 重置為 N/A」"""
        node = HarmonicSilenceGateNode(silence_threshold=0.01)
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        gated_chords = self.blackboard.get_val("chord_progression")
        self.assertIsNotNone(gated_chords)
        
        # 前 2 小節因為 RMS < 0.01 應被重置為 N/A
        self.assertEqual(gated_chords[0]["chord"], "N/A")
        self.assertEqual(gated_chords[1]["chord"], "N/A")
        # 後 2 小節保留原始和弦
        self.assertEqual(gated_chords[2]["chord"], "C Major")
        self.assertEqual(gated_chords[3]["chord"], "G Major")

if __name__ == "__main__":
    unittest.main()
