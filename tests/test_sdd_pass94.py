"""
SDD Pass 94 — CheckAudioSNRConditionNode 防禦性波形 Lazy Load 測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.smart_demixing_bt import CheckAudioSNRConditionNode


class TestSDDPass94SmartDemixingLazyLoad(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "lazy_test.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = 0.3 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_audio_snr_lazy_load_when_y_is_none(self):
        """驗證當 y 未填寫時，CheckAudioSNRConditionNode 能自動從 audio_path 加載並成功執行"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_wav)
        self.assertIsNone(blackboard.get_val("y"))

        node = CheckAudioSNRConditionNode()
        status = node.run(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(blackboard.get_val("y"))
        self.assertEqual(blackboard.get_val("sr"), 22050)
        self.assertIn("rms_level", blackboard)

    def test_check_audio_snr_fails_gracefully_when_no_audio(self):
        """驗證當既無 y 也無有效 audio_path 時安全返回 FAILURE"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", "non_existent_file.wav")

        node = CheckAudioSNRConditionNode()
        status = node.run(blackboard)
        self.assertEqual(status, NodeStatus.FAILURE)


if __name__ == "__main__":
    unittest.main()
