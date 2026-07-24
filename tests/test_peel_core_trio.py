"""
Unit tests for PeelCoreTrioStemSeparator (Guitar, Piano, Strings Dynamic Peel-and-Subtract Engine)
"""

import os
import pytest
import numpy as np
import scipy.io.wavfile as wavfile
from pgm_craft.separator import PeelCoreTrioStemSeparator


@pytest.fixture
def dummy_audio_file(tmp_path):
    sr = 22050
    duration = 3.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # A mix of harmonics simulating an instrumental track
    audio = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    audio_int16 = (audio * 32767).astype(np.int16)

    file_path = tmp_path / "test_instrumental.wav"
    wavfile.write(str(file_path), sr, audio_int16)
    return str(file_path)


def test_probe_core_trio_scores(dummy_audio_file):
    separator = PeelCoreTrioStemSeparator()
    scores = separator.probe_core_trio_scores(dummy_audio_file)

    assert isinstance(scores, dict)
    assert "guitar" in scores
    assert "piano" in scores
    assert "strings" in scores
    for k, v in scores.items():
        assert 0.0 <= v <= 1.0


def test_run_peel_trio_loop(dummy_audio_file, tmp_path):
    separator = PeelCoreTrioStemSeparator()
    output_dir = str(tmp_path / "peel_stems")

    # Run the loop with low threshold so it exercises the loop
    results = separator.run_peel_trio_loop(dummy_audio_file, output_dir=output_dir, min_threshold=0.01)

    assert isinstance(results, dict)
    assert "trio_residual" in results
    assert os.path.exists(results["trio_residual"])
