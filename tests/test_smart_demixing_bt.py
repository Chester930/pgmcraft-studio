import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.smart_demixing_bt import (
    CheckAudioSNRConditionNode,
    DetectInstrumentPresenceNode,
    SmartPreprocessActionNode
)

class TestSmartDemixingBT(unittest.TestCase):
    def setUp(self):
        self.blackboard = Blackboard()
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "test_input.wav")
        # 產生 1 秒 Sine 波微弱音訊
        sr = 22050
        t = np.linspace(0, 1, sr, endpoint=False)
        y = 0.005 * np.sin(2 * np.pi * 440 * t) # 極小音量
        sf.write(self.test_wav, y, sr)

        self.blackboard.set_val("y", y)
        self.blackboard.set_val("sr", sr)
        self.blackboard.set_val("audio_path", self.test_wav)
        self.blackboard.set_val("output_dir", self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_snr_check_and_pre_amplification_guard(self):
        """測試微弱訊號被Guard偵測並觸發先降噪再增益防護」"""
        snr_guard = CheckAudioSNRConditionNode(min_rms_threshold=0.01)
        status = snr_guard.execute(self.blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(self.blackboard.get_val("need_pre_amplification"))

        preprocess = SmartPreprocessActionNode()
        status_prep = preprocess.execute(self.blackboard)
        self.assertEqual(status_prep, NodeStatus.SUCCESS)

    def test_instrument_presence_detection_guard(self):
        """測試樂器存在性檢測門控：不存在鋼琴時成功 Skip 分支」"""
        self.blackboard.set_val("detected_instruments", {"vocals": 0.9, "piano": 0.02})
        piano_guard = DetectInstrumentPresenceNode(target_instrument="piano", probability_threshold=0.20)
        status = piano_guard.execute(self.blackboard)
        self.assertEqual(status, NodeStatus.FAILURE) # 未達門檻，Skip 分拆！

if __name__ == '__main__':
    unittest.main()
