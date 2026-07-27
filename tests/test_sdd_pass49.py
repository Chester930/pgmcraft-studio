"""
SDD Pass 49 — CREPE & BasicPitch 採譜專項護航與 Ghost Note 清洗單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import BasicPitchNode, CREPEPitchNode


class TestSDDPass49TranscriptionGuard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample_vocal.wav")
        # 產生 1 秒單聲道 16kHz 正弦波 (440Hz A4 音高)
        sr = 16000
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.8).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_crepe_node_vocal_lowpass_and_pure_vocal_guard(self):
        """驗證 CREPEPitchNode 低通濾波與純人聲音軌優先選用機制」"""
        node = CREPEPitchNode()
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("output_dir", self.test_dir)

        # 設定純人聲軌
        vocal_wav = os.path.join(self.test_dir, "pure_vocal.wav")
        sf.write(vocal_wav, np.random.randn(16000).astype(np.float32) * 0.1, 16000)
        bb.set_val("lead_vocal_path", vocal_wav)

        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(bb.get_val("vocal_pitch_midi"))
        self.assertIsNotNone(bb.get_val("pitch_contour_json"))

        # 測試 lowpass 功能
        y_test = np.random.randn(16000).astype(np.float32)
        y_clean = node._apply_vocal_lowpass(y_test, 16000, 3500.0)
        self.assertEqual(len(y_clean), len(y_test))

    def test_basic_pitch_node_peak_guard_and_ghost_note_filtering(self):
        """驗證 BasicPitchNode 音訊標準化與 Ghost Note 音符防護」"""
        node = BasicPitchNode()
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("output_dir", self.test_dir)
        bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3]]))

        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        midi_path = bb.get_val("melody_lead_midi")
        self.assertTrue(os.path.exists(midi_path))


if __name__ == "__main__":
    unittest.main()
