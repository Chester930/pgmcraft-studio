"""Module 3 beat/click Behavior Tree nodes.

This module keeps the manual beat-click workflow narrower than the full
pipeline: it builds multiple candidate timing sources, records which source is
trusted per segment, synthesizes one canonical beat grid, then exports click
artifacts for listening tests.
"""

import json
import os
from typing import Dict, Iterable, List, Optional

import numpy as np

from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.synthesizer import PGMSynthesizer
from pgm_craft.workflow.audio_nodes import (
    ClickSynthesisNode,
)
from pgm_craft.workflow.audio_quality_bt import build_audio_quality_tree
from pgm_craft.workflow.beat_tracking_bt import (
    KickBassDownbeatVerifierNode,
    _score_beat_grid_quality,
    build_beat_refinement_nodes,
    build_beat_tracking_analysis_nodes,
    build_beat_tracking_preparation_nodes,
)
from pgm_craft.workflow.export_bt import BackingWithClickSynthesizerNode
from pgm_craft.workflow.input_acquisition_bt import build_input_acquisition_tree
from pgm_craft.workflow.music_analysis_bt import build_music_analysis_tree
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode
from pgm_craft.workflow.stem_separation_bt import build_stem_separation_tree


SOURCE_KEYS = ("full_mix", "rhythm", "band", "vocal")
BEATS_KEY_BY_SOURCE = {
    "full_mix": "beats_full_mix",
    "rhythm": "beats_rhythm",
    "band": "beats_band",
    "vocal": "beats_vocal",
}
ROLE_WEIGHTS = {
    "full_mix": 0.78,
    "rhythm": 1.0,
    "band": 0.88,
    "vocal": 0.48,
}


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim > 1:
        return y.mean(axis=1) if y.shape[0] > y.shape[1] else y.mean(axis=0)
    return y


def _normalize_beats(beats) -> np.ndarray:
    if beats is None:
        return np.empty((0, 2), dtype=float)
    arr = np.asarray(beats, dtype=float)
    if arr.size == 0:
        return np.empty((0, 2), dtype=float)
    if arr.ndim == 1:
        arr = np.column_stack([arr, (np.arange(len(arr)) % 4) + 1])
    if arr.shape[1] < 2:
        arr = np.column_stack([arr[:, 0], (np.arange(len(arr)) % 4) + 1])
    arr = arr[:, :2]
    arr = arr[np.argsort(arr[:, 0])]
    return arr


def _existing_path(*paths) -> Optional[str]:
    for path in paths:
        if isinstance(path, str) and path and os.path.exists(path):
            return path
    return None


def _safe_stem_lookup(stems: dict, *keys) -> Optional[str]:
    for key in keys:
        val = stems.get(key)
        if isinstance(val, str) and os.path.exists(val):
            return val
        if isinstance(val, dict):
            path = val.get("path")
            if isinstance(path, str) and os.path.exists(path):
                return path
    return None


def _selected_candidate_sources(blackboard: Blackboard) -> set:
    raw = blackboard.get_val("module3_candidate_sources")
    if raw is None:
        return set(SOURCE_KEYS)
    if isinstance(raw, str):
        raw = [raw]
    selected = {str(item) for item in (raw or []) if str(item) in SOURCE_KEYS}
    return selected or {"full_mix"}


class OptionalStemSeparationNode(BaseNode):
    """Runs Stage 2 only when enable_stem is true; otherwise prepares empty stems."""

    required_keys = ["audio_path"]
    optional_keys = ["enable_stem", "project_dir", "output_dir"]
    output_keys = ["stems", "stems_dir", "stem_separation_status"]

    def __init__(self):
        super().__init__("OptionalStemSeparationNode")
        self.tree = build_stem_separation_tree()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        project_dir = blackboard.get_val("project_dir") or blackboard.get_val("output_dir", "outputs")
        stems_dir = blackboard.get_val("stems_dir") or os.path.join(project_dir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        blackboard.set_val("stems_dir", stems_dir)

        if not blackboard.get_val("enable_stem", False):
            blackboard.set_val("stems", blackboard.get_val("stems", {}))
            blackboard.set_val("stem_separation_status", "SKIPPED")
            print(f"[{self.name}] enable_stem=false, using original audio candidates.")
            return NodeStatus.SUCCESS

        status = self.tree.run(blackboard, parent=self.name)
        blackboard.set_val("stem_separation_status", status.name)
        return NodeStatus.SUCCESS if status == NodeStatus.SUCCESS else NodeStatus.FAILURE


class CandidateTrackBuildNode(BaseNode):
    """Builds the four timing candidate sources used by Module 3."""

    optional_keys = [
        "audio_path",
        "denoised_wav_path",
        "normalized_wav_path",
        "target_analysis_path",
        "project_dir",
        "output_dir",
        "stems",
        "stems_dir",
        "module3_candidate_sources",
    ]
    output_keys = [
        "beat_candidate_tracks",
        "module3_candidate_sources",
        "full_mix_track_path",
        "rhythm_track_path",
        "band_track_path",
        "vocal_track_path",
    ]

    def __init__(self):
        super().__init__("CandidateTrackBuildNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        full_mix = _existing_path(
            blackboard.get_val("denoised_wav_path"),
            blackboard.get_val("normalized_wav_path"),
            audio_path,
            blackboard.get_val("target_analysis_path"),
        )
        if not full_mix:
            print(f"[{self.name}] no usable audio source")
            return NodeStatus.FAILURE

        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        project_dir = blackboard.get_val("project_dir") or blackboard.get_val("output_dir", "outputs")
        submix_dir = os.path.join(project_dir, "stems", "submix")
        os.makedirs(submix_dir, exist_ok=True)

        drums = _existing_path(
            _safe_stem_lookup(stems, "drums", "kick"),
            os.path.join(stems_dir, "drums", "drums.wav") if stems_dir else "",
        )
        bass = _existing_path(
            _safe_stem_lookup(stems, "bass", "electric_bass", "sub_bass_808"),
            os.path.join(stems_dir, "bass", "bass.wav") if stems_dir else "",
        )
        guitar = _existing_path(
            _safe_stem_lookup(stems, "guitar", "guitars"),
            os.path.join(stems_dir, "guitars", "guitar.wav") if stems_dir else "",
        )
        piano = _existing_path(
            _safe_stem_lookup(stems, "piano", "pianos"),
            os.path.join(stems_dir, "pianos", "piano.wav") if stems_dir else "",
        )
        no_vocals = _existing_path(
            _safe_stem_lookup(stems, "no_vocals", "instrumental"),
            blackboard.get_val("no_vocals_path"),
            blackboard.get_val("instrumental_path"),
            os.path.join(stems_dir, "no_vocals.wav") if stems_dir else "",
            os.path.join(stems_dir, "instrumental.wav") if stems_dir else "",
        )
        vocal = _existing_path(
            _safe_stem_lookup(stems, "lead_vocal", "vocals", "vocals_debreathed"),
            blackboard.get_val("lead_vocal_path"),
            blackboard.get_val("vocals_path"),
            os.path.join(stems_dir, "vocals", "lead_vocal.wav") if stems_dir else "",
            os.path.join(stems_dir, "vocals", "vocals.wav") if stems_dir else "",
        )

        rhythm = self._mix_or_fallback(
            [drums, bass],
            os.path.join(submix_dir, "module3_rhythm_drums_bass.wav"),
            fallback=drums or bass or full_mix,
        )
        band = self._mix_or_fallback(
            [drums, bass, guitar, piano],
            os.path.join(submix_dir, "module3_band_drums_bass_guitar_piano.wav"),
            fallback=no_vocals or full_mix,
        )
        selected_sources = _selected_candidate_sources(blackboard)
        rhythm_available = bool(rhythm and os.path.exists(rhythm) and (drums or bass or rhythm != full_mix))
        band_available = bool(band and os.path.exists(band) and (no_vocals or drums or bass or guitar or piano or band != full_mix))
        vocal_available = bool(vocal and os.path.exists(vocal))

        candidate_tracks = {
            "full_mix": {
                "path": full_mix,
                "role": "original reference",
                "base_weight": ROLE_WEIGHTS["full_mix"],
                "available": bool(full_mix and os.path.exists(full_mix)),
            },
            "rhythm": {
                "path": rhythm,
                "role": "drums+bass groove",
                "base_weight": ROLE_WEIGHTS["rhythm"],
                "available": rhythm_available,
            },
            "band": {
                "path": band,
                "role": "no-vocal band context",
                "base_weight": ROLE_WEIGHTS["band"],
                "available": band_available,
            },
            "vocal": {
                "path": vocal,
                "role": "vocal phrase support",
                "base_weight": ROLE_WEIGHTS["vocal"],
                "available": vocal_available,
            },
        }
        for source, meta in candidate_tracks.items():
            meta["selected"] = source in selected_sources
            meta["enabled"] = bool(meta["selected"] and meta["available"])
            blackboard.set_val(f"{source}_track_path", meta.get("path"))

        blackboard.set_val("module3_candidate_sources", sorted(selected_sources))
        blackboard.set_val("beat_candidate_tracks", candidate_tracks)
        print(f"[{self.name}] built candidate tracks: {', '.join(k for k, v in candidate_tracks.items() if v['enabled'])}")
        return NodeStatus.SUCCESS

    def _mix_or_fallback(self, paths: Iterable[Optional[str]], output_path: str, fallback: Optional[str]) -> Optional[str]:
        valid_paths = [path for path in paths if path and os.path.exists(path)]
        if len(valid_paths) < 2:
            return fallback
        try:
            import soundfile as sf

            tracks = []
            for path in valid_paths:
                y, sr = sf.read(path)
                tracks.append((_to_mono(np.asarray(y)), sr))
            min_len = min(len(row[0]) for row in tracks)
            mixed = sum(row[0][:min_len] for row in tracks) / float(len(tracks))
            sf.write(output_path, mixed.astype(np.float32), tracks[0][1])
            return output_path
        except Exception as exc:
            print(f"[{self.name}] submix fallback for {output_path}: {exc}")
            return fallback


class PerTrackBeatAnalysisNode(BaseNode):
    """Runs or gathers beat candidates for every enabled timing source."""

    optional_keys = ["beat_candidate_tracks"]
    output_keys = ["beat_candidates"]

    def __init__(self):
        super().__init__("PerTrackBeatAnalysisNode")
        self.analyzer = MusicAnalyzer(use_beatnet=False)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        tracks = blackboard.get_val("beat_candidate_tracks", {}) or {}
        beat_candidates = blackboard.get_val("beat_candidates", {}) or {}

        for source in SOURCE_KEYS:
            beats_key = BEATS_KEY_BY_SOURCE[source]
            meta = tracks.get(source, {})
            if not meta.get("enabled", False):
                continue

            beats = blackboard.get_val(beats_key)
            if beats is None and source == "band":
                beats = blackboard.get_val("beats_inst")

            path = meta.get("path")
            if beats is None and path and os.path.exists(path):
                try:
                    print(f"[{self.name}] analyzing {source}: {path}")
                    beats = self.analyzer._librosa_fallback(path)
                except Exception as exc:
                    print(f"[{self.name}] {source} analysis failed: {exc}")
                    beats = None

            arr = _normalize_beats(beats)
            if len(arr) > 0:
                blackboard.set_val(beats_key, arr)
                beat_candidates[source] = {
                    "source": source,
                    "path": path,
                    "beats": arr,
                    "base_weight": float(meta.get("base_weight", ROLE_WEIGHTS[source])),
                }

        if not beat_candidates:
            print(f"[{self.name}] no beat candidates available")
            return NodeStatus.FAILURE

        blackboard.set_val("beat_candidates", beat_candidates)
        return NodeStatus.SUCCESS


class SegmentGridNode(BaseNode):
    """Creates measure-like analysis segments for source confidence attribution."""

    optional_keys = ["measure_map", "beats", "refined_beats", "beat_candidates"]
    output_keys = ["analysis_segments"]

    def __init__(self, beats_per_segment: int = 4):
        super().__init__("SegmentGridNode")
        self.beats_per_segment = beats_per_segment

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        measure_map = blackboard.get_val("measure_map", []) or []
        if measure_map:
            segments = [
                {
                    "segment_index": idx,
                    "measure": item.get("measure", idx + 1),
                    "start_time": float(item.get("start_time", 0.0)),
                    "end_time": float(item.get("end_time", item.get("start_time", 0.0))),
                }
                for idx, item in enumerate(measure_map)
            ]
            blackboard.set_val("analysis_segments", segments)
            return NodeStatus.SUCCESS

        beats = _normalize_beats(blackboard.get_val("refined_beats", blackboard.get_val("beats")))
        if len(beats) == 0:
            beats = self._longest_candidate_beats(blackboard.get_val("beat_candidates", {}) or {})
        if len(beats) == 0:
            print(f"[{self.name}] no beats available to create segments")
            return NodeStatus.FAILURE

        intervals = np.diff(beats[:, 0])
        median_interval = float(np.median(intervals)) if len(intervals) else 0.5
        segments = []
        for start_idx in range(0, len(beats), self.beats_per_segment):
            chunk = beats[start_idx:start_idx + self.beats_per_segment]
            if len(chunk) == 0:
                continue
            end_time = float(chunk[-1, 0] + median_interval)
            segments.append({
                "segment_index": len(segments),
                "measure": len(segments) + 1,
                "start_time": float(chunk[0, 0]),
                "end_time": end_time,
            })

        blackboard.set_val("analysis_segments", segments)
        return NodeStatus.SUCCESS

    def _longest_candidate_beats(self, candidates: dict) -> np.ndarray:
        longest = np.empty((0, 2), dtype=float)
        for meta in candidates.values():
            arr = _normalize_beats(meta.get("beats"))
            if len(arr) > len(longest):
                longest = arr
        return longest


class PerSegmentConfidenceNode(BaseNode):
    """Scores each source per segment instead of choosing one global winner."""

    required_keys = ["analysis_segments", "beat_candidates"]
    optional_keys = ["beat_candidate_tracks"]
    output_keys = ["per_segment_confidence"]

    def __init__(self):
        super().__init__("PerSegmentConfidenceNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        segments = blackboard.get_val("analysis_segments", []) or []
        candidates = blackboard.get_val("beat_candidates", {}) or {}
        tracks = blackboard.get_val("beat_candidate_tracks", {}) or {}
        confidence_rows = []

        for segment in segments:
            start = float(segment.get("start_time", 0.0))
            end = float(segment.get("end_time", start))
            duration = max(0.001, end - start)
            expected_beats = max(1.0, duration / self._global_median_interval(candidates))
            scores = {}

            for source, meta in candidates.items():
                beats = _normalize_beats(meta.get("beats"))
                in_segment = beats[(beats[:, 0] >= start) & (beats[:, 0] < end)]
                coverage = min(1.0, len(in_segment) / expected_beats)
                stability = self._stability(in_segment)
                energy = self._energy_score(tracks.get(source, {}).get("path"), start, end)
                role_weight = float(meta.get("base_weight", ROLE_WEIGHTS.get(source, 0.5)))
                raw_score = role_weight * (0.45 * coverage + 0.35 * stability + 0.20 * energy)
                if source == "vocal" and self._has_non_vocal_support(scores):
                    raw_score = min(raw_score, 0.65)
                scores[source] = {
                    "score": round(float(np.clip(raw_score, 0.0, 1.0)), 4),
                    "coverage": round(float(coverage), 4),
                    "tempo_stability": round(float(stability), 4),
                    "energy": round(float(energy), 4),
                    "beats_in_segment": int(len(in_segment)),
                }

            confidence_rows.append({**segment, "track_confidence": scores})

        blackboard.set_val("per_segment_confidence", confidence_rows)
        print(f"[{self.name}] scored {len(confidence_rows)} segments across {len(candidates)} sources.")
        return NodeStatus.SUCCESS

    def _global_median_interval(self, candidates: dict) -> float:
        intervals = []
        for meta in candidates.values():
            beats = _normalize_beats(meta.get("beats"))
            if len(beats) > 1:
                intervals.extend(np.diff(beats[:, 0]).tolist())
        return float(np.median(intervals)) if intervals else 0.5

    def _stability(self, beats: np.ndarray) -> float:
        if len(beats) == 0:
            return 0.0
        if len(beats) < 3:
            return 0.55
        intervals = np.diff(beats[:, 0])
        mean = float(np.mean(intervals))
        if mean <= 0:
            return 0.0
        return float(np.clip(1.0 - (np.std(intervals) / mean), 0.0, 1.0))

    def _energy_score(self, path: Optional[str], start: float, end: float) -> float:
        if not path or not os.path.exists(path):
            return 0.45
        try:
            import soundfile as sf

            y, sr = sf.read(path)
            mono = _to_mono(np.asarray(y))
            s_idx = int(max(0, start * sr))
            e_idx = int(min(len(mono), end * sr))
            if e_idx <= s_idx:
                return 0.0
            rms = float(np.sqrt(np.mean(mono[s_idx:e_idx] ** 2)))
            return float(np.clip(rms / 0.08, 0.0, 1.0))
        except Exception:
            return 0.45

    def _has_non_vocal_support(self, scores: dict) -> bool:
        return any(source != "vocal" and meta.get("score", 0.0) > 0.2 for source, meta in scores.items())


class SegmentSourceAttributionNode(BaseNode):
    """Records the primary and supporting timing source for every segment."""

    required_keys = ["per_segment_confidence"]
    output_keys = ["segment_source_map"]

    def __init__(self, support_margin: float = 0.15):
        super().__init__("SegmentSourceAttributionNode")
        self.support_margin = support_margin

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        rows = []
        for item in blackboard.get_val("per_segment_confidence", []) or []:
            scores = item.get("track_confidence", {})
            if not scores:
                continue
            ranked = sorted(scores.items(), key=lambda pair: pair[1].get("score", 0.0), reverse=True)
            primary, primary_meta = ranked[0]
            primary_score = float(primary_meta.get("score", 0.0))
            supporting = [
                source for source, meta in ranked[1:]
                if meta.get("score", 0.0) >= max(0.2, primary_score - self.support_margin)
            ]
            reason = self._reason(primary, scores)
            rows.append({
                "segment_index": item.get("segment_index"),
                "measure": item.get("measure"),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "primary_source": primary,
                "primary_score": round(primary_score, 4),
                "supporting_sources": supporting,
                "reason": reason,
                "track_confidence": scores,
            })

        blackboard.set_val("segment_source_map", rows)
        print(f"[{self.name}] attributed {len(rows)} segments.")
        return NodeStatus.SUCCESS if rows else NodeStatus.FAILURE

    def _reason(self, primary: str, scores: dict) -> str:
        if primary == "rhythm":
            return "rhythm_track_has_clearest_groove"
        if primary == "band":
            return "band_track_has_stable_context"
        if primary == "vocal":
            return "vocal_phrase_is_strongest_available_source"
        return "full_mix_is_most_reliable_or_fallback"


class BeatGridSynthesisNode(BaseNode):
    """Synthesizes one canonical beat grid from segment-level attribution."""

    required_keys = ["segment_source_map", "beat_candidates"]
    output_keys = ["beats", "refined_beats", "beat_synthesis_report"]

    def __init__(self):
        super().__init__("BeatGridSynthesisNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        source_map = blackboard.get_val("segment_source_map", []) or []
        candidates = blackboard.get_val("beat_candidates", {}) or {}
        rows = []
        report_segments = []

        for segment in source_map:
            start = float(segment.get("start_time", 0.0))
            end = float(segment.get("end_time", start))
            source = self._first_source_with_beats(segment, candidates, start, end)
            segment_beats = self._segment_beats(candidates.get(source, {}).get("beats"), start, end)
            if len(segment_beats) == 0:
                segment_beats = self._inertia_fill(rows, start, end)
                source = "tempo_inertia"
            rows.extend(segment_beats.tolist())
            report_segments.append({
                "measure": segment.get("measure"),
                "start_time": start,
                "end_time": end,
                "chosen_source": source,
                "supporting_sources": segment.get("supporting_sources", []),
                "beats_used": int(len(segment_beats)),
                "reason": segment.get("reason"),
            })

        final = self._sanitize(rows)
        if len(final) == 0:
            print(f"[{self.name}] synthesized grid is empty")
            return NodeStatus.FAILURE

        blackboard.set_val("beats", final)
        blackboard.set_val("refined_beats", final)
        blackboard.set_val("beat_synthesis_report", {
            "total_beats": int(len(final)),
            "segments": report_segments,
            "strategy": "segment_source_attribution",
        })
        print(f"[{self.name}] synthesized {len(final)} canonical beats.")
        return NodeStatus.SUCCESS

    def _first_source_with_beats(self, segment: dict, candidates: dict, start: float, end: float) -> str:
        ordered = [segment.get("primary_source")] + list(segment.get("supporting_sources", [])) + ["full_mix", "band", "rhythm"]
        for source in ordered:
            if source in candidates and len(self._segment_beats(candidates[source].get("beats"), start, end)) > 0:
                return source
        return "full_mix"

    def _segment_beats(self, beats, start: float, end: float) -> np.ndarray:
        arr = _normalize_beats(beats)
        if len(arr) == 0:
            return arr
        return arr[(arr[:, 0] >= start) & (arr[:, 0] < end)]

    def _inertia_fill(self, rows: list, start: float, end: float) -> np.ndarray:
        if not rows:
            return np.empty((0, 2), dtype=float)
        previous = _normalize_beats(rows)
        intervals = np.diff(previous[:, 0])
        interval = float(np.median(intervals)) if len(intervals) else 0.5
        t = max(start, float(previous[-1, 0]) + interval)
        out = []
        beat_num = int(previous[-1, 1])
        while t < end:
            beat_num = (beat_num % 4) + 1
            out.append([t, beat_num])
            t += interval
        return _normalize_beats(out)

    def _sanitize(self, rows: list) -> np.ndarray:
        arr = _normalize_beats(rows)
        if len(arr) == 0:
            return arr
        clean = []
        last_t = -1.0
        for row in arr:
            if float(row[0]) > last_t + 1e-4:
                clean.append([float(row[0]), int(row[1])])
                last_t = float(row[0])
        return _normalize_beats(clean)


class SubdivisionGridNode(BaseNode):
    """Builds an eighth-note analysis grid while preserving quarter-note click grid."""

    required_keys = ["beats"]
    optional_keys = ["measure_map"]
    output_keys = ["subdivision_grid", "click_grid"]

    def __init__(self):
        super().__init__("SubdivisionGridNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = _normalize_beats(blackboard.get_val("refined_beats", blackboard.get_val("beats")))
        if len(beats) == 0:
            return NodeStatus.FAILURE
        subdivision_grid = []
        click_grid = []
        for idx, row in enumerate(beats):
            beat_num = int(row[1]) if row[1] else (idx % 4) + 1
            measure = self._measure_for_time(float(row[0]), blackboard.get_val("measure_map", []))
            quarter = {
                "time": round(float(row[0]), 6),
                "label": str(beat_num),
                "beat": beat_num,
                "measure": measure,
                "click": True,
            }
            subdivision_grid.append(quarter)
            click_grid.append(quarter)
            if idx + 1 < len(beats):
                midpoint = (float(row[0]) + float(beats[idx + 1, 0])) / 2.0
                subdivision_grid.append({
                    "time": round(midpoint, 6),
                    "label": f"{beat_num}&",
                    "beat": beat_num,
                    "measure": measure,
                    "click": False,
                })

        blackboard.set_val("subdivision_grid", subdivision_grid)
        blackboard.set_val("click_grid", click_grid)
        return NodeStatus.SUCCESS

    def _measure_for_time(self, time_sec: float, measure_map: list) -> Optional[int]:
        for item in measure_map or []:
            if float(item.get("start_time", 0.0)) <= time_sec < float(item.get("end_time", 0.0)):
                return item.get("measure")
        return None


class SyncopationClassificationNode(BaseNode):
    """Classifies onsets against subdivision grid so click does not chase syncopation."""

    required_keys = ["subdivision_grid", "click_grid"]
    optional_keys = ["onset_events"]
    output_keys = ["syncopation_events", "snap_exclusion_zones"]

    def __init__(self):
        super().__init__("SyncopationClassificationNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        onsets = blackboard.get_val("onset_events", []) or []
        subdivision_grid = blackboard.get_val("subdivision_grid", []) or []
        click_grid = blackboard.get_val("click_grid", []) or []
        events = []
        exclusions = []

        for raw in onsets:
            t = float(raw.get("time", raw if isinstance(raw, (int, float)) else 0.0))
            nearest_click = self._nearest(click_grid, t)
            nearest_sub = self._nearest(subdivision_grid, t)
            if not nearest_click or not nearest_sub:
                continue
            offset_click_ms = (t - nearest_click["time"]) * 1000.0
            offset_sub_ms = (t - nearest_sub["time"]) * 1000.0
            classification = "phrase_onset"
            snap_click = False
            if abs(offset_click_ms) <= 35.0:
                classification = "true_beat"
                snap_click = True
            elif -250.0 <= offset_click_ms <= -60.0 and not nearest_sub.get("click"):
                classification = "anticipation"
                exclusions.append({"start_time": round(t - 0.04, 6), "end_time": round(t + 0.04, 6), "reason": classification})
            elif not nearest_sub.get("click") and abs(offset_sub_ms) <= 80.0:
                classification = "syncopation"
                exclusions.append({"start_time": round(t - 0.04, 6), "end_time": round(t + 0.04, 6), "reason": classification})

            events.append({
                "time": round(t, 6),
                "nearest_subdivision": nearest_sub.get("label"),
                "nearest_click_beat": nearest_click.get("label"),
                "offset_to_click_ms": round(offset_click_ms, 3),
                "offset_to_subdivision_ms": round(offset_sub_ms, 3),
                "classification": classification,
                "snap_click": snap_click,
            })

        blackboard.set_val("syncopation_events", events)
        blackboard.set_val("snap_exclusion_zones", exclusions)
        return NodeStatus.SUCCESS

    def _nearest(self, grid: List[dict], t: float) -> Optional[dict]:
        if not grid:
            return None
        return min(grid, key=lambda item: abs(float(item.get("time", 0.0)) - t))


class Module3OutputSummaryNode(BaseNode):
    """Writes a compact Module 3 report for the frontend/manual listening test."""

    optional_keys = [
        "project_dir",
        "output_dir",
        "raw_wav_path",
        "normalized_wav_path",
        "denoised_wav_path",
        "audio_path",
        "stems_dir",
        "crowd_path",
        "dereverb_dry_path",
        "measure_map_json",
        "sections_json",
        "beat_candidate_tracks",
        "click_track",
        "mix_with_click",
        "backing_with_click_path",
        "segment_source_map",
        "beat_synthesis_report",
        "subdivision_grid",
        "syncopation_events",
        "beat_validation",
        "downbeat_refinement",
        "measure_map",
        "estimated_key",
        "chord_progression",
        "barstart_v2_report",
        "barstart_v2_grid_beats",
        "barstart_v2_promoted_to_main",
        "barstart_v2_click_track",
        "barstart_v2_mix_with_click",
        "barstart_v2_comparison_report",
        "module3_legacy_beats",
        "module3_legacy_click_track",
        "module3_legacy_mix_with_click",
        "module3_legacy_comparison_report",
        "bar_length_report",
        "bar_start_seed_report",
        "committed_bar_starts",
        "bar_grid_boundaries",
        "meter_profile",
        "active_bar_probe_window",
        "bar_probe_windows",
        "bar_probe_policy",
        "bar_start_decision_report",
        "unresolved_bar_spans",
        "local_model_registry",
        "model_availability_report",
        "model_license_report",
        "drum_bar_evidence_report",
        "drum_bass_evidence_report",
        "chord_track_pk",
        "harmonic_anchor_evidence_report",
        "melody_track_pk",
        "phrase_anchor_evidence_report",
        "beat_this_candidate_report",
    ]
    output_keys = ["module3_outputs", "module3_report_json"]

    def __init__(self):
        super().__init__("Module3OutputSummaryNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        project_dir = blackboard.get_val("project_dir") or blackboard.get_val("output_dir", "outputs")
        source_dir = os.path.join(project_dir, "source")
        click_dir = os.path.join(project_dir, "click")
        stems_dir = blackboard.get_val("stems_dir") or os.path.join(project_dir, "stems")
        reports_dir = os.path.join(project_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, "module3_beat_click_report.json")
        candidate_tracks = blackboard.get_val("beat_candidate_tracks", {}) or {}
        outputs = dict(blackboard.get_val("module3_outputs", {}) or {})
        outputs.update({
            "test_project_dir": project_dir,
            "source_dir": source_dir,
            "stems_dir": stems_dir,
            "click_dir": click_dir,
            "reports_dir": reports_dir,
            "source_audio": blackboard.get_val("audio_path"),
            "raw_wav": blackboard.get_val("raw_wav_path"),
            "normalized_wav": blackboard.get_val("normalized_wav_path"),
            "denoised_wav": blackboard.get_val("denoised_wav_path"),
            "crowd_path": blackboard.get_val("crowd_path"),
            "dereverb_dry_path": blackboard.get_val("dereverb_dry_path"),
            "measure_map_json": blackboard.get_val("measure_map_json"),
            "sections_json": blackboard.get_val("sections_json"),
            "candidate_tracks": {
                source: {
                    "path": meta.get("path"),
                    "role": meta.get("role"),
                    "enabled": bool(meta.get("enabled")),
                    "selected": bool(meta.get("selected")),
                    "available": bool(meta.get("available")),
                    "base_weight": meta.get("base_weight"),
                }
                for source, meta in candidate_tracks.items()
            },
            "selected_candidate_sources": blackboard.get_val("module3_candidate_sources", list(SOURCE_KEYS)),
            "click_track": blackboard.get_val("click_track"),
            "mix_with_click": blackboard.get_val("mix_with_click"),
            "backing_with_click": blackboard.get_val("backing_with_click_path"),
            "backing_with_click_status": blackboard.get_val("backing_with_click_status"),
            "module3_report_json": report_path,
        })
        barstart_v2_report = blackboard.get_val("barstart_v2_report")
        if barstart_v2_report:
            outputs["barstart_v2_report"] = barstart_v2_report
            outputs["barstart_v2_status"] = barstart_v2_report.get("status")
            outputs["barstart_v2_promoted_to_main"] = blackboard.get_val("barstart_v2_promoted_to_main", False)
            outputs["barstart_v2_click_track"] = blackboard.get_val("barstart_v2_click_track")
            outputs["barstart_v2_mix_with_click"] = blackboard.get_val("barstart_v2_mix_with_click")
            outputs["barstart_v2_comparison_report"] = blackboard.get_val("barstart_v2_comparison_report", {})
            outputs["module3_legacy_click_track"] = blackboard.get_val("module3_legacy_click_track")
            outputs["module3_legacy_mix_with_click"] = blackboard.get_val("module3_legacy_mix_with_click")
            outputs["module3_legacy_comparison_report"] = blackboard.get_val("module3_legacy_comparison_report", {})

        report = {
            "estimated_key": blackboard.get_val("estimated_key"),
            "total_beats": int(len(_normalize_beats(blackboard.get_val("refined_beats", blackboard.get_val("beats"))))),
            "beat_validation": blackboard.get_val("beat_validation", {}),
            "downbeat_refinement": blackboard.get_val("downbeat_refinement", {}),
            "measure_map": blackboard.get_val("measure_map", []),
            "segment_source_map": blackboard.get_val("segment_source_map", []),
            "beat_synthesis_report": blackboard.get_val("beat_synthesis_report", {}),
            "subdivision_grid": blackboard.get_val("subdivision_grid", []),
            "syncopation_events": blackboard.get_val("syncopation_events", []),
            "chord_progression": blackboard.get_val("chord_progression", []),
            "outputs": outputs,
        }
        if barstart_v2_report:
            report["barstart_v2_report"] = barstart_v2_report
            report["barstart_v2_promoted_to_main"] = blackboard.get_val("barstart_v2_promoted_to_main", False)
            report["barstart_v2_click_track"] = blackboard.get_val("barstart_v2_click_track")
            report["barstart_v2_mix_with_click"] = blackboard.get_val("barstart_v2_mix_with_click")
            report["barstart_v2_comparison_report"] = blackboard.get_val("barstart_v2_comparison_report", {})
            report["module3_legacy_click_track"] = blackboard.get_val("module3_legacy_click_track")
            report["module3_legacy_mix_with_click"] = blackboard.get_val("module3_legacy_mix_with_click")
            report["module3_legacy_comparison_report"] = blackboard.get_val("module3_legacy_comparison_report", {})
            report["bar_length_report"] = blackboard.get_val("bar_length_report", {})
            report["committed_bar_starts"] = blackboard.get_val("committed_bar_starts", [])
            report["bar_grid_boundaries"] = blackboard.get_val("bar_grid_boundaries", [])
            report["active_bar_probe_window"] = blackboard.get_val("active_bar_probe_window", {})
            report["bar_probe_windows"] = blackboard.get_val("bar_probe_windows", [])
            report["bar_probe_policy"] = blackboard.get_val("bar_probe_policy", {})
            report["local_model_registry"] = blackboard.get_val("local_model_registry", {})
            report["model_availability_report"] = blackboard.get_val("model_availability_report", {})
            report["model_license_report"] = blackboard.get_val("model_license_report", {})
            report["drum_bar_evidence_report"] = blackboard.get_val("drum_bar_evidence_report", {})
            report["drum_bass_evidence_report"] = blackboard.get_val("drum_bass_evidence_report", {})
            report["chord_track_pk"] = blackboard.get_val("chord_track_pk", {})
            report["harmonic_anchor_evidence_report"] = blackboard.get_val("harmonic_anchor_evidence_report", {})
            report["melody_track_pk"] = blackboard.get_val("melody_track_pk", {})
            report["phrase_anchor_evidence_report"] = blackboard.get_val("phrase_anchor_evidence_report", {})
            report["beat_this_candidate_report"] = blackboard.get_val("beat_this_candidate_report", {})
            report["bar_start_decision_report"] = blackboard.get_val("bar_start_decision_report", {})
            report["unresolved_bar_spans"] = blackboard.get_val("unresolved_bar_spans", [])
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        blackboard.set_val("module3_outputs", outputs)
        blackboard.set_val("module3_report_json", report_path)
        print(f"[{self.name}] wrote Module 3 report: {report_path}")
        return NodeStatus.SUCCESS


def _run_barstart_v2_comparison(blackboard: Blackboard):
    """Run the real v2 evidence-ladder engine on an isolated copy of
    blackboard and score both v1's existing grid and v2's grid with the same
    metric. Shared by Module3BarStartV2MergeNode (strict human-acceptance
    gate, used by the isolated 節奏定位 tab) and BarStartV2AutoMergeNode
    (automatic score-only gate, used by the main pipeline) so the two
    callers never run two different implementations of "what does v2
    produce and how good is it" -- only the promotion *decision* differs.

    Returns None if there is no v1 grid to compare against. Otherwise
    returns a dict with success=False (v2 produced nothing usable) or
    success=True plus the raw beat grids/scores callers need.
    """
    original_beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
    original_beat_grid = (
        np.asarray(original_beats, dtype=float)
        if original_beats is not None
        else np.empty((0, 2), dtype=float)
    )
    if len(original_beat_grid) == 0:
        return None

    from pgm_craft.workflow.module3_barstart_v2_bt import (
        BarGridContinuityRepairNode,
        BarStartTempoSmoothingNode,
        BarStartV2QualityScoreNode,
        ChordMelodyOnsetSplitNode,
        FullSongBarStartLoopNode,
        ManualCommittedBarStartsSeedNode,
        MeterAwareBeatGridNode,
        MeterProfileNode,
    )

    # Run the real v2 engine on an isolated blackboard copy so it cannot
    # clobber v1's own grid while we are still deciding whether to adopt
    # it -- v2's evidence-ladder writes many of the same key names v1
    # already produced (beats/committed_bar_starts/...).
    v2_blackboard = Blackboard(blackboard)
    # NOTE: manual_bar_starts is intentionally *not* cleared -- it is the
    # legitimate mechanism for a caller to seed v2's starting point (e.g.
    # a reference-verified bar list), and popping it here would silently
    # discard that input every time.
    for key in (
        "committed_bar_starts", "beats", "refined_beats",
        "bar_start_candidates", "unresolved_bar_spans", "provisional_bar_starts",
    ):
        v2_blackboard.pop(key, None)

    # Pass 128: no per-beat onset snapping here either -- same reasoning
    # as build_module3_barstart_v2_export_tree() in module3_barstart_v2_bt.py.
    v2_core = SequenceNode("BarStartV2CoreChain", [
        MeterProfileNode(),
        ManualCommittedBarStartsSeedNode(),
        ChordMelodyOnsetSplitNode(),
        FullSongBarStartLoopNode(),
        BarGridContinuityRepairNode(),
        # Run twice -- see module3_barstart_v2_bt.py's pipeline wiring for why.
        BarStartTempoSmoothingNode(),
        BarStartTempoSmoothingNode(),
        MeterAwareBeatGridNode(),
        KickBassDownbeatVerifierNode(),
        BarStartV2QualityScoreNode(),
    ])
    core_status = v2_core.run(v2_blackboard, parent="BarStartV2CoreChain")
    v2_beats = v2_blackboard.get_val("refined_beats", v2_blackboard.get_val("beats"))
    v2_beat_grid = (
        np.asarray(v2_beats, dtype=float)
        if v2_beats is not None
        else np.empty((0, 2), dtype=float)
    )
    full_song_loop_report = v2_blackboard.get_val("full_song_loop_report", {})

    if core_status != NodeStatus.SUCCESS or len(v2_beat_grid) == 0:
        return {"success": False, "full_song_loop_report": full_song_loop_report}

    # Same scoring function, same (empty) optional args on both sides --
    # v2 additionally carries its own penalties (unresolved spans, grid
    # repairs, downbeat rotation) that v1 is never charged for, so this is
    # a deliberately conservative comparison biased against over-promoting v2.
    original_quality = _score_beat_grid_quality(original_beat_grid)
    v2_quality = v2_blackboard.get_val("barstart_v2_quality_score") or {
        "score": _score_beat_grid_quality(v2_beat_grid)["score"]
    }
    unresolved_spans = v2_blackboard.get_val("unresolved_bar_spans", []) or []
    committed_bar_starts = ManualCommittedBarStartsSeedNode()._normalize_times(
        v2_blackboard.get_val("committed_bar_starts")
    )

    return {
        "success": True,
        "original_beat_grid": original_beat_grid,
        "v2_beat_grid": v2_beat_grid,
        "original_quality": original_quality,
        "v2_quality": v2_quality,
        "unresolved_spans": unresolved_spans,
        "committed_bar_starts": committed_bar_starts,
        "full_song_loop_report": full_song_loop_report,
    }


class Module3BarStartV2MergeNode(BaseNode):
    """
    Runs the real BarStart v2 engine and adopts its grid as the 節奏定位 tab's
    main output whenever v2 completes cleanly (no unresolved bar spans) --
    see `evaluate_barstart_v2_completeness()`. v1's own grid is kept as a
    fallback for whatever portion of the song v2 could not resolve, and its
    click/mix are still exported as `module3_legacy_*` artifacts for
    reference, but it is no longer compared against v2 on a quality score:
    real listening tests confirmed v2 consistently sounds better, so v2 is
    now the default rather than something that has to win a comparison.

    An earlier version of this node re-derived "v2" from v1's own
    measure_map/beat labels and wrote a hardcoded 88-vs-95 "listening test"
    score -- it never ran the real v2 evidence-ladder engine at all. This
    version does.
    """

    optional_keys = [
        "barstart_v2_report",
        "beats",
        "refined_beats",
        "audio_path",
        "project_dir",
        "output_dir",
        "click_gain_db",
    ]
    output_keys = [
        "barstart_v2_report",
        "barstart_v2_grid_beats",
        "barstart_v2_promoted_to_main",
        "barstart_v2_click_track",
        "barstart_v2_mix_with_click",
        "barstart_v2_comparison_report",
        "module3_legacy_beats",
        "module3_legacy_click_track",
        "module3_legacy_mix_with_click",
        "module3_legacy_comparison_report",
        "refined_beats",
        "beats",
    ]

    def __init__(self):
        super().__init__("Module3BarStartV2MergeNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if blackboard.get_val("barstart_v2_report"):
            return NodeStatus.SUCCESS

        comparison = _run_barstart_v2_comparison(blackboard)
        if comparison is None:
            blackboard.set_val("barstart_v2_report", {
                "status": "MERGED_DIAGNOSTIC_SKIPPED",
                "reason": "no_module3_beats_to_compare",
                "replaces_module3_click": False,
            })
            return NodeStatus.SUCCESS

        if not comparison["success"]:
            blackboard.set_val("barstart_v2_report", {
                "status": "MERGED_DIAGNOSTIC_SKIPPED",
                "reason": "v2_engine_produced_no_grid",
                "replaces_module3_click": False,
                "full_song_loop_report": comparison["full_song_loop_report"],
            })
            return NodeStatus.SUCCESS

        from pgm_craft.workflow.module3_barstart_v2_bt import evaluate_barstart_v2_completeness

        original_beat_grid = comparison["original_beat_grid"]
        v2_beat_grid = comparison["v2_beat_grid"]
        original_quality = comparison["original_quality"]
        v2_quality = comparison["v2_quality"]
        unresolved_spans = comparison["unresolved_spans"]
        full_song_loop_report = comparison["full_song_loop_report"]

        completeness = evaluate_barstart_v2_completeness(unresolved_bar_spans=unresolved_spans)
        # Informational only -- kept in the report for reference, no longer
        # used to decide whether v2 is adopted.
        quality_comparison = {
            "original_score": original_quality["score"],
            "barstart_v2_score": v2_quality["score"],
            "v2_scores_higher": v2_quality["score"] > original_quality["score"],
        }
        promoted = bool(completeness["adoptable"])

        committed_bar_starts = comparison["committed_bar_starts"]
        legacy_artifacts = self._write_legacy_artifacts(blackboard, original_beat_grid)
        comparison_artifacts = self._write_barstart_v2_artifacts(blackboard, v2_beat_grid, committed_bar_starts)
        blackboard.set_val("module3_legacy_beats", original_beat_grid.copy())
        blackboard.set_val("barstart_v2_grid_beats", v2_beat_grid)
        blackboard.set_val("barstart_v2_promoted_to_main", promoted)
        if promoted:
            blackboard.set_val("refined_beats", v2_beat_grid)
            blackboard.set_val("beats", v2_beat_grid)

        report = {
            "status": "PROMOTED_TO_MODULE3_DEFAULT" if promoted else "COMPARED_NOT_PROMOTED",
            "replaces_module3_click": promoted,
            "committed_bar_starts": committed_bar_starts,
            "beat_count": int(len(v2_beat_grid)),
            "full_song_loop_report": full_song_loop_report,
            "unresolved_bar_span_count": len(unresolved_spans),
            "comparison_artifacts": comparison_artifacts,
            "legacy_artifacts": legacy_artifacts,
            "promotion_gate": completeness,
            "quality_comparison": quality_comparison,
            "notes": [
                "BarStart v2 is the default click grid whenever it completes "
                "with no unresolved bar spans -- confirmed via real listening "
                "tests to consistently sound better than v1, so it is no "
                "longer compared on a quality score before being adopted.",
                "Legacy Module 3 click artifacts are preserved for reference.",
            ],
        }
        blackboard.set_val("barstart_v2_report", report)
        return NodeStatus.SUCCESS

    def _write_legacy_artifacts(self, blackboard: Blackboard, original_beats) -> dict:
        return self._write_click_artifacts(
            blackboard=blackboard,
            beats=original_beats,
            click_filename="legacy_click_track.wav",
            mix_filename="legacy_mix_with_click.wav",
            source="module3_legacy_refined_beats",
            target_keys={
                "click": "module3_legacy_click_track",
                "mix": "module3_legacy_mix_with_click",
                "report": "module3_legacy_comparison_report",
            },
        )

    def _write_barstart_v2_artifacts(self, blackboard: Blackboard, v2_beats: np.ndarray, grid_boundaries: list) -> dict:
        report = self._write_click_artifacts(
            blackboard=blackboard,
            beats=v2_beats,
            click_filename="barstart_v2_click_track.wav",
            mix_filename="barstart_v2_mix_with_click.wav",
            source="barstart_v2_committed_bar_starts",
            target_keys={
                "click": "barstart_v2_click_track",
                "mix": "barstart_v2_mix_with_click",
                "report": "barstart_v2_comparison_report",
            },
        )
        report["bar_count"] = max(0, len(grid_boundaries) - 1)
        blackboard.set_val("barstart_v2_comparison_report", report)
        return report

    def _write_click_artifacts(
        self,
        blackboard: Blackboard,
        beats,
        click_filename: str,
        mix_filename: str,
        source: str,
        target_keys: dict,
    ) -> dict:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            report = {"status": "SKIPPED_NO_AUDIO", "reason": "audio_path_missing"}
            blackboard.set_val(target_keys["report"], report)
            return report

        comparison_beats = np.asarray(beats, dtype=float) if beats is not None else np.empty((0, 2), dtype=float)
        if len(comparison_beats) == 0:
            report = {"status": "SKIPPED_NO_GRID", "reason": "not_enough_committed_bar_starts"}
            blackboard.set_val(target_keys["report"], report)
            return report

        target_dir = blackboard.get_val("project_dir") or blackboard.get_val("output_dir", "outputs")
        click_dir = os.path.join(target_dir, "click") if os.path.basename(target_dir) != "click" else target_dir
        tmp_dir = os.path.join(click_dir, f"{os.path.splitext(click_filename)[0]}_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        click_gain_db = float(blackboard.get_val("click_gain_db", PGMSynthesizer.CLICK_GAIN_DB))
        click_path, mix_path = PGMSynthesizer().synthesize_click(
            audio_path,
            comparison_beats,
            output_dir=tmp_dir,
            click_gain_db=click_gain_db,
        )
        final_click_path = os.path.join(click_dir, click_filename)
        final_mix_path = os.path.join(click_dir, mix_filename)
        os.replace(click_path, final_click_path)
        os.replace(mix_path, final_mix_path)

        report = {
            "status": "EXPORTED",
            "control": "same_module3_run_same_audio_only_click_grid_differs",
            "click_track": final_click_path,
            "mix_with_click": final_mix_path,
            "beat_count": int(len(comparison_beats)),
            "source": source,
        }
        blackboard.set_val(target_keys["click"], final_click_path)
        blackboard.set_val(target_keys["mix"], final_mix_path)
        blackboard.set_val(target_keys["report"], report)
        return report


class BarStartV2AutoMergeNode(BaseNode):
    """
    Main-pipeline counterpart to Module3BarStartV2MergeNode.

    Runs the exact same v1-vs-v2 comparison (via `_run_barstart_v2_comparison`)
    and adopts v2's grid whenever `evaluate_barstart_v2_completeness()` says
    it finished cleanly (no unresolved bar spans) -- v2 is the default
    output everywhere now that real listening tests confirmed it
    consistently sounds better than v1, so there is no quality-score
    comparison or human-acceptance step left to gate on. It does not write
    the legacy/comparison A/B audio artifacts Module3BarStartV2MergeNode
    produces for manual review -- the main pipeline only needs the final
    grid, not a side-by-side comparison file nobody asked to see.
    """

    optional_keys = [
        "barstart_v2_auto_report",
        "beats",
        "refined_beats",
    ]
    output_keys = [
        "barstart_v2_auto_report",
        "refined_beats",
        "beats",
    ]

    def __init__(self):
        super().__init__("BarStartV2AutoMergeNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if blackboard.get_val("barstart_v2_auto_report"):
            return NodeStatus.SUCCESS

        comparison = _run_barstart_v2_comparison(blackboard)
        if comparison is None:
            blackboard.set_val("barstart_v2_auto_report", {
                "status": "AUTO_MERGE_SKIPPED",
                "reason": "no_v1_beats_to_compare",
                "promoted": False,
            })
            return NodeStatus.SUCCESS

        if not comparison["success"]:
            blackboard.set_val("barstart_v2_auto_report", {
                "status": "AUTO_MERGE_SKIPPED",
                "reason": "v2_engine_produced_no_grid",
                "promoted": False,
                "full_song_loop_report": comparison["full_song_loop_report"],
            })
            return NodeStatus.SUCCESS

        from pgm_craft.workflow.module3_barstart_v2_bt import evaluate_barstart_v2_completeness

        original_quality = comparison["original_quality"]
        v2_quality = comparison["v2_quality"]
        # Informational only -- kept in the report for reference, no longer
        # used to decide whether v2 is adopted.
        quality_comparison = {
            "original_score": original_quality["score"],
            "barstart_v2_score": v2_quality["score"],
            "v2_scores_higher": v2_quality["score"] > original_quality["score"],
        }
        completeness = evaluate_barstart_v2_completeness(
            unresolved_bar_spans=comparison["unresolved_spans"],
        )
        promoted = bool(completeness["adoptable"])
        if promoted:
            blackboard.set_val("refined_beats", comparison["v2_beat_grid"])
            blackboard.set_val("beats", comparison["v2_beat_grid"])

        blackboard.set_val("barstart_v2_auto_report", {
            "status": "AUTO_PROMOTED" if promoted else "AUTO_COMPARED_NOT_PROMOTED",
            "promoted": promoted,
            "auto_promotion_gate": completeness,
            "quality_comparison": quality_comparison,
            "bar_count": max(0, len(comparison["committed_bar_starts"]) - 1),
            "unresolved_bar_span_count": len(comparison["unresolved_spans"]),
            "full_song_loop_report": comparison["full_song_loop_report"],
        })
        return NodeStatus.SUCCESS


class Module3BackingWithClickNode(BaseNode):
    """Exports backing_with_click only when a real no-vocal/instrumental source exists."""

    optional_keys = ["stems", "stems_dir", "no_vocals_path", "instrumental_path"]
    output_keys = ["backing_with_click_path", "backing_with_click_status"]

    def __init__(self):
        super().__init__("Module3BackingWithClickNode")
        self.backing_node = BackingWithClickSynthesizerNode()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        candidate = _existing_path(
            _safe_stem_lookup(stems, "no_vocals", "instrumental"),
            blackboard.get_val("no_vocals_path"),
            blackboard.get_val("instrumental_path"),
            os.path.join(stems_dir, "no_vocals.wav") if stems_dir else "",
            os.path.join(stems_dir, "instrumental.wav") if stems_dir else "",
        )
        if not candidate:
            blackboard.set_val("backing_with_click_path", None)
            blackboard.set_val("backing_with_click_status", "SKIPPED_NO_NO_VOCAL_SOURCE")
            print(f"[{self.name}] no no-vocal/instrumental stem; skipping backing_with_click export.")
            return NodeStatus.SUCCESS

        status = self.backing_node.execute(blackboard)
        blackboard.set_val(
            "backing_with_click_status",
            "EXPORTED" if status == NodeStatus.SUCCESS and blackboard.get_val("backing_with_click_path") else "SKIPPED",
        )
        return NodeStatus.SUCCESS


def build_module3_export_tree() -> SequenceNode:
    """Builds the narrow Module 3 export tree: click + optional backing + report."""
    return SequenceNode("Module3ExportRoot", [
        ClickSynthesisNode(),
        Module3BackingWithClickNode(),
        Module3OutputSummaryNode(),
    ])


def build_module3_pipeline_tree() -> SequenceNode:
    """Builds the Module 3 chord/click test project pipeline."""
    return SequenceNode("Module3BeatClickRoot", [
        build_input_acquisition_tree(),
        build_audio_quality_tree(),
        OptionalStemSeparationNode(),
        CandidateTrackBuildNode(),
        *build_beat_tracking_preparation_nodes(),
        *build_beat_tracking_analysis_nodes(),
        PerTrackBeatAnalysisNode(),
        SegmentGridNode(),
        PerSegmentConfidenceNode(),
        SegmentSourceAttributionNode(),
        BeatGridSynthesisNode(),
        *build_beat_refinement_nodes(),
        build_music_analysis_tree(),
        SubdivisionGridNode(),
        SyncopationClassificationNode(),
        Module3BarStartV2MergeNode(),
        build_module3_export_tree(),
    ])
