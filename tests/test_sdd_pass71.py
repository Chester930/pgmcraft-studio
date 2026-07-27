"""
SDD Pass 71 — Transcribe 工作流 4-2：爵士/流行樂曲和弦與調性分析報告狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.transcribe_bt import build_transcribe_chord_key_workflow


class TestSDDPass71TranscribeChordKeyWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "pop_song.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 261.63 * t) * 0.4).astype(np.float32)  # C4 Note
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_transcribe_chord_key_execution(self):
        """驗證 TranscribeChordKeyRoot 狀態機成功估算調性與和弦報告」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_transcribe_chord_key_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        report_p = blackboard.get_val("chord_key_json_path")
        est_key = blackboard.get_val("estimated_key")

        self.assertTrue(os.path.exists(report_p))
        self.assertIn("Major", est_key)


if __name__ == "__main__":
    unittest.main()
