"""Module 3 bar-start-first v2 Behavior Tree nodes.

This experimental workflow keeps the current Module 3 path intact while the
bar-start-first design is developed and tested in small SDD passes.
"""

from __future__ import annotations

import os
import importlib.util
from typing import Iterable

import numpy as np

from pgm_craft.workflow.audio_quality_bt import build_audio_quality_tree
from pgm_craft.workflow.input_acquisition_bt import build_input_acquisition_tree
from pgm_craft.workflow.module3_bt import Module3BackingWithClickNode, Module3OutputSummaryNode, OptionalStemSeparationNode
from pgm_craft.workflow.audio_nodes import ClickSynthesisNode
from pgm_craft.workflow.beat_tracking_bt import (
    KickBassDownbeatVerifierNode,
    _score_beat_grid_quality,
)
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode


METER_PROFILES = {
    "4/4": {"base_meter": "4/4", "beats_per_bar": 4, "beat_unit": 4},
    "3/4": {"base_meter": "3/4", "beats_per_bar": 3, "beat_unit": 4},
    "5/4": {"base_meter": "5/4", "beats_per_bar": 5, "beat_unit": 4},
    "6/8": {"base_meter": "6/8", "beats_per_bar": 6, "beat_unit": 8, "macro_beats": 2},
    "7/8": {"base_meter": "7/8", "beats_per_bar": 7, "beat_unit": 8},
}


LOCAL_MODEL_SPECS = {
    "beat_this": {
        "module": "beat_this",
        "role": "beat_downbeat_candidate",
        "fallback": "BeatNet/Librosa",
        "license": "MIT",
    },
    "beatnet": {
        "module": "BeatNet.BeatNet",
        "role": "beat_downbeat_candidate",
        "fallback": "librosa",
        "license": "MIT",
    },
    "librosa": {
        "module": "librosa",
        "role": "deterministic_beat_fallback",
        "fallback": None,
        "license": "ISC",
    },
    "demucs": {
        "module": "demucs",
        "role": "stem_separation",
        "fallback": "no_stem_mode",
        "license": "MIT",
    },
    "basic_pitch": {
        "module": "basic_pitch",
        "role": "melody_candidate",
        "fallback": "librosa_pyin",
        "license": "Apache-2.0",
    },
    "chord_model": {
        "module": "madmom",
        "role": "harmonic_candidate",
        "fallback": "librosa_chroma_template",
        "license": "BSD-3-Clause",
    },
}


class LocalModelRegistryNode(BaseNode):
    """Records optional local model availability without loading heavy model weights."""

    optional_keys = ["local_model_overrides"]
    output_keys = ["local_model_registry", "model_availability_report", "model_license_report"]

    def __init__(self, import_checker=None):
        super().__init__("LocalModelRegistryNode")
        self.import_checker = import_checker or self._module_available

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        overrides = dict(blackboard.get_val("local_model_overrides", {}) or {})
        registry = {}
        for name, spec in LOCAL_MODEL_SPECS.items():
            override = dict(overrides.get(name, {}) or {})
            available = bool(override.get("available")) if "available" in override else bool(self.import_checker(spec["module"]))
            registry[name] = {
                "available": available,
                "module": spec["module"],
                "role": spec["role"],
                "fallback": spec["fallback"],
                "license": override.get("license", spec["license"]),
                "source": "override" if override else "import_check",
                "path": override.get("path"),
            }

        available_models = sorted(name for name, item in registry.items() if item["available"])
        unavailable_models = sorted(name for name, item in registry.items() if not item["available"])
        availability_report = {
            "available_count": len(available_models),
            "unavailable_count": len(unavailable_models),
            "available_models": available_models,
            "unavailable_models": unavailable_models,
            "status": "RECORDED",
        }
        license_report = {
            "licenses": {name: item["license"] for name, item in registry.items()},
            "status": "RECORDED",
            "note": "Availability is metadata only; model weights are not loaded by this node.",
        }

        blackboard.set_val("local_model_registry", registry)
        blackboard.set_val("model_availability_report", availability_report)
        blackboard.set_val("model_license_report", license_report)
        return NodeStatus.SUCCESS

    def _module_available(self, module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False


class MeterProfileNode(BaseNode):
    """Builds the meter profile used to divide each committed bar span."""

    optional_keys = ["user_meter_selection", "allow_temporary_bar_delta", "meter_profile"]
    output_keys = ["meter_profile", "allowed_bar_lengths", "temporary_bar_policy"]

    def __init__(self):
        super().__init__("MeterProfileNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        existing = blackboard.get_val("meter_profile")
        if isinstance(existing, dict) and existing.get("beats_per_bar"):
            profile = dict(existing)
        else:
            selection = str(blackboard.get_val("user_meter_selection", "4/4") or "4/4")
            if selection == "auto":
                selection = "4/4"
            profile = dict(METER_PROFILES.get(selection, METER_PROFILES["4/4"]))
            profile["source"] = "user_selection" if selection else "default"

        beats_per_bar = int(profile.get("beats_per_bar", 4))
        beat_unit = int(profile.get("beat_unit", 4))
        base_meter = str(profile.get("base_meter", f"{beats_per_bar}/{beat_unit}"))
        delta = blackboard.get_val("allow_temporary_bar_delta", 0)
        allowed = self._allowed_bar_lengths(beats_per_bar, delta)
        policy = "fixed" if allowed == [beats_per_bar] else "allow_temporary_delta"

        profile["base_meter"] = base_meter
        profile["meter"] = base_meter
        profile["beats_per_bar"] = beats_per_bar
        profile["beat_unit"] = beat_unit
        profile["clicks_per_bar"] = beats_per_bar
        profile["allowed_bar_lengths"] = allowed
        profile["temporary_bar_policy"] = policy
        blackboard.set_val("meter_profile", profile)
        blackboard.set_val("allowed_bar_lengths", allowed)
        blackboard.set_val("temporary_bar_policy", policy)
        return NodeStatus.SUCCESS

    def _allowed_bar_lengths(self, beats_per_bar: int, delta) -> list[int]:
        if isinstance(delta, str):
            if delta in ("auto", "自動偵測"):
                return sorted({beats_per_bar - 1, beats_per_bar, beats_per_bar + 1, beats_per_bar + 2})
            if delta.startswith("+"):
                try:
                    delta = int(delta[1:])
                    return list(range(beats_per_bar, beats_per_bar + delta + 1))
                except ValueError:
                    return [beats_per_bar]
            try:
                delta = int(delta)
            except ValueError:
                return [beats_per_bar]

        try:
            delta_int = int(delta)
        except (TypeError, ValueError):
            delta_int = 0
        if delta_int == 0:
            return [beats_per_bar]
        if delta_int > 0:
            return list(range(beats_per_bar, beats_per_bar + delta_int + 1))
        return list(range(max(1, beats_per_bar + delta_int), beats_per_bar + 1))


class ManualCommittedBarStartsSeedNode(BaseNode):
    """Seeds `committed_bar_starts` from manual input for early v2 testing."""

    optional_keys = ["committed_bar_starts", "manual_bar_starts", "first_bar_anchor"]
    output_keys = ["committed_bar_starts", "bar_start_seed_report"]

    def __init__(self):
        super().__init__("ManualCommittedBarStartsSeedNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        existing = self._normalize_times(blackboard.get_val("committed_bar_starts"))
        if len(existing) >= 2:
            blackboard.set_val("committed_bar_starts", existing)
            blackboard.set_val("bar_start_seed_report", {"source": "existing_committed_bar_starts", "count": len(existing)})
            return NodeStatus.SUCCESS

        manual = self._normalize_times(blackboard.get_val("manual_bar_starts"))
        if len(manual) >= 2:
            blackboard.set_val("committed_bar_starts", manual)
            blackboard.set_val("bar_start_seed_report", {"source": "manual_bar_starts", "count": len(manual)})
            return NodeStatus.SUCCESS

        anchor = blackboard.get_val("first_bar_anchor")
        if anchor is not None:
            try:
                start = float(anchor)
            except (TypeError, ValueError):
                start = 0.0
            seeded = [start, start + 2.0]
            blackboard.set_val("committed_bar_starts", seeded)
            blackboard.set_val("bar_start_seed_report", {"source": "first_bar_anchor_demo_seed", "count": len(seeded)})
            return NodeStatus.SUCCESS

        # Keep the frontend smoke path executable while marking the seed as provisional.
        seeded = [0.0, 2.0]
        blackboard.set_val("committed_bar_starts", seeded)
        blackboard.set_val(
            "bar_start_seed_report",
            {"source": "fallback_demo_seed", "count": len(seeded), "provisional": True},
        )
        return NodeStatus.SUCCESS

    def _normalize_times(self, raw) -> list[float]:
        if raw is None:
            return []
        if isinstance(raw, (int, float)):
            raw = [raw]
        out = []
        for item in raw:
            if isinstance(item, dict):
                item = item.get("time", item.get("start_time"))
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                continue
        return sorted(set(round(t, 6) for t in out if t >= 0.0))


class RollingProbeWindowNode(BaseNode):
    """Builds the next adaptive window used to search for one bar start."""

    optional_keys = [
        "committed_bar_starts",
        "bar_probe_window_sec",
        "last_bar_probe_result",
        "bar_probe_history",
    ]
    output_keys = [
        "bar_probe_window_sec",
        "bar_probe_windows",
        "active_bar_probe_window",
        "bar_probe_history",
        "bar_probe_policy",
    ]

    def __init__(self, default_window_sec: float = 5.0, min_window_sec: float = 2.0, max_window_sec: float = 12.0):
        super().__init__("RollingProbeWindowNode")
        self.default_window_sec = float(default_window_sec)
        self.min_window_sec = float(min_window_sec)
        self.max_window_sec = float(max_window_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        if not committed:
            print(f"[{self.name}] need at least one committed bar start")
            return NodeStatus.FAILURE

        previous_window = self._window_sec(blackboard.get_val("bar_probe_window_sec"))
        result = blackboard.get_val("last_bar_probe_result", {}) or {}
        next_window = self._adjust_window(previous_window, result)
        start_time = self._next_start_time(committed[-1], previous_window, result)
        active = {
            "start_time": round(start_time, 6),
            "end_time": round(start_time + next_window, 6),
            "duration_sec": round(next_window, 6),
            "anchor_time": round(committed[-1], 6),
            "expected_bar_starts": 1,
            "strategy": "rolling_single_bar_probe",
        }
        policy = {
            "default_window_sec": self.default_window_sec,
            "min_window_sec": self.min_window_sec,
            "max_window_sec": self.max_window_sec,
            "step_sec": 1.0,
            "adjustment": self._adjustment_label(previous_window, next_window),
        }
        history = list(blackboard.get_val("bar_probe_history", []) or [])
        if result:
            history.append({
                "input_result": result,
                "previous_window_sec": round(previous_window, 6),
                "next_window_sec": round(next_window, 6),
                "next_start_time": round(start_time, 6),
            })
        windows = list(blackboard.get_val("bar_probe_windows", []) or [])
        windows.append(active)

        blackboard.set_val("bar_probe_window_sec", next_window)
        blackboard.set_val("bar_probe_windows", windows)
        blackboard.set_val("active_bar_probe_window", active)
        blackboard.set_val("bar_probe_history", history)
        blackboard.set_val("bar_probe_policy", policy)
        return NodeStatus.SUCCESS

    def _window_sec(self, raw) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = self.default_window_sec
        return float(np.clip(value, self.min_window_sec, self.max_window_sec))

    def _adjust_window(self, current: float, result: dict) -> float:
        status = str(result.get("status", "")).lower()
        if status in {"not_found", "failed", "uncertain"}:
            return self._clamp(current + 1.0)
        if status in {"found_fast", "too_fast"}:
            return self._clamp(current - 1.0)
        if status == "found":
            offset = result.get("candidate_offset_sec")
            if offset is None and result.get("candidate_time") is not None and result.get("window_start") is not None:
                try:
                    offset = float(result["candidate_time"]) - float(result["window_start"])
                except (TypeError, ValueError):
                    offset = None
            if offset is not None and float(offset) <= max(1.0, current * 0.35):
                return self._clamp(current - 1.0)
        return self._clamp(current)

    def _next_start_time(self, last_committed: float, previous_window: float, result: dict) -> float:
        status = str(result.get("status", "")).lower()
        if status in {"found", "found_fast", "too_fast"} and result.get("candidate_time") is not None:
            try:
                return max(0.0, float(result["candidate_time"]))
            except (TypeError, ValueError):
                return last_committed
        if status in {"not_found", "failed", "uncertain"}:
            try:
                return max(0.0, float(result.get("window_end")))
            except (TypeError, ValueError):
                return last_committed + previous_window
        return last_committed

    def _adjustment_label(self, previous: float, current: float) -> str:
        if current > previous:
            return "increase_by_1s"
        if current < previous:
            return "decrease_by_1s"
        return "keep"

    def _clamp(self, value: float) -> float:
        return float(np.clip(value, self.min_window_sec, self.max_window_sec))


class ReliableBarAnchorNode(BaseNode):
    """Collect high-confidence anchors without treating every onset as a bar start."""

    optional_keys = [
        "reliable_bar_anchors",
        "committed_bar_starts",
        "bar_start_candidates",
        "reliable_anchor_confidence_threshold",
        "meter_profile",
        "tempo_bpm",
    ]
    output_keys = ["reliable_bar_anchors", "reliable_anchor_report"]

    def __init__(self, default_threshold: float = 0.78):
        super().__init__("ReliableBarAnchorNode")
        self.default_threshold = float(default_threshold)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        threshold = float(blackboard.get_val("reliable_anchor_confidence_threshold", self.default_threshold))
        profile = dict(blackboard.get_val("meter_profile", {}) or {})
        raw = blackboard.get_val("reliable_bar_anchors")
        if raw is None:
            raw = blackboard.get_val("bar_start_candidates", [])
        anchors = []
        for item in raw or []:
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                time_sec = float(item.get("time", item.get("bar_start_candidate_time")))
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if confidence < threshold:
                continue
            anchors.append({
                "time": round(time_sec, 6),
                "source": item.get("source", item.get("evidence_sources", ["candidate"])),
                "confidence": round(confidence, 6),
                "meter": item.get("meter", profile.get("meter", "4/4")),
                "tempo": item.get("tempo", blackboard.get_val("tempo_bpm")),
            })
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(
            blackboard.get_val("committed_bar_starts")
        )
        known = {round(float(item["time"]), 6) for item in anchors}
        for time_sec in committed:
            if round(time_sec, 6) not in known:
                anchors.append({
                    "time": round(time_sec, 6),
                    "source": "committed",
                    "confidence": 1.0,
                    "meter": profile.get("meter", "4/4"),
                    "tempo": blackboard.get_val("tempo_bpm"),
                })
        anchors.sort(key=lambda item: item["time"])
        blackboard.set_val("reliable_bar_anchors", anchors)
        blackboard.set_val("reliable_anchor_report", {
            "status": "READY" if anchors else "NO_RELIABLE_ANCHOR",
            "count": len(anchors),
            "threshold": threshold,
        })
        return NodeStatus.SUCCESS


class NoDrumPhaseCarryNode(BaseNode):
    """Carry the previous bar phase through a no-drum span as provisional bars.

    When a future drum anchor exists within the lookahead window, bars are
    carried up to that anchor (unchanged behaviour). When no future anchor is
    found at all -- e.g. a long ambient outro past the lookahead range -- v1's
    `_inertia_fill` still produced a bounded constant-tempo extrapolation
    instead of silently leaving that whole span without any click coverage.
    This pass ports that fallback here, capped at `max_fallback_bars` and by
    the audio's own duration when known, and tagged with a distinct status so
    reviewers can tell it apart from an anchor-confirmed carry.
    """

    optional_keys = [
        "reliable_bar_anchors",
        "committed_bar_starts",
        "bar_duration_sec",
        "tempo_bpm",
        "meter_profile",
        "lookahead_bar_candidates",
        "audio_duration_sec",
        "y",
        "sr",
    ]
    output_keys = ["provisional_bar_starts", "no_drum_phase_report"]

    def __init__(self, tolerance_sec: float = 0.08, max_fallback_bars: int = 8):
        super().__init__("NoDrumPhaseCarryNode")
        self.tolerance_sec = float(tolerance_sec)
        self.max_fallback_bars = int(max_fallback_bars)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        anchors = list(blackboard.get_val("reliable_bar_anchors", []) or [])
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(
            blackboard.get_val("committed_bar_starts")
        )
        previous = float(anchors[-1]["time"]) if anchors else (committed[-1] if committed else None)
        next_anchor = self._next_anchor(blackboard.get_val("lookahead_bar_candidates", []), previous)
        bar_duration = self._bar_duration(blackboard)
        provisional = []
        status = "NO_SPAN"
        used_fallback = False

        if previous is not None and bar_duration > 0:
            if next_anchor is not None:
                current = previous + bar_duration
                while current < next_anchor - self.tolerance_sec:
                    provisional.append(round(current, 6))
                    current += bar_duration
                status = "CARRIED" if provisional else "NO_SPAN"
            else:
                duration_cap = self._audio_duration_cap(blackboard)
                current = previous + bar_duration
                count = 0
                while count < self.max_fallback_bars and (
                    duration_cap is None or current <= duration_cap + self.tolerance_sec
                ):
                    provisional.append(round(current, 6))
                    current += bar_duration
                    count += 1
                used_fallback = True
                status = "CARRIED_FALLBACK_NO_LOOKAHEAD" if provisional else "NO_SPAN"

        blackboard.set_val("provisional_bar_starts", provisional)
        blackboard.set_val("no_drum_phase_report", {
            "status": status,
            "previous_anchor": previous,
            "next_anchor": next_anchor,
            "bar_duration_sec": round(bar_duration, 6) if bar_duration else None,
            "count": len(provisional),
            "provisional": True,
            "used_no_lookahead_fallback": used_fallback,
        })
        return NodeStatus.SUCCESS

    def _audio_duration_cap(self, blackboard: Blackboard) -> float | None:
        try:
            explicit = float(blackboard.get_val("audio_duration_sec"))
            if explicit > 0:
                return explicit
        except (TypeError, ValueError):
            pass
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr")
        try:
            if y is not None and sr:
                length = y.shape[-1] if hasattr(y, "shape") else len(y)
                return float(length) / float(sr)
        except (TypeError, ValueError, AttributeError):
            pass
        return None

    def _next_anchor(self, candidates, previous):
        values = []
        for item in candidates or []:
            try:
                time_sec = float(item.get("time", item.get("candidate_time"))) if isinstance(item, dict) else float(item)
            except (TypeError, ValueError):
                continue
            if previous is None or time_sec > previous + self.tolerance_sec:
                confidence = float(item.get("confidence", 0.0)) if isinstance(item, dict) else 0.0
                values.append((confidence, time_sec))
        return max(values, key=lambda pair: (pair[0], -pair[1]))[1] if values else None

    def _bar_duration(self, blackboard):
        try:
            explicit = float(blackboard.get_val("bar_duration_sec"))
            if explicit > 0:
                return explicit
        except (TypeError, ValueError):
            pass
        try:
            bpm = float(blackboard.get_val("tempo_bpm", 120.0))
            beats_per_bar = int((blackboard.get_val("meter_profile", {}) or {}).get("beats_per_bar", 4))
            return 60.0 / bpm * beats_per_bar if bpm > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0


class LookaheadDrumEventScanNode(BaseNode):
    """Scans kick/snare anchors ahead of the current position into
    `lookahead_drum_events` for `LookaheadDrumAnchorSearchNode` to consume.

    `kick_anchors`/`snare_anchors` (Stage 3's `KickSnarePulseNode`, shared
    into v2's blackboard when running through `Module3BarStartV2MergeNode`)
    are a full-song array computed once upfront. Nothing ever filtered them
    down into `lookahead_drum_events`, so the bidirectional re-anchoring
    across no-drum spans (Pass 116-117) never had real data to work with in
    production -- only in unit tests that set the key by hand. This is what
    was missing.
    """

    optional_keys = ["kick_anchors", "snare_anchors", "committed_bar_starts", "lookahead_horizon_sec"]
    output_keys = ["lookahead_drum_events"]

    def __init__(self, horizon_sec: float = 30.0, dedupe_tolerance_sec: float = 0.05):
        super().__init__("LookaheadDrumEventScanNode")
        self.horizon_sec = float(horizon_sec)
        self.dedupe_tolerance_sec = float(dedupe_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        previous = committed[-1] if committed else 0.0
        horizon = self._horizon(blackboard)

        events = []
        for key, base_confidence in (("kick_anchors", 0.75), ("snare_anchors", 0.6)):
            for t in self._normalize_anchor_times(blackboard.get_val(key)):
                if t <= previous or t > previous + horizon:
                    continue
                events.append({"time": round(t, 6), "confidence": base_confidence})

        blackboard.set_val("lookahead_drum_events", self._dedupe(events))
        return NodeStatus.SUCCESS

    def _horizon(self, blackboard: Blackboard) -> float:
        try:
            value = float(blackboard.get_val("lookahead_horizon_sec"))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
        return self.horizon_sec

    def _normalize_anchor_times(self, raw) -> list[float]:
        if raw is None:
            return []
        try:
            arr = np.asarray(raw, dtype=float).reshape(-1)
        except (TypeError, ValueError):
            return []
        return sorted(float(t) for t in arr if np.isfinite(t) and t >= 0.0)

    def _dedupe(self, events: list[dict]) -> list[dict]:
        out = []
        for event in sorted(events, key=lambda item: (-item["confidence"], item["time"])):
            if all(abs(event["time"] - existing["time"]) > self.dedupe_tolerance_sec for existing in out):
                out.append(event)
        return sorted(out, key=lambda item: item["time"])


class LookaheadDrumAnchorSearchNode(BaseNode):
    """Turn future drum evidence into candidates with offsets, never direct commits."""

    optional_keys = [
        "lookahead_drum_events",
        "drum_onset_candidates",
        "bar_start_candidates",
        "committed_bar_starts",
        "lookahead_offsets_sec",
    ]
    output_keys = ["lookahead_bar_candidates", "lookahead_anchor_report"]

    def __init__(self):
        super().__init__("LookaheadDrumAnchorSearchNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raw = blackboard.get_val("lookahead_drum_events")
        if raw is None:
            raw = blackboard.get_val("drum_onset_candidates")
        if raw is None:
            raw = []
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(
            blackboard.get_val("committed_bar_starts")
        )
        previous = committed[-1] if committed else None
        offsets = blackboard.get_val("lookahead_offsets_sec", [0.0, -0.5, 0.5, -1.0, 1.0])
        candidates = []
        for item in raw:
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                event_time = float(item.get("time", item.get("onset_time", item.get("candidate_time"))))
            except (TypeError, ValueError):
                continue
            if previous is not None and event_time <= previous:
                continue
            base_confidence = float(item.get("confidence", item.get("score", 0.65)))
            for offset in offsets:
                candidate_time = event_time + float(offset)
                if previous is not None and candidate_time <= previous:
                    continue
                candidates.append({
                    "time": round(candidate_time, 6),
                    "event_time": round(event_time, 6),
                    "offset_sec": round(float(offset), 6),
                    "confidence": round(max(0.0, min(1.0, base_confidence - abs(float(offset)) * 0.08)), 6),
                    "evidence_sources": ["lookahead_drum"],
                    "is_fill_or_pickup": bool(item.get("is_fill_or_pickup", False)),
                })
        candidates.sort(key=lambda item: (-item["confidence"], item["time"]))
        blackboard.set_val("lookahead_bar_candidates", candidates)
        blackboard.set_val("lookahead_anchor_report", {
            "status": "READY" if candidates else "LOOKAHEAD_PENDING",
            "event_count": len(raw),
            "candidate_count": len(candidates),
        })
        return NodeStatus.SUCCESS


class InterveningBarCountEstimatorNode(BaseNode):
    """Estimate N-1/N/N+1 bars between two anchors."""

    optional_keys = ["reliable_bar_anchors", "lookahead_bar_candidates", "bar_duration_sec", "meter_profile", "tempo_bpm"]
    output_keys = ["intervening_bar_count_candidates", "selected_intervening_bar_count"]

    def __init__(self):
        super().__init__("InterveningBarCountEstimatorNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        anchors = list(blackboard.get_val("reliable_bar_anchors", []) or [])
        candidates = list(blackboard.get_val("lookahead_bar_candidates", []) or [])
        previous = float(anchors[-1]["time"]) if anchors else None
        next_item = max(candidates, key=lambda item: (float(item.get("confidence", 0.0)), -float(item.get("offset_sec", 0.0)))) if candidates else None
        duration = NoDrumPhaseCarryNode()._bar_duration(blackboard)
        rows = []
        selected = None
        if previous is not None and next_item is not None and duration > 0:
            delta = max(0.0, float(next_item["time"]) - previous)
            estimate = max(1, int(round(delta / duration)))
            allowed = sorted({max(1, estimate - 1), estimate, estimate + 1})
            for count in allowed:
                error = abs(delta - count * duration)
                rows.append({
                    "bar_count": count,
                    "duration_error_sec": round(error, 6),
                    "next_anchor_time": next_item["time"],
                    "candidate": next_item,
                })
            selected = min(rows, key=lambda row: row["duration_error_sec"])
        blackboard.set_val("intervening_bar_count_candidates", rows)
        blackboard.set_val("selected_intervening_bar_count", selected)
        return NodeStatus.SUCCESS


class BidirectionalBarAlignmentNode(BaseNode):
    """Validate forward/backward projections before creating commit candidates."""

    optional_keys = [
        "reliable_bar_anchors",
        "selected_intervening_bar_count",
        "provisional_bar_starts",
        "lookahead_bar_candidates",
        "bar_duration_sec",
        "transition_alignment_tolerance_sec",
    ]
    output_keys = ["bidirectional_alignment_report", "bar_start_candidates"]

    def __init__(self, tolerance_sec: float = 0.18):
        super().__init__("BidirectionalBarAlignmentNode")
        self.tolerance_sec = float(tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        anchors = list(blackboard.get_val("reliable_bar_anchors", []) or [])
        selected = blackboard.get_val("selected_intervening_bar_count") or {}
        next_item = selected.get("candidate", {})
        duration = NoDrumPhaseCarryNode()._bar_duration(blackboard)
        report = {"status": "LOOKAHEAD_PENDING", "phase_error_sec": None, "bar_count": selected.get("bar_count")}
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        if anchors and next_item and selected.get("bar_count") and duration > 0:
            previous = float(anchors[-1]["time"])
            next_time = float(next_item["time"])
            count = int(selected["bar_count"])
            forward_end = previous + count * duration
            backward_start = next_time - count * duration
            phase_error = abs(forward_end - next_time)
            report.update({
                "forward_projection_end": round(forward_end, 6),
                "backward_projection_start": round(backward_start, 6),
                "phase_error_sec": round(phase_error, 6),
                "status": "ALIGNED" if phase_error <= float(blackboard.get_val("transition_alignment_tolerance_sec", self.tolerance_sec)) else "AMBIGUOUS_TRANSITION",
            })
            if next_item.get("is_fill_or_pickup"):
                report["status"] = "PICKUP_CANDIDATE_ONLY"
            if (
                report["status"] == "ALIGNED"
                and float(next_item.get("confidence", 0.0)) >= 0.78
                and not next_item.get("is_fill_or_pickup")
            ):
                for index in range(1, count + 1):
                    time_sec = round(previous + index * duration, 6)
                    candidates.append({
                        "time": time_sec,
                        "confidence": max(0.0, min(0.95, float(next_item.get("confidence", 0.0)) - phase_error)),
                        "evidence_sources": ["bidirectional_alignment", "lookahead_drum"],
                        "transition_candidate": True,
                    })
        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("bidirectional_alignment_report", report)
        return NodeStatus.SUCCESS


class TransitionConfidenceNode(BaseNode):
    """Require post-entry stability before promoting a transition to high confidence."""

    optional_keys = ["bidirectional_alignment_report", "transition_observed_bars", "transition_confidence_report"]
    output_keys = ["transition_confidence_report"]

    def __init__(self, stable_bars_required: int = 2):
        super().__init__("TransitionConfidenceNode")
        self.stable_bars_required = int(stable_bars_required)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        alignment = dict(blackboard.get_val("bidirectional_alignment_report", {}) or {})
        observed = int(blackboard.get_val("transition_observed_bars", 0) or 0)
        status = alignment.get("status", "LOOKAHEAD_PENDING")
        if status == "ALIGNED" and observed >= self.stable_bars_required:
            confidence = "HIGH"
        elif status == "ALIGNED":
            confidence = "MEDIUM_PENDING_STABILITY"
        else:
            confidence = "LOW"
        report = {
            "status": confidence,
            "alignment_status": status,
            "observed_bars": observed,
            "stable_bars_required": self.stable_bars_required,
            "can_promote": confidence == "HIGH",
        }
        blackboard.set_val("transition_confidence_report", report)
        return NodeStatus.SUCCESS


def _score_bar_start_list_quality(bars: list[float]) -> float | None:
    """Lightweight duration-consistency score for a committed bar-start list.

    Mirrors the intent of Stage 3's `_score_beat_grid_quality` (tempo
    stability is its largest single weight) but works directly on bar-start
    times, since v2 commits bars one probe window at a time -- before any
    beat matrix exists for `_score_beat_grid_quality` to consume. Returns
    `None` when there are too few bars to judge duration consistency, which
    callers must treat as "no opinion" rather than a low score.
    """
    if len(bars) < 3:
        return None
    ordered = sorted(bars)
    intervals = [b - a for a, b in zip(ordered, ordered[1:])]
    valid = [d for d in intervals if d > 0.05]
    if len(valid) < 2:
        return None
    mean = sum(valid) / len(valid)
    if mean <= 0:
        return None
    variance = sum((d - mean) ** 2 for d in valid) / len(valid)
    std = variance ** 0.5
    return max(0.0, 1.0 - (std / mean))


class BarStartCandidateCommitNode(BaseNode):
    """Commits the best bar-start candidate or records an unresolved probe span."""

    optional_keys = [
        "bar_start_candidates",
        "committed_bar_starts",
        "active_bar_probe_window",
        "candidate_commit_confidence_threshold",
        "unresolved_bar_spans",
    ]
    output_keys = [
        "bar_start_candidates",
        "committed_bar_starts",
        "unresolved_bar_spans",
        "bar_start_decision_report",
        "last_bar_probe_result",
    ]

    def __init__(
        self,
        default_threshold: float = 0.7,
        duplicate_tolerance_sec: float = 0.03,
        quality_drop_tolerance: float = 0.15,
    ):
        super().__init__("BarStartCandidateCommitNode")
        self.default_threshold = float(default_threshold)
        self.duplicate_tolerance_sec = float(duplicate_tolerance_sec)
        self.quality_drop_tolerance = float(quality_drop_tolerance)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = self._normalize_candidates(blackboard.get_val("bar_start_candidates", []), window)
        threshold = self._threshold(blackboard.get_val("candidate_commit_confidence_threshold"))
        best = self._best_candidate(candidates)

        report = {
            "threshold": threshold,
            "candidate_count": len(candidates),
            "active_bar_probe_window": window,
            "status": "NO_CANDIDATE",
        }

        if best and best["confidence"] >= threshold:
            candidate_committed = self._append_unique(list(committed), best["time"])
            quality_before = _score_bar_start_list_quality(committed)
            quality_after = _score_bar_start_list_quality(candidate_committed)
            regresses = (
                quality_before is not None
                and quality_after is not None
                and quality_after < quality_before - self.quality_drop_tolerance
            )

            if regresses:
                reason = "quality_regression"
                unresolved = list(blackboard.get_val("unresolved_bar_spans", []) or [])
                unresolved.append({
                    "start_time": window.get("start_time"),
                    "end_time": window.get("end_time"),
                    "reason": reason,
                    "best_confidence": best["confidence"],
                    "rejected_time": best["time"],
                    "quality_before": quality_before,
                    "quality_after": quality_after,
                })
                result = self._probe_result("uncertain", window, best)
                report.update({
                    "status": "UNRESOLVED",
                    "reason": reason,
                    "best_candidate": best,
                    "quality_before": quality_before,
                    "quality_after": quality_after,
                })
                blackboard.set_val("unresolved_bar_spans", unresolved)
                blackboard.set_val("last_bar_probe_result", result)
            else:
                committed = candidate_committed
                result = self._probe_result("found", window, best)
                report.update({
                    "status": "COMMITTED",
                    "committed_time": best["time"],
                    "confidence": best["confidence"],
                    "evidence_sources": best.get("evidence_sources", []),
                    "quality_before": quality_before,
                    "quality_after": quality_after,
                })
                blackboard.set_val("committed_bar_starts", committed)
                blackboard.set_val("last_bar_probe_result", result)
        else:
            reason = "confidence_below_threshold" if best else "no_candidates"
            unresolved = list(blackboard.get_val("unresolved_bar_spans", []) or [])
            span = {
                "start_time": window.get("start_time"),
                "end_time": window.get("end_time"),
                "reason": reason,
                "best_confidence": best.get("confidence") if best else None,
            }
            unresolved.append(span)
            result_status = "uncertain" if best else "not_found"
            result = self._probe_result(result_status, window, best)
            report.update({
                "status": "UNRESOLVED",
                "reason": reason,
                "best_candidate": best or {},
            })
            blackboard.set_val("unresolved_bar_spans", unresolved)
            blackboard.set_val("last_bar_probe_result", result)

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("bar_start_decision_report", report)
        return NodeStatus.SUCCESS

    def _normalize_candidates(self, raw, window: dict) -> list[dict]:
        if isinstance(raw, dict):
            raw = [raw]
        start = window.get("start_time")
        end = window.get("end_time")
        out = []
        for idx, item in enumerate(raw or []):
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                time_sec = float(item.get("time", item.get("bar_start_candidate_time")))
            except (TypeError, ValueError):
                continue
            if start is not None and time_sec < float(start):
                continue
            if end is not None and time_sec > float(end):
                continue
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            evidence = item.get("evidence_sources", item.get("sources", []))
            if isinstance(evidence, str):
                evidence = [evidence]
            out.append({
                "candidate_id": item.get("candidate_id", f"bar_start_candidate_{idx + 1}"),
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "evidence_sources": list(evidence or []),
                "source_node": item.get("source_node", item.get("source", "unknown")),
                "failure_reason": item.get("failure_reason"),
                "uncertainty_reason": item.get("uncertainty_reason"),
            })
        return sorted(out, key=lambda item: (item["time"], -item["confidence"]))

    def _best_candidate(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item["confidence"], -item["time"]))

    def _append_unique(self, committed: list[float], time_sec: float) -> list[float]:
        if all(abs(float(existing) - float(time_sec)) > self.duplicate_tolerance_sec for existing in committed):
            committed.append(float(time_sec))
        return sorted(set(round(float(t), 6) for t in committed if float(t) >= 0.0))

    def _threshold(self, raw) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = self.default_threshold
        return round(float(np.clip(value, 0.0, 1.0)), 6)

    def _probe_result(self, status: str, window: dict, best: dict | None) -> dict:
        candidate_time = best.get("time") if best else None
        result = {
            "status": status,
            "window_start": window.get("start_time"),
            "window_end": window.get("end_time"),
            "candidate_time": candidate_time,
            "confidence": best.get("confidence") if best else None,
        }
        if candidate_time is not None and window.get("start_time") is not None:
            result["candidate_offset_sec"] = round(float(candidate_time) - float(window["start_time"]), 6)
        return result


class DrumEvidenceBarSearchNode(BaseNode):
    """Produces bar-start candidates from drums and drum-substem anchors."""

    optional_keys = [
        "active_bar_probe_window",
        "committed_bar_starts",
        "kick_anchors",
        "snare_anchors",
        "drum_onset_candidates",
        "snap_exclusion_zones",
        "drum_fill_regions",
        "bar_start_candidates",
    ]
    output_keys = ["bar_start_candidates", "drum_bar_evidence_report"]

    def __init__(self):
        super().__init__("DrumEvidenceBarSearchNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        if not window:
            blackboard.set_val("drum_bar_evidence_report", {"status": "SKIPPED_NO_WINDOW", "candidate_count": 0})
            return NodeStatus.SUCCESS

        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        expected_interval = self._expected_interval(committed)
        kick_times = self._normalize_times(blackboard.get_val("kick_anchors"))
        snare_times = self._normalize_times(blackboard.get_val("snare_anchors"))
        onset_times = self._normalize_times(blackboard.get_val("drum_onset_candidates"))
        exclusions = list(blackboard.get_val("snap_exclusion_zones", []) or []) + list(blackboard.get_val("drum_fill_regions", []) or [])
        existing = list(blackboard.get_val("bar_start_candidates", []) or [])

        candidates = []
        for time_sec in kick_times:
            if not self._inside_window(time_sec, window):
                continue
            candidates.append(self._candidate(time_sec, "kick", window, expected_interval, snare_times, exclusions))

        if not candidates:
            for time_sec in onset_times or snare_times:
                if not self._inside_window(time_sec, window):
                    continue
                candidates.append(self._candidate(time_sec, "drum_onset", window, expected_interval, snare_times, exclusions, base=0.35))

        deduped = self._dedupe_candidates(candidates)
        blackboard.set_val("bar_start_candidates", existing + deduped)
        blackboard.set_val("drum_bar_evidence_report", {
            "status": "CANDIDATES_BUILT" if deduped else "NO_DRUM_EVIDENCE",
            "candidate_count": len(deduped),
            "kick_count_in_window": sum(1 for t in kick_times if self._inside_window(t, window)),
            "snare_count_in_window": sum(1 for t in snare_times if self._inside_window(t, window)),
            "expected_interval_sec": expected_interval,
        })
        return NodeStatus.SUCCESS

    def _candidate(
        self,
        time_sec: float,
        source: str,
        window: dict,
        expected_interval: float | None,
        snare_times: list[float],
        exclusions: list[dict],
        base: float = 0.55,
    ) -> dict:
        confidence = base
        evidence = ["drums", source]
        offset = float(time_sec) - float(window.get("start_time", 0.0))
        if expected_interval and abs(offset - expected_interval) <= max(0.12, expected_interval * 0.18):
            confidence += 0.2
            evidence.append("expected_bar_interval")
        if any(0.25 <= snare - time_sec <= max(0.8, (expected_interval or 2.0) * 0.65) for snare in snare_times):
            confidence += 0.15
            evidence.append("snare_backbeat_support")

        uncertainty = None
        if self._inside_exclusion(time_sec, exclusions):
            confidence -= 0.3
            uncertainty = "inside_drum_fill_or_snap_exclusion"
            evidence.append("exclusion_penalty")
        else:
            confidence += 0.1
            evidence.append("outside_fill_exclusion")

        return {
            "time": round(float(time_sec), 6),
            "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
            "evidence_sources": evidence,
            "source_node": self.name,
            "uncertainty_reason": uncertainty,
        }

    def _expected_interval(self, committed: list[float]) -> float | None:
        if len(committed) < 2:
            return None
        interval = committed[-1] - committed[-2]
        return float(interval) if interval > 0 else None

    def _normalize_times(self, raw) -> list[float]:
        return ManualCommittedBarStartsSeedNode()._normalize_times(raw)

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end

    def _inside_exclusion(self, time_sec: float, exclusions: list[dict]) -> bool:
        for zone in exclusions:
            start = zone.get("start_time", zone.get("start"))
            end = zone.get("end_time", zone.get("end"))
            if start is None or end is None:
                continue
            if float(start) <= float(time_sec) <= float(end):
                return True
        return False

    def _dedupe_candidates(self, candidates: list[dict]) -> list[dict]:
        out = []
        for candidate in sorted(candidates, key=lambda item: (-item["confidence"], item["time"])):
            if all(abs(candidate["time"] - existing["time"]) > 0.03 for existing in out):
                out.append(candidate)
        return sorted(out, key=lambda item: item["time"])


class DrumBassEvidenceBarSearchNode(BaseNode):
    """Adds bass support to drum candidates or emits conservative bass-only candidates."""

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "bass_anchors",
        "bass_onset_candidates",
        "committed_bar_starts",
    ]
    output_keys = ["bar_start_candidates", "drum_bass_evidence_report"]

    def __init__(self, coincidence_tolerance_sec: float = 0.09):
        super().__init__("DrumBassEvidenceBarSearchNode")
        self.coincidence_tolerance_sec = float(coincidence_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        bass_times = self._normalize_times(blackboard.get_val("bass_anchors"))
        bass_times += self._normalize_times(blackboard.get_val("bass_onset_candidates"))
        bass_times = sorted(set(round(t, 6) for t in bass_times if self._inside_window(t, window)))
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        drum_candidates = [
            candidate for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("source_node") == "DrumEvidenceBarSearchNode"
        ]

        boosted = 0
        for candidate in drum_candidates:
            nearest = self._nearest_bass(float(candidate.get("time", 0.0)), bass_times)
            if nearest is None:
                continue
            confidence = float(candidate.get("confidence", 0.0))
            candidate["confidence"] = round(float(np.clip(confidence + 0.12, 0.0, 1.0)), 6)
            evidence = list(candidate.get("evidence_sources", []) or [])
            if "bass_coincidence_support" not in evidence:
                evidence.append("bass_coincidence_support")
            candidate["evidence_sources"] = evidence
            candidate["bass_support_time"] = nearest
            boosted += 1

        added = []
        if not drum_candidates and bass_times:
            committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
            expected_interval = self._expected_interval(committed)
            for time_sec in bass_times:
                if self._has_candidate_near(candidates + added, time_sec):
                    continue
                added.append(self._bass_only_candidate(time_sec, window, expected_interval))
                break
            candidates.extend(added)

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("drum_bass_evidence_report", {
            "status": "UPDATED" if boosted or added else "NO_BASS_SUPPORT",
            "bass_count_in_window": len(bass_times),
            "boosted_candidate_count": boosted,
            "bass_only_candidate_count": len(added),
        })
        return NodeStatus.SUCCESS

    def _normalize_times(self, raw) -> list[float]:
        return ManualCommittedBarStartsSeedNode()._normalize_times(raw)

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        if not window:
            return False
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end

    def _nearest_bass(self, time_sec: float, bass_times: list[float]) -> float | None:
        if not bass_times:
            return None
        nearest = min(bass_times, key=lambda t: abs(float(t) - time_sec))
        return nearest if abs(float(nearest) - time_sec) <= self.coincidence_tolerance_sec else None

    def _bass_only_candidate(self, time_sec: float, window: dict, expected_interval: float | None) -> dict:
        confidence = 0.42
        offset = float(time_sec) - float(window.get("start_time", 0.0))
        evidence = ["bass", "bass_onset"]
        if expected_interval and abs(offset - expected_interval) <= max(0.12, expected_interval * 0.18):
            confidence += 0.15
            evidence.append("expected_bar_interval")
        return {
            "time": round(float(time_sec), 6),
            "confidence": round(float(np.clip(confidence, 0.0, 0.68)), 6),
            "evidence_sources": evidence,
            "source_node": self.name,
            "uncertainty_reason": "bass_only_requires_other_support",
        }

    def _has_candidate_near(self, candidates: list[dict], time_sec: float) -> bool:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                existing_time = float(candidate.get("time", candidate.get("bar_start_candidate_time")))
            except (TypeError, ValueError):
                continue
            if abs(existing_time - float(time_sec)) <= self.coincidence_tolerance_sec:
                return True
        return False

    def _expected_interval(self, committed: list[float]) -> float | None:
        if len(committed) < 2:
            return None
        interval = committed[-1] - committed[-2]
        return float(interval) if interval > 0 else None


class ChordTrackPKNode(BaseNode):
    """Builds guitar/piano harmonic anchors and uses them as conservative bar-start evidence."""

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "guitar_chord_anchors",
        "piano_chord_anchors",
        "chord_progression",
    ]
    output_keys = ["bar_start_candidates", "chord_track_pk", "harmonic_anchor_evidence_report"]

    def __init__(self, coincidence_tolerance_sec: float = 0.12):
        super().__init__("ChordTrackPKNode")
        self.coincidence_tolerance_sec = float(coincidence_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        anchors = []
        anchors.extend(self._normalize_anchors(blackboard.get_val("guitar_chord_anchors"), "guitar_chord", window))
        anchors.extend(self._normalize_anchors(blackboard.get_val("piano_chord_anchors"), "piano_chord", window))
        anchors.extend(self._anchors_from_chord_progression(blackboard.get_val("chord_progression"), window))
        anchors = self._dedupe_anchors(anchors)

        pk = self._build_pk(anchors)
        boosted = self._boost_candidates(candidates, anchors)
        added = []
        if not self._has_rhythm_candidate(candidates) and anchors:
            for anchor in sorted(anchors, key=lambda item: (-item["confidence"], item["time"])):
                if self._has_candidate_near(candidates + added, anchor["time"]):
                    continue
                added.append(self._harmonic_only_candidate(anchor))
                break
            candidates.extend(added)

        status = "ANCHORS_BUILT" if anchors else "NO_HARMONIC_ANCHORS"
        report = {
            "status": status,
            "anchor_count": len(anchors),
            "boosted_candidate_count": boosted,
            "harmonic_only_candidate_count": len(added),
            "primary_source": pk.get("primary_source"),
            "primary_anchor_time": pk.get("primary_anchor_time"),
        }

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("chord_track_pk", pk)
        blackboard.set_val("harmonic_anchor_evidence_report", report)
        return NodeStatus.SUCCESS

    def _normalize_anchors(self, raw, source: str, window: dict) -> list[dict]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            raw = [raw]
        out = []
        for item in raw or []:
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                time_sec = float(item.get("time", item.get("start_time")))
            except (TypeError, ValueError):
                continue
            if not self._inside_window(time_sec, window):
                continue
            try:
                confidence = float(item.get("confidence", 0.65))
            except (TypeError, ValueError):
                confidence = 0.65
            out.append({
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "source": source,
                "chord": item.get("chord", item.get("label")),
            })
        return out

    def _anchors_from_chord_progression(self, raw, window: dict) -> list[dict]:
        anchors = []
        if isinstance(raw, dict):
            raw = [raw]
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            chord = item.get("chord")
            if not chord or str(chord).upper() in {"N/A", "N.C.", "NC"}:
                continue
            try:
                time_sec = float(item.get("start_time", item.get("time")))
            except (TypeError, ValueError):
                continue
            if self._inside_window(time_sec, window):
                anchors.append({
                    "time": round(time_sec, 6),
                    "confidence": 0.58,
                    "source": "chord_progression",
                    "chord": chord,
                })
        return anchors

    def _dedupe_anchors(self, anchors: list[dict]) -> list[dict]:
        out = []
        for anchor in sorted(anchors, key=lambda item: (-item["confidence"], item["time"])):
            if all(anchor["source"] != existing["source"] or abs(anchor["time"] - existing["time"]) > 0.01 for existing in out):
                out.append(anchor)
        return sorted(out, key=lambda item: item["time"])

    def _build_pk(self, anchors: list[dict]) -> dict:
        if not anchors:
            return {"status": "NO_HARMONIC_ANCHORS", "anchor_count": 0, "anchors": []}
        ranked = sorted(anchors, key=lambda item: (item["confidence"], item["source"] == "piano_chord"), reverse=True)
        primary = ranked[0]
        consensus = [
            anchor for anchor in anchors
            if abs(anchor["time"] - primary["time"]) <= self.coincidence_tolerance_sec
        ]
        return {
            "status": "ANCHORS_BUILT",
            "primary_source": primary["source"],
            "primary_anchor_time": primary["time"],
            "primary_chord": primary.get("chord"),
            "primary_confidence": primary["confidence"],
            "anchor_count": len(anchors),
            "consensus_count": len(consensus),
            "anchors": anchors,
        }

    def _boost_candidates(self, candidates: list[dict], anchors: list[dict]) -> int:
        boosted = 0
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("source_node") == self.name:
                continue
            nearest = self._nearest_anchor(float(candidate.get("time", 0.0)), anchors)
            if nearest is None:
                continue
            confidence = float(candidate.get("confidence", 0.0))
            candidate["confidence"] = round(float(np.clip(confidence + 0.14, 0.0, 1.0)), 6)
            evidence = list(candidate.get("evidence_sources", []) or [])
            if "harmonic_anchor_support" not in evidence:
                evidence.append("harmonic_anchor_support")
            candidate["evidence_sources"] = evidence
            candidate["harmonic_support_time"] = nearest["time"]
            candidate["harmonic_support_source"] = nearest["source"]
            boosted += 1
        return boosted

    def _nearest_anchor(self, time_sec: float, anchors: list[dict]) -> dict | None:
        if not anchors:
            return None
        nearest = min(anchors, key=lambda item: abs(item["time"] - time_sec))
        return nearest if abs(nearest["time"] - time_sec) <= self.coincidence_tolerance_sec else None

    def _harmonic_only_candidate(self, anchor: dict) -> dict:
        confidence = min(0.66, 0.38 + float(anchor.get("confidence", 0.0)) * 0.2)
        return {
            "time": anchor["time"],
            "confidence": round(float(np.clip(confidence, 0.0, 0.66)), 6),
            "evidence_sources": ["harmonic_anchor", anchor["source"]],
            "source_node": self.name,
            "harmonic_support_source": anchor["source"],
            "chord": anchor.get("chord"),
            "uncertainty_reason": "harmonic_only_requires_rhythm_support",
        }

    def _has_rhythm_candidate(self, candidates: list[dict]) -> bool:
        rhythm_sources = {"DrumEvidenceBarSearchNode", "DrumBassEvidenceBarSearchNode"}
        return any(isinstance(candidate, dict) and candidate.get("source_node") in rhythm_sources for candidate in candidates)

    def _has_candidate_near(self, candidates: list[dict], time_sec: float) -> bool:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                existing_time = float(candidate.get("time", candidate.get("bar_start_candidate_time")))
            except (TypeError, ValueError):
                continue
            if abs(existing_time - float(time_sec)) <= self.coincidence_tolerance_sec:
                return True
        return False

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        if not window:
            return False
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end


class MelodyTrackPKNode(BaseNode):
    """Builds melody phrase anchors while keeping melody-only evidence below commit threshold."""

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "vocal_melody_anchors",
        "piano_melody_anchors",
        "guitar_melody_anchors",
        "count_in_events",
    ]
    output_keys = ["bar_start_candidates", "melody_track_pk", "phrase_anchor_evidence_report"]

    def __init__(self, coincidence_tolerance_sec: float = 0.14):
        super().__init__("MelodyTrackPKNode")
        self.coincidence_tolerance_sec = float(coincidence_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        anchors = []
        anchors.extend(self._normalize_anchors(blackboard.get_val("vocal_melody_anchors"), "vocal_melody", window))
        anchors.extend(self._normalize_anchors(blackboard.get_val("piano_melody_anchors"), "piano_melody", window))
        anchors.extend(self._normalize_anchors(blackboard.get_val("guitar_melody_anchors"), "guitar_melody", window))
        anchors.extend(self._normalize_anchors(blackboard.get_val("count_in_events"), "count_in", window, default_confidence=0.7))
        anchors = self._dedupe_anchors(anchors)

        pk = self._build_pk(anchors)
        boosted = self._boost_candidates(candidates, anchors)
        added = []
        if not candidates and anchors:
            for anchor in sorted(anchors, key=lambda item: (-item["confidence"], item["time"])):
                added.append(self._phrase_only_candidate(anchor))
                break
            candidates.extend(added)

        report = {
            "status": "ANCHORS_BUILT" if anchors else "NO_PHRASE_ANCHORS",
            "anchor_count": len(anchors),
            "boosted_candidate_count": boosted,
            "phrase_only_candidate_count": len(added),
            "primary_source": pk.get("primary_source"),
            "primary_anchor_time": pk.get("primary_anchor_time"),
        }

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("melody_track_pk", pk)
        blackboard.set_val("phrase_anchor_evidence_report", report)
        return NodeStatus.SUCCESS

    def _normalize_anchors(self, raw, source: str, window: dict, default_confidence: float = 0.62) -> list[dict]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            raw = [raw]
        out = []
        for item in raw or []:
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                time_sec = float(item.get("time", item.get("start_time")))
            except (TypeError, ValueError):
                continue
            if not self._inside_window(time_sec, window):
                continue
            try:
                confidence = float(item.get("confidence", default_confidence))
            except (TypeError, ValueError):
                confidence = default_confidence
            out.append({
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "source": source,
                "phrase": item.get("phrase", item.get("label", source)),
            })
        return out

    def _dedupe_anchors(self, anchors: list[dict]) -> list[dict]:
        out = []
        for anchor in sorted(anchors, key=lambda item: (-item["confidence"], item["time"])):
            if all(anchor["source"] != existing["source"] or abs(anchor["time"] - existing["time"]) > 0.01 for existing in out):
                out.append(anchor)
        return sorted(out, key=lambda item: item["time"])

    def _build_pk(self, anchors: list[dict]) -> dict:
        if not anchors:
            return {"status": "NO_PHRASE_ANCHORS", "anchor_count": 0, "anchors": []}
        ranked = sorted(anchors, key=lambda item: (item["confidence"], item["source"] == "vocal_melody"), reverse=True)
        primary = ranked[0]
        consensus = [
            anchor for anchor in anchors
            if abs(anchor["time"] - primary["time"]) <= self.coincidence_tolerance_sec
        ]
        return {
            "status": "ANCHORS_BUILT",
            "primary_source": primary["source"],
            "primary_anchor_time": primary["time"],
            "primary_phrase": primary.get("phrase"),
            "primary_confidence": primary["confidence"],
            "anchor_count": len(anchors),
            "consensus_count": len(consensus),
            "anchors": anchors,
        }

    def _boost_candidates(self, candidates: list[dict], anchors: list[dict]) -> int:
        boosted = 0
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("source_node") == self.name:
                continue
            nearest = self._nearest_anchor(float(candidate.get("time", 0.0)), anchors)
            if nearest is None:
                continue
            confidence = float(candidate.get("confidence", 0.0))
            candidate["confidence"] = round(float(np.clip(confidence + 0.08, 0.0, 1.0)), 6)
            evidence = list(candidate.get("evidence_sources", []) or [])
            if "phrase_anchor_support" not in evidence:
                evidence.append("phrase_anchor_support")
            candidate["evidence_sources"] = evidence
            candidate["phrase_support_time"] = nearest["time"]
            candidate["phrase_support_source"] = nearest["source"]
            boosted += 1
        return boosted

    def _nearest_anchor(self, time_sec: float, anchors: list[dict]) -> dict | None:
        if not anchors:
            return None
        nearest = min(anchors, key=lambda item: abs(item["time"] - time_sec))
        return nearest if abs(nearest["time"] - time_sec) <= self.coincidence_tolerance_sec else None

    def _phrase_only_candidate(self, anchor: dict) -> dict:
        confidence = min(0.6, 0.32 + float(anchor.get("confidence", 0.0)) * 0.18)
        return {
            "time": anchor["time"],
            "confidence": round(float(np.clip(confidence, 0.0, 0.6)), 6),
            "evidence_sources": ["phrase_anchor", anchor["source"]],
            "source_node": self.name,
            "phrase_support_source": anchor["source"],
            "phrase": anchor.get("phrase"),
            "uncertainty_reason": "phrase_only_requires_rhythm_or_harmonic_support",
        }

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        if not window:
            return False
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end


class BeatThisCandidateAdapterNode(BaseNode):
    """Adapts optional Beat This! beat/downbeat candidates into the bar-start evidence ladder."""

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "beat_this_beats",
        "beat_this_downbeats",
        "beat_this_candidates",
        "committed_bar_starts",
    ]
    output_keys = ["bar_start_candidates", "beat_this_candidate_report"]

    def __init__(self, coincidence_tolerance_sec: float = 0.08):
        super().__init__("BeatThisCandidateAdapterNode")
        self.coincidence_tolerance_sec = float(coincidence_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        expected_interval = self._expected_interval(committed)

        beat_this_candidates = []
        beat_this_candidates.extend(self._normalize_downbeats(blackboard.get_val("beat_this_downbeats"), window))
        beat_this_candidates.extend(self._normalize_beats(blackboard.get_val("beat_this_beats"), window))
        beat_this_candidates.extend(self._normalize_candidates(blackboard.get_val("beat_this_candidates"), window))
        beat_this_candidates = self._dedupe_candidates(beat_this_candidates)

        if not beat_this_candidates:
            blackboard.set_val("beat_this_candidate_report", {
                "status": "SKIPPED_NO_BEAT_THIS_CANDIDATES",
                "candidate_count": 0,
                "boosted_candidate_count": 0,
                "fallback": "BeatNet/Librosa candidates remain authoritative",
            })
            return NodeStatus.SUCCESS

        boosted = self._boost_existing_candidates(candidates, beat_this_candidates)
        added = []
        for item in sorted(beat_this_candidates, key=lambda row: (-row["confidence"], row["time"])):
            if self._has_candidate_near(candidates + added, item["time"]):
                continue
            added.append(self._bar_start_candidate(item, window, expected_interval))
            break
        candidates.extend(added)

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("beat_this_candidate_report", {
            "status": "CANDIDATES_BUILT",
            "candidate_count": len(added),
            "raw_candidate_count": len(beat_this_candidates),
            "boosted_candidate_count": boosted,
            "fallback": "BeatNet/Librosa retained as fallback candidates",
        })
        return NodeStatus.SUCCESS

    def _normalize_downbeats(self, raw, window: dict) -> list[dict]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            raw = [raw]
        out = []
        for item in raw or []:
            if not isinstance(item, dict):
                item = {"time": item}
            try:
                time_sec = float(item.get("time", item.get("start_time")))
            except (TypeError, ValueError):
                continue
            if not self._inside_window(time_sec, window):
                continue
            try:
                confidence = float(item.get("confidence", 0.82))
            except (TypeError, ValueError):
                confidence = 0.82
            out.append({
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "kind": "downbeat",
            })
        return out

    def _normalize_beats(self, raw, window: dict) -> list[dict]:
        if raw is None:
            return []
        arr = np.asarray(raw, dtype=object)
        if arr.size == 0:
            return []
        if arr.ndim == 1:
            rows = [[item, None] for item in arr.tolist()]
        else:
            rows = arr.tolist()
        out = []
        for row in rows:
            if isinstance(row, dict):
                time_raw = row.get("time", row.get("start_time"))
                label = row.get("beat", row.get("label", row.get("beat_num")))
                confidence_raw = row.get("confidence", 0.72)
            else:
                if not isinstance(row, (list, tuple)) or not row:
                    continue
                time_raw = row[0]
                label = row[1] if len(row) > 1 else None
                confidence_raw = row[2] if len(row) > 2 else 0.72
            try:
                time_sec = float(time_raw)
            except (TypeError, ValueError):
                continue
            if not self._inside_window(time_sec, window):
                continue
            if str(label) not in {"1", "1.0", "downbeat", "Downbeat"}:
                continue
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = 0.72
            out.append({
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "kind": "downbeat",
            })
        return out

    def _normalize_candidates(self, raw, window: dict) -> list[dict]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            raw = [raw]
        out = []
        for item in raw or []:
            if not isinstance(item, dict):
                item = {"time": item}
            kind = str(item.get("kind", item.get("candidate_type", "downbeat"))).lower()
            if kind not in {"downbeat", "bar_start", "bar-start"}:
                continue
            try:
                time_sec = float(item.get("time", item.get("start_time")))
            except (TypeError, ValueError):
                continue
            if not self._inside_window(time_sec, window):
                continue
            try:
                confidence = float(item.get("confidence", 0.78))
            except (TypeError, ValueError):
                confidence = 0.78
            out.append({
                "time": round(time_sec, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "kind": kind,
            })
        return out

    def _dedupe_candidates(self, candidates: list[dict]) -> list[dict]:
        out = []
        for item in sorted(candidates, key=lambda row: (-row["confidence"], row["time"])):
            if all(abs(item["time"] - existing["time"]) > self.coincidence_tolerance_sec for existing in out):
                out.append(item)
        return sorted(out, key=lambda row: row["time"])

    def _boost_existing_candidates(self, candidates: list[dict], beat_this_candidates: list[dict]) -> int:
        boosted = 0
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            nearest = self._nearest_candidate(float(candidate.get("time", 0.0)), beat_this_candidates)
            if nearest is None:
                continue
            confidence = float(candidate.get("confidence", 0.0))
            candidate["confidence"] = round(float(np.clip(confidence + 0.16, 0.0, 1.0)), 6)
            evidence = list(candidate.get("evidence_sources", []) or [])
            if "beat_this_downbeat_support" not in evidence:
                evidence.append("beat_this_downbeat_support")
            candidate["evidence_sources"] = evidence
            candidate["beat_this_support_time"] = nearest["time"]
            boosted += 1
        return boosted

    def _nearest_candidate(self, time_sec: float, beat_this_candidates: list[dict]) -> dict | None:
        if not beat_this_candidates:
            return None
        nearest = min(beat_this_candidates, key=lambda item: abs(item["time"] - time_sec))
        return nearest if abs(nearest["time"] - time_sec) <= self.coincidence_tolerance_sec else None

    def _bar_start_candidate(self, item: dict, window: dict, expected_interval: float | None) -> dict:
        confidence = float(item.get("confidence", 0.78))
        evidence = ["beat_this_downbeat"]
        offset = float(item["time"]) - float(window.get("start_time", 0.0))
        if expected_interval and abs(offset - expected_interval) <= max(0.12, expected_interval * 0.18):
            confidence += 0.06
            evidence.append("expected_bar_interval")
        return {
            "time": item["time"],
            "confidence": round(float(np.clip(confidence, 0.0, 0.92)), 6),
            "evidence_sources": evidence,
            "source_node": self.name,
            "model": "Beat This!",
        }

    def _has_candidate_near(self, candidates: list[dict], time_sec: float) -> bool:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                existing_time = float(candidate.get("time", candidate.get("bar_start_candidate_time")))
            except (TypeError, ValueError):
                continue
            if abs(existing_time - float(time_sec)) <= self.coincidence_tolerance_sec:
                return True
        return False

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        if not window:
            return False
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end

    def _expected_interval(self, committed: list[float]) -> float | None:
        if len(committed) < 2:
            return None
        interval = committed[-1] - committed[-2]
        return float(interval) if interval > 0 else None


class BarGridContinuityRepairNode(BaseNode):
    """Bar-level analog of Stage 3's per-beat continuity/oscillation repair.

    v2's final grid is only as good as `committed_bar_starts`:
    `MeterAwareBeatGridNode` just geometrically subdivides whatever bar list it
    is given. This node repairs that list itself -- before the fine-grained
    beat grid is derived -- by inserting bars skipped by a missed detection,
    dropping near-duplicate bar starts, and damping an isolated bar-duration
    oscillation (one very short bar immediately followed by one very long bar,
    or vice versa) that a real tempo ramp would not produce.
    """

    required_keys = ["committed_bar_starts"]
    output_keys = ["committed_bar_starts", "bar_grid_repair_report"]

    def __init__(
        self,
        insert_gap_ratio: float = 1.55,
        duplicate_gap_ratio: float = 0.42,
        oscillation_ratio: float = 0.30,
        pair_sum_tolerance: float = 0.45,
        max_insertions_per_gap: int = 3,
    ):
        super().__init__("BarGridContinuityRepairNode")
        self.insert_gap_ratio = insert_gap_ratio
        self.duplicate_gap_ratio = duplicate_gap_ratio
        self.oscillation_ratio = oscillation_ratio
        self.pair_sum_tolerance = pair_sum_tolerance
        self.max_insertions_per_gap = max_insertions_per_gap

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        bars = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        if len(bars) < 4:
            blackboard.set_val("bar_grid_repair_report", {
                "status": "SKIPPED_NOT_ENOUGH_BARS",
                "bar_count_before": len(bars),
                "bar_count_after": len(bars),
            })
            return NodeStatus.SUCCESS

        intervals = np.diff(bars)
        valid = intervals[np.isfinite(intervals) & (intervals > 0.05)]
        if len(valid) == 0:
            blackboard.set_val("bar_grid_repair_report", {
                "status": "SKIPPED_NO_VALID_INTERVAL",
                "bar_count_before": len(bars),
                "bar_count_after": len(bars),
            })
            return NodeStatus.SUCCESS

        median_interval = float(np.median(valid))

        # Pass A: drop near-duplicate bar starts, insert bars for skipped gaps.
        repaired = [bars[0]]
        inserted_count = 0
        removed_count = 0
        for t in bars[1:]:
            prev = repaired[-1]
            gap = float(t - prev)
            if gap <= median_interval * self.duplicate_gap_ratio:
                removed_count += 1
                continue
            if gap >= median_interval * self.insert_gap_ratio:
                steps = int(round(gap / median_interval))
                insertions = max(0, steps - 1)
                if 0 < insertions <= self.max_insertions_per_gap:
                    for step in range(1, insertions + 1):
                        repaired.append(prev + median_interval * step)
                        inserted_count += 1
            repaired.append(t)

        # Pass B: damp an isolated short/long bar-duration oscillation, mirroring
        # Stage 3's TempoOscillationDampingNode but at bar granularity.
        oscillation_damped = 0
        for i in range(1, len(repaired) - 1):
            left = repaired[i] - repaired[i - 1]
            right = repaired[i + 1] - repaired[i]
            if left <= 0.05 or right <= 0.05:
                continue
            if not self._is_oscillation_pair(left, right, median_interval):
                continue
            proposed = (repaired[i - 1] + repaired[i + 1]) / 2.0
            if abs(proposed - repaired[i]) < 0.02:
                continue
            repaired[i] = proposed
            oscillation_damped += 1

        repaired_arr = sorted(round(float(t), 6) for t in repaired)
        status = "PASS"
        if inserted_count or removed_count or oscillation_damped:
            status = "REPAIRED"
            blackboard.set_val("committed_bar_starts", repaired_arr)

        blackboard.set_val("bar_grid_repair_report", {
            "status": status,
            "bar_count_before": len(bars),
            "bar_count_after": len(repaired_arr),
            "median_bar_interval_sec": round(median_interval, 6),
            "inserted_bar_count": inserted_count,
            "removed_bar_count": removed_count,
            "oscillation_damped_count": oscillation_damped,
        })
        if status == "REPAIRED":
            print(
                f"[{self.name}] 修復小節網格：補 {inserted_count} 個小節、"
                f"移除 {removed_count} 個近重複小節、抑制 {oscillation_damped} 處小節級節奏震盪。"
            )
        return NodeStatus.SUCCESS

    def _is_oscillation_pair(self, left: float, right: float, median_interval: float) -> bool:
        short_limit = median_interval * (1.0 - self.oscillation_ratio)
        long_limit = median_interval * (1.0 + self.oscillation_ratio)
        is_fast_slow = left <= short_limit and right >= long_limit
        is_slow_fast = left >= long_limit and right <= short_limit
        if not (is_fast_slow or is_slow_fast):
            return False
        pair_sum = left + right
        expected_sum = 2.0 * median_interval
        return abs(pair_sum - expected_sum) / (expected_sum + 1e-6) <= self.pair_sum_tolerance


class BarStartV2SyncopationClassificationNode(BaseNode):
    """Classifies onsets against the v2 bar-grid so downstream snap logic does
    not chase syncopation/anticipation instead of the true beat.

    Module 3 v1's `SyncopationClassificationNode` needs a `subdivision_grid`
    that v2 never produces (`MeterAwareBeatGridNode` only emits a per-beat
    `click_grid`). This node derives a lightweight half-beat subdivision grid
    from `click_grid` itself, then reuses v1's classification thresholds.
    Exclusion zones are merged additively with whatever is already on the
    blackboard, the same accumulation pattern `DrumFillDetectionNode` uses --
    this covers the more general "any instrument played off the grid" case,
    where the drum-fill node only covers dense kick/snare bursts.
    """

    required_keys = ["click_grid"]
    optional_keys = ["onset_events", "kick_anchors", "snare_anchors", "bass_anchors", "snap_exclusion_zones"]
    output_keys = ["syncopation_events", "snap_exclusion_zones", "subdivision_grid", "syncopation_report"]

    def __init__(self):
        super().__init__("BarStartV2SyncopationClassificationNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        click_grid = list(blackboard.get_val("click_grid", []) or [])
        if len(click_grid) < 2:
            blackboard.set_val("syncopation_report", {"status": "SKIPPED_NOT_ENOUGH_CLICK_GRID", "event_count": 0})
            return NodeStatus.SUCCESS

        ordered = sorted(click_grid, key=lambda item: float(item.get("time", 0.0)))
        subdivision_grid = self._derive_subdivision_grid(ordered)
        blackboard.set_val("subdivision_grid", subdivision_grid)

        onsets = self._collect_onset_times(blackboard)
        if not onsets:
            blackboard.set_val("syncopation_report", {"status": "NO_ONSET_EVENTS", "event_count": 0})
            return NodeStatus.SUCCESS

        events = []
        new_exclusions = []
        for t in onsets:
            nearest_click = self._nearest(ordered, t)
            nearest_sub = self._nearest(subdivision_grid, t)
            if nearest_click is None or nearest_sub is None:
                continue
            offset_click_ms = (t - float(nearest_click["time"])) * 1000.0
            offset_sub_ms = (t - float(nearest_sub["time"])) * 1000.0
            classification = "phrase_onset"
            snap_click = False
            if abs(offset_click_ms) <= 35.0:
                classification = "true_beat"
                snap_click = True
            elif -250.0 <= offset_click_ms <= -60.0 and not nearest_sub.get("click"):
                classification = "anticipation"
                new_exclusions.append({
                    "start_time": round(t - 0.04, 6),
                    "end_time": round(t + 0.04, 6),
                    "reason": classification,
                })
            elif not nearest_sub.get("click") and abs(offset_sub_ms) <= 80.0:
                classification = "syncopation"
                new_exclusions.append({
                    "start_time": round(t - 0.04, 6),
                    "end_time": round(t + 0.04, 6),
                    "reason": classification,
                })

            events.append({
                "time": round(t, 6),
                "nearest_click_beat": nearest_click.get("label"),
                "offset_to_click_ms": round(offset_click_ms, 3),
                "offset_to_subdivision_ms": round(offset_sub_ms, 3),
                "classification": classification,
                "snap_click": snap_click,
            })

        combined_exclusions = list(blackboard.get_val("snap_exclusion_zones", []) or []) + new_exclusions
        blackboard.set_val("syncopation_events", events)
        blackboard.set_val("snap_exclusion_zones", combined_exclusions)
        blackboard.set_val("syncopation_report", {
            "status": "CLASSIFIED",
            "event_count": len(events),
            "syncopation_count": sum(1 for e in events if e["classification"] == "syncopation"),
            "anticipation_count": sum(1 for e in events if e["classification"] == "anticipation"),
            "new_exclusion_count": len(new_exclusions),
        })
        return NodeStatus.SUCCESS

    def _derive_subdivision_grid(self, ordered_click_grid: list[dict]) -> list[dict]:
        subdivisions = [
            {"time": float(item["time"]), "label": item.get("label"), "click": True}
            for item in ordered_click_grid
        ]
        for a, b in zip(ordered_click_grid, ordered_click_grid[1:]):
            mid = (float(a["time"]) + float(b["time"])) / 2.0
            subdivisions.append({"time": mid, "label": "and", "click": False})
        return sorted(subdivisions, key=lambda item: item["time"])

    def _collect_onset_times(self, blackboard: Blackboard) -> list[float]:
        raw = list(blackboard.get_val("onset_events", []) or [])
        times = []
        for item in raw:
            if isinstance(item, dict):
                item = item.get("time")
            try:
                times.append(float(item))
            except (TypeError, ValueError):
                continue
        if not times:
            for key in ("kick_anchors", "snare_anchors", "bass_anchors"):
                for item in blackboard.get_val(key, []) or []:
                    if isinstance(item, dict):
                        item = item.get("time")
                    try:
                        times.append(float(item))
                    except (TypeError, ValueError):
                        continue
        return sorted(set(round(t, 6) for t in times if t >= 0.0))

    def _nearest(self, grid: list[dict], t: float) -> dict | None:
        if not grid:
            return None
        return min(grid, key=lambda item: abs(float(item.get("time", 0.0)) - t))


class MeterAwareBeatGridNode(BaseNode):
    """Generates final click beats from committed bar starts and meter profile."""

    required_keys = ["committed_bar_starts", "meter_profile"]
    output_keys = ["beats", "refined_beats", "click_grid", "measure_map", "meter_changes", "bar_length_report"]

    def __init__(self):
        super().__init__("MeterAwareBeatGridNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        bar_starts = self._normalize_times(blackboard.get_val("committed_bar_starts"))
        if len(bar_starts) < 2:
            print(f"[{self.name}] need at least two committed bar starts")
            return NodeStatus.FAILURE

        profile = dict(blackboard.get_val("meter_profile", {}) or {})
        beats_per_bar = int(profile.get("beats_per_bar", 4))
        beat_unit = int(profile.get("beat_unit", 4))
        base_meter = str(profile.get("base_meter", f"{beats_per_bar}/{beat_unit}"))

        beat_rows = []
        click_grid = []
        measure_map = []
        durations = []

        for idx in range(len(bar_starts) - 1):
            start = float(bar_starts[idx])
            end = float(bar_starts[idx + 1])
            if end <= start:
                continue
            duration = end - start
            durations.append(duration)
            step = duration / float(beats_per_bar)
            measure_num = idx + 1
            measure_beats = []
            for beat_idx in range(beats_per_bar):
                t = start + beat_idx * step
                label = beat_idx + 1
                beat_rows.append([round(t, 6), label])
                grid_item = {
                    "time": round(t, 6),
                    "label": str(label),
                    "beat": label,
                    "measure": measure_num,
                    "click": True,
                    "source": "meter_aware_bar_division",
                }
                click_grid.append(grid_item)
                measure_beats.append(grid_item)
            measure_map.append({
                "measure": measure_num,
                "start_time": round(start, 6),
                "end_time": round(end, 6),
                "beat_count": beats_per_bar,
                "meter": base_meter,
                "source": "committed_bar_starts",
                "beats": measure_beats,
            })

        if not beat_rows:
            return NodeStatus.FAILURE

        beats = np.asarray(beat_rows, dtype=float)
        median_duration = float(np.median(durations)) if durations else 0.0
        variation = self._duration_variation(durations)
        report = {
            "bar_count": len(measure_map),
            "beats_per_bar": beats_per_bar,
            "meter": base_meter,
            "median_bar_duration_sec": round(median_duration, 6),
            "bar_duration_variation": round(variation, 6),
            "strategy": "meter_aware_bar_division",
        }

        blackboard.set_val("beats", beats)
        blackboard.set_val("refined_beats", beats)
        blackboard.set_val("click_grid", click_grid)
        blackboard.set_val("measure_map", measure_map)
        blackboard.set_val("meter_changes", [{"measure": 1, "time": bar_starts[0], "meter": base_meter}])
        blackboard.set_val("bar_length_report", report)
        return NodeStatus.SUCCESS

    def _normalize_times(self, raw) -> list[float]:
        return ManualCommittedBarStartsSeedNode()._normalize_times(raw)

    def _duration_variation(self, durations: Iterable[float]) -> float:
        values = [float(v) for v in durations if float(v) > 0]
        if len(values) < 2:
            return 0.0
        mean = float(np.mean(values))
        return 0.0 if mean <= 0 else float(np.std(values) / mean)


class BarStartV2QualityScoreNode(BaseNode):
    """Quantified 0-100 quality score for the v2 grid, as an auxiliary metric
    next to the pass/fail `promotion_gate`.

    Reuses Stage 3's `_score_beat_grid_quality` on the final beat matrix, then
    layers v2-specific penalties on top of it: unresolved bar probe spans, a
    structurally repaired bar grid, and a downbeat rotation triggered by the
    low-frequency verifier. This does not replace `evaluate_barstart_v2_promotion_gate`'s
    blocker logic -- it gives reference/manual reviewers an objective number to
    compare runs against while they decide pass/fail.
    """

    required_keys = ["beats"]
    optional_keys = [
        "refined_beats",
        "phase_realignment_report",
        "downbeat_fix_report",
        "bar_grid_repair_report",
        "unresolved_bar_spans",
    ]
    output_keys = ["barstart_v2_quality_score"]

    def __init__(self):
        super().__init__("BarStartV2QualityScoreNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        base = _score_beat_grid_quality(beats)
        score = float(base["score"])
        warnings = list(base.get("warnings", []))

        unresolved = list(blackboard.get_val("unresolved_bar_spans", []) or [])
        if unresolved:
            score -= min(15.0, len(unresolved) * 5.0)
            warnings.append(f"unresolved_bar_spans={len(unresolved)}")

        repair = blackboard.get_val("bar_grid_repair_report", {}) or {}
        if repair.get("status") == "REPAIRED":
            repaired_count = (
                int(repair.get("inserted_bar_count", 0) or 0)
                + int(repair.get("removed_bar_count", 0) or 0)
                + int(repair.get("oscillation_damped_count", 0) or 0)
            )
            if repaired_count:
                score -= min(8.0, repaired_count * 2.0)
                warnings.append(f"bar_grid_repairs={repaired_count}")

        downbeat_fix = blackboard.get_val("downbeat_fix_report", {}) or {}
        if downbeat_fix.get("status") == "ROTATED":
            score -= 3.0
            warnings.append("downbeat_rotated_by_low_freq_verifier")

        result = {
            "score": round(float(np.clip(score, 0.0, 100.0)), 2),
            "base_score": base["score"],
            "tempo_stability": base["tempo_stability"],
            "downbeat_consistency": base["downbeat_consistency"],
            "warnings": warnings,
        }
        blackboard.set_val("barstart_v2_quality_score", result)
        return NodeStatus.SUCCESS


class Module3BarStartV2SummaryNode(BaseNode):
    """Writes a compact v2 diagnostic report into Module 3 outputs."""

    optional_keys = [
        "module3_outputs",
        "meter_profile",
        "bar_length_report",
        "bar_start_seed_report",
        "committed_bar_starts",
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
        "reliable_bar_anchors",
        "reliable_anchor_report",
        "provisional_bar_starts",
        "no_drum_phase_report",
        "lookahead_bar_candidates",
        "lookahead_anchor_report",
        "intervening_bar_count_candidates",
        "selected_intervening_bar_count",
        "bidirectional_alignment_report",
        "transition_confidence_report",
        "reference_acceptance",
        "manual_acceptance",
        "downbeat_fix_report",
        "bar_grid_repair_report",
        "barstart_v2_quality_score",
        "full_song_loop_report",
    ]
    output_keys = ["module3_outputs", "barstart_v2_report"]

    def __init__(self):
        super().__init__("Module3BarStartV2SummaryNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        outputs = dict(blackboard.get_val("module3_outputs", {}) or {})
        report = {
            "status": "EXPERIMENTAL_PASS_129",
            "meter_profile": blackboard.get_val("meter_profile", {}),
            "bar_length_report": blackboard.get_val("bar_length_report", {}),
            "bar_start_seed_report": blackboard.get_val("bar_start_seed_report", {}),
            "committed_bar_starts": blackboard.get_val("committed_bar_starts", []),
            "active_bar_probe_window": blackboard.get_val("active_bar_probe_window", {}),
            "bar_probe_windows": blackboard.get_val("bar_probe_windows", []),
            "bar_probe_policy": blackboard.get_val("bar_probe_policy", {}),
            "local_model_registry": blackboard.get_val("local_model_registry", {}),
            "model_availability_report": blackboard.get_val("model_availability_report", {}),
            "model_license_report": blackboard.get_val("model_license_report", {}),
            "drum_bar_evidence_report": blackboard.get_val("drum_bar_evidence_report", {}),
            "drum_bass_evidence_report": blackboard.get_val("drum_bass_evidence_report", {}),
            "chord_track_pk": blackboard.get_val("chord_track_pk", {}),
            "harmonic_anchor_evidence_report": blackboard.get_val("harmonic_anchor_evidence_report", {}),
            "melody_track_pk": blackboard.get_val("melody_track_pk", {}),
            "phrase_anchor_evidence_report": blackboard.get_val("phrase_anchor_evidence_report", {}),
            "beat_this_candidate_report": blackboard.get_val("beat_this_candidate_report", {}),
            "reliable_bar_anchors": blackboard.get_val("reliable_bar_anchors", []),
            "reliable_anchor_report": blackboard.get_val("reliable_anchor_report", {}),
            "provisional_bar_starts": blackboard.get_val("provisional_bar_starts", []),
            "no_drum_phase_report": blackboard.get_val("no_drum_phase_report", {}),
            "lookahead_bar_candidates": blackboard.get_val("lookahead_bar_candidates", []),
            "lookahead_anchor_report": blackboard.get_val("lookahead_anchor_report", {}),
            "intervening_bar_count_candidates": blackboard.get_val("intervening_bar_count_candidates", []),
            "selected_intervening_bar_count": blackboard.get_val("selected_intervening_bar_count", {}),
            "bidirectional_alignment_report": blackboard.get_val("bidirectional_alignment_report", {}),
            "transition_confidence_report": blackboard.get_val("transition_confidence_report", {}),
            "bar_start_decision_report": blackboard.get_val("bar_start_decision_report", {}),
            "unresolved_bar_spans": blackboard.get_val("unresolved_bar_spans", []),
            "full_song_loop_report": blackboard.get_val("full_song_loop_report", {}),
            "bar_grid_repair_report": blackboard.get_val("bar_grid_repair_report", {}),
            "quality_score": blackboard.get_val("barstart_v2_quality_score", {}),
            "downbeat_fix_report": blackboard.get_val("downbeat_fix_report", {}),
            "promotion_gate": evaluate_barstart_v2_promotion_gate(
                reference_acceptance=blackboard.get_val("reference_acceptance", {}),
                manual_acceptance=blackboard.get_val("manual_acceptance", {}),
                unresolved_bar_spans=blackboard.get_val("unresolved_bar_spans", []),
            ),
        }
        outputs["barstart_v2_report"] = report
        outputs["barstart_v2_status"] = report["status"]
        blackboard.set_val("barstart_v2_report", report)
        blackboard.set_val("module3_outputs", outputs)
        return NodeStatus.SUCCESS


def evaluate_barstart_v2_promotion_gate(
    *,
    reference_acceptance=None,
    manual_acceptance=None,
    unresolved_bar_spans=None,
):
    """Return an explicit promotion decision; never auto-replaces Module 3."""
    reference_ok = str((reference_acceptance or {}).get("status", "")).lower() == "pass"
    manual_ok = str((manual_acceptance or {}).get("status", "")).lower() == "pass"
    unresolved_count = len(unresolved_bar_spans or [])
    blockers = []
    if not reference_ok:
        blockers.append("REFERENCE_ACCEPTANCE_REQUIRED")
    if not manual_ok:
        blockers.append("MANUAL_ACCEPTANCE_REQUIRED")
    if unresolved_count:
        blockers.append("UNRESOLVED_BAR_SPANS_PRESENT")
    return {
        "promotable": not blockers,
        "status": "PROMOTE_READY" if not blockers else "EXPERIMENTAL_ONLY",
        "blockers": blockers,
        "reference_acceptance": reference_acceptance or {},
        "manual_acceptance": manual_acceptance or {},
        "unresolved_bar_span_count": unresolved_count,
    }


def evaluate_barstart_v2_auto_promotion_gate(
    *,
    unresolved_bar_spans=None,
    v2_score=None,
    original_score=None,
    min_margin=0.0,
):
    """Automatic, score-only promotion gate for the main pipeline.

    Unlike evaluate_barstart_v2_promotion_gate(), this never requires a human
    to record reference/manual acceptance -- the isolated 節奏定位 tab needs
    that strict human-in-the-loop gate before Module 3's own click grid is
    ever replaced, but the main one-click pipeline has no UI path to record
    acceptance at all, so requiring it there would mean v2 could never be
    adopted in practice. This gate promotes v2 only when it has no unresolved
    bar spans and its quantified quality score is strictly higher than v1's
    on the same metric -- both sides of the same conservative bar this
    module already applies elsewhere.
    """
    unresolved_count = len(unresolved_bar_spans or [])
    blockers = []
    if unresolved_count:
        blockers.append("UNRESOLVED_BAR_SPANS_PRESENT")
    if v2_score is None or original_score is None:
        blockers.append("QUALITY_SCORES_UNAVAILABLE")
    elif v2_score <= original_score + min_margin:
        blockers.append("V2_SCORE_NOT_HIGHER")
    return {
        "promotable": not blockers,
        "status": "AUTO_PROMOTE_READY" if not blockers else "AUTO_PROMOTION_BLOCKED",
        "blockers": blockers,
        "unresolved_bar_span_count": unresolved_count,
    }


def build_module3_barstart_v2_export_tree() -> SequenceNode:
    # Pass 128: dropped the per-beat acoustic snapping stage (Pass 118
    # OnsetPhaseRealignmentNode, plus the two exclusion-zone detectors that
    # only existed to feed it -- Pass 119 DrumFillDetectionNode and Pass 123
    # BarStartV2SyncopationClassificationNode). User listening feedback: v2's
    # job is to get each bar's first beat right and evenly subdivide the rest
    # -- per-beat onset chasing can snap onto a nearby syncopated/decorative
    # hit instead of the true beat, which reads as audibly worse than a plain
    # even grid. Onset/fill detection remain available as node classes (and
    # still run on the Stage 3 main line) if this needs revisiting.
    return SequenceNode("Module3BarStartV2ExportRoot", [
        # Pass 120: Böck et al. (2016 madmom) 40-120Hz low-frequency downbeat
        # check. This only re-labels which existing (evenly-spaced) grid
        # point is beat 1 -- it never moves a beat's time -- so it stays: it
        # is exactly "confirm the bar's first beat", not per-beat tuning.
        KickBassDownbeatVerifierNode(),
        # Pass 122: quantified score for the finalized grid, an auxiliary metric
        # next to the pass/fail promotion_gate.
        BarStartV2QualityScoreNode(),
        ClickSynthesisNode(),
        Module3BackingWithClickNode(),
        Module3BarStartV2SummaryNode(),
        Module3OutputSummaryNode(),
    ])


def build_module3_barstart_v2_probe_tick_tree() -> SequenceNode:
    """One probe-and-commit tick: search a single rolling window for the next
    bar start and either commit it or record the window unresolved.

    `FullSongBarStartLoopNode` (Pass 126) re-runs this tick repeatedly to walk
    an entire song -- every node here was built and unit-tested (Pass 105-117)
    assuming exactly that outer loop would exist, but until Pass 126 nothing
    ever re-invoked the tick, so a single pipeline run only ever committed one
    bar past the seed.
    """
    return SequenceNode("BarStartV2ProbeTick", [
        RollingProbeWindowNode(),
        LocalModelRegistryNode(),
        DrumEvidenceBarSearchNode(),
        DrumBassEvidenceBarSearchNode(),
        ChordTrackPKNode(),
        MelodyTrackPKNode(),
        BeatThisCandidateAdapterNode(),
        ReliableBarAnchorNode(),
        # Pass 129: populates lookahead_drum_events from real kick/snare
        # anchors so LookaheadDrumAnchorSearchNode has actual future evidence
        # to search, instead of always finding none in production.
        LookaheadDrumEventScanNode(),
        LookaheadDrumAnchorSearchNode(),
        NoDrumPhaseCarryNode(),
        InterveningBarCountEstimatorNode(),
        BidirectionalBarAlignmentNode(),
        TransitionConfidenceNode(),
        BarStartCandidateCommitNode(),
    ])


class FullSongBarStartLoopNode(BaseNode):
    """Drives the single-bar probe/commit tick across an entire song.

    Stop conditions, checked once per tick:
    - `reached_audio_duration`: the last committed bar reached the known
      audio length (`audio_duration_sec`, or derived from `y`/`sr`).
    - `stalled_no_recovery`: no bar committed for `stall_limit` consecutive
      ticks *and* `NoDrumPhaseCarryNode` had nothing in `provisional_bar_starts`
      to fall back on either -- a genuine dead end (e.g. silence).
    - `max_iterations_reached`: hard safety cap so a bug elsewhere can never
      hang this node forever.

    Stall recovery: when a tick fails to commit for `stall_limit` tries in a
    row (e.g. a long ambient stretch with no drum/bass/chord/melody evidence
    at all), the loop merges in whatever `NoDrumPhaseCarryNode` already
    computed for that tick in `provisional_bar_starts` (Pass 121-125
    strengthened that fallback) instead of spinning until `max_iterations`.
    """

    optional_keys = [
        "committed_bar_starts",
        "audio_duration_sec",
        "y",
        "sr",
        "provisional_bar_starts",
    ]
    output_keys = ["committed_bar_starts", "full_song_loop_report"]

    def __init__(self, max_iterations: int = 500, stall_limit: int = 3):
        super().__init__("FullSongBarStartLoopNode")
        self.max_iterations = int(max_iterations)
        self.stall_limit = int(stall_limit)
        self._tick = build_module3_barstart_v2_probe_tick_tree()
        self.children = [self._tick]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        duration_cap = NoDrumPhaseCarryNode()._audio_duration_cap(blackboard)
        stall_count = 0
        stall_recoveries = 0
        iterations = 0
        stop_reason = "max_iterations_reached"

        while iterations < self.max_iterations:
            before = self._normalize(blackboard.get_val("committed_bar_starts"))
            if duration_cap is not None and before and before[-1] >= duration_cap - 0.08:
                # Checked *before* spending a tick: once the last committed bar
                # already reaches the known audio length there is no more song
                # left to probe. Running the tick anyway would just record a
                # spurious "unresolved" span for a window past the end of the
                # track, which would permanently block promotion_gate from
                # ever seeing zero unresolved spans.
                stop_reason = "reached_audio_duration"
                break

            iterations += 1
            self._tick.run(blackboard, parent=self.name)
            after = self._normalize(blackboard.get_val("committed_bar_starts"))

            if len(after) > len(before):
                stall_count = 0
                continue

            stall_count += 1
            if stall_count < self.stall_limit:
                continue

            provisional = self._normalize(blackboard.get_val("provisional_bar_starts"))
            if provisional:
                merged = sorted(set(after) | set(provisional))
                blackboard.set_val("committed_bar_starts", merged)
                stall_recoveries += 1
                stall_count = 0
                continue

            stop_reason = "stalled_no_recovery"
            break

        final = self._normalize(blackboard.get_val("committed_bar_starts"))
        blackboard.set_val("full_song_loop_report", {
            "status": "COMPLETED" if stop_reason != "max_iterations_reached" else "MAX_ITERATIONS_REACHED",
            "iterations": iterations,
            "committed_bar_count": len(final),
            "stall_recoveries": stall_recoveries,
            "stop_reason": stop_reason,
            "unresolved_span_count": len(blackboard.get_val("unresolved_bar_spans", []) or []),
        })
        return NodeStatus.SUCCESS

    def _normalize(self, raw) -> list[float]:
        return ManualCommittedBarStartsSeedNode()._normalize_times(raw)


def build_module3_barstart_v2_pipeline_tree() -> SequenceNode:
    return SequenceNode("Module3BarStartClickRoot", [
        build_input_acquisition_tree(),
        build_audio_quality_tree(),
        OptionalStemSeparationNode(),
        MeterProfileNode(),
        ManualCommittedBarStartsSeedNode(),
        FullSongBarStartLoopNode(),
        BarGridContinuityRepairNode(),
        MeterAwareBeatGridNode(),
        build_module3_barstart_v2_export_tree(),
    ])
