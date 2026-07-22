import unittest
import os
import shutil
import tempfile
from pgm_craft.music_ai import NonDemixingMusicAIEngine

class TestNonDemixingMusicAI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_audio_to_midi_transcription(self):
        """測試 Basic Pitch 音訊轉多音階 MIDI 採譜功能"""
        engine = NonDemixingMusicAIEngine()
        out_midi = os.path.join(self.temp_dir, "polyphonic_notes.mid")
        res = engine.audio_to_midi_transcription(self.test_wav, out_midi)
        self.assertTrue(os.path.exists(res))

    def test_vocal_pitch_tracking_crepe(self):
        """測試 CREPE 微秒級人聲音高音準分析功能"""
        engine = NonDemixingMusicAIEngine()
        pitch_data = engine.pitch_estimation_crepe(self.test_wav)
        self.assertIn("frequencies_hz", pitch_data)

    def test_music_structure_segmentation(self):
        """測試樂段結構識別 (Intro/Verse/Chorus/Bridge)"""
        engine = NonDemixingMusicAIEngine()
        sections = engine.detect_song_sections(self.test_wav)
        self.assertEqual(sections[0]["section"], "Intro")
        self.assertEqual(sections[2]["section"], "Chorus 1")

if __name__ == '__main__':
    unittest.main()
