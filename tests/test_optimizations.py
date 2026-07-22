import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.enhancer import (
    DynamicAudioChunker,
    StereoPhaseAligner,
    MIDIQuantizer,
    AudioEnhancerEngine
)

class TestAdvancedOptimizations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sr = 22050

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dynamic_audio_chunker_overlap_add(self):
        """測試低顯存適應性動態切片與 Hanning Crossfade 縫合"""
        chunker = DynamicAudioChunker()
        # 產生 15 秒測試音訊 (大於 10s chunk)
        t = np.linspace(0, 15, self.sr * 15, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)

        # 模擬 dummy 神經網路處理函數
        dummy_process = lambda seg: seg * 1.0

        y_processed = chunker.chunk_and_process(y, self.sr, dummy_process, chunk_duration=10.0, overlap_duration=0.5)
        self.assertEqual(len(y_processed), len(y))
        # 驗證無切峰與失真
        self.assertLessEqual(np.max(np.abs(y_processed)), 0.6)

    def test_stereo_phase_alignment(self):
        """測試希爾伯特轉換立體聲反相修正 (Phase Alignment)"""
        aligner = StereoPhaseAligner()
        t = np.linspace(0, 1, self.sr, endpoint=False)
        left = 0.5 * np.sin(2 * np.pi * 440 * t)
        right = -0.5 * np.sin(2 * np.pi * 440 * t) # 完全反相
        stereo = np.column_stack((left, right))

        aligned = aligner.align_stereo_phase(stereo)
        # 驗證右聲道已被修復對齊
        phase_diff_after = np.mean(aligned[:, 0] - aligned[:, 1])
        self.assertLess(np.abs(phase_diff_after), 0.1)

    def test_midi_quantization(self):
        """測試 MIDI 音符 1/16 拍自動網格量化"""
        quantizer = MIDIQuantizer()
        raw_notes = [
            {'pitch': 60, 'start_time': 0.012, 'end_time': 0.495}, # 近似 0.0 與 0.5 秒 (120 BPM 下的 1/4 拍)
            {'pitch': 64, 'start_time': 0.508, 'end_time': 0.998}
        ]
        q_notes = quantizer.quantize_notes(raw_notes, bpm=120.0, grid_fraction=16)
        self.assertEqual(q_notes[0]['start_time'], 0.0)
        self.assertEqual(q_notes[0]['end_time'], 0.5)

if __name__ == '__main__':
    unittest.main()
