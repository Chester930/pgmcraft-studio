"""
SDD Pass 54 — P0 雙核升級 (Count-In Click 預備拍與 7/sus4/add9 擴展和弦識別) 單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.synthesizer import PGMSynthesizer
from pgm_craft.analyzer import CHORD_TEMPLATES, NOTE_NAMES


class TestSDDPass54P0Features(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample.wav")
        sr = 22050
        y = np.random.randn(sr * 2).astype(np.float32) * 0.1
        sf.write(self.audio_path, y, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_chord_templates_contain_extended_chords(self):
        """驗證 CHORD_TEMPLATES 已成功包含 7, maj7, m7, sus4, add9 擴展和弦樣板」"""
        for note in NOTE_NAMES:
            self.assertIn(f"{note}7", CHORD_TEMPLATES)
            self.assertIn(f"{note}maj7", CHORD_TEMPLATES)
            self.assertIn(f"{note}m7", CHORD_TEMPLATES)
            self.assertIn(f"{note}sus4", CHORD_TEMPLATES)
            self.assertIn(f"{note}add9", CHORD_TEMPLATES)

    def test_synthesize_click_count_in_guard_runs(self):
        """驗證 synthesize_click 正確產生帶 Count-In 預備拍之 click 檔案」"""
        synth = PGMSynthesizer()
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]])
        click_p, mix_p = synth.synthesize_click(
            self.audio_path, beats, output_dir=self.test_dir, prepend_count_in_bar=True
        )
        self.assertTrue(os.path.exists(click_p))
        self.assertTrue(os.path.exists(mix_p))


if __name__ == "__main__":
    unittest.main()
