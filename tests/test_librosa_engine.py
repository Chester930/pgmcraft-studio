import unittest
import os
import numpy as np
import librosa

class TestLibrosaEngine(unittest.TestCase):
    def setUp(self):
        self.audio_path = "sample_test.wav"
        self.assertTrue(os.path.exists(self.audio_path), "測試用 sample_test.wav 檔不存在")

    def test_audio_loading(self):
        """測試 Librosa 音訊讀取能力"""
        y, sr = librosa.load(self.audio_path, sr=22050, mono=True)
        self.assertGreater(len(y), 0, "音訊資料讀取為空")
        self.assertEqual(sr, 22050, "採樣率與預期不符")

    def test_beat_tracking(self):
        """測試 Librosa 節拍追蹤與時間戳產生"""
        y, sr = librosa.load(self.audio_path, sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        
        self.assertGreater(tempo, 0, "估計 BPM 應大於 0")
        self.assertGreater(len(beat_times), 0, "應至少追蹤到一個節拍點")
        self.assertTrue(np.all(np.diff(beat_times) > 0), "節拍時間戳必須嚴格遞增")

if __name__ == '__main__':
    unittest.main()
