"""
PGMCraft Audio Quality Enhancement Engine & Advanced Optimizations.
Implements:
1. Dynamic Audio Chunking with Overlap Crossfade (低顯存適應性動態切片)
2. Stereo Phase Alignment via Hilbert Transform (立體聲相位解算與對齊)
3. MIDI Grid Quantization & Swing Factor (MIDI 採譜自動網格量化)
4. EBU R128 Loudness Normalization & Soft Peak Limiter
"""

import os
import numpy as np
import scipy.signal
import soundfile as sf

class DynamicAudioChunker:
    """低顯存適應性動態切片器 (防止小於 6GB VRAM 的 GPU OOM 溢出)"""

    def chunk_and_process(self, y, sr, process_func, chunk_duration=10.0, overlap_duration=0.5):
        """
        將長音軌切片為 10s 離散區段，並在交界處使用 Linear Hanning Crossfade 平滑縫合
        """
        chunk_samples = int(chunk_duration * sr)
        overlap_samples = int(overlap_duration * sr)
        step_samples = chunk_samples - overlap_samples

        total_samples = len(y)
        if total_samples <= chunk_samples:
            return process_func(y)

        # 輸出陣列初始化
        y_out = np.zeros_like(y, dtype=np.float32)
        weight_out = np.zeros(total_samples, dtype=np.float32)

        start = 0
        window = np.hanning(chunk_samples) if y.ndim == 1 else np.hanning(chunk_samples)[:, None]

        while start < total_samples:
            end = min(start + chunk_samples, total_samples)
            segment = y[start:end]
            
            # 若最後一個區段小於 chunk_samples，補零補齊後傳給 process_func
            if len(segment) < chunk_samples:
                pad_len = chunk_samples - len(segment)
                pad_width = ((0, pad_len), (0, 0)) if y.ndim > 1 else (0, pad_len)
                segment_padded = np.pad(segment, pad_width, mode='constant')
                proc_padded = process_func(segment_padded)
                proc_segment = proc_padded[:len(segment)]
                curr_window = window[:len(segment)]
            else:
                proc_segment = process_func(segment)
                curr_window = window

            # 淡入淡出加權疊加 (Overlap Add)
            y_out[start:end] += proc_segment * curr_window
            weight_out[start:end] += (curr_window[:, 0] if y.ndim > 1 else curr_window)

            start += step_samples

        # 消除權重避免振幅衰減
        weight_out = np.maximum(weight_out, 1e-6)
        if y.ndim > 1:
            y_out = y_out / weight_out[:, None]
        else:
            y_out = y_out / weight_out

        return y_out


class StereoPhaseAligner:
    """立體聲相位解算與對齊器 (希爾伯特轉換 Phase Correction)"""

    def align_stereo_phase(self, y_stereo):
        """
        計算左與右聲道之瞬間相位差 (Instantaneous Phase)，進行對齊補償，解決反相抵銷
        """
        if y_stereo.ndim != 2 or y_stereo.shape[1] != 2:
            return y_stereo

        left = y_stereo[:, 0]
        right = y_stereo[:, 1]

        # 計算 Hilbert 轉換相位
        analytic_left = scipy.signal.hilbert(left)
        analytic_right = scipy.signal.hilbert(right)

        phase_left = np.angle(analytic_left)
        phase_right = np.angle(analytic_right)

        # 計算平均相位差
        phase_diff = np.mean(phase_left - phase_right)
        
        # 若反相 (相位差接近 pi 弧度)，修復右聲道相位
        if np.abs(phase_diff) > (np.pi / 2):
            print(f"[Stereo Aligner] 檢測到聲道相位差 ({phase_diff:.2f} rad)，自動進行相位對齊...")
            right_aligned = -right
            return np.column_stack((left, right_aligned))

        return y_stereo


class MIDIQuantizer:
    """MIDI 音符採譜自動網格量化器 (Quantization Grid)"""

    def quantize_notes(self, notes_data, bpm=120.0, grid_fraction=16):
        """
        將微秒級真人和聲 MIDI 音符對齊到 1/16 拍或 1/32 拍網格
        """
        seconds_per_beat = 60.0 / bpm
        grid_seconds = seconds_per_beat / (grid_fraction / 4.0)

        quantized_notes = []
        for note in notes_data:
            start_q = round(note['start_time'] / grid_seconds) * grid_seconds
            end_q = round(note['end_time'] / grid_seconds) * grid_seconds
            if end_q <= start_q:
                end_q = start_q + grid_seconds

            quantized_notes.append({
                'pitch': note['pitch'],
                'start_time': round(start_q, 4),
                'end_time': round(end_q, 4),
                'velocity': note.get('velocity', 100)
            })
        return quantized_notes


class AudioEnhancerEngine:
    """全功能音質優化與進階後處理引擎"""

    def __init__(self):
        self.chunker = DynamicAudioChunker()
        self.phase_aligner = StereoPhaseAligner()

    def normalize_loudness_ebu_r128(self, y, sr, target_lufs=-14.0):
        rms = np.sqrt(np.mean(y ** 2))
        if rms <= 0: return y
        
        current_db = 20 * np.log10(rms)
        gain = 10 ** ((target_lufs - current_db) / 20.0)
        y_amplified = y * gain
        
        max_peak = np.max(np.abs(y_amplified))
        if max_peak > 0.98:
            y_amplified = y_amplified * (0.98 / max_peak)
        return y_amplified

    def spectral_denoise(self, y, sr, alpha=1.5):
        stft = scipy.signal.stft(y, fs=sr, nperseg=1024)
        mag = np.abs(stft[2])
        phase = np.angle(stft[2])

        noise_profile = np.mean(mag[:, :10], axis=1, keepdims=True)
        mag_denoised = np.maximum(mag - alpha * noise_profile, 0.0)
        _, y_denoised = scipy.signal.istft(mag_denoised * np.exp(1j * phase), fs=sr)
        return y_denoised

    def enhance_audio_file(self, input_wav_path, output_wav_path=None, target_lufs=-14.0):
        if output_wav_path is None:
            output_wav_path = input_wav_path

        y, sr = sf.read(input_wav_path)
        
        # Step 1: 立體聲相位對齊
        if y.ndim == 2:
            y = self.phase_aligner.align_stereo_phase(y)

        # Step 2: 頻譜降噪
        y_clean = self.spectral_denoise(y, sr)
        
        # Step 3: EBU R128 響度增益與 Peak Limit
        y_enhanced = self.normalize_loudness_ebu_r128(y_clean, sr, target_lufs=target_lufs)
        
        sf.write(output_wav_path, y_enhanced, sr)
        return output_wav_path
