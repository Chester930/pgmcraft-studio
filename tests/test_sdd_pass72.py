"""
SDD Pass 72 — Transcribe 工作流 4-3：爵士鼓與打擊樂器節拍聲軌採譜狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.transcribe_bt import build_transcribe_drum_pattern_workflow


class TestSDDPass72TranscribeDrumPatternWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "drum_loop.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 100 * t) * 0.5).astype(np.float32)  # Low frequency kick-like sound
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_transcribe_drum_pattern_execution(self):
        """驗證 TranscribeDrumPatternRoot 狀態機成功導出鼓 MIDI 與 JSON 報告」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_transcribe_drum_pattern_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        d_midi_p = blackboard.get_val("drum_midi_path")
        d_json_p = blackboard.get_val("drum_json_path")

        self.assertTrue(os.path.exists(d_midi_p))
        self.assertTrue(os.path.exists(d_json_p))


if __name__ == "__main__":
    unittest.main()
