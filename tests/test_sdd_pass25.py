import unittest
import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import (
    SynthesizeHarmonicTrackNode,
    SynthesizeStructureTrackNode,
    build_music_analysis_tree,
    MusicAnalysisBTEngine
)

class TestSDDPass25(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_sdd25_output"
        os.makedirs(self.test_dir, exist_ok=True)
        self.sr = 22050
        self.duration = 3.0

        # 模擬人聲 (Vocals)
        self.vocals_path = os.path.join(self.test_dir, "vocals.wav")
        y_voc = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.vocals_path, y_voc, self.sr)

        # 模擬鼓組 (Drums)
        self.drums_path = os.path.join(self.test_dir, "drums.wav")
        y_drum = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.drums_path, y_drum, self.sr)

        # 模擬伴奏 (No Vocals / Instrumental)
        self.no_vocals_path = os.path.join(self.test_dir, "no_vocals.wav")
        y_inst = np.random.uniform(-0.1, 0.1, int(self.sr * self.duration)).astype(np.float32)
        sf.write(self.no_vocals_path, y_inst, self.sr)

    def test_synthesize_structure_track_node(self):
        """測試 Stage 4 樂段結構專屬 Sub-mix (Vocals+Drums+Other) 合成節點"""
        bb = Blackboard()
        bb.set_val("stems", {"vocals": self.vocals_path, "drums": self.drums_path, "instrumental": self.no_vocals_path})
        bb.set_val("stems_dir", self.test_dir)
        bb.set_val("audio_path", "sample_test.wav")

        node = SynthesizeStructureTrackNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        struct_path = bb.get_val("structure_track_path")
        self.assertIsNotNone(struct_path)
        self.assertTrue(os.path.exists(struct_path))

    def test_full_stage4_pass25_bt_engine(self):
        """測試 Pass 25 雙 Sub-mix 整合後之 Stage 4 BT 完整樹鏈」"""
        bb = Blackboard()
        bb.set_val("stems", {"vocals": self.vocals_path, "drums": self.drums_path, "instrumental": self.no_vocals_path})
        bb.set_val("stems_dir", self.test_dir)
        bb.set_val("audio_path", "sample_test.wav")

        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1], [2.5, 2]])
        bb.set_val("beats", beats)
        bb.set_val("beat_validation", {"status": "PASS"})

        engine = MusicAnalysisBTEngine()
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("music_analysis_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("harmonic_track_path"))
        self.assertIsNotNone(result_bb.get_val("structure_track_path"))
        self.assertIsNotNone(result_bb.get_val("sections"))

if __name__ == "__main__":
    unittest.main()
