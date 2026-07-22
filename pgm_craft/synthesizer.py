"""
PGMCraft PGM Synthesizer Module
Synthesizes Click Tracks and exports MIDI Tempo Maps for DAW / Live PGM sync.
"""

import os
import numpy as np
import soundfile as sf
import pretty_midi
import librosa

class PGMSynthesizer:
    def synthesize_click(self, audio_path, beats, output_dir="outputs"):
        """Synthesizes high/low click track and mixes with original audio."""
        os.makedirs(output_dir, exist_ok=True)
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        total_samples = len(y)
        click_audio = np.zeros(total_samples)

        # High click (1000Hz) for Beat 1, Low click (600Hz) for Beats 2-4
        t_click = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
        high_click = 0.8 * np.sin(2 * np.pi * 1000 * t_click) * np.exp(-t_click * 60)
        low_click = 0.5 * np.sin(2 * np.pi * 600 * t_click) * np.exp(-t_click * 60)

        for timestamp, beat_num in beats:
            idx = int(timestamp * sr)
            if idx >= total_samples:
                continue
            click_wave = high_click if int(beat_num) == 1 else low_click
            end_idx = min(idx + len(click_wave), total_samples)
            actual_len = end_idx - idx
            click_audio[idx:end_idx] += click_wave[:actual_len]

        click_path = os.path.join(output_dir, "click_track.wav")
        mix_path = os.path.join(output_dir, "mix_with_click.wav")

        sf.write(click_path, click_audio, sr)
        mixed = 0.7 * y + 0.5 * click_audio
        max_val = np.max(np.abs(mixed))
        if max_val > 1.0:
            mixed /= max_val
        sf.write(mix_path, mixed, sr)

        return click_path, mix_path

    def export_midi_tempo_map(self, beats, output_dir="outputs"):
        """Exports MIDI file with tempo map & click notes for DAW import."""
        os.makedirs(output_dir, exist_ok=True)
        pm = pretty_midi.PrettyMIDI()
        click_inst = pretty_midi.Instrument(program=115) # Woodblock

        for timestamp, beat_num in beats:
            pitch = 76 if int(beat_num) == 1 else 77
            note = pretty_midi.Note(
                velocity=115 if int(beat_num) == 1 else 85,
                pitch=pitch,
                start=float(timestamp),
                end=float(timestamp) + 0.05
            )
            click_inst.notes.append(note)

        pm.instruments.append(click_inst)
        midi_path = os.path.join(output_dir, "tempo_map.mid")
        pm.write(midi_path)
        return midi_path
