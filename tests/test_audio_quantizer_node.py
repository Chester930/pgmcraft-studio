"""
AudioQuantizerNode 自動節拍量化對齊節點單元測試
"""

import numpy as np
import unittest
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import AudioQuantizerNode

class TestAudioQuantizerNode(unittest.TestCase):
    def setUp(self):
        self.blackboard = Blackboard()
        sr = 22050
        y = np.zeros(sr * 2) # 2 秒音訊
        # 在 0.49s 產生突發脈衝 (相對於 0.50s 的理想拍點微幅偏移 -10ms)
        y[int(0.49 * sr)] = 1.0
        
        self.blackboard.set_val("y", y)
        self.blackboard.set_val("sr", sr)
        # 傳入包含時間戳與拍標籤的 beats list: [[0.50, 1], [1.00, 2], [1.50, 3]]
        self.blackboard.set_val("beats", np.array([[0.50, 1], [1.00, 2], [1.50, 3]]))

    def test_audio_quantizer_execution(self):
        """測試 AudioQuantizerNode 能計算量化格點對齊與平均偏移 ms"""
        node = AudioQuantizerNode(grid_resolution=16) # 16 分音符格點對齊
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        quantized_beats = self.blackboard.get_val("quantized_beats")
        offset_ms = self.blackboard.get_val("quantization_offset_ms")
        
        self.assertIsNotNone(quantized_beats)
        self.assertIsNotNone(offset_ms)
        self.assertIsInstance(offset_ms, float)
        self.assertEqual(len(quantized_beats), 3)

if __name__ == '__main__':
    unittest.main()
