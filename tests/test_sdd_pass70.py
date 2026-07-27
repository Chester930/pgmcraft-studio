"""
SDD Pass 70 — Transcribe 工作流 4-1：鋼琴/吉他獨奏與多音音符自動轉 MIDI 狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.transcribe_bt import build_transcribe_instrument_midi_workflow


class TestSDDPass70TranscribeMidiWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "solo_piano.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_transcribe_instrument_midi_execution(self):
        """驗證 TranscribeInstrumentMidiRoot 狀態機成功匯出 MIDI 與 JSON 報告」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_transcribe_instrument_midi_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        midi_p = blackboard.get_val("transcribed_midi_path")
        json_p = blackboard.get_val("transcription_json_path")

        self.assertTrue(os.path.exists(midi_p))
        self.assertTrue(os.path.exists(json_p))


if __name__ == "__main__":
    unittest.main()
