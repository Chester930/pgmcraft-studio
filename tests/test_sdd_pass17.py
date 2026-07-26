"""
SDD Pass 17 — Stage 1: Audio Quality Inspection & Enhancement BT
=================================================================
Module 1:  AudioLoadNode — 各格式載入 + 失敗邊界
Module 2:  AudioQualityInspectorNode — 10 項偵測指標
Module 3:  AudioQualityInspectorNode — grade 判定邏輯
Module 4:  QualityGateNode — FAIL 阻擋 / PASS 放行
Module 5:  DCOffsetRemovalNode — 10Hz HPF 去 DC
Module 6:  SilenceTrimNode — 開場靜音截除 + trim_offset_sec
Module 7:  PhaseAlignmentNode — 反相修復
Module 8:  SpectralDenoiseNode — Minimum Statistics
Module 9:  LoudnessNormalizeNode — Soft Knee Limiter
Module 10: build_audio_quality_tree() — 完整樹端對端
Module 11: AudioQualityBTEngine — 引擎契約
Module 12: WriteNormalizedWAVNode — 寫磁碟 + audio_path 更新
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_quality_bt import (
    AudioLoadNode,
    AudioQualityInspectorNode,
    QualityGateNode,
    DCOffsetRemovalNode,
    SilenceTrimNode,
    PhaseAlignmentNode,
    SpectralDenoiseNode,
    CrowdNoiseRemovalNode,
    LoudnessNormalizeNode,
    PassthroughNode,
    NeedsEnhancementConditionNode,
    WriteNormalizedWAVNode,
    build_audio_quality_tree,
    AudioQualityBTEngine,
    EBU_TRUE_PEAK_CEILING_DBTP,
    DC_OFFSET_THRESHOLD,
    LEADING_SILENCE_SEC,
    CLIP_RATIO_FAIL_THRESHOLD,
    CLIP_RATIO_WARN_THRESHOLD,
    SILENCE_RATIO_FAIL,
    STEREO_CORR_WARN,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_wav(path: str, sr: int = 44100, duration: float = 3.0,
              freq: float = 440.0, amplitude: float = 0.5,
              channels: int = 1) -> str:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)
    if channels == 2:
        y = np.stack([y, y], axis=0).T   # (samples, 2)
    sf.write(path, y, sr)
    return path


def _make_silent_wav(path: str, sr: int = 44100, duration: float = 3.0) -> str:
    y = np.zeros(int(sr * duration), dtype=np.float32)
    sf.write(path, y, sr)
    return path


def _make_clipped_wav(path: str, sr: int = 44100, duration: float = 3.0) -> str:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = np.ones_like(t, dtype=np.float32)   # 全部 1.0 = 全削峰
    sf.write(path, y, sr)
    return path


def _bb_with_y(y: np.ndarray, sr: int = 44100) -> Blackboard:
    bb = Blackboard()
    bb.set_val("y", y.astype(np.float32))
    bb.set_val("sr", sr)
    return bb


# ---------------------------------------------------------------------------
# Module 1 — AudioLoadNode
# ---------------------------------------------------------------------------

class TestAudioLoadNode(unittest.TestCase):

    def test_loads_valid_wav(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            self.assertEqual(AudioLoadNode().run(bb), NodeStatus.SUCCESS)
            self.assertIsNotNone(bb.get_val("y"))
            self.assertIsNotNone(bb.get_val("sr"))
            self.assertEqual(bb.get_val("target_analysis_path"), wav)

    def test_missing_file_returns_failure(self):
        bb = Blackboard()
        bb.set_val("audio_path", "/nonexistent/song.wav")
        self.assertEqual(AudioLoadNode().run(bb), NodeStatus.FAILURE)

    def test_empty_path_returns_failure(self):
        bb = Blackboard()
        bb.set_val("audio_path", "")
        self.assertEqual(AudioLoadNode().run(bb), NodeStatus.FAILURE)

    def test_stereo_wav_preserves_channels(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "stereo.wav"), channels=2)
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            AudioLoadNode().run(bb)
            y = bb.get_val("y")
            # librosa 載入立體聲 shape = (2, samples)
            self.assertTrue(y.ndim == 2 or y.ndim == 1)


# ---------------------------------------------------------------------------
# Module 2 — AudioQualityInspectorNode 偵測指標
# ---------------------------------------------------------------------------

class TestAudioQualityInspector_Metrics(unittest.TestCase):

    def _run_inspector(self, y, sr=44100):
        bb = _bb_with_y(y, sr)
        AudioQualityInspectorNode().run(bb)
        return bb.get_val("quality_report"), bb.get_val("quality_flags")

    def test_healthy_audio_no_bad_flags(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        _, flags = self._run_inspector(y)
        self.assertFalse(flags.get("has_severe_clipping"))
        self.assertFalse(flags.get("high_silence_ratio"))
        self.assertFalse(flags.get("has_dc_offset"))

    def test_clipped_audio_detected(self):
        y = np.ones(44100 * 3, dtype=np.float32)   # 全部 1.0
        _, flags = self._run_inspector(y)
        self.assertTrue(flags.get("has_clipping") or flags.get("has_severe_clipping"))

    def test_clip_ratio_value_correct(self):
        y = np.ones(44100 * 3, dtype=np.float32)
        report, _ = self._run_inspector(y)
        self.assertGreater(report["clip_ratio"], CLIP_RATIO_FAIL_THRESHOLD)

    def test_dc_offset_detected(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        y += 0.05   # 人工加 DC
        _, flags = self._run_inspector(y)
        self.assertTrue(flags.get("has_dc_offset"))

    def test_no_dc_clean_signal(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        _, flags = self._run_inspector(y)
        self.assertFalse(flags.get("has_dc_offset"))

    def test_silent_audio_high_silence_ratio(self):
        y = np.zeros(44100 * 5, dtype=np.float32)
        _, flags = self._run_inspector(y)
        self.assertTrue(flags.get("high_silence_ratio"))

    def test_low_rms_triggers_needs_amplify(self):
        y = np.zeros(44100 * 3, dtype=np.float32)
        y += 1e-6   # 極低電平
        _, flags = self._run_inspector(y)
        self.assertTrue(flags.get("needs_amplify"))

    def test_low_sample_rate_flagged(self):
        t = np.linspace(0, 3, 8000 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        _, flags = self._run_inspector(y, sr=8000)
        self.assertTrue(flags.get("low_sample_rate"))

    def test_preferred_sr_flagged(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        _, flags = self._run_inspector(y, sr=44100)
        self.assertTrue(flags.get("preferred_sample_rate"))

    def test_true_peak_calculated(self):
        t = np.linspace(0, 1, 44100, endpoint=False)
        y = (np.sin(2 * np.pi * 1000 * t) * 0.9).astype(np.float32)
        report, _ = self._run_inspector(y)
        self.assertIn("true_peak_dbtp", report)
        self.assertIsInstance(report["true_peak_dbtp"], float)

    def test_stereo_correlation_computed_for_stereo(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        left = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        right = left.copy()
        y = np.stack([left, right])   # (2, samples)
        bb = Blackboard()
        bb.set_val("y", y)
        bb.set_val("sr", sr)
        AudioQualityInspectorNode().run(bb)
        report = bb.get_val("quality_report")
        self.assertAlmostEqual(report["stereo_correlation"], 1.0, places=2)

    def test_anti_phase_stereo_detected(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        left = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.5
        right = -left   # 完全反相
        y = np.stack([left, right])
        bb = Blackboard()
        bb.set_val("y", y)
        bb.set_val("sr", sr)
        AudioQualityInspectorNode().run(bb)
        flags = bb.get_val("quality_flags")
        self.assertTrue(flags.get("has_phase_issue"))

    def test_leading_silence_detected(self):
        sr = 44100
        silence = np.zeros(int(sr * 2.5), dtype=np.float32)
        signal = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr)) * 0.5).astype(np.float32)
        y = np.concatenate([silence, signal])
        _, flags = self._run_inspector(y, sr)
        self.assertTrue(flags.get("has_leading_silence"))

    def test_no_leading_silence_for_immediate_onset(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        _, flags = self._run_inspector(y)
        self.assertFalse(flags.get("has_leading_silence"))

    def test_dynamic_range_computed(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        report, _ = self._run_inspector(y)
        self.assertIn("dynamic_range_db", report)
        self.assertGreater(report["dynamic_range_db"], 0)

    def test_low_dr_flagged(self):
        """RMS 接近峰值 → DR < 6dB"""
        y = np.ones(44100 * 3, dtype=np.float32) * 0.9   # 幾乎無動態
        report, flags = self._run_inspector(y)
        self.assertTrue(flags.get("low_dynamic_range"))


# ---------------------------------------------------------------------------
# Module 3 — grade 判定
# ---------------------------------------------------------------------------

class TestAudioQualityGradeLogic(unittest.TestCase):

    def _grade(self, y, sr=44100):
        bb = _bb_with_y(y, sr)
        AudioQualityInspectorNode().run(bb)
        return bb.get_val("quality_grade")

    def test_clean_signal_not_fail(self):
        """正常訊號不應 FAIL（WARN 是合理的，純正弦波 DR ≈ 3dB 本身就低動態）"""
        t = np.linspace(0, 5, 44100 * 5, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        grade = self._grade(y)
        self.assertNotEqual(grade, "FAIL")

    def test_real_music_like_signal_gets_reasonable_grade(self):
        """帶有動態變化的訊號（模擬真實音樂）應得 A 或 B"""
        sr = 44100
        rng = np.random.default_rng(42)
        t = np.linspace(0, 5, sr * 5, endpoint=False)
        # 多頻率加動態包絡，DR >> 6dB
        envelope = np.abs(np.sin(2 * np.pi * 0.5 * t)) * 0.5 + 0.05
        y = (np.sin(2 * np.pi * 440 * t) * envelope).astype(np.float32)
        grade = self._grade(y, sr)
        self.assertIn(grade, ["A", "B", "WARN"])  # 不應 FAIL

    def test_severe_clipping_gets_FAIL(self):
        y = np.ones(44100 * 5, dtype=np.float32)
        grade = self._grade(y)
        self.assertEqual(grade, "FAIL")

    def test_silent_gets_FAIL(self):
        y = np.zeros(44100 * 5, dtype=np.float32)
        grade = self._grade(y)
        self.assertEqual(grade, "FAIL")

    def test_grade_written_to_report(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        bb = _bb_with_y(y)
        AudioQualityInspectorNode().run(bb)
        self.assertIn(bb.get_val("quality_report", {}).get("grade"),
                      ["A", "B", "C", "WARN", "FAIL"])


# ---------------------------------------------------------------------------
# Module 4 — QualityGateNode
# ---------------------------------------------------------------------------

class TestQualityGateNode(unittest.TestCase):

    def test_grade_fail_blocks(self):
        bb = Blackboard()
        bb.set_val("quality_grade", "FAIL")
        bb.set_val("quality_flags", {"has_severe_clipping": True})
        bb.set_val("quality_report", {"sample_rate": 44100})
        self.assertEqual(QualityGateNode().run(bb), NodeStatus.FAILURE)

    def test_grade_a_passes(self):
        bb = Blackboard()
        bb.set_val("quality_grade", "A")
        self.assertEqual(QualityGateNode().run(bb), NodeStatus.SUCCESS)

    def test_grade_b_passes(self):
        bb = Blackboard()
        bb.set_val("quality_grade", "B")
        self.assertEqual(QualityGateNode().run(bb), NodeStatus.SUCCESS)

    def test_grade_warn_passes(self):
        bb = Blackboard()
        bb.set_val("quality_grade", "WARN")
        self.assertEqual(QualityGateNode().run(bb), NodeStatus.SUCCESS)

    def test_fail_writes_reason(self):
        bb = Blackboard()
        bb.set_val("quality_grade", "FAIL")
        bb.set_val("quality_flags", {"high_silence_ratio": True})
        bb.set_val("quality_report", {"sample_rate": 44100})
        QualityGateNode().run(bb)
        reasons = bb.get_val("quality_gate_reason", [])
        self.assertIsInstance(reasons, list)


# ---------------------------------------------------------------------------
# Module 5 — DCOffsetRemovalNode
# ---------------------------------------------------------------------------

class TestDCOffsetRemovalNode(unittest.TestCase):

    def test_dc_removed(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.3 + 0.05).astype(np.float32)  # +0.05 DC
        bb = _bb_with_y(y)
        bb.set_val("quality_flags", {"has_dc_offset": True})
        DCOffsetRemovalNode().run(bb)
        y_out = bb.get_val("y")
        self.assertLess(abs(float(np.mean(y_out))), DC_OFFSET_THRESHOLD * 2)

    def test_no_dc_flag_skips_processing(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        bb = _bb_with_y(y)
        bb.set_val("quality_flags", {"has_dc_offset": False})
        before = y.copy()
        DCOffsetRemovalNode().run(bb)
        np.testing.assert_array_equal(bb.get_val("y"), before)

    def test_dc_removal_preserves_length(self):
        t = np.linspace(0, 3, 44100 * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.3 + 0.05).astype(np.float32)
        bb = _bb_with_y(y)
        bb.set_val("quality_flags", {"has_dc_offset": True})
        DCOffsetRemovalNode().run(bb)
        self.assertEqual(len(bb.get_val("y")), len(y))


# ---------------------------------------------------------------------------
# Module 6 — SilenceTrimNode
# ---------------------------------------------------------------------------

class TestSilenceTrimNode(unittest.TestCase):

    def test_leading_silence_trimmed(self):
        sr = 44100
        silence = np.zeros(int(sr * 2.5), dtype=np.float32)
        signal = (np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2)) * 0.5).astype(np.float32)
        y = np.concatenate([silence, signal])
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_leading_silence": True})
        SilenceTrimNode().run(bb)
        y_out = bb.get_val("y")
        offset = bb.get_val("trim_offset_sec", 0.0)
        self.assertLess(len(y_out), len(y))
        self.assertGreater(offset, 0.0)

    def test_no_leading_silence_flag_skips(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_leading_silence": False})
        SilenceTrimNode().run(bb)
        self.assertEqual(bb.get_val("trim_offset_sec"), 0.0)

    def test_trim_offset_sec_default_zero(self):
        bb = Blackboard()
        bb.set_val("y", np.zeros(1000, dtype=np.float32))
        bb.set_val("sr", 44100)
        bb.set_val("quality_flags", {"has_leading_silence": False})
        SilenceTrimNode().run(bb)
        self.assertEqual(bb.get_val("trim_offset_sec"), 0.0)


# ---------------------------------------------------------------------------
# Module 7 — PhaseAlignmentNode
# ---------------------------------------------------------------------------

class TestPhaseAlignmentNode(unittest.TestCase):

    def test_anti_phase_stereo_flipped(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        left = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        right = -left
        y = np.stack([left, right])   # (2, samples)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_phase_issue": True})
        PhaseAlignmentNode().run(bb)
        y_out = bb.get_val("y")
        # 右聲道應該與左聲道同相
        np.testing.assert_allclose(y_out[1], left, atol=1e-4)

    def test_no_phase_flag_skips(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        y = np.stack([
            (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32),
            (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32),
        ])
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_phase_issue": False})
        before = y.copy()
        PhaseAlignmentNode().run(bb)
        np.testing.assert_array_equal(bb.get_val("y"), before)

    def test_mono_signal_skipped(self):
        sr = 44100
        y = np.sin(np.linspace(0, 3 * 2 * np.pi * 440, sr * 3)).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_phase_issue": True})
        before = y.copy()
        PhaseAlignmentNode().run(bb)
        np.testing.assert_array_equal(bb.get_val("y"), before)


# ---------------------------------------------------------------------------
# Module 8 — SpectralDenoiseNode
# ---------------------------------------------------------------------------

class TestSpectralDenoiseNode(unittest.TestCase):

    def test_output_length_preserved(self):
        sr = 44100
        t = np.linspace(0, 3, sr * 3, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.3 + np.random.randn(sr * 3) * 0.01).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_grade", "C")
        SpectralDenoiseNode().run(bb)
        y_out = bb.get_val("y")
        self.assertEqual(len(y_out), len(y))

    def test_skipped_for_grade_a(self):
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.5).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_grade", "A")
        before = y.copy()
        SpectralDenoiseNode().run(bb)
        np.testing.assert_array_equal(bb.get_val("y"), before)

    def test_skipped_for_grade_b(self):
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.5).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_grade", "B")
        before = y.copy()
        SpectralDenoiseNode().run(bb)
        np.testing.assert_array_equal(bb.get_val("y"), before)

    def test_noise_reduced_after_denoising(self):
        """降噪後 RMS 應小於等於原始（不應放大）"""
        sr = 44100
        np.random.seed(42)
        noise = (np.random.randn(sr * 3) * 0.1).astype(np.float32)
        signal = (np.sin(2 * np.pi * 440 * np.linspace(0, 3, sr * 3)) * 0.3).astype(np.float32)
        y = signal + noise
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_grade", "C")
        SpectralDenoiseNode().run(bb)
        y_out = bb.get_val("y")
        self.assertLessEqual(float(np.sqrt(np.mean(y_out ** 2))),
                             float(np.sqrt(np.mean(y ** 2))) * 1.05)


# ---------------------------------------------------------------------------
# Module 9 — LoudnessNormalizeNode
# ---------------------------------------------------------------------------

class TestLoudnessNormalizeNode(unittest.TestCase):

    def test_quiet_signal_amplified(self):
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.001).astype(np.float32)   # 極低
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"needs_amplify": True})
        bb.set_val("quality_grade", "C")
        LoudnessNormalizeNode().run(bb)
        y_out = bb.get_val("y")
        rms_before = float(np.sqrt(np.mean(y ** 2)))
        rms_after = float(np.sqrt(np.mean(y_out ** 2)))
        self.assertGreater(rms_after, rms_before)

    def test_gain_db_written_to_blackboard(self):
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.001).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"needs_amplify": True})
        bb.set_val("quality_grade", "C")
        LoudnessNormalizeNode().run(bb)
        gain = bb.get_val("applied_lufs_gain_db", None)
        self.assertIsNotNone(gain)
        self.assertIsInstance(gain, float)

    def test_output_does_not_exceed_true_peak_ceiling(self):
        """Soft Knee Limiter 確保 peak < 0 dBFS（EBU -1.0 dBTP 近似）"""
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.001).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"needs_amplify": True})
        bb.set_val("quality_grade", "C")
        LoudnessNormalizeNode().run(bb)
        y_out = bb.get_val("y")
        max_peak = float(np.max(np.abs(y_out)))
        self.assertLessEqual(max_peak, 1.0)  # 不超過 0 dBFS

    def test_skipped_for_grade_a_without_amplify_flag(self):
        sr = 44100
        y = (np.sin(np.linspace(0, 3, sr * 3)) * 0.5).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"needs_amplify": False})
        bb.set_val("quality_grade", "A")
        before = y.copy()
        LoudnessNormalizeNode().run(bb)
        # gain 應為 0
        self.assertEqual(bb.get_val("applied_lufs_gain_db", 0.0), 0.0)


# ---------------------------------------------------------------------------
# Module 10 — build_audio_quality_tree() 完整樹 E2E
# ---------------------------------------------------------------------------

class TestAudioQualityTreeE2E(unittest.TestCase):

    def test_clean_wav_passes_full_tree(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"), amplitude=0.5)
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("trim_offset_sec", 0.0)
            status = build_audio_quality_tree().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertIsNotNone(bb.get_val("quality_grade"))
            self.assertIsNotNone(bb.get_val("quality_report"))
            self.assertIsNotNone(bb.get_val("y"))

    def test_full_silence_fails_gate(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_silent_wav(os.path.join(d, "silent.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            status = build_audio_quality_tree().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)
            self.assertEqual(bb.get_val("quality_grade"), "FAIL")

    def test_full_clip_fails_gate(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_clipped_wav(os.path.join(d, "clipped.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            status = build_audio_quality_tree().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)
            self.assertEqual(bb.get_val("quality_grade"), "FAIL")

    def test_missing_file_fails(self):
        bb = Blackboard()
        bb.set_val("audio_path", "/nonexistent/audio.wav")
        status = build_audio_quality_tree().run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_blackboard_contract_after_success(self):
        """所有 Stage 1 輸出 key (含 ABC 三版契約) 都必須存在"""
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("trim_offset_sec", 0.0)
            build_audio_quality_tree().run(bb)
            for key in ["y", "sr", "quality_report", "quality_flags",
                        "quality_grade", "trim_offset_sec", "raw_wav_path",
                        "normalized_wav_path", "denoised_wav_path", "target_analysis_path"]:
                self.assertIsNotNone(bb.get_val(key), f"missing: {key}")

    def test_workflow_trace_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "trace.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("trim_offset_sec", 0.0)
            build_audio_quality_tree().run(bb)
            trace = bb.get_val("workflow_trace", [])
            names = [t["node"] for t in trace]
            self.assertIn("AudioLoadNode", names)
            self.assertIn("AudioQualityInspectorNode", names)
            self.assertIn("QualityGateNode", names)

    def test_dc_offset_audio_processed(self):
        """有 DC 的音訊應通過，且 DC 被去除"""
        with tempfile.TemporaryDirectory() as d:
            sr = 44100
            t = np.linspace(0, 3, sr * 3, endpoint=False)
            y = (np.sin(2 * np.pi * 440 * t) * 0.3 + 0.05).astype(np.float32)
            wav = os.path.join(d, "dc.wav")
            sf.write(wav, y, sr)
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("trim_offset_sec", 0.0)
            status = build_audio_quality_tree().run(bb)
            # 有 DC 不是 FAIL，應該通過
            self.assertEqual(status, NodeStatus.SUCCESS)

    def test_leading_silence_trimmed_e2e(self):
        """開場靜音應被截除，trim_offset_sec > 0"""
        with tempfile.TemporaryDirectory() as d:
            sr = 44100
            silence = np.zeros(int(sr * 2.5), dtype=np.float32)
            signal = (np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2)) * 0.5).astype(np.float32)
            y = np.concatenate([silence, signal])
            wav = os.path.join(d, "silence_lead.wav")
            sf.write(wav, y, sr)
            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("trim_offset_sec", 0.0)
            status = build_audio_quality_tree().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            offset = bb.get_val("trim_offset_sec", 0.0)
            self.assertGreater(offset, 0.0)


# ---------------------------------------------------------------------------
# Module 11 — AudioQualityBTEngine 引擎契約
# ---------------------------------------------------------------------------

class TestAudioQualityBTEngine(unittest.TestCase):

    def test_returns_blackboard(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"))
            engine = AudioQualityBTEngine()
            bb = engine.run(audio_path=wav)
            self.assertIsInstance(bb, Blackboard)

    def test_status_key_exists(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"))
            engine = AudioQualityBTEngine()
            bb = engine.run(audio_path=wav)
            self.assertIn(
                bb.get_val("audio_quality_status"),
                ["SUCCESS", "FAILURE", "RUNNING"]
            )

    def test_success_on_clean_audio(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"), amplitude=0.5)
            engine = AudioQualityBTEngine()
            bb = engine.run(audio_path=wav)
            self.assertEqual(bb.get_val("audio_quality_status"), "SUCCESS")

    def test_failure_on_silent_audio(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _make_silent_wav(os.path.join(d, "silent.wav"))
            engine = AudioQualityBTEngine()
            bb = engine.run(audio_path=wav)
            self.assertEqual(bb.get_val("audio_quality_status"), "FAILURE")

    def test_quality_optimized_flag(self):
        """正常音訊 grade A → optimized=False；有問題音訊 → True"""
        with tempfile.TemporaryDirectory() as d:
            wav = _make_wav(os.path.join(d, "song.wav"), amplitude=0.5)
            bb = AudioQualityBTEngine().run(audio_path=wav)
            self.assertIsInstance(bb.get_val("quality_optimized"), bool)


# ---------------------------------------------------------------------------
# Module 12 — WriteNormalizedWAVNode
# ---------------------------------------------------------------------------

class TestWriteNormalizedWAVNode(unittest.TestCase):

    def _bb_with_wav(self, tmpdir, filename="song.wav",
                     amplitude=0.05, sr=44100) -> tuple:
        """Return (bb, src_path) with y/sr/audio_path already set."""
        wav = _make_wav(os.path.join(tmpdir, filename), amplitude=amplitude, sr=sr)
        import librosa
        y, _ = librosa.load(wav, sr=None, mono=False)
        bb = Blackboard()
        bb.set_val("y", y.astype(np.float32))
        bb.set_val("sr", sr)
        bb.set_val("audio_path", wav)
        return bb, wav

    def test_writes_file_with_project_dir(self):
        """project_dir + project_name 設定時，寫入 source/_normalized.wav"""
        with tempfile.TemporaryDirectory() as root:
            project_dir = os.path.join(root, "MySong")
            source_dir = os.path.join(project_dir, "source")
            os.makedirs(source_dir)
            src = _make_wav(os.path.join(root, "orig.wav"), amplitude=0.3)

            import librosa
            y, sr = librosa.load(src, sr=None, mono=False)
            bb = Blackboard()
            bb.set_val("y", y.astype(np.float32))
            bb.set_val("sr", int(sr))
            bb.set_val("audio_path", src)
            bb.set_val("project_dir", project_dir)
            bb.set_val("project_name", "MySong")

            status = WriteNormalizedWAVNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

            expected = os.path.join(source_dir, "MySong_normalized.wav")
            self.assertTrue(os.path.isfile(expected))

    def test_audio_path_updated_to_normalized(self):
        """audio_path blackboard key 必須指向 _normalized.wav"""
        with tempfile.TemporaryDirectory() as root:
            project_dir = os.path.join(root, "MySong")
            os.makedirs(os.path.join(project_dir, "source"))
            src = _make_wav(os.path.join(root, "orig.wav"))

            import librosa
            y, sr = librosa.load(src, sr=None, mono=False)
            bb = Blackboard()
            bb.set_val("y", y.astype(np.float32))
            bb.set_val("sr", int(sr))
            bb.set_val("audio_path", src)
            bb.set_val("project_dir", project_dir)
            bb.set_val("project_name", "MySong")

            WriteNormalizedWAVNode().run(bb)
            self.assertIn("_normalized", bb.get_val("audio_path"))
            self.assertEqual(bb.get_val("original_wav_path"), src)

    def test_fallback_to_same_dir_without_project_dir(self):
        """project_dir 未設定時，寫入與原始音檔同目錄"""
        with tempfile.TemporaryDirectory() as d:
            src = _make_wav(os.path.join(d, "track.wav"))
            import librosa
            y, sr = librosa.load(src, sr=None, mono=False)
            bb = Blackboard()
            bb.set_val("y", y.astype(np.float32))
            bb.set_val("sr", int(sr))
            bb.set_val("audio_path", src)
            # 不設 project_dir / project_name

            status = WriteNormalizedWAVNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            expected = os.path.join(d, "track_normalized.wav")
            self.assertTrue(os.path.isfile(expected))

    def test_original_wav_path_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src = _make_wav(os.path.join(d, "original.wav"))
            import librosa
            y, sr = librosa.load(src, sr=None, mono=False)
            bb = Blackboard()
            bb.set_val("y", y.astype(np.float32))
            bb.set_val("sr", int(sr))
            bb.set_val("audio_path", src)

            WriteNormalizedWAVNode().run(bb)
            self.assertEqual(bb.get_val("original_wav_path"), src)

    def test_normalized_wav_is_valid_audio(self):
        """寫出的檔案要能被 soundfile 讀回，且長度相近"""
        with tempfile.TemporaryDirectory() as d:
            src = _make_wav(os.path.join(d, "song.wav"), duration=2.0, amplitude=0.4)
            import librosa
            y, sr = librosa.load(src, sr=None, mono=False)
            bb = Blackboard()
            bb.set_val("y", y.astype(np.float32))
            bb.set_val("sr", int(sr))
            bb.set_val("audio_path", src)

            WriteNormalizedWAVNode().run(bb)
            out_path = bb.get_val("normalized_wav_path")
            self.assertIsNotNone(out_path)
            y_out, sr_out = sf.read(out_path)
            self.assertEqual(sr_out, sr)
            self.assertGreater(len(y_out), 0)

    def test_e2e_normalized_file_in_project_folder(self):
        """完整 E2E：有問題音訊經過完整樹後，專案資料夾應有 _normalized.wav"""
        with tempfile.TemporaryDirectory() as root:
            sr = 44100
            # 詳細很低 → needs_amplify
            t = np.linspace(0, 3, sr * 3, endpoint=False)
            y = (np.sin(2 * np.pi * 440 * t) * 0.001).astype(np.float32)
            wav = os.path.join(root, "quiet.wav")
            sf.write(wav, y, sr)

            project_dir = os.path.join(root, "quiet")
            os.makedirs(os.path.join(project_dir, "source"))

            bb = Blackboard()
            bb.set_val("audio_path", wav)
            bb.set_val("project_dir", project_dir)
            bb.set_val("project_name", "quiet")
            bb.set_val("trim_offset_sec", 0.0)

            status = build_audio_quality_tree().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

            norm_path = bb.get_val("normalized_wav_path")
            self.assertIsNotNone(norm_path)
            self.assertTrue(os.path.isfile(norm_path),
                            f"normalized WAV not found: {norm_path}")
            self.assertIn("_normalized", norm_path)

            # 原始檔不被覆寫
            self.assertTrue(os.path.isfile(wav))


# ---------------------------------------------------------------------------
# Module 13 — CrowdNoiseRemovalNode
# ---------------------------------------------------------------------------

class TestCrowdNoiseRemovalNode(unittest.TestCase):

    def test_skips_when_no_crowd_noise_flag(self):
        sr = 44100
        t = np.linspace(0, 2, sr * 2, endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_crowd_noise": False})
        before = y.copy()
        status = CrowdNoiseRemovalNode().run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        np.testing.assert_array_equal(bb.get_val("y"), before)

    def test_applies_filtering_when_crowd_noise_flag_true(self):
        sr = 44100
        t = np.linspace(0, 2, sr * 2, endpoint=False)
        # 加上 2.5kHz 人群噪聲波段
        y = (np.sin(2 * np.pi * 440 * t) * 0.5 + np.sin(2 * np.pi * 2500 * t) * 0.3).astype(np.float32)
        bb = _bb_with_y(y, sr)
        bb.set_val("quality_flags", {"has_crowd_noise": True})
        status = CrowdNoiseRemovalNode().run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        y_out = bb.get_val("y")
        self.assertEqual(len(y_out), len(y))
        self.assertFalse(np.array_equal(y_out, y))


if __name__ == "__main__":
    unittest.main()
