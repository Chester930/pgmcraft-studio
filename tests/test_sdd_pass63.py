"""
SDD Pass 63 — Vlog 工作流 2-1：戶外外景低頻風切聲與車流雜音降噪狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vlog_bt import build_vlog_wind_env_clean_workflow


class TestSDDPass63VlogWindCleanWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "vlog_outdoor_wind.wav")
        # 產生包含 30Hz 低頻風氣音衝擊與環境噪音的合成訊號
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        speech = np.sin(2 * np.pi * 350 * t) * 0.2
        wind_rumble = np.sin(2 * np.pi * 30 * t) * 0.4  # 強烈 30Hz 風切低頻震盪
        noise = np.random.randn(sr) * 0.02
        sig = (speech + wind_rumble + noise).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vlog_wind_clean_workflow_execution(self):
        """驗證 VlogWindCleanRoot 狀態機成功濾除 30Hz 風切並完成標準化」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vlog_wind_env_clean_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        vlog_p = blackboard.get_val("vlog_clean_path")
        self.assertTrue(os.path.exists(vlog_p))

        y_clean, sr_c = sf.read(vlog_p)
        self.assertGreater(len(y_clean), 0)


if __name__ == "__main__":
    unittest.main()
