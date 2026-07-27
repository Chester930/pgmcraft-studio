import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import MultiBandChromaKeyNode

class TestSDDPass45(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        
        # 建立測試 Bass 與 Harmonic 音軌 (130.81Hz = C3, 440Hz = A4)
        sr = 22050
        t = np.linspace(0, 2, sr * 2)
        y_bass = 0.6 * np.sin(2 * np.pi * 130.81 * t)
        y_harm = 0.5 * np.sin(2 * np.pi * 261.63 * t) + 0.5 * np.sin(2 * np.pi * 329.63 * t) # C4, E4
        
        bass_path = os.path.join(self.test_dir, "bass.wav")
        harm_path = os.path.join(self.test_dir, "harmonic.wav")
        sf.write(bass_path, y_bass, sr)
        sf.write(harm_path, y_harm, sr)
        
        stems = {"bass": bass_path}
        self.blackboard.set_val("stems", stems)
        self.blackboard.set_val("harmonic_track_path", harm_path)
        self.blackboard.set_val("estimated_key", "C Major")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_multiband_chroma_key_node_success(self):
        """驗證 MultiBandChromaKeyNode 成功執行並輸出優化後之 estimated_key」"""
        node = MultiBandChromaKeyNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        key = self.blackboard.get_val("estimated_key")
        self.assertIsNotNone(key)
        self.assertIn("Major", key)

if __name__ == "__main__":
    unittest.main()
