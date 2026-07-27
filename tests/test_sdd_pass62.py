"""
SDD Pass 62 — Podcast 工作流 1-3：Talking Head 獨立語音抽出與背景音分離狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.podcast_bt import build_podcast_voice_isolation_workflow


class TestSDDPass62VoiceIsolationWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample_test.wav")
        # 產生混合測試聲波
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.2 + np.sin(2 * np.pi * 880 * t) * 0.1).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_podcast_voice_isolation_execution(self):
        """驗證 PodcastVoiceIsolationRoot 狀態機成功抽離說話聲與 BGM」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_podcast_voice_isolation_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        sp_p = blackboard.get_val("isolated_speech_path")
        bgm_p = blackboard.get_val("isolated_bgm_path")

        self.assertTrue(os.path.exists(sp_p))
        self.assertTrue(os.path.exists(bgm_p))


if __name__ == "__main__":
    unittest.main()
