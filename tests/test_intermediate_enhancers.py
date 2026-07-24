"""
Unit tests for Model-Specific Intermediate Enhancement Engine methods
"""

import pytest
import numpy as np
from pgm_craft.enhancer import AudioEnhancerEngine


def test_debreathe_vocal_filter():
    enhancer = AudioEnhancerEngine()
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # High frequency noise simulating breath
    y = np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 14000 * t)

    y_clean = enhancer.apply_debreathe_vocal_filter(y, sr)
    assert len(y_clean) == len(y)


def test_transient_punch_shaper():
    enhancer = AudioEnhancerEngine()
    sr = 22050
    y = np.zeros(sr)
    y[100:150] = 0.8  # Simulating a kick drum hit

    y_punched = enhancer.apply_transient_punch_shaper(y, sr)
    assert len(y_punched) == len(y)
    assert np.max(np.abs(y_punched)) <= 1.0


def test_subharmonic_bass_enhancer():
    enhancer = AudioEnhancerEngine()
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = np.sin(2 * np.pi * 80 * t)

    y_enhanced = enhancer.apply_subharmonic_bass_enhancer(y, sr)
    assert len(y_enhanced) == len(y)
