import unittest
import os
import numpy as np

class TestBeatNetEngine(unittest.TestCase):
    def setUp(self):
        self.audio_path = "sample_test.wav"
        self.assertTrue(os.path.exists(self.audio_path), "測試用 sample_test.wav 檔不存在")

    def test_beatnet_import_and_inference(self):
        """測試 BeatNet 模型導入與離線推論功能"""
        try:
            from BeatNet.BeatNet import BeatNet
        except ImportError:
            self.skipTest("環境未安裝 BeatNet，跳過測試")

        estimator = BeatNet(1, mode='offline', inference_model='DBN', plot=[], thread=False)
        output = estimator.process(self.audio_path)

        self.assertIsNotNone(output, "BeatNet 輸出不應為 None")
        self.assertGreater(len(output), 0, "BeatNet 應追蹤出至少一個節拍")
        self.assertEqual(output.shape[1], 2, "輸出維度應為 (N, 2)，包含 [時間戳, 拍標籤]")
        
        # 驗證拍標籤範圍 (1 為 Downbeat, 2-4 為普通拍)
        labels = output[:, 1]
        self.assertTrue(np.all((labels >= 1) & (labels <= 4)), "拍標籤應在 1 到 4 之間")

if __name__ == '__main__':
    unittest.main()
