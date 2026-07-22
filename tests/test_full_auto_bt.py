import unittest
import os
import shutil
import tempfile
from pgm_craft.workflow.full_auto_bt import FullAutoDemixingBTEngine

class TestFullAutoDemixingBT(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_auto_bt_pipeline(self):
        """測試全自動需求驅動分軌行為樹 BT 流程 (跳過鋼琴/弦樂無謂拆分)"""
        engine = FullAutoDemixingBTEngine()
        probs = {
            "vocals": 0.90,
            "drums": 0.80,
            "bass": 0.70,
            "guitar": 0.50,
            "piano": 0.05,  # 預期 Skip
            "strings": 0.02 # 預期 Skip
        }
        stems = engine.run_full_auto_demixing(self.test_wav, output_dir=self.temp_dir, instrument_probs=probs)
        self.assertIn("vocals", stems)
        self.assertIn("drums", stems)
        self.assertIn("bass", stems)
        self.assertNotIn("piano", stems) # 驗證已被 Guard 安全 Skip 跳過！

if __name__ == '__main__':
    unittest.main()
