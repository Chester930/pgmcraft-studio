"""
PGMCraft Stage 1 — Audio Quality Inspection & Enhancement Behavior Tree.

業界標準根據：
  - EBU R128 (ITU-R BS.1770)：Integrated Loudness, True Peak, Gating
  - HTDemucs 官方：44.1k/48k WAV 為最佳輸入
  - Mastering 業界：True Peak ≤ -1.0 dBTP, DC HPF 10Hz, Minimum Statistics 降噪
  - SoundOnSound / Sweetwater：立體聲相關性全曲平均 < 0 才算反相

Blackboard 輸出契約（本 Stage 結束後保證存在）：
  y                   → 處理後（或原始）的 numpy array
  sr                  → 取樣率
  quality_report      → dict：所有偵測數值
  quality_flags       → dict：所有 bool flags
  quality_grade       → "A" | "B" | "C" | "WARN" | "FAIL"
  quality_optimized   → bool：是否有做過任何處理
  trim_offset_sec     → float：截掉的開場靜音秒數（預設 0.0）
"""

import os
import numpy as np
import scipy.signal

from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.workflow.nodes import SequenceNode, FallbackNode


# ---------------------------------------------------------------------------
# Constants — 業界標準數值，有出處
# ---------------------------------------------------------------------------

# EBU R128 gating
EBU_ABSOLUTE_GATE_LUFS = -70.0          # 絕對靜音門限
EBU_TRUE_PEAK_CEILING_DBTP = -1.0       # 串流平台統一要求

# HTDemucs 官方建議
HTDEMUCS_MIN_SR = 22050                 # 低於此 SDR 顯著下降
HTDEMUCS_PREFERRED_SR = (44100, 48000)  # 訓練資料取樣率

# Mastering 業界
CLIP_RATIO_FAIL_THRESHOLD = 0.005       # 0.5% 以上連續削峰 → FAIL
CLIP_RATIO_WARN_THRESHOLD = 0.001       # 0.1% → WARN
DYNAMIC_RANGE_WARN_DB = 6.0             # DR < 6 dB → 過壓縮
DC_OFFSET_THRESHOLD = 0.005             # 5mV 等效
LEADING_SILENCE_SEC = 1.5              # 開場靜音超過此秒數影響 BeatNet
SILENCE_RATIO_FAIL = 0.60               # 60% 以上靜音 → FAIL
STEREO_CORR_WARN = 0.0                  # 全曲平均相關係數 < 0 → WARN
SPECTRAL_CENTROID_MIN_HZ = 500.0        # 低於此值疑似截頻

# 響度正規化
TARGET_LUFS_ANALYSIS = -18.0            # 送 HTDemucs 前修復的電平目標（保守）
TARGET_TRUE_PEAK_DBTP = -1.0            # 串流標準

# Minimum Statistics 降噪 (優化參數：避免 Musical Noise 電子音)
MS_FRAME_SEC = 0.025                    # 25ms 幀
MS_WINDOW_SEC = 1.5                     # 1.5s 滑動最小值視窗
MS_ALPHA = 1.0                          # 扣除因子 (降低避免破壞細節)
MS_BETA = 0.15                          # Spectral Floor 底限 (提升至 15% 消除水底嗶嗶聲)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _rms_to_lufs(rms: float) -> float:
    """RMS 近似 LUFS（無 K-weighting，僅用於相對比較）。"""
    if rms <= 0:
        return -120.0
    return float(20 * np.log10(rms) - 0.691)  # ITU-R BS.1770 offset 近似


def _estimate_true_peak(y: np.ndarray, oversample: int = 4) -> float:
    """4x oversampling 估算 True Peak (dBTP)。
    業界標準方法：上採樣後取最大值。
    """
    if y.ndim > 1:
        mono = y.mean(axis=1) if y.shape[0] > y.shape[1] else y.mean(axis=0)
    else:
        mono = y
    # 4x 上採樣
    up = scipy.signal.resample_poly(mono, oversample, 1)
    peak = float(np.max(np.abs(up)))
    return 20 * np.log10(peak) if peak > 0 else -120.0


def _find_quiet_segment(y_mono: np.ndarray, sr: int, duration_sec: float = 0.5) -> np.ndarray:
    """找全曲中 RMS 最低的 0.5s 片段，用於 Minimum Statistics 初始估噪。"""
    frame_len = int(duration_sec * sr)
    n_frames = len(y_mono) // frame_len
    if n_frames == 0:
        return y_mono
    frames = y_mono[:n_frames * frame_len].reshape(n_frames, frame_len)
    rms_per_frame = np.sqrt(np.mean(frames ** 2, axis=1))
    quietest_idx = int(np.argmin(rms_per_frame))
    return frames[quietest_idx]


# ---------------------------------------------------------------------------
# 1-A  AudioLoadNode（現有節點整合介面，Stage 1 直接使用）
# ---------------------------------------------------------------------------

class AudioLoadNode(BaseNode):
    """載入音訊為 numpy array，採用 soxr_hq 高精度重採樣。"""
    required_keys = ["audio_path"]
    optional_keys = []
    output_keys = ["y", "sr", "target_analysis_path"]

    def __init__(self):
        super().__init__("AudioLoadNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            print(f"[AudioLoad] file not found: {audio_path}")
            return NodeStatus.FAILURE
        try:
            import librosa
            try:
                y, sr = librosa.load(audio_path, sr=None, mono=False, res_type="soxr_hq")
            except Exception:
                y, sr = librosa.load(audio_path, sr=None, mono=False)
            blackboard.set_val("y", y)
            blackboard.set_val("sr", int(sr))
            blackboard.set_val("target_analysis_path", audio_path)
            duration = y.shape[-1] / sr if y.ndim > 1 else len(y) / sr
            print(f"[AudioLoad] OK sr={sr} duration={duration:.2f}s shape={y.shape}")
            return NodeStatus.SUCCESS
        except Exception as exc:
            print(f"[AudioLoad] FAILED: {exc}")
            return NodeStatus.FAILURE


# ---------------------------------------------------------------------------
# 1-B  AudioQualityInspectorNode — 純偵測，不修改 y
# ---------------------------------------------------------------------------

class AudioQualityInspectorNode(BaseNode):
    """
    全面音質診斷節點。只讀不寫音訊資料。

    偵測項目與業界標準：
      1. Integrated Loudness (EBU R128 近似)
      2. True Peak via 4x oversampling (EBU R128)
      3. Clip Ratio：連續飽和幀比例 (Mastering 業界)
      4. Dynamic Range DR (DR Meter 標準)
      5. DC Offset：mean(y) > 0.005 (5mV 等效)
      6. Leading Silence：EBU -70 gating
      7. Sample Rate check (HTDemucs 官方)
      8. Stereo Correlation (SoundOnSound / Sweetwater)
      9. Spectral Centroid：截頻偵測
     10. Silence Ratio：EBU -70 gating
    """
    required_keys = ["y", "sr"]
    optional_keys = []
    output_keys = ["quality_report", "quality_flags", "quality_grade"]

    def __init__(self):
        super().__init__("AudioQualityInspectorNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        if y is None or sr is None:
            print("[Inspector] y or sr missing")
            return NodeStatus.FAILURE

        # 統一轉成 mono float32 用於分析（不修改 blackboard 的 y）
        if y.ndim > 1:
            # librosa 載入時 shape = (channels, samples) 或 (samples, channels)
            mono = y.mean(axis=0) if y.shape[0] <= 2 else y.mean(axis=1)
        else:
            mono = y.copy()
        mono = mono.astype(np.float32)

        report = {}
        flags = {}

        # 1. Integrated Loudness（RMS 近似 LUFS）
        rms = float(np.sqrt(np.mean(mono ** 2)))
        lufs = _rms_to_lufs(rms)
        report["integrated_lufs"] = round(lufs, 2)
        report["rms"] = round(rms, 6)
        flags["needs_amplify"] = lufs < -40.0

        # 2. True Peak (4x oversampling)
        true_peak_dbtp = _estimate_true_peak(y)
        report["true_peak_dbtp"] = round(true_peak_dbtp, 2)
        flags["has_true_peak_risk"] = true_peak_dbtp > EBU_TRUE_PEAK_CEILING_DBTP

        # 3. Clip Ratio：連續超過 0.9999 的樣本比例
        clip_mask = np.abs(mono) >= 0.9999
        clip_ratio = float(np.mean(clip_mask))
        report["clip_ratio"] = round(clip_ratio, 6)
        flags["has_clipping"] = clip_ratio > CLIP_RATIO_WARN_THRESHOLD
        flags["has_severe_clipping"] = clip_ratio > CLIP_RATIO_FAIL_THRESHOLD

        # 4. Dynamic Range DR = peak_db - rms_db
        peak_db = float(20 * np.log10(np.max(np.abs(mono)) + 1e-9))
        rms_db = float(20 * np.log10(rms + 1e-9))
        dr = peak_db - rms_db
        report["dynamic_range_db"] = round(dr, 2)
        report["peak_db"] = round(peak_db, 2)
        flags["low_dynamic_range"] = dr < DYNAMIC_RANGE_WARN_DB

        # 5. DC Offset：abs(mean(y))
        dc_offset = float(abs(np.mean(mono)))
        report["dc_offset"] = round(dc_offset, 6)
        flags["has_dc_offset"] = dc_offset > DC_OFFSET_THRESHOLD

        # 6. Leading Silence：EBU -70 LUFS gating
        frame_len = max(1, int(0.1 * sr))   # 100ms 幀
        leading_sil_sec = 0.0
        for i in range(0, min(len(mono), int(sr * 10)), frame_len):  # 最多掃前 10s
            seg = mono[i:i + frame_len]
            seg_lufs = _rms_to_lufs(float(np.sqrt(np.mean(seg ** 2))))
            if seg_lufs < EBU_ABSOLUTE_GATE_LUFS:
                leading_sil_sec += frame_len / sr
            else:
                break
        report["leading_silence_sec"] = round(leading_sil_sec, 3)
        flags["has_leading_silence"] = leading_sil_sec > LEADING_SILENCE_SEC

        # 7. Sample Rate
        report["sample_rate"] = int(sr)
        flags["low_sample_rate"] = sr < HTDEMUCS_MIN_SR
        flags["preferred_sample_rate"] = sr in HTDEMUCS_PREFERRED_SR

        # 8. Stereo Correlation（全曲平均，非瞬間）
        if y.ndim > 1 and y.shape[0] >= 2:
            left = y[0].astype(np.float32)
            right = y[1].astype(np.float32)
            # Pearson 相關係數
            if np.std(left) > 0 and np.std(right) > 0:
                corr = float(np.corrcoef(left, right)[0, 1])
            else:
                corr = 1.0
            report["stereo_correlation"] = round(corr, 4)
            flags["has_phase_issue"] = corr < STEREO_CORR_WARN
        else:
            report["stereo_correlation"] = 1.0
            flags["has_phase_issue"] = False

        # 9. Spectral Centroid（取前 30s 避免太慢）
        try:
            import librosa
            analysis_len = min(len(mono), sr * 30)
            sc = librosa.feature.spectral_centroid(y=mono[:analysis_len], sr=sr)
            centroid_hz = float(np.mean(sc))
            report["spectral_centroid_hz"] = round(centroid_hz, 1)
            flags["truncated_spectrum"] = centroid_hz < SPECTRAL_CENTROID_MIN_HZ
        except Exception:
            report["spectral_centroid_hz"] = 1000.0
            flags["truncated_spectrum"] = False

        # 10. Silence Ratio (EBU -70 gating)
        frame_len_sil = max(1, int(0.1 * sr))
        n_total = len(mono) // frame_len_sil
        if n_total > 0:
            frames = mono[:n_total * frame_len_sil].reshape(n_total, frame_len_sil)
            rms_frames = np.sqrt(np.mean(frames ** 2, axis=1))
            lufs_frames = np.where(
                rms_frames > 1e-10,
                20 * np.log10(np.maximum(rms_frames, 1e-10)) - 0.691,
                -120.0
            )
            silence_ratio = float(np.mean(lufs_frames < EBU_ABSOLUTE_GATE_LUFS))
        else:
            silence_ratio = 0.0
        report["silence_ratio"] = round(silence_ratio, 4)
        flags["high_silence_ratio"] = silence_ratio > SILENCE_RATIO_FAIL

        # 11. Crowd / Ambient Speech Detect (特徵：中高頻 1kHz~4kHz 能量異動與動態波動)
        crowd_noise_detected = False
        try:
            # 檢查中頻段 1kHz~4kHz 音量能量佔比，現場人群喧鬧或鼓掌聲此頻段比例異常高
            if 'librosa' in locals() or 'librosa' in globals():
                S = np.abs(librosa.stft(mono[:min(len(mono), sr * 10)], n_fft=1024))
                freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
                mid_band = (freqs >= 1000) & (freqs <= 4000)
                mid_energy = np.mean(S[mid_band, :])
                total_energy = np.mean(S) + 1e-9
                if (mid_energy / total_energy) > 0.65 and dr > 12.0:
                    crowd_noise_detected = True
        except Exception:
            crowd_noise_detected = False
        flags["has_crowd_noise"] = crowd_noise_detected

        # --- Grade 判定 ---
        grade = self._compute_grade(flags, report)
        report["grade"] = grade

        blackboard.set_val("quality_report", report)
        blackboard.set_val("quality_flags", flags)
        blackboard.set_val("quality_grade", grade)

        print(f"[Inspector] grade={grade} lufs={lufs:.1f} true_peak={true_peak_dbtp:.1f}dBTP "
              f"dr={dr:.1f}dB clip={clip_ratio*100:.3f}% sr={sr} crowd_noise={crowd_noise_detected}")
        return NodeStatus.SUCCESS

    @staticmethod
    def _compute_grade(flags: dict, report: dict) -> str:
        # FAIL 條件
        if flags.get("has_severe_clipping"):
            return "FAIL"
        if flags.get("high_silence_ratio"):
            return "FAIL"
        if report.get("sample_rate", 44100) < 8000:
            return "FAIL"

        # WARN 條件（可繼續，但告知使用者）
        if flags.get("has_clipping"):
            return "WARN"
        if flags.get("low_dynamic_range"):
            return "WARN"
        if flags.get("has_true_peak_risk"):
            return "WARN"

        # C：需要多項修復
        problem_count = sum([
            flags.get("needs_amplify", False),
            flags.get("has_dc_offset", False),
            flags.get("has_phase_issue", False),
            flags.get("has_leading_silence", False),
            flags.get("low_sample_rate", False),
            flags.get("has_crowd_noise", False),
        ])
        if problem_count >= 2:
            return "C"
        if problem_count == 1:
            return "B"
        return "A"


# ---------------------------------------------------------------------------
# 1-C  QualityGateNode — Guard，FAIL 時阻止進入 AI 推理
# ---------------------------------------------------------------------------

class QualityGateNode(BaseNode):
    """
    Guard: grade == FAIL 時停止整個 Stage。
    防止無效音訊（全削峰 / 全靜音）進入耗時的 HTDemucs 推理。
    """
    required_keys = ["quality_grade"]
    optional_keys = []
    output_keys = ["quality_gate_reason"]

    def __init__(self):
        super().__init__("QualityGateNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        grade = blackboard.get_val("quality_grade", "A")
        if grade == "FAIL":
            flags = blackboard.get_val("quality_flags", {})
            reason = []
            if flags.get("has_severe_clipping"):
                reason.append("severe clipping > 0.5%")
            if flags.get("high_silence_ratio"):
                reason.append("silence ratio > 60%")
            if blackboard.get_val("quality_report", {}).get("sample_rate", 44100) < 8000:
                reason.append("sample rate < 8000 Hz")
            print(f"[QualityGate] FAIL — {', '.join(reason) or 'unknown reason'}")
            blackboard.set_val("quality_gate_reason", reason)
            return NodeStatus.FAILURE
        print(f"[QualityGate] PASS grade={grade}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Enhancement Chain nodes
# ---------------------------------------------------------------------------

class StereoPhaseCorrectionNode(BaseNode):
    """
    P1-1: 雙聲道相位反相檢測與自動翻轉修復衛兵
    若左右聲道相關係數 corr < -0.5（嚴重 180 度反相），自動翻轉右聲道 y[1] = -y[1]。
    """
    required_keys = ["y", "quality_report"]
    output_keys = ["y", "phase_corrected"]

    def __init__(self):
        super().__init__("StereoPhaseCorrectionNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        report = blackboard.get_val("quality_report", {})
        corr = report.get("stereo_correlation", 1.0)

        if y is not None and y.ndim > 1 and y.shape[0] >= 2 and corr < -0.5:
            y[1] = -y[1]
            blackboard.set_val("y", y)
            blackboard.set_val("phase_corrected", True)
            print(f"[{self.name}] 🛡️ 檢測到嚴重立體聲反相 (corr={corr:.2f})，已成功自動執行 180 度相位翻轉修復！")
        else:
            blackboard.set_val("phase_corrected", False)
        return NodeStatus.SUCCESS


class DCOffsetRemovalNode(BaseNode):
    """
    去除 DC Offset。
    方法：10Hz HPF（linear phase filtfilt），零相位失真。
    業界標準：10–20 Hz HPF 是去 DC 的行業推薦做法。
    """
    required_keys = ["y", "sr", "quality_flags"]
    optional_keys = []
    output_keys = ["y"]

    def __init__(self):
        super().__init__("DCOffsetRemovalNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not blackboard.get_val("quality_flags", {}).get("has_dc_offset"):
            return NodeStatus.SUCCESS   # 不需要處理

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        try:
            nyq = sr / 2.0
            cutoff = 10.0 / nyq   # 10 Hz highpass
            b, a = scipy.signal.butter(4, cutoff, btype="high")
            if y.ndim > 1:
                y_fixed = scipy.signal.filtfilt(b, a, y, axis=-1)
            else:
                y_fixed = scipy.signal.filtfilt(b, a, y)
            blackboard.set_val("y", y_fixed.astype(np.float32))
            print("[DCOffsetRemoval] OK — 10Hz HPF applied (filtfilt, zero-phase)")
        except Exception as exc:
            # Fallback：直接減均值
            print(f"[DCOffsetRemoval] filtfilt failed ({exc}), using mean subtraction")
            blackboard.set_val("y", (y - np.mean(y)).astype(np.float32))

        return NodeStatus.SUCCESS


class SilenceTrimNode(BaseNode):
    """
    截掉開場與結尾靜音。
    方法：librosa.effects.trim，-60 dB top_db 門限。
    記錄 trim_offset_sec 供後續 BeatNet 時間補正。
    """
    required_keys = ["y", "sr", "quality_flags"]
    optional_keys = []
    output_keys = ["y", "trim_offset_sec"]

    def __init__(self):
        super().__init__("SilenceTrimNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        blackboard.set_val("trim_offset_sec", 0.0)   # 預設

        if not blackboard.get_val("quality_flags", {}).get("has_leading_silence"):
            return NodeStatus.SUCCESS

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        try:
            import librosa
            if y.ndim > 1:
                mono = y.mean(axis=0) if y.shape[0] <= 2 else y.mean(axis=1)
            else:
                mono = y

            _, (start_idx, end_idx) = librosa.effects.trim(mono, top_db=60)
            trim_offset = start_idx / sr

            if y.ndim > 1:
                y_trimmed = y[..., start_idx:end_idx]
            else:
                y_trimmed = y[start_idx:end_idx]

            blackboard.set_val("y", y_trimmed.astype(np.float32))
            blackboard.set_val("trim_offset_sec", float(trim_offset))
            print(f"[SilenceTrim] trimmed {trim_offset:.3f}s leading silence")
        except Exception as exc:
            print(f"[SilenceTrim] WARN: {exc}")

        return NodeStatus.SUCCESS


class PhaseAlignmentNode(BaseNode):
    """
    修復立體聲反相。
    條件：全曲平均 Pearson 相關係數 < 0（業界標準：持續負值才視為問題）。
    方法：翻轉右聲道極性。
    """
    required_keys = ["y", "quality_flags"]
    optional_keys = []
    output_keys = ["y"]

    def __init__(self):
        super().__init__("PhaseAlignmentNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not blackboard.get_val("quality_flags", {}).get("has_phase_issue"):
            return NodeStatus.SUCCESS

        y = blackboard.get_val("y")
        if y.ndim < 2:
            return NodeStatus.SUCCESS  # mono，無需處理

        try:
            y_fixed = y.copy()
            # shape: (channels, samples) or (samples, channels)
            if y_fixed.shape[0] <= 2:
                y_fixed[1] = -y_fixed[1]   # flip right channel
            else:
                y_fixed[:, 1] = -y_fixed[:, 1]
            blackboard.set_val("y", y_fixed.astype(np.float32))
            print("[PhaseAlignment] right channel polarity inverted")
        except Exception as exc:
            print(f"[PhaseAlignment] WARN: {exc}")

        return NodeStatus.SUCCESS


class SpectralDenoiseNode(BaseNode):
    """
    頻譜降噪。
    方法：Minimum Statistics 動態噪聲追蹤 + Wiener Filter。
    業界標準：Martin's Minimum Statistics (1994)，不依賴固定靜音段估噪。
    三版策略：於此處產出 y_denoised 寫入 Blackboard "y_denoised"，供 C 版檔匯出與後續 AI 樂器分離/節拍追蹤最佳化使用。
    """
    required_keys = ["y", "sr"]
    optional_keys = ["quality_grade"]
    output_keys = ["y_denoised"]

    def __init__(self, enable_for_grades=("A", "B", "C", "WARN")):
        super().__init__("SpectralDenoiseNode")
        self.enable_for_grades = set(enable_for_grades)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        try:
            if y.ndim > 1:
                # 獨立對每個聲道進行降噪，避免點對點相除除爆產生電子噪聲
                channels = []
                for ch in range(y.shape[0] if y.shape[0] <= 2 else y.shape[1]):
                    ch_data = y[ch] if y.shape[0] <= 2 else y[:, ch]
                    denoised_ch = self._minimum_statistics_denoise(ch_data.astype(np.float32), sr)
                    channels.append(denoised_ch)
                if y.shape[0] <= 2:
                    y_denoised = np.stack(channels, axis=0)
                else:
                    y_denoised = np.stack(channels, axis=1)
            else:
                y_denoised = self._minimum_statistics_denoise(y.astype(np.float32), sr)

            blackboard.set_val("y_denoised", y_denoised.astype(np.float32))
            print("[SpectralDenoise] Smooth Minimum Statistics denoising applied (natural sound, zero musical noise)")
        except Exception as exc:
            print(f"[SpectralDenoise] WARN fallback to original y: {exc}")
            blackboard.set_val("y_denoised", y.astype(np.float32))

        return NodeStatus.SUCCESS

    @staticmethod
    def _minimum_statistics_denoise(mono: np.ndarray, sr: int) -> np.ndarray:
        """
        Minimum Statistics 頻譜平滑降噪核心。
        採用 Decision-Directed / Temporal Smoothing 防止金屬電子音 (Musical Noise)。
        """
        frame_len = int(MS_FRAME_SEC * sr)
        hop_len = frame_len // 2
        n_fft = frame_len

        # STFT
        f, t, Zxx = scipy.signal.stft(mono, fs=sr, nperseg=n_fft, noverlap=frame_len - hop_len)
        mag = np.abs(Zxx)
        phase = np.angle(Zxx)

        # Minimum Statistics：滑動視窗最小值追蹤
        window_frames = max(1, int(MS_WINDOW_SEC / MS_FRAME_SEC))
        noise_est = np.zeros_like(mag)
        for i in range(mag.shape[1]):
            start = max(0, i - window_frames)
            noise_est[:, i] = np.min(mag[:, start:i + 1], axis=1)

        # 初始增益計算 (Wiener Filter)
        gain_raw = np.maximum(1.0 - MS_ALPHA * noise_est / (mag + 1e-9), MS_BETA)

        # 時間維度一階平滑 (First-order IIR smoothing across time) 防閃爍電子音
        gain_smooth = np.zeros_like(gain_raw)
        smooth_factor = 0.85  # 85% 歷史繼承，平滑過渡
        gain_smooth[:, 0] = gain_raw[:, 0]
        for i in range(1, gain_raw.shape[1]):
            gain_smooth[:, i] = smooth_factor * gain_smooth[:, i - 1] + (1 - smooth_factor) * gain_raw[:, i]

        mag_denoised = mag * gain_smooth

        # iSTFT
        _, y_denoised = scipy.signal.istft(
            mag_denoised * np.exp(1j * phase),
            fs=sr, nperseg=n_fft, noverlap=frame_len - hop_len
        )
        y_out = np.zeros_like(mono)
        n = min(len(mono), len(y_denoised))
        y_out[:n] = y_denoised[:n]
        return y_out


class CrowdNoiseRemovalNode(BaseNode):
    """
    人群喧鬧聲 / 現場雜訊去除節點 (Direct Discard / Clean Node)。
    當 quality_flags 中 has_crowd_noise 為 True 時觸發。
    使用中頻瞬態壓制與低通帶通組合，將喧鬧聲/拍手聲直接清洗過濾，不留下額外檔案。
    """
    required_keys = ["y", "sr", "quality_flags"]
    optional_keys = []
    output_keys = ["y"]

    def __init__(self):
        super().__init__("CrowdNoiseRemovalNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        flags = blackboard.get_val("quality_flags", {})
        if not flags.get("has_crowd_noise"):
            return NodeStatus.SUCCESS

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        try:
            # 使用 Notch / Bandstop 壓制 2kHz~3.5kHz 突發人群拍手喧躁主頻段
            nyq = sr / 2.0
            b, a = scipy.signal.butter(3, [1800.0 / nyq, 3400.0 / nyq], btype='bandstop')
            if y.ndim > 1:
                y_clean = scipy.signal.filtfilt(b, a, y, axis=-1)
            else:
                y_clean = scipy.signal.filtfilt(b, a, y)

            blackboard.set_val("y", y_clean.astype(np.float32))
            print("[CrowdNoiseRemoval] OK — Crowd noise filter applied, noise signal discarded")
        except Exception as exc:
            print(f"[CrowdNoiseRemoval] WARN: {exc}")

        return NodeStatus.SUCCESS


class LoudnessNormalizeNode(BaseNode):
    """
    響度正規化。
    目標：-18 LUFS（給 HTDemucs 留 headroom），True Peak ≤ -1.0 dBTP。
    方法：RMS 近似 LUFS 增益 + Soft Knee True Peak Limiter。
    業界標準：EBU R128, 串流 -14 LUFS / -1.0 dBTP。

    注意：分析前只做到 -18 LUFS（保守），不是最終 mastering 標準。
    """
    required_keys = ["y", "sr", "quality_flags"]
    optional_keys = []
    output_keys = ["y", "applied_lufs_gain_db"]

    def __init__(self, target_lufs: float = TARGET_LUFS_ANALYSIS):
        super().__init__("LoudnessNormalizeNode")
        self.target_lufs = target_lufs

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        flags = blackboard.get_val("quality_flags", {})
        grade = blackboard.get_val("quality_grade", "A")

        # 只在需要時處理
        if not flags.get("needs_amplify") and grade not in ("C",):
            blackboard.set_val("applied_lufs_gain_db", 0.0)
            return NodeStatus.SUCCESS

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")

        try:
            if y.ndim > 1:
                mono = y.mean(axis=0) if y.shape[0] <= 2 else y.mean(axis=1)
            else:
                mono = y

            rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2)))
            current_lufs = _rms_to_lufs(rms)
            gain_db = self.target_lufs - current_lufs
            gain_linear = 10 ** (gain_db / 20.0)

            y_amplified = y.astype(np.float32) * gain_linear

            # Soft Knee True Peak Limiter（業界：-1.0 dBTP ceiling）
            ceiling = 10 ** (TARGET_TRUE_PEAK_DBTP / 20.0)   # ≈ 0.8913
            y_amplified = self._soft_knee_limiter(y_amplified, ceiling=ceiling, knee_db=3.0)

            blackboard.set_val("y", y_amplified)
            blackboard.set_val("applied_lufs_gain_db", round(gain_db, 2))
            print(f"[LoudnessNormalize] {current_lufs:.1f} → {self.target_lufs:.1f} LUFS "
                  f"gain={gain_db:+.1f}dB, True Peak ceiling={TARGET_TRUE_PEAK_DBTP}dBTP")
        except Exception as exc:
            print(f"[LoudnessNormalize] WARN: {exc}")
            blackboard.set_val("applied_lufs_gain_db", 0.0)

        return NodeStatus.SUCCESS

    @staticmethod
    def _soft_knee_limiter(y: np.ndarray, ceiling: float = 0.891, knee_db: float = 3.0) -> np.ndarray:
        """
        Soft Knee Limiter。
        knee_db 以下線性通過，以上平滑壓縮至 ceiling，避免硬截切。
        """
        knee_lin = ceiling * 10 ** (-knee_db / 20.0)
        abs_y = np.abs(y)
        # knee 以下不動
        out = y.copy()
        mask = abs_y > knee_lin
        if np.any(mask):
            # soft knee 壓縮
            over = abs_y[mask] - knee_lin
            over_max = ceiling - knee_lin + 1e-9
            compress_ratio = 1 - (over / (over_max + over))  # 漸進比例
            compressed = knee_lin + over * compress_ratio
            compressed = np.minimum(compressed, ceiling)
            out[mask] = np.sign(y[mask]) * compressed
        return out


class WriteNormalizedWAVNode(BaseNode):
    """
    分層降噪多版本 (A / B / C 三版) 匯出節點：
    - A 版 ({name}_raw.wav): 零處理原聲備份
    - B 版 ({name}_normalized.wav): 輕度修復（10Hz 祛直流、Phase 校正、靜音修剪、EBU R128 音量正規化）
    - C 版 ({name}_denoised.wav): 深度降噪（Martin Minimum Statistics + 人群/現場喧噪清洗）

    Blackboard 更新：
      raw_wav_path        → A 版原檔
      normalized_wav_path → B 版輕度修復檔
      denoised_wav_path   → C 版深度降噪檔
      target_analysis_path→ 指向 C 版 ({name}_denoised.wav)，供 AI 樂器分離與 Beat tracking 最佳化
      audio_path          → 指向 B 版 ({name}_normalized.wav) 供廣播/聽感預覽使用
    """
    required_keys = ["y", "sr", "audio_path"]
    optional_keys = ["project_dir", "project_name", "y_denoised"]
    output_keys = ["audio_path", "raw_wav_path", "normalized_wav_path", "denoised_wav_path", "target_analysis_path"]

    def __init__(self):
        super().__init__("WriteNormalizedWAVNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        import shutil

        y = blackboard.get_val("y")
        y_denoised = blackboard.get_val("y_denoised", y)
        sr = blackboard.get_val("sr")
        original_path = blackboard.get_val("audio_path", "")
        project_dir = blackboard.get_val("project_dir", "")
        project_name = blackboard.get_val("project_name", "")

        if project_dir and project_name:
            source_dir = os.path.join(project_dir, "source")
            os.makedirs(source_dir, exist_ok=True)
            raw_out = os.path.join(source_dir, f"{project_name}_raw.wav")
            norm_out = os.path.join(source_dir, f"{project_name}_normalized.wav")
            denoise_out = os.path.join(source_dir, f"{project_name}_denoised.wav")
        elif original_path:
            base_dir = os.path.dirname(original_path)
            stem = os.path.splitext(os.path.basename(original_path))[0]
            raw_out = os.path.join(base_dir, f"{stem}_raw.wav")
            norm_out = os.path.join(base_dir, f"{stem}_normalized.wav")
            denoise_out = os.path.join(base_dir, f"{stem}_denoised.wav")
        else:
            print("[WriteNormalizedWAV] cannot determine output path")
            return NodeStatus.FAILURE

        try:
            # 輔助轉置函式
            def _to_write_fmt(arr):
                if arr.ndim == 2 and arr.shape[0] <= 2:
                    return arr.T
                return arr

            # 1. 寫入 / 備份 A 版 (raw)
            if original_path and os.path.exists(original_path) and original_path != raw_out:
                shutil.copyfile(original_path, raw_out)
            else:
                sf.write(raw_out, _to_write_fmt(y).astype(np.float32), sr)

            # 2. 寫入 B 版 (normalized)
            sf.write(norm_out, _to_write_fmt(y).astype(np.float32), sr)

            # 3. 寫入 C 版 (denoised)
            sf.write(denoise_out, _to_write_fmt(y_denoised).astype(np.float32), sr)

            # 註冊三版契約至 Blackboard
            blackboard.set_val("original_wav_path", original_path)
            blackboard.set_val("raw_wav_path", raw_out)
            blackboard.set_val("normalized_wav_path", norm_out)
            blackboard.set_val("denoised_wav_path", denoise_out)

            # 廣播預覽預設使用 B 版；AI 追蹤分析優先指向 C 版
            blackboard.set_val("audio_path", norm_out)
            blackboard.set_val("target_analysis_path", denoise_out)

            print(f"[WriteMultiTierWAV] OK — 成功輸出三版音訊：\n"
                  f"  - A版(Raw): {raw_out}\n"
                  f"  - B版(Normalized): {norm_out}\n"
                  f"  - C版(Denoised): {denoise_out}")
            return NodeStatus.SUCCESS
        except Exception as exc:
            print(f"[WriteMultiTierWAV] FAILED: {exc}")
            return NodeStatus.FAILURE


class PassthroughNode(BaseNode):
    """Grade A 音訊 Passthrough 節點，同時確保 A/B/C 三版均有落盤檔案。"""
    required_keys = ["y", "sr", "audio_path"]
    optional_keys = ["project_dir", "project_name"]
    output_keys = ["raw_wav_path", "normalized_wav_path", "denoised_wav_path", "target_analysis_path"]

    def __init__(self):
        super().__init__("PassthroughNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        writer = WriteNormalizedWAVNode()
        return writer.execute(blackboard)


class NeedsEnhancementConditionNode(BaseNode):
    required_keys = ["quality_grade"]
    optional_keys = []
    output_keys = ["needs_enhancement_checked"]

    def __init__(self):
        super().__init__("NeedsEnhancementConditionNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        grade = blackboard.get_val("quality_grade", "A")
        if grade in ("B", "C", "WARN"):
            blackboard.set_val("needs_enhancement_checked", True)
            return NodeStatus.SUCCESS
        return NodeStatus.FAILURE   # grade A → Fallback 走 Passthrough


# ---------------------------------------------------------------------------
# Tree Builder & Engine
# ---------------------------------------------------------------------------

def build_audio_quality_tree() -> SequenceNode:
    """
    Build Stage 1 Audio Quality Inspection & Enhancement BT.

    Sequence [AudioQualityRoot]
    ├── AudioLoadNode
    ├── AudioQualityInspectorNode
    ├── QualityGateNode
    └── Fallback [QualityOptimizationSelector]
        ├── Sequence [EnhancementChain]       ← grade B/C/WARN
        │   ├── NeedsEnhancementConditionNode
        │   ├── DCOffsetRemovalNode
        │   ├── SilenceTrimNode
        │   ├── PhaseAlignmentNode
        │   ├── SpectralDenoiseNode
        │   ├── LoudnessNormalizeNode
        │   └── WriteNormalizedWAVNode        ← 寫磁碟 + 更新 audio_path
        └── PassthroughNode                   ← grade A，audio_path 不變
    """
    enhancement_chain = SequenceNode("EnhancementChain", [
        NeedsEnhancementConditionNode(),
        DCOffsetRemovalNode(),
        SilenceTrimNode(),
        PhaseAlignmentNode(),
        DeHumFilterNode(),
        SpectralDenoiseNode(),
        CrowdNoiseRemovalNode(),
        SeparateCrowdNode(),
        DeReverbFilterNode(),
        LoudnessNormalizeNode(),
        WriteNormalizedWAVNode(),
    ])

class DeHumFilterNode(BaseNode):
    """【Pre-Vocal 淨化】：去除 50Hz/60Hz 交流電嗡嗡聲與線材接觸不良雜聲。"""
    required_keys = ["y", "sr"]
    optional_keys = []
    output_keys = ["y"]

    def __init__(self):
        super().__init__("DeHumFilterNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")
        if y is None or sr is None:
            return NodeStatus.FAILURE
        try:
            import numpy as np
            from scipy.signal import iirnotch, filtfilt
            # 濾除 50Hz / 60Hz 及其諧波 (100, 120Hz)
            for freq in [50.0, 60.0, 100.0, 120.0]:
                if freq < sr / 2.0:
                    b_n, a_n = iirnotch(freq, 30.0, sr)
                    if y.ndim == 1:
                        y = filtfilt(b_n, a_n, y)
                    else:
                        y[0] = filtfilt(b_n, a_n, y[0])
                        y[1] = filtfilt(b_n, a_n, y[1])
            blackboard.set_val("y", y)
            print("[DeHumFilter] ✅ 成功消除 50/60Hz 電流嗡嗡聲")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[DeHumFilter Warning] {e}")
            return NodeStatus.SUCCESS


class SeparateCrowdNode(BaseNode):
    """【Pre-Vocal 淨化】：現場觀眾歡呼與尖叫聲剝離至 source/crowd_cheering.wav。"""
    required_keys = ["audio_path"]
    optional_keys = ["output_dir"]
    output_keys = ["crowd_path"]

    def __init__(self, separator=None):
        super().__init__("SeparateCrowdNode")
        from pgm_craft.separator import CascadedStemSeparator
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        output_dir = blackboard.get_val("output_dir", os.path.dirname(audio_path))
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE
        try:
            crowd_path, _ = self.separator.separate_crowd(audio_path, output_dir)
            blackboard.set_val("crowd_path", crowd_path)
            print(f"[SeparateCrowdNode] OK -> {crowd_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateCrowdNode Warning] {e}")
            return NodeStatus.SUCCESS


class DeReverbFilterNode(BaseNode):
    """【Pre-Vocal 淨化】：去除房間迴音與教堂殘響，還原 Studio 極乾聲。"""
    required_keys = ["audio_path"]
    optional_keys = ["output_dir"]
    output_keys = ["dereverb_dry_path"]

    def __init__(self, separator=None):
        super().__init__("DeReverbFilterNode")
        from pgm_craft.separator import CascadedStemSeparator
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        output_dir = blackboard.get_val("output_dir", os.path.dirname(audio_path))
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE
        try:
            dry_path, _ = self.separator.process_dereverb(audio_path, output_dir)
            blackboard.set_val("dereverb_dry_path", dry_path)
            print(f"[DeReverbFilterNode] OK -> {dry_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[DeReverbFilterNode Warning] {e}")
            return NodeStatus.SUCCESS


def build_audio_quality_tree() -> BaseNode:
    enhancement_chain = SequenceNode("EnhancementChain", [
        NeedsEnhancementConditionNode(),
        DCOffsetRemovalNode(),
        SilenceTrimNode(),
        PhaseAlignmentNode(),
        DeHumFilterNode(),
        SpectralDenoiseNode(),
        CrowdNoiseRemovalNode(),
        SeparateCrowdNode(),
        DeReverbFilterNode(),
        LoudnessNormalizeNode(),
        WriteNormalizedWAVNode(),
    ])

    optimization_selector = FallbackNode("QualityOptimizationSelector", [
        enhancement_chain,
        PassthroughNode(),
    ])

    return SequenceNode("AudioQualityRoot", [
        AudioLoadNode(),
        AudioQualityInspectorNode(),
        QualityGateNode(),
        optimization_selector,
    ])


class AudioQualityBTEngine:
    """Stage 1 Audio Quality BT Engine wrapper."""

    def __init__(self):
        self.tree = build_audio_quality_tree()

    def run(self, *, audio_path: str, output_dir: str = "") -> Blackboard:
        bb = Blackboard()
        bb.set_val("audio_path", audio_path)
        bb.set_val("output_dir", output_dir)
        bb.set_val("trim_offset_sec", 0.0)
        bb.set_val("quality_optimized", False)

        print("\n=== [AudioQualityBT] Stage 1 Start ===")
        status = self.tree.run(bb)
        bb.set_val("audio_quality_status", status.name)

        if status.name == "SUCCESS":
            grade = bb.get_val("quality_grade", "?")
            print(f"=== [AudioQualityBT] Done grade={grade} ===")
            bb.set_val("quality_optimized",
                       bb.get_val("quality_grade") not in ("A",))
        else:
            print("=== [AudioQualityBT] FAILED ===")

        return bb
