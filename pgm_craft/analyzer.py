"""
PGMCraft Music Analyzer Module
Handles Dynamic Beat/Downbeat Tracking, Key Detection, and Measure Chord Analysis.
"""

import numpy as np
import librosa

try:
    from BeatNet.BeatNet import BeatNet
except Exception:
    BeatNet = None

KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 2.69, 3.34, 3.17, 3.28])
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

CHORD_TEMPLATES = {}
for i, name in enumerate(NOTE_NAMES):
    maj_vec = np.zeros(12)
    maj_vec[i], maj_vec[(i + 4) % 12], maj_vec[(i + 7) % 12] = 1.0, 0.8, 0.8
    CHORD_TEMPLATES[f"{name}"] = maj_vec / np.linalg.norm(maj_vec)

    min_vec = np.zeros(12)
    min_vec[i], min_vec[(i + 3) % 12], min_vec[(i + 7) % 12] = 1.0, 0.8, 0.8
    CHORD_TEMPLATES[f"{name}m"] = min_vec / np.linalg.norm(min_vec)


class MusicAnalyzer:
    def __init__(self, use_beatnet=True):
        self.use_beatnet = use_beatnet

    def track_beats(self, audio_path):
        """Track beats & downbeats. Returns np.ndarray (N, 2): [timestamp, beat_label (1 for downbeat)]"""
        beats = None
        if self.use_beatnet and BeatNet is not None:
            try:
                print("[PGMCraft Analyzer] Running BeatNet CRNN model...")
                estimator = BeatNet(1, mode='offline', inference_model='dbn', plot=[], thread=False)
                output = estimator.process(audio_path)
                if output is not None and len(output) > 0:
                    beats = output
            except Exception as e:
                print(f"[PGMCraft Analyzer] BeatNet failed ({e}). Using Librosa fallback.")

        if beats is None:
            beats = self._librosa_fallback(audio_path)
        return beats

    def _librosa_fallback(self, audio_path):
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if len(beat_times) == 0:
            return np.array([[0.0, 1]])

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        beat_onsets = onset_env[np.minimum(beat_frames, len(onset_env) - 1)]

        best_offset, max_energy = 0, -1.0
        for offset in range(4):
            cycle_energy = sum(beat_onsets[i] for i in range(offset, len(beat_onsets), 4))
            if cycle_energy > max_energy:
                max_energy, best_offset = cycle_energy, offset

        beats = []
        for i, t in enumerate(beat_times):
            beat_label = 1 if ((i - best_offset) % 4 == 0) else (((i - best_offset) % 4) + 1)
            beats.append([t, beat_label])
        return np.array(beats)

    def analyze_key(self, audio_path):
        """Estimate musical key (e.g. C Major, F Minor)"""
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_avg = np.mean(chroma, axis=1)

        best_corr, estimated_key = -2.0, "C Major"
        for i in range(12):
            maj_profile = np.roll(KS_MAJOR, i)
            corr_maj = np.corrcoef(chroma_avg, maj_profile)[0, 1]
            if corr_maj > best_corr:
                best_corr, estimated_key = corr_maj, f"{NOTE_NAMES[i]} Major"

            min_profile = np.roll(KS_MINOR, i)
            corr_min = np.corrcoef(chroma_avg, min_profile)[0, 1]
            if corr_min > best_corr:
                best_corr, estimated_key = corr_min, f"{NOTE_NAMES[i]} Minor"

        return estimated_key

    def analyze_chords(self, audio_path, beats):
        """Analyze chords per measure for transcription reference."""
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        
        downbeat_indices = [i for i, b in enumerate(beats) if int(b[1]) == 1]
        if not downbeat_indices:
            downbeat_indices = list(range(0, len(beats), 4))

        measures = []
        for idx in range(len(downbeat_indices)):
            start_beat_idx = downbeat_indices[idx]
            end_beat_idx = downbeat_indices[idx + 1] if idx + 1 < len(downbeat_indices) else len(beats) - 1

            start_time = beats[start_beat_idx][0]
            end_time = beats[end_beat_idx][0] if end_beat_idx < len(beats) else beats[-1][0]

            start_frame = librosa.time_to_frames(start_time, sr=sr)
            end_frame = max(start_frame + 1, librosa.time_to_frames(end_time, sr=sr))

            meas_chroma = np.mean(chroma[:, start_frame:end_frame], axis=1)
            norm = np.linalg.norm(meas_chroma)
            if norm > 0:
                meas_chroma /= norm

            best_score, detected_chord = -1.0, "N.C."
            for name, template in CHORD_TEMPLATES.items():
                score = np.dot(meas_chroma, template)
                if score > best_score:
                    best_score, detected_chord = score, name

            ext_type = "7th/Extended" if ("7" in detected_chord or "maj" in detected_chord or "m7" in detected_chord) else "Triad"
            measures.append({
                "measure": idx + 1,
                "start_time": round(float(start_time), 2),
                "end_time": round(float(end_time), 2),
                "chord": detected_chord,
                "extension": ext_type,
                "confidence": round(float(best_score), 3)
            })
        return measures

