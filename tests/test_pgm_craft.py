import unittest
import os
import shutil
import tempfile
from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.synthesizer import PGMSynthesizer
from pgm_craft.pipeline import PGMCraftEngine

class TestPGMCraftPackage(unittest.TestCase):
    def setUp(self):
        self.test_audio = "sample_test.wav"
        self.assertTrue(os.path.exists(self.test_audio), "sample_test.wav 測試檔不存在")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_analyzer_key_and_beats(self):
        """測試 PGMCraft MusicAnalyzer 調性與節拍估計"""
        analyzer = MusicAnalyzer(use_beatnet=False)
        beats = analyzer.track_beats(self.test_audio)
        self.assertGreater(len(beats), 0)

        key = analyzer.analyze_key(self.test_audio)
        self.assertIsInstance(key, str)
        self.assertIn("Major", key) if "Major" in key else self.assertIn("Minor", key)

        chords = analyzer.analyze_chords(self.test_audio, beats)
        self.assertGreater(len(chords), 0)

    def test_synthesizer_click_and_midi(self):
        """測試 PGMCraft PGMSynthesizer 節拍音檔與 MIDI 導出"""
        analyzer = MusicAnalyzer(use_beatnet=False)
        beats = analyzer.track_beats(self.test_audio)

        synth = PGMSynthesizer()
        click_path, mix_path = synth.synthesize_click(self.test_audio, beats, output_dir=self.temp_dir)
        midi_path = synth.export_midi_tempo_map(beats, output_dir=self.temp_dir)

        self.assertTrue(os.path.exists(click_path))
        self.assertTrue(os.path.exists(mix_path))
        self.assertTrue(os.path.exists(midi_path))

    def test_engine_pipeline(self):
        """測試 PGMCraftEngine 完整 Pipeline"""
        engine = PGMCraftEngine(enable_stem_separation=False)
        report = engine.run(self.test_audio, output_dir=self.temp_dir)

        self.assertIn("estimated_key", report)
        self.assertIn("average_bpm", report)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "pgm_report.json")))

if __name__ == '__main__':
    unittest.main()
