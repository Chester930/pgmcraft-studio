"""
Beat Tracker Engine: Dynamic Beat/Downbeat Tracking, Key Detection, Chord Recognition,
Click Track & MIDI Map Generation, and Visualization.
"""

import os
import json
import math
import numpy as np
import scipy.signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import soundfile as sf

import librosa
import pretty_midi
try:
    from BeatNet.BeatNet import BeatNet
except Exception:
    BeatNet = None

# Key Profiles (Krumhansl-Schmuckler)
KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 2.69, 3.34, 3.17, 3.28])
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Basic Chord Templates (Triads)
CHORD_TEMPLATES = {}
for i, name in enumerate(NOTE_NAMES):
    # Major triad: root, +4 semitones, +7 semitones
    maj_vec = np.zeros(12)
    maj_vec[i] = 1.0
    maj_vec[(i + 4) % 12] = 0.8
    maj_vec[(i + 7) % 12] = 0.8
    CHORD_TEMPLATES[f"{name}"] = maj_vec / np.linalg.norm(maj_vec)

    # Minor triad: root, +3 semitones, +7 semitones
    min_vec = np.zeros(12)
    min_vec[i] = 1.0
    min_vec[(i + 3) % 12] = 0.8
    min_vec[(i + 7) % 12] = 0.8
    CHORD_TEMPLATES[f"{name}m"] = min_vec / np.linalg.norm(min_vec)


class BeatTrackingSystem:
    def __init__(self, use_beatnet=True):
        self.use_beatnet = use_beatnet

    def track_beats(self, audio_path):
        """
        Track beats and downbeats.
        Returns: numpy array of shape (N, 2), columns: [timestamp_seconds, beat_label (1 for downbeat, 2-4 for weak beats)]
        """
        beats = None
        
        if self.use_beatnet and BeatNet is not None:
            try:
                print("Running BeatNet model for dynamic beat tracking...")
                estimator = BeatNet(1, mode='offline', inference_model='dbn', plot=[], thread=False)
                output = estimator.process(audio_path)
                if output is not None and len(output) > 0:
                    beats = output
                    print(f"BeatNet successfully tracked {len(beats)} beats.")
            except Exception as e:
                print(f"BeatNet tracking failed or not available ({e}). Falling back to Librosa.")

        # 2. Fallback to Librosa beat tracking + downbeat estimation
        if beats is None:
            beats = self._librosa_fallback_track(audio_path)
            
        return beats

    def _librosa_fallback_track(self, audio_path):
        """Fallback beat & downbeat estimator using Librosa onset & spectral analysis."""
        print("Running Librosa fallback beat tracking...")
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        
        # Dynamic BPM and beat frame estimation
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        
        if len(beat_times) == 0:
            return np.array([[0.0, 1]])

        # Estimate downbeats by spectral energy at beat positions
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        beat_onsets = onset_env[np.minimum(beat_frames, len(onset_env) - 1)]
        
        # Simple 4/4 meter downbeat tagging using 4-beat cycle energy sum
        best_offset = 0
        max_energy = -1.0
        for offset in range(4):
            cycle_energy = sum(beat_onsets[i] for i in range(offset, len(beat_onsets), 4))
            if cycle_energy > max_energy:
                max_energy = cycle_energy
                best_offset = offset
                
        beats = []
        for i, t in enumerate(beat_times):
            beat_num = ((i - best_offset) % 4) + 1
            beats.append([float(t), int(beat_num)])
            
        return np.array(beats)

    def synthesize_click_track(self, audio_path, beats, output_click_path, output_mix_path):
        """
        Synthesizes high/low click audio track and creates a mixed preview file.
        """
        y, sr = sf.read(audio_path)
        if len(y.shape) > 1:
            num_channels = y.shape[1]
            total_samples = y.shape[0]
        else:
            num_channels = 1
            total_samples = len(y)
            y = y.reshape(-1, 1)

        click_signal = np.zeros((total_samples, 1), dtype=np.float32)

        # Generate click sounds: High pitch (1000Hz) for downbeat 1, Low pitch (500Hz) for beats 2, 3, 4
        high_click = self._generate_beep(frequency=1000, duration=0.04, sr=sr, amplitude=0.8)
        low_click = self._generate_beep(frequency=500, duration=0.03, sr=sr, amplitude=0.5)

        for b in beats:
            t_sec, beat_num = b[0], int(b[1])
            sample_idx = int(t_sec * sr)
            if sample_idx >= total_samples:
                continue
            
            click_sound = high_click if beat_num == 1 else low_click
            click_len = len(click_sound)
            end_idx = min(sample_idx + click_len, total_samples)
            actual_len = end_idx - sample_idx
            
            click_signal[sample_idx:end_idx, 0] += click_sound[:actual_len]

        # Save standalone click track (stereo matching or mono)
        if num_channels > 1:
            click_track_out = np.hstack([click_signal, click_signal])
        else:
            click_track_out = click_signal

        sf.write(output_click_path, click_track_out, sr)
        print(f"Click track saved to: {output_click_path}")

        # Normalize and mix
        norm_y = y / (np.max(np.abs(y)) + 1e-6)
        norm_click = click_track_out / (np.max(np.abs(click_track_out)) + 1e-6)
        
        mixed = 0.7 * norm_y + 0.3 * norm_click
        mixed = mixed / (np.max(np.abs(mixed)) + 1e-6) # Normalize preventing clipping

        sf.write(output_mix_path, mixed, sr)
        print(f"Mixed track saved to: {output_mix_path}")

    def _generate_beep(self, frequency, duration, sr, amplitude=0.5):
        """Generates a sine wave beep with exponential decay."""
        t = np.linspace(0, duration, int(sr * duration), False)
        envelope = np.exp(-15 * t / duration)
        sine = amplitude * np.sin(2 * np.pi * frequency * t) * envelope
        return sine.astype(np.float32)

    def export_midi_tempo_map(self, beats, output_midi_path):
        """
        Exports a PrettyMIDI file containing dynamic tempo changes and downbeat markers.
        """
        if pretty_midi is None:
            print("pretty_midi package not installed. Skipping MIDI export.")
            return

        pm = pretty_midi.PrettyMIDI()

        # Calculate dynamic tempo changes for every beat interval
        for i in range(len(beats) - 1):
            t1, _ = beats[i]
            t2, _ = beats[i+1]
            dt = t2 - t1
            if dt > 0.05: # Avoid divide by zero / extreme values
                bpm = 60.0 / dt
                # PrettyMIDI allows adding tempo changes
                pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, t1))

        # Create a dummy click instrument track with MIDI notes
        click_inst = pretty_midi.Instrument(program=115) # Woodblock / Percussion
        for b in beats:
            t_sec, beat_num = b[0], int(b[1])
            pitch = 76 if beat_num == 1 else 68 # High vs Low Woodblock
            velocity = 110 if beat_num == 1 else 80
            note = pretty_midi.Note(
                velocity=velocity, pitch=pitch, start=t_sec, end=t_sec + 0.08
            )
            click_inst.notes.append(note)

        pm.instruments.append(click_inst)
        pm.write(output_midi_path)
        print(f"MIDI tempo map saved to: {output_midi_path}")

    def analyze_key_and_chords(self, audio_path, beats):
        """
        Performs Key Detection (Krumhansl-Schmuckler) and Chord Progression analysis per beat/bar.
        """
        if librosa is None:
            return {"key": "Unknown (librosa required)", "chords": []}

        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        
        # 1. Global Key Detection
        global_chroma = np.sum(chroma, axis=1)
        global_chroma = global_chroma / (np.linalg.norm(global_chroma) + 1e-6)

        best_key = "C Major"
        max_corr = -999.0

        for root_idx in range(12):
            # Major key correlation
            shifted_major = np.roll(KS_MAJOR, root_idx)
            corr_maj = np.corrcoef(global_chroma, shifted_major)[0, 1]
            if corr_maj > max_corr:
                max_corr = corr_maj
                best_key = f"{NOTE_NAMES[root_idx]} Major"

            # Minor key correlation
            shifted_minor = np.roll(KS_MINOR, root_idx)
            corr_min = np.corrcoef(global_chroma, shifted_minor)[0, 1]
            if corr_min > max_corr:
                max_corr = corr_min
                best_key = f"{NOTE_NAMES[root_idx]} Minor"

        # 2. Measure-by-Measure Chord Progression
        measure_downbeats = [b[0] for b in beats if int(b[1]) == 1]
        if len(measure_downbeats) == 0 and len(beats) > 0:
            measure_downbeats = [beats[i][0] for i in range(0, len(beats), 4)]

        chord_progression = []
        for idx in range(len(measure_downbeats)):
            start_t = measure_downbeats[idx]
            end_t = measure_downbeats[idx+1] if idx+1 < len(measure_downbeats) else beats[-1][0]
            
            start_frame = librosa.time_to_frames(start_t, sr=sr)
            end_frame = librosa.time_to_frames(end_t, sr=sr)
            
            if start_frame >= chroma.shape[1]:
                continue
            end_frame = max(start_frame + 1, min(end_frame, chroma.shape[1]))
            
            seg_chroma = np.mean(chroma[:, start_frame:end_frame], axis=1)
            norm_seg = seg_chroma / (np.linalg.norm(seg_chroma) + 1e-6)
            
            best_chord = "C"
            max_sim = -999.0
            for chord_name, template in CHORD_TEMPLATES.items():
                sim = np.dot(norm_seg, template)
                if sim > max_sim:
                    max_sim = sim
                    best_chord = chord_name
            
            chord_progression.append({
                "measure": idx + 1,
                "start_time": round(float(start_t), 2),
                "end_time": round(float(end_t), 2),
                "chord": best_chord
            })

        return {
            "key": best_key,
            "chord_progression": chord_progression
        }

    def plot_tempo_curve(self, beats, output_png_path):
        """
        Plots BPM over time graph.
        """
        timestamps = []
        bpms = []

        for i in range(len(beats) - 1):
            t1 = beats[i][0]
            t2 = beats[i+1][0]
            dt = t2 - t1
            if dt > 0.05:
                bpm = 60.0 / dt
                if 40 <= bpm <= 260: # Reasonable musical tempo filter
                    timestamps.append(t1)
                    bpms.append(bpm)

        if len(bpms) == 0:
            return

        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        
        # Plot raw BPM points & smooth curve
        ax.plot(timestamps, bpms, color='#1f77b4', alpha=0.4, linestyle='--', label='Instantaneous BPM')
        
        # Moving average smoothing
        window_size = min(7, len(bpms))
        if window_size > 1:
            smoothed_bpms = np.convolve(bpms, np.ones(window_size)/window_size, mode='same')
            ax.plot(timestamps, smoothed_bpms, color='#ff7f0e', linewidth=2.5, label='Smoothed Tempo Trend')

        avg_bpm = np.mean(bpms)
        ax.axhline(avg_bpm, color='red', linestyle=':', label=f'Average BPM ({avg_bpm:.1f})')

        ax.set_title('Dynamic Tempo Curve over Time (BPM)', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Time (seconds)', fontsize=12)
        ax.set_ylabel('Beats Per Minute (BPM)', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper right')
        
        plt.tight_layout()
        plt.savefig(output_png_path)
        plt.close()
        print(f"Tempo curve saved to: {output_png_path}")

    def run_full_pipeline(self, audio_path, output_dir="outputs"):
        """
        Runs complete pipeline from tracking to report generation.
        """
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        click_path = os.path.join(output_dir, "click_track.wav")
        mix_path = os.path.join(output_dir, "mix_with_click.wav")
        midi_path = os.path.join(output_dir, "tempo_map.mid")
        png_path = os.path.join(output_dir, "tempo_curve.png")
        report_json_path = os.path.join(output_dir, "analysis_report.json")
        report_txt_path = os.path.join(output_dir, "analysis_report.txt")

        # 1. Track beats
        beats = self.track_beats(audio_path)
        
        # 2. Synthesize audio click and mix
        self.synthesize_click_track(audio_path, beats, click_path, mix_path)

        # 3. Export MIDI Map
        self.export_midi_tempo_map(beats, midi_path)

        # 4. Plot Tempo Curve
        self.plot_tempo_curve(beats, png_path)

        # 5. Key and Chord Analysis
        analysis_res = self.analyze_key_and_chords(audio_path, beats)

        # 6. Calculate total metrics
        total_beats = len(beats)
        downbeats = [b for b in beats if int(b[1]) == 1]
        total_measures = len(downbeats) if len(downbeats) > 0 else math.ceil(total_beats / 4)

        bpms = [60.0 / (beats[i+1][0] - beats[i][0]) for i in range(len(beats)-1) if (beats[i+1][0] - beats[i][0]) > 0.05]
        avg_bpm = float(np.mean(bpms)) if len(bpms) > 0 else 120.0
        min_bpm = float(np.min(bpms)) if len(bpms) > 0 else avg_bpm
        max_bpm = float(np.max(bpms)) if len(bpms) > 0 else avg_bpm

        report_data = {
            "file_name": os.path.basename(audio_path),
            "estimated_key": analysis_res["key"],
            "average_bpm": round(avg_bpm, 1),
            "min_bpm": round(min_bpm, 1),
            "max_bpm": round(max_bpm, 1),
            "total_measures": total_measures,
            "total_beats": total_beats,
            "chord_progression": analysis_res["chord_progression"],
            "outputs": {
                "click_track": click_path,
                "mix_with_click": mix_path,
                "tempo_map_midi": midi_path,
                "tempo_curve_plot": png_path
            }
        }

        # Save JSON report
        with open(report_json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # Save TXT report
        with open(report_txt_path, 'w', encoding='utf-8') as f:
            f.write("========== 自動節拍與音樂分析報告 ==========\n")
            f.write(f"檔名: {report_data['file_name']}\n")
            f.write(f"推定調性 (Key): {report_data['estimated_key']}\n")
            f.write(f"平均 BPM: {report_data['average_bpm']}\n")
            f.write(f"BPM 範圍: {report_data['min_bpm']} ~ {report_data['max_bpm']}\n")
            f.write(f"總小節數 (Total Measures): {report_data['total_measures']}\n")
            f.write(f"總拍數 (Total Beats): {report_data['total_beats']}\n")
            f.write("\n----- 小節和弦進行 (Chord Progression) -----\n")
            for c in report_data["chord_progression"]:
                f.write(f"第 {c['measure']:02d} 小節 ({c['start_time']}s ~ {c['end_time']}s): {c['chord']}\n")
            f.write("=========================================\n")

        print("\nPipeline execution complete!")
        print(f"Key: {report_data['estimated_key']} | Avg BPM: {report_data['average_bpm']} | Total Measures: {total_measures}")
        return report_data
