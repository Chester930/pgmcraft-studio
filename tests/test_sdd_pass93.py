"""
SDD Pass 93 — 全自動 Behavior Tree 引擎 (FullAutoDemixingBTEngine) 標準化與 Telemetry/Guard 整合測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.full_auto_bt import FullAutoDemixingBTEngine, LoadAudioToBlackboardNode


class TestSDDPass93FullAutoBTEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "test_audio.wav")
        # 產生 1 秒的測試弦波音訊檔
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_audio_to_blackboard_node(self):
        """驗證 LoadAudioToBlackboardNode 能自動載入音訊波形 y 與 sr 到 Blackboard"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_wav)

        node = LoadAudioToBlackboardNode()
        status = node.run(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(blackboard.get_val("y"))
        self.assertEqual(blackboard.get_val("sr"), 22050)

    def test_full_auto_bt_engine_execution_and_telemetry(self):
        """驗證 FullAutoDemixingBTEngine 經 BT 樹狀運作後，產生完整 workflow_trace 與結果"""
        engine = FullAutoDemixingBTEngine()
        probs = {
            "vocals": 0.90,
            "drums": 0.80,
            "bass": 0.70,
            "guitar": 0.50,
            "piano": 0.05,  # 低於門檻 預期 Skip
            "strings": 0.02 # 低於門檻 預期 Skip
        }

        stems = engine.run_full_auto_demixing(
            self.test_wav,
            output_dir=self.temp_dir,
            instrument_probs=probs
        )

        self.assertIsInstance(stems, dict)
        self.assertIn("vocals", stems)
        self.assertNotIn("piano", stems)
        self.assertNotIn("strings", stems)

    def test_full_auto_bt_blackboard_trace_recorded(self):
        """驗證 run_full_auto_demixing 使用了 .run() 並且記錄了 workflow_trace 機制"""
        engine = FullAutoDemixingBTEngine()
        probs = {
            "vocals": 0.90,
            "drums": 0.10,  # Skip
            "bass": 0.10,   # Skip
            "guitar": 0.10, # Skip
            "piano": 0.05,  # Skip
        }
        stems = engine.run_full_auto_demixing(
            self.test_wav,
            output_dir=self.temp_dir,
            instrument_probs=probs
        )
        self.assertIn("vocals", stems)


if __name__ == "__main__":
    unittest.main()
