import unittest
import os
import tempfile
import numpy as np
import soundfile as sf
import mido

from pgm_craft.synthesizer import PGMSynthesizer

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
        """測試 tempo_map.mid 真的包含 DAW 可讀的 tempo meta event"""
        synth = PGMSynthesizer()
        output_mid = synth.export_midi_tempo_map(self.fake_beats, output_dir=self.temp_dir)

        self.assertTrue(os.path.exists(output_mid))
        loaded_mid = mido.MidiFile(output_mid)
        tempo_events = [
            msg
            for track in loaded_mid.tracks
            for msg in track
            if msg.type == "set_tempo"
        ]
        anchor_notes = [
            msg
            for track in loaded_mid.tracks
            for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        ]
        self.assertGreaterEqual(len(tempo_events), 1)
        self.assertGreaterEqual(len(anchor_notes), 1)

    def test_midi_click_guide_export(self):
        """測試 click_guide.mid 保留逐拍 MIDI click notes"""
        synth = PGMSynthesizer()
        output_mid = synth.export_midi_click_guide(self.fake_beats, output_dir=self.temp_dir)

        self.assertTrue(os.path.exists(output_mid))
        loaded_mid = mido.MidiFile(output_mid)
        click_notes = [
            msg
            for track in loaded_mid.tracks
            for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        ]
        self.assertEqual(len(click_notes), len(self.fake_beats))

    def test_midi_chord_guide_export(self):
        """測試 chord_guide.mid 的 MIDI 和弦導引軌與 Marker 標記產出"""
        synth = PGMSynthesizer()
        fake_chords = [
            {"measure": 1, "chord": "Cmaj", "start_time": 0.5, "end_time": 2.5},
            {"measure": 2, "chord": "Amin", "start_time": 2.5, "end_time": 4.5},
        ]
        output_mid = synth.export_midi_chord_guide(fake_chords, self.fake_beats, output_dir=self.temp_dir)

        self.assertTrue(os.path.exists(output_mid))
        loaded_mid = mido.MidiFile(output_mid)

        markers = [
            msg
            for track in loaded_mid.tracks
            for msg in track
            if msg.type == "marker"
        ]
        chord_notes = [
            msg
            for track in loaded_mid.tracks
            for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        ]

        self.assertGreaterEqual(len(markers), 2)
        self.assertGreaterEqual(len(chord_notes), 2)
        self.assertIn("Cmaj", markers[0].text)

if __name__ == '__main__':
    unittest.main()

