import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import KickSnarePulseNode

class TestSDDPass39(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        
        # 建立測試 Kick WAV (包含在 t=0.0s 與 t=2.0s 的大鼓脈衝)
        sr = 22050
        y_kick = np.zeros(sr * 4, dtype=np.float32)
        # 加入 60Hz 大鼓脈衝
        t_p = np.linspace(0, 0.1, int(sr * 0.1), endpoint=False)
        pulse = 0.8 * np.sin(2 * np.pi * 60 * t_p) * np.exp(-t_p * 20)
        y_kick[0:len(pulse)] += pulse
        y_kick[int(2.0 * sr):int(2.0 * sr) + len(pulse)] += pulse
        
        kick_path = os.path.join(self.test_dir, "kick.wav")
        sf.write(kick_path, y_kick, sr)
        
        stems = {"kick": kick_path}
        self.blackboard.set_val("stems", stems)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_kick_snare_pulse_node_extracts_kick_anchors(self):
        """驗證 KickSnarePulseNode 能成功提取大鼓脈衝點並寫入 kick_anchors」"""
        node = KickSnarePulseNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        kick_anchors = self.blackboard.get_val("kick_anchors")
        self.assertIsNotNone(kick_anchors)
        self.assertGreater(len(kick_anchors), 0)
        # 第一拍應接近 0.0s
        self.assertAlmostEqual(kick_anchors[0], 0.0, delta=0.1)

if __name__ == "__main__":
    unittest.main()
