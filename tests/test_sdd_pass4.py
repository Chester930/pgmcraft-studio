"""
Unit tests for Pass 4 Engineering Optimizations:
Module 1: Chord Extension Annotation in MusicAnalyzer
Module 2: -1.0 dBFS Peak & Loudness Guard in PGMSynthesizer
"""

import os
import numpy as np
import pytest
from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.synthesizer import PGMSynthesizer


def test_chord_extension_annotation(tmp_path):
    analyzer = MusicAnalyzer()
    # Create test dummy wav
    audio_path = os.path.join(tmp_path, "test.wav")
    import soundfile as sf
    sf.write(audio_path, np.zeros(22050 * 2), 22050)

    beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1]])
    chords = analyzer.analyze_chords(audio_path, beats)

    assert len(chords) > 0
    assert "extension" in chords[0]
    assert chords[0]["extension"] in ("Triad", "7th/Extended")


def test_peak_guard_in_synthesizer(tmp_path):
    synth = PGMSynthesizer()
    audio_path = os.path.join(tmp_path, "loud_test.wav")
    import soundfile as sf
    # High amplitude audio
    sf.write(audio_path, np.ones(22050 * 2) * 0.9, 22050)

    beats = [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4)]
    click_path, mix_path = synth.synthesize_click(audio_path, beats, output_dir=str(tmp_path))

    import librosa
    y_mix, _ = librosa.load(mix_path, sr=22050)
    max_peak = np.max(np.abs(y_mix))

    # Peak must be clamped below -1.0 dBFS (<= 0.895)
    assert max_peak <= 0.895
