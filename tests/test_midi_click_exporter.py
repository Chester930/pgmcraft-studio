import unittest
import os
import tempfile
import numpy as np
import soundfile as sf
import pretty_midi

class TestMidiClickExporter(unittest.TestCase):
    def setUp(self):
        # 模擬節拍時間戳資料: [時間戳, 拍數]
        self.fake_beats = np.array([
            [0.5, 1], # 小節第1拍 (強拍)
            [1.0, 2], # 第2拍 (弱拍)
            [1.5, 3], # 第3拍 (弱拍)
            [2.0, 4], # 第4拍 (弱拍)
            [2.5, 1], # 小節第1拍 (強拍)
        ])
        self.temp_dir = tempfile.mkdtemp()

    def test_click_track_synthesis(self):
        """測試 Click 音效合成邏輯與長度正確性"""
        sr = 22050
        duration = 3.0
        total_samples = int(duration * sr)
        click_audio = np.zeros(total_samples)
        
        # 合成高/低音 Sine 波 Click
        t_click = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
        high_click = 0.8 * np.sin(2 * np.pi * 1000 * t_click) * np.exp(-t_click * 60)
        low_click = 0.5 * np.sin(2 * np.pi * 600 * t_click) * np.exp(-t_click * 60)

        for timestamp, beat_num in self.fake_beats:
            idx = int(timestamp * sr)
            click_wave = high_click if int(beat_num) == 1 else low_click
            end_idx = min(idx + len(click_wave), total_samples)
            actual_len = end_idx - idx
            click_audio[idx:end_idx] += click_wave[:actual_len]

        output_wav = os.path.join(self.temp_dir, "test_click.wav")
        sf.write(output_wav, click_audio, sr)
        
        self.assertTrue(os.path.exists(output_wav))
        read_data, read_sr = sf.read(output_wav)
        self.assertEqual(len(read_data), total_samples)
        self.assertGreater(np.max(np.abs(read_data)), 0.1, "Click 音軌振幅應包含合成訊號")

    def test_midi_export(self):
        """測試 Pretty_MIDI Tempo Map / Beat Note 寫入能力"""
        pm = pretty_midi.PrettyMIDI()
        inst = pretty_midi.Instrument(program=115) # Woodblock / Percussion
        
        for timestamp, beat_num in self.fake_beats:
            pitch = 76 if int(beat_num) == 1 else 77
            note = pretty_midi.Note(
                velocity=110 if int(beat_num) == 1 else 80,
                pitch=pitch,
                start=timestamp,
                end=timestamp + 0.05
            )
            inst.notes.append(note)

        pm.instruments.append(inst)
        output_mid = os.path.join(self.temp_dir, "test_tempo_map.mid")
        pm.write(output_mid)

        self.assertTrue(os.path.exists(output_mid))
        loaded_pm = pretty_midi.PrettyMIDI(output_mid)
        self.assertEqual(len(loaded_pm.instruments[0].notes), len(self.fake_beats))

if __name__ == '__main__':
    unittest.main()
