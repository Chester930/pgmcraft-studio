import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import BeatFusionArbitratorNode

class TestSDDPass40(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        
        # 模擬 A 軌 (鼓組軌)：前 2 秒有鼓點，後 3 秒完全靜音 (低能量無鼓區)
        sr = 22050
        y_rhythm = np.zeros(sr * 5, dtype=np.float32)
        # 前 2 秒加入每 0.5 秒 (120 BPM) 的脈衝
        for t_s in [0.0, 0.5, 1.0, 1.5]:
            idx = int(t_s * sr)
            y_rhythm[idx:idx+500] = 0.8
            
        rhythm_path = os.path.join(self.test_dir, "track_a_rhythm.wav")
        sf.write(rhythm_path, y_rhythm, sr)
        
        # A 軌 AI 分析出的混亂拍點 (包含後 3 秒亂跳的拍點)
        beats_a = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.1, 2], [2.3, 3], [2.9, 1], [3.4, 2], [4.8, 4]  # 亂跳
        ])
        
        # B 軌 伴奏拍點
        beats_b = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4], [4.0, 1]
        ])
        
        self.blackboard.set_val("rhythm_track_path", rhythm_path)
        self.blackboard.set_val("beats_rhythm", beats_a)
        self.blackboard.set_val("beats_inst", beats_b)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_beat_fusion_tempo_inertia_on_low_energy(self):
        """驗證 BeatFusionArbitratorNode 在無鼓區間開啟 Tempo Inertia 速度慣性等速內插」"""
        node = BeatFusionArbitratorNode(energy_threshold=0.02)
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        beats = self.blackboard.get_val("beats")
        self.assertIsNotNone(beats)
        self.assertGreater(len(beats), 0)
        
        # 驗證無鼓段落的拍點間隔保持穩定 (~0.5s = 120 BPM)
        times = beats[:, 0].astype(float)
        diffs = np.diff(times)
        # 後半段的拍點間隔不應出現過短小於 0.3s 的亂跳
        self.assertTrue(np.all(diffs >= 0.3))

if __name__ == "__main__":
    unittest.main()
