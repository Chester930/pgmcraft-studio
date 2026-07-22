import unittest
import os
import shutil
import tempfile
from pgm_craft.podcast_ai import PodcastAIEngine

class TestPodcastAIEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_speaker_diarization(self):
        """測試 Podcast 多人對話 (Host vs Guest) 聲紋分離"""
        engine = PodcastAIEngine()
        res = engine.separate_speakers_diarization(self.test_wav, self.temp_dir)
        self.assertTrue(os.path.exists(res["host"]))
        self.assertTrue(os.path.exists(res["guest"]))

    def test_speech_to_text_whisper(self):
        """測試 Whisper 廣播級語音轉逐字稿"""
        engine = PodcastAIEngine()
        transcript = engine.speech_to_text_transcription(self.test_wav)
        self.assertGreater(len(transcript), 0)
        self.assertEqual(transcript[0]["speaker"], "Host")

    def test_broadcast_voice_enhancer(self):
        """測試廣播級聲音優化 (De-Hum + De-Esser)"""
        engine = PodcastAIEngine()
        out_wav = os.path.join(self.temp_dir, "enhanced_voice.wav")
        res = engine.broadcast_voice_enhancer(self.test_wav, out_wav)
        self.assertTrue(os.path.exists(res))

if __name__ == '__main__':
    unittest.main()
