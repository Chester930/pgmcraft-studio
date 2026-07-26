import unittest
import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import (
    SynthesizeHarmonicTrackNode,
    build_music_analysis_tree,
    MusicAnalysisBTEngine
)

class TestSDDPass24(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_sdd24_output"
        os.makedirs(self.test_dir, exist_ok=True)
        self.sr = 22050
        self.duration = 3.0

        # 模擬鋼琴軌 (Piano)
        self.piano_path = os.path.join(self.test_dir, "piano.wav")
        y_piano = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.piano_path, y_piano, self.sr)

        # 模擬吉他軌 (Guitar)
        self.guitar_path = os.path.join(self.test_dir, "guitar.wav")
        y_guitar = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.guitar_path, y_guitar, self.sr)

        # 模擬貝斯軌 (Bass)
        self.bass_path = os.path.join(self.test_dir, "bass.wav")
        y_bass = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.bass_path, y_bass, self.sr)

    def test_synthesize_harmonic_track_node(self):
        """測試 Stage 4 和聲專屬 Sub-mix (Piano+Guitar+Bass) 合成節點"""
        bb = Blackboard()
        bb.set_val("stems", {"piano": self.piano_path, "guitar": self.guitar_path, "bass": self.bass_path})
        bb.set_val("stems_dir", self.test_dir)
        bb.set_val("audio_path", "sample_test.wav")

        node = SynthesizeHarmonicTrackNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        harm_path = bb.get_val("harmonic_track_path")
        self.assertIsNotNone(harm_path)
        self.assertTrue(os.path.exists(harm_path))

    def test_full_stage4_bt_engine(self):
        """測試 Stage 4 BT Engine 完整樹鏈與和聲分析」"""
        bb = Blackboard()
        bb.set_val("stems", {"piano": self.piano_path, "guitar": self.guitar_path, "bass": self.bass_path})
        bb.set_val("stems_dir", self.test_dir)
        bb.set_val("audio_path", "sample_test.wav")
        
        # 提供假節拍 (Stage 3 輸出契約)
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1], [2.5, 2]])
        bb.set_val("beats", beats)
        bb.set_val("beat_validation", {"status": "PASS"})

        engine = MusicAnalysisBTEngine()
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("music_analysis_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("estimated_key"))
        self.assertIsNotNone(result_bb.get_val("chord_progression"))

if __name__ == "__main__":
    unittest.main()
