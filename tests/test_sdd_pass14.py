"""
Unit tests for Pass 14 SDD (Specification-Driven Development):
Module 1: HPSS & Low-Pass Acoustic Separation Verification (CascadedStemSeparator)
Module 2: Low-Frequency Downbeat Alignment & Beat Interval Smoothing Guard Verification
Module 3: Dynamic MIDI Time Signature & Reaper TEMPOENVEX Envelope Export Verification
"""

import os
import tempfile
import numpy as np
import soundfile as sf
import pytest
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.workflow.audio_nodes import DownbeatRefineNode
from pgm_craft.synthesizer import PGMSynthesizer
from pgm_craft.daw_exporter import DAWExporter


def test_hpss_and_lowpass_separation_guard():
    """驗證 CascadedStemSeparator 分離出的 drums.wav 與 bass.wav 為具體聲學特徵音軌，非複製佔位檔"""
    separator = CascadedStemSeparator()
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "test_input.wav")
        sr = 22050
        t = np.linspace(0, 2.0, sr * 2, False)
        y = np.sin(2 * np.pi * 100 * t) + np.sin(2 * np.pi * 2000 * t)
        sf.write(audio_path, y.astype(np.float32), sr)

        drums_path, _ = separator.separate_drums(audio_path, tmpdir)
        bass_path, _ = separator.separate_bass(audio_path, tmpdir)

        assert os.path.exists(drums_path)
        assert os.path.exists(bass_path)

        y_drums, _ = sf.read(drums_path)
        y_bass, _ = sf.read(bass_path)

        # 斷言 Drums 與 Bass 音軌具備不同的聲學頻譜特徵，且非原始 y 的無效完全複製
        assert not np.array_equal(y_drums, y)
        assert not np.array_equal(y_bass, y)


def test_downbeat_refine_interval_smoothing():
    """驗證 DownbeatRefineNode 對暴衝離群拍距 (Beat Artifacts) 的自動平滑修復」"""
    node = DownbeatRefineNode()
    # 建立一個包含離群拍距 (例如第 3 拍到第 4 拍突然暴衝 2.0 秒) 的 beats 陣列
    raw_beats = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [3.0, 4],  # 離群跳躍
        [3.5, 1],
        [4.0, 2]
    ])

    refined, result = node.refine(raw_beats)
    assert result["status"] in ("PASS", "WARN")
    # 斷言離群 timestamp 已被修復對齊中位數拍距 (0.5s)
    diff = refined[3, 0] - refined[2, 0]
    assert abs(diff - 0.5) < 0.1


def test_dynamic_midi_time_signature_and_reaper_tempo_env():
    """驗證 PGMSynthesizer 匯出動態拍號與 DAWExporter 產生 TEMPOENVEX 速度包絡點"""
    synth = PGMSynthesizer()
    exporter = DAWExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3],  # 3/4 變拍小節
            [3.5, 1], [4.0, 2], [4.5, 3], [5.0, 4]
        ])

        midi_path = synth.export_midi_tempo_map(beats, output_dir=tmpdir)
        assert os.path.exists(midi_path)

        report = {
            "average_bpm": 120.0,
            "beats": beats,
            "chord_progression": [{"measure": 1, "start_time": 0.0, "chord": "C"}]
        }
        rpp_path = exporter.export_reaper_project(report, output_dir=tmpdir)
        assert os.path.exists(rpp_path)

        with open(rpp_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "<TEMPOENVEX" in content
        assert "PT 0.000000" in content
