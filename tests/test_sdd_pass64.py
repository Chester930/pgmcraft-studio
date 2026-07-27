"""
SDD Pass 64 — Vlog 工作流 2-2：影片對白與背景音樂 (BGM) 二分抽離狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vlog_bt import build_vlog_dialogue_bgm_split_workflow


class TestSDDPass64DialogueBGMSplitWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "vlog_with_bgm.wav")
        # 產生混合測試聲波
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 300 * t) * 0.2 + np.sin(2 * np.pi * 600 * t) * 0.1).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vlog_dialogue_bgm_split_execution(self):
        """驗證 VlogDialogueBGMSplitRoot 狀態機成功抽離對白與 BGM」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vlog_dialogue_bgm_split_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        dia_p = blackboard.get_val("isolated_dialogue_path")
        bgm_p = blackboard.get_val("isolated_bgm_path")

        self.assertTrue(os.path.exists(dia_p))
        self.assertTrue(os.path.exists(bgm_p))


if __name__ == "__main__":
    unittest.main()
