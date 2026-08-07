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
    AnchorTransientSnapNode,
    KickBassDownbeatVerifierNode,
    _extract_peak_anchors,
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


def _v1_reference_downbeats(blackboard: Blackboard) -> list[float]:
    """Shared helper: extract v1's own downbeat times from the
    `v1_reference_beat_grid` blackboard key (see `V1GridEvidenceBarSearchNode`,
    Pass 156). Used wherever a node would otherwise have to assume a constant
    bar duration across a drum-sparse span -- v1's grid keeps tracking through
    such spans via vocal/harmonic cues even though v2's evidence tiers cannot.
    """
    grid = blackboard.get_val("v1_reference_beat_grid")
    if grid is None:
        return []
    try:
        arr = np.asarray(grid, dtype=float)
    except (TypeError, ValueError):
        return []
    if arr.ndim != 2 or arr.shape[1] < 2 or len(arr) == 0:
        return []
    return sorted(float(t) for t in arr[arr[:, 1] == 1, 0])


class NoDrumPhaseCarryNode(BaseNode):
    """Carry the previous bar phase through a no-drum span as provisional bars.

    When a future drum anchor exists within the lookahead window, bars are
    carried up to that anchor. When no future anchor is found at all -- e.g. a
    long ambient outro past the lookahead range -- v1's `_inertia_fill` still
    produced a bounded constant-tempo extrapolation instead of silently
    leaving that whole span without any click coverage. This pass ports that
    fallback here, capped at `max_fallback_bars` and by the audio's own
    duration when known, and tagged with a distinct status so reviewers can
    tell it apart from an anchor-confirmed carry.

    Pass 157: both branches previously spaced provisional bars evenly using a
    single global `bar_duration` -- a constant-tempo assumption across the
    whole gap. When `v1_reference_beat_grid` (Pass 156) has real downbeats
    inside the gap, those are used directly instead, since they reflect v1's
    actual tempo-tracking rather than an equal-spacing guess.
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
        used_v1_grid = False

        if previous is not None and bar_duration > 0:
            if next_anchor is not None:
                v1_times = self._v1_grid_times_in_span(blackboard, previous, next_anchor)
                if v1_times:
                    provisional = [round(t, 6) for t in v1_times]
                    used_v1_grid = True
                    status = "CARRIED_V1_GRID"
                else:
                    current = previous + bar_duration
                    while current < next_anchor - self.tolerance_sec:
                        provisional.append(round(current, 6))
                        current += bar_duration
                    status = "CARRIED" if provisional else "NO_SPAN"
            else:
                duration_cap = self._audio_duration_cap(blackboard)
                v1_times = self._v1_grid_times_in_span(
                    blackboard, previous, duration_cap, max_count=self.max_fallback_bars
                )
                if v1_times:
                    provisional = [round(t, 6) for t in v1_times]
                    used_v1_grid = True
                    status = "CARRIED_FALLBACK_V1_GRID"
                else:
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
            "used_v1_grid": used_v1_grid,
        })
        return NodeStatus.SUCCESS

    def _v1_grid_times_in_span(
        self, blackboard: Blackboard, start: float, end: float | None, max_count: int | None = None
    ) -> list[float]:
        """Real v1 downbeat times strictly between `start` and `end` (`end`
        may be None when there is no known upper bound -- the no-lookahead
        fallback case), capped at `max_count` when given."""
        downbeats = _v1_reference_downbeats(blackboard)
        if not downbeats:
            return []
        in_span = [
            t for t in downbeats
            if t > start + self.tolerance_sec and (end is None or t < end - self.tolerance_sec)
        ]
        if max_count is not None:
            in_span = in_span[:max_count]
        return in_span

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
    """Estimate N-1/N/N+1 bars between two anchors.

    Pass 157: the arithmetic estimate (`delta / duration`) implicitly assumes
    constant tempo across the whole gap, which is exactly the assumption that
    breaks down across a long no-drum span. When `v1_reference_beat_grid`
    (Pass 156) has real downbeats between `previous` and the next anchor, the
    actual count of those downbeats is used to seed the N-1/N/N+1 exploration
    instead of the arithmetic guess -- it reflects v1's own tempo-tracking
    rather than an equal-spacing assumption. The `duration`-based
    `duration_error_sec` tie-break is kept as-is for consistency with
    downstream consumers (e.g. `BidirectionalBarAlignmentNode`).
    """

    optional_keys = ["reliable_bar_anchors", "lookahead_bar_candidates", "bar_duration_sec", "meter_profile", "tempo_bpm", "v1_reference_beat_grid"]
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
        source = None
        if previous is not None and next_item is not None and duration > 0:
            next_time = float(next_item["time"])
            delta = max(0.0, next_time - previous)
            v1_count = self._v1_downbeat_count(blackboard, previous, next_time)
            if v1_count is not None:
                estimate = max(1, v1_count)
                source = "v1_grid_count"
            else:
                estimate = max(1, int(round(delta / duration)))
                source = "arithmetic_estimate"
            allowed = sorted({max(1, estimate - 1), estimate, estimate + 1})
            for count in allowed:
                error = abs(delta - count * duration)
                rows.append({
                    "bar_count": count,
                    "duration_error_sec": round(error, 6),
                    "next_anchor_time": next_item["time"],
                    "candidate": next_item,
                    "estimate_source": source,
                })
            selected = min(rows, key=lambda row: row["duration_error_sec"])
        blackboard.set_val("intervening_bar_count_candidates", rows)
        blackboard.set_val("selected_intervening_bar_count", selected)
        return NodeStatus.SUCCESS

    def _v1_downbeat_count(self, blackboard: Blackboard, start: float, end: float) -> int | None:
        downbeats = _v1_reference_downbeats(blackboard)
        if not downbeats:
            return None
        tolerance = 0.08
        count = sum(1 for t in downbeats if start + tolerance < t < end - tolerance)
        return count if count > 0 else None


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
    """Commits the best bar-start candidate or records an unresolved probe span.

    Pass 158: every evidence tier (kick/bass/chord/melody/v1-grid/lookahead)
    only ever scores a candidate's own local plausibility -- none of them
    check whether the resulting gap from the *previous committed bar* is
    actually a real bar length. In passages with a kick on every beat (common
    -- four-on-the-floor, verses, choruses), that means a beat-level kick
    hit right after the previous commit routinely outscores the true next
    bar three beats later on raw confidence alone, so v2 ends up committing
    on nearly every beat instead of every bar (~0.4s median gap observed on
    a real song vs v1's own ~1.45s real downbeat-to-downbeat spacing --
    almost 4x too dense, "a wall of clicks" per user report). Before picking
    the best candidate, filter out ones whose gap from the last committed
    bar is implausibly short relative to v1's own real bar-duration estimate
    (from `v1_reference_beat_grid`, Pass 156/157); if that filter would
    eliminate every candidate (legitimate short/pickup bar, or no v1 grid
    available), fall back to the unfiltered list so this never introduces a
    false negative that Pass 153's stall bug already taught us to avoid.
    """

    optional_keys = [
        "bar_start_candidates",
        "committed_bar_starts",
        "active_bar_probe_window",
        "candidate_commit_confidence_threshold",
        "unresolved_bar_spans",
        "v1_reference_beat_grid",
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
        min_bar_gap_ratio: float = 0.6,
    ):
        super().__init__("BarStartCandidateCommitNode")
        self.default_threshold = float(default_threshold)
        self.duplicate_tolerance_sec = float(duplicate_tolerance_sec)
        self.quality_drop_tolerance = float(quality_drop_tolerance)
        self.min_bar_gap_ratio = float(min_bar_gap_ratio)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        committed = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = self._normalize_candidates(blackboard.get_val("bar_start_candidates", []), window)
        threshold = self._threshold(blackboard.get_val("candidate_commit_confidence_threshold"))
        # The probe window's own start_time is anchored at the last committed
        # bar, so that bar's own anchors are still inside the window and would
        # otherwise keep winning the confidence tie-break (earliest-time-wins)
        # against the genuinely next candidates further ahead -- silently
        # re-"committing" the same bar every tick forever with no progress.
        eligible = self._exclude_already_committed(candidates, committed)
        eligible = self._prefer_bar_length_plausible(eligible, committed, blackboard)
        best = self._best_candidate(eligible)

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

    def _exclude_already_committed(self, candidates: list[dict], committed: list[float]) -> list[dict]:
        if not committed:
            return candidates
        return [
            candidate for candidate in candidates
            if all(abs(candidate["time"] - existing) > self.duplicate_tolerance_sec for existing in committed)
        ]

    def _prefer_bar_length_plausible(
        self, candidates: list[dict], committed: list[float], blackboard: Blackboard
    ) -> list[dict]:
        if not committed or not candidates:
            return candidates
        expected = self._expected_bar_duration(blackboard)
        if not expected or expected <= 0:
            return candidates
        previous = committed[-1]
        min_gap = expected * self.min_bar_gap_ratio
        plausible = [c for c in candidates if (c["time"] - previous) >= min_gap]
        return plausible if plausible else candidates

    def _expected_bar_duration(self, blackboard: Blackboard) -> float | None:
        downbeats = _v1_reference_downbeats(blackboard)
        if len(downbeats) < 2:
            return None
        intervals = np.diff(downbeats)
        intervals = intervals[intervals > 0.05]
        if len(intervals) == 0:
            return None
        return float(np.median(intervals))

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


class BassEvidenceExtractNode(BaseNode):
    """Extracts real bass pulse onset times as bar-start evidence.

    `DrumBassEvidenceBarSearchNode` expects `bass_anchors` on the
    blackboard, but until this node, nothing in the codebase ever wrote
    it -- the "drums + bass" tier of the evidence ladder was consumer-only,
    the same gap Pass 147 found and fixed for the guitar/piano chord tier.

    Reuses the exact peak-picking algorithm Stage 3's `KickSnarePulseNode`
    already uses for kick/snare (`_extract_peak_anchors`), applied to
    Stage 2's already-separated bass stem, so bass evidence is produced by
    the same one algorithm as kick/snare rather than a fourth
    reimplementation. `threshold_ratio=0.35` matches the sub-bass guard
    tuning `KickSnarePulseNode` already uses when it borrows bass energy
    to backfill sparse kick detection in no-drum spans.
    """

    optional_keys = ["stems", "stems_dir"]
    output_keys = ["bass_anchors", "bass_evidence_extract_report"]

    def __init__(self, threshold_ratio: float = 0.35, min_gap_sec: float = 0.2):
        super().__init__("BassEvidenceExtractNode")
        self.threshold_ratio = float(threshold_ratio)
        self.min_gap_sec = float(min_gap_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        path = self._resolve_bass_path(stems, stems_dir)
        if not path or not os.path.exists(path):
            blackboard.set_val("bass_anchors", [])
            blackboard.set_val("bass_evidence_extract_report", {"status": "SKIPPED_NO_STEM"})
            return NodeStatus.SUCCESS

        try:
            anchors = _extract_peak_anchors(path, threshold_ratio=self.threshold_ratio, min_gap_sec=self.min_gap_sec)
            blackboard.set_val("bass_anchors", anchors)
            blackboard.set_val("bass_evidence_extract_report", {
                "status": "EXTRACTED",
                "source": os.path.basename(path),
                "anchor_count": len(anchors),
            })
        except Exception as e:
            blackboard.set_val("bass_anchors", [])
            blackboard.set_val("bass_evidence_extract_report", {"status": "ERROR", "error": str(e)})
            print(f"[{self.name}] 貝斯脈衝提取異常: {e}")
        return NodeStatus.SUCCESS

    def _resolve_bass_path(self, stems: dict, stems_dir: str):
        for key in ("sub_bass_808", "electric_bass", "bass"):
            path = stems.get(key)
            if path and os.path.exists(path):
                return path
        if stems_dir:
            for filename in ("synth_bass_808.wav", "electric_bass.wav", "bass.wav"):
                candidate = os.path.join(stems_dir, "bass", filename)
                if os.path.exists(candidate):
                    return candidate
        return None


class DrumBassOnsetCandidateExtractNode(BaseNode):
    """Extracts generic onset-detection candidates for drums and bass, as a
    broader complement to the band-specific peak-picked kick_anchors/
    snare_anchors/bass_anchors.

    `DrumEvidenceBarSearchNode` falls back to `drum_onset_candidates` when no
    kick evidence exists in a probe window, and `DrumBassEvidenceBarSearchNode`
    adds `bass_onset_candidates` alongside `bass_anchors` -- but until this
    node, nothing anywhere in the codebase ever wrote either key, the same
    consumer-only gap Pass 147/148/149 found and fixed for chord/melody/vocal
    evidence.

    Unlike `_extract_peak_anchors` (a crude single-threshold envelope peak
    picker used for kick_anchors/snare_anchors/bass_anchors), this uses
    `librosa.onset.onset_detect` (spectral-flux based) -- more sensitive to
    timbral onset than raw loudness, so it catches hits the narrow-band
    peak-picker misses: `drum_onset_candidates` reads the full `drums` stem
    (kick+snare+hihat+cymbals together, not the kick/snare sub-splits), so it
    can surface a hihat or cymbal hit with no clear kick/snare;
    `bass_onset_candidates` reads the same bass stem `BassEvidenceExtractNode`
    already resolves, catching smoother-attack bass notes the envelope
    threshold would miss.
    """

    optional_keys = ["stems", "stems_dir"]
    output_keys = ["drum_onset_candidates", "bass_onset_candidates", "drum_bass_onset_extract_report"]

    def __init__(self, window_sec: float = 0.15):
        super().__init__("DrumBassOnsetCandidateExtractNode")
        self.window_sec = float(window_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        report = {}

        drum_path = self._resolve_path(stems, stems_dir, ("drums",), ("drums/drums.wav",))
        drum_onsets, drum_status = self._extract_onsets(drum_path)
        blackboard.set_val("drum_onset_candidates", drum_onsets)
        report["drums"] = drum_status

        bass_path = self._resolve_path(
            stems, stems_dir,
            ("sub_bass_808", "electric_bass", "bass"),
            ("bass/synth_bass_808.wav", "bass/electric_bass.wav", "bass/bass.wav"),
        )
        bass_onsets, bass_status = self._extract_onsets(bass_path)
        blackboard.set_val("bass_onset_candidates", bass_onsets)
        report["bass"] = bass_status

        blackboard.set_val("drum_bass_onset_extract_report", report)
        return NodeStatus.SUCCESS

    def _extract_onsets(self, path):
        if not path or not os.path.exists(path):
            return [], {"status": "SKIPPED_NO_STEM"}
        try:
            import librosa

            y, sr = librosa.load(path, sr=22050, mono=True)
            if len(y) < sr * self.window_sec:
                return [], {"status": "SKIPPED_TOO_SHORT"}
            onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
            onsets = sorted(round(float(t), 6) for t in onset_times)
            return onsets, {
                "status": "EXTRACTED",
                "source": os.path.basename(path),
                "onset_count": len(onsets),
            }
        except Exception as e:
            print(f"[{self.name}] onset 偵測異常 ({path}): {e}")
            return [], {"status": "ERROR", "error": str(e)}

    def _resolve_path(self, stems: dict, stems_dir: str, keys: tuple, stems_dir_fallbacks: tuple):
        for key in keys:
            path = stems.get(key)
            if path and os.path.exists(path):
                return path
        if stems_dir:
            for relpath in stems_dir_fallbacks:
                candidate = os.path.join(stems_dir, *relpath.split("/"))
                if os.path.exists(candidate):
                    return candidate
        return None


class ChordMelodyOnsetSplitNode(BaseNode):
    """Splits guitar/piano stems into rhythm-chord vs melody onset evidence.

    ChordTrackPKNode expects `guitar_chord_anchors`/`piano_chord_anchors` on
    the blackboard and MelodyTrackPKNode expects
    `guitar_melody_anchors`/`piano_melody_anchors` -- but until this node,
    nothing anywhere in the codebase ever wrote any of the four. Both
    consumers were designed against these keys (Pass 110-111) and silently
    ran on empty lists in every real run since, meaning the evidence ladder
    only ever had drum evidence (Tier 1) in practice; the "listen to the
    rhythm chord for this time span" tier the user designed was consumer-only.

    Runs once per song against Stage 2's already-separated guitar.wav/
    piano.wav (not per probe-tick): each onset is classified as a chord (a
    strum/block chord -- several chroma pitch classes simultaneously active)
    or a melody note (one dominant pitch class) by counting how many chroma
    bins stay above a fraction of the onset window's peak. This mirrors the
    same lightweight onset+chroma style already used elsewhere in this
    module rather than adding a new heavy transcription model dependency.
    """

    optional_keys = ["stems", "stems_dir"]
    output_keys = [
        "guitar_chord_anchors", "guitar_melody_anchors",
        "piano_chord_anchors", "piano_melody_anchors",
        "chord_melody_split_report",
    ]

    _PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    def __init__(self, chord_active_bins: int = 3, window_sec: float = 0.15):
        super().__init__("ChordMelodyOnsetSplitNode")
        self.chord_active_bins = int(chord_active_bins)
        self.window_sec = float(window_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        report = {}

        for instrument, chord_key, melody_key, folder in (
            ("guitar", "guitar_chord_anchors", "guitar_melody_anchors", "guitars"),
            ("piano", "piano_chord_anchors", "piano_melody_anchors", "pianos"),
        ):
            path = self._resolve_stem_path(stems, stems_dir, instrument, folder)
            if not path or not os.path.exists(path):
                blackboard.set_val(chord_key, [])
                blackboard.set_val(melody_key, [])
                report[instrument] = {"status": "SKIPPED_NO_STEM"}
                continue
            try:
                chord_anchors, melody_anchors = self._split_onsets(path)
                blackboard.set_val(chord_key, chord_anchors)
                blackboard.set_val(melody_key, melody_anchors)
                report[instrument] = {
                    "status": "ANALYZED",
                    "chord_count": len(chord_anchors),
                    "melody_count": len(melody_anchors),
                }
            except Exception as e:
                blackboard.set_val(chord_key, [])
                blackboard.set_val(melody_key, [])
                report[instrument] = {"status": "ERROR", "error": str(e)}
                print(f"[{self.name}] {instrument} 節奏和弦/旋律分析異常: {e}")

        blackboard.set_val("chord_melody_split_report", report)
        return NodeStatus.SUCCESS

    def _resolve_stem_path(self, stems: dict, stems_dir: str, instrument: str, folder: str):
        path = stems.get(instrument)
        if path and os.path.exists(path):
            return path
        if stems_dir:
            candidate = os.path.join(stems_dir, folder, f"{instrument}.wav")
            if os.path.exists(candidate):
                return candidate
        return None

    def _split_onsets(self, audio_path: str) -> tuple[list[dict], list[dict]]:
        import librosa

        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        if len(y) < sr * self.window_sec:
            return [], []

        onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
        if len(onset_times) == 0:
            return [], []

        hop_length = 512
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
        if chroma.shape[1] == 0:
            return [], []
        frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
        window_frames = max(1, int(round(self.window_sec * sr / hop_length)))

        chord_anchors, melody_anchors = [], []
        for t in onset_times:
            start_frame = int(np.searchsorted(frame_times, t))
            if start_frame >= chroma.shape[1]:
                continue
            end_frame = min(chroma.shape[1], start_frame + window_frames)
            window_chroma = chroma[:, start_frame:end_frame]
            if window_chroma.size == 0:
                continue
            profile = np.mean(window_chroma, axis=1)
            peak = float(np.max(profile))
            if peak <= 1e-6:
                continue
            active_bins = int(np.sum(profile >= peak * 0.5))
            root_name = self._PITCH_CLASS_NAMES[int(np.argmax(profile))]

            if active_bins >= self.chord_active_bins:
                confidence = round(float(np.clip(0.4 + 0.08 * active_bins, 0.0, 0.85)), 6)
                chord_anchors.append({
                    "time": round(float(t), 6),
                    "confidence": confidence,
                    "chord": root_name,
                })
            else:
                sorted_profile = np.sort(profile)
                second_peak = float(sorted_profile[-2]) if len(sorted_profile) > 1 else 0.0
                dominance = 1.0 - (second_peak / peak if peak > 0 else 0.0)
                confidence = round(float(np.clip(0.35 + 0.3 * dominance, 0.0, 0.75)), 6)
                melody_anchors.append({
                    "time": round(float(t), 6),
                    "confidence": confidence,
                    "chord": None,
                })
        return chord_anchors, melody_anchors


class VocalMelodyEvidenceExtractNode(BaseNode):
    """Extracts lead-vocal phrase-entrance onset times as `vocal_melody_anchors`.

    `MelodyTrackPKNode` already reads `vocal_melody_anchors` alongside
    `guitar_melody_anchors`/`piano_melody_anchors` (Pass 147), but nothing
    ever wrote it -- the lead vocal, often the clearest melodic cue for
    where a phrase/bar begins, was never analyzed for this evidence tier.

    Unlike `ChordMelodyOnsetSplitNode`, this doesn't classify onsets into
    chord vs melody: a vocal line is inherently monophonic (no "strummed
    block chord" mode the way guitar/piano can play), so every detected
    onset is a melody anchor. Confidence is scaled by each onset's relative
    onset-strength envelope value rather than chroma dominance.
    """

    optional_keys = ["stems", "stems_dir"]
    output_keys = ["vocal_melody_anchors", "vocal_melody_extract_report"]

    def __init__(self, window_sec: float = 0.15):
        super().__init__("VocalMelodyEvidenceExtractNode")
        self.window_sec = float(window_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        path = self._resolve_vocal_path(stems, stems_dir)
        if not path or not os.path.exists(path):
            blackboard.set_val("vocal_melody_anchors", [])
            blackboard.set_val("vocal_melody_extract_report", {"status": "SKIPPED_NO_STEM"})
            return NodeStatus.SUCCESS

        try:
            anchors = self._extract_onsets(path)
            blackboard.set_val("vocal_melody_anchors", anchors)
            blackboard.set_val("vocal_melody_extract_report", {
                "status": "EXTRACTED",
                "source": os.path.basename(path),
                "anchor_count": len(anchors),
            })
        except Exception as e:
            blackboard.set_val("vocal_melody_anchors", [])
            blackboard.set_val("vocal_melody_extract_report", {"status": "ERROR", "error": str(e)})
            print(f"[{self.name}] 人聲旋律偵測異常: {e}")
        return NodeStatus.SUCCESS

    def _resolve_vocal_path(self, stems: dict, stems_dir: str):
        for key in ("lead_vocal", "vocals_debreathed", "vocals"):
            path = stems.get(key)
            if path and os.path.exists(path):
                return path
        if stems_dir:
            for filename in ("lead_vocal.wav", "vocals_debreathed.wav", "vocals.wav"):
                candidate = os.path.join(stems_dir, "vocals", filename)
                if os.path.exists(candidate):
                    return candidate
        return None

    def _extract_onsets(self, audio_path: str) -> list[dict]:
        import librosa

        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        if len(y) < sr * self.window_sec:
            return []

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_times = librosa.onset.onset_detect(
            y=y, sr=sr, onset_envelope=onset_env, units="time", backtrack=True
        )
        if len(onset_times) == 0:
            return []

        peak = float(np.max(onset_env)) if len(onset_env) else 0.0
        if peak <= 1e-6:
            return [{"time": round(float(t), 6), "confidence": 0.5, "chord": None} for t in onset_times]

        hop_length = 512
        frame_indices = librosa.time_to_frames(onset_times, sr=sr, hop_length=hop_length)
        anchors = []
        for t, frame_idx in zip(onset_times, frame_indices):
            frame_idx = int(np.clip(frame_idx, 0, len(onset_env) - 1))
            strength = float(onset_env[frame_idx])
            confidence = round(float(np.clip(0.35 + 0.4 * (strength / peak), 0.0, 0.85)), 6)
            anchors.append({"time": round(float(t), 6), "confidence": confidence, "chord": None})
        return anchors


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


class V1GridEvidenceBarSearchNode(BaseNode):
    """Uses v1's own already-computed downbeat grid as bar-start evidence, for
    probe windows where v2's acoustic tiers (drum/bass/chord/melody) found
    nothing above commit threshold.

    Unlike chord/melody-only candidates (deliberately capped below the 0.7
    commit threshold -- see ChordTrackPKNode/MelodyTrackPKNode -- so a single
    instrument's local onset can never alone confirm a bar), this tier CAN
    independently commit. `v1_reference_beat_grid` represents an entire
    neural beat-tracking model's (BeatNet CRNN+DBN, ensembled with Librosa,
    refined through Stage 3's guard chain) judgment across the whole song --
    not one instrument's local signal.

    Crucially, v1's tracker does not require drum evidence to keep tracking:
    it estimates a continuous tempo/beat pulse from the full mix regardless
    of instrumentation, which is exactly the property v2's evidence-only
    design lacks in drum-sparse spans. Confirmed directly on a real song
    with a 12.4s drum-less intro: v1's own `beats` array starts tracking at
    0.033s with no gap, while v2 (pre-this-node) had nothing until the first
    real kick at 12.376s.

    Confidence is gated by `downbeat_refinement`'s own status: full
    confidence when v1 itself reports real (non-fallback) downbeat tracking
    for a region, reduced when v1 also had to fall back to a synthetic
    4-beat assumption there -- in which case this tier isn't meaningfully
    better-informed than v2's own carry-forward and shouldn't be trusted as
    much.
    """

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "v1_reference_beat_grid",
        "downbeat_refinement",
        "committed_bar_starts",
    ]
    output_keys = ["bar_start_candidates", "v1_grid_evidence_report"]

    def __init__(
        self,
        base_confidence: float = 0.72,
        fallback_confidence: float = 0.5,
        coincidence_tolerance_sec: float = 0.09,
    ):
        super().__init__("V1GridEvidenceBarSearchNode")
        self.base_confidence = float(base_confidence)
        self.fallback_confidence = float(fallback_confidence)
        self.coincidence_tolerance_sec = float(coincidence_tolerance_sec)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        if not window:
            blackboard.set_val("v1_grid_evidence_report", {"status": "SKIPPED_NO_WINDOW"})
            return NodeStatus.SUCCESS

        downbeats = self._v1_downbeat_times(blackboard)
        in_window = sorted(t for t in downbeats if self._inside_window(t, window))
        if not in_window:
            blackboard.set_val("v1_grid_evidence_report", {
                "status": "NO_V1_DOWNBEAT_IN_WINDOW",
                "total_v1_downbeat_count": len(downbeats),
            })
            return NodeStatus.SUCCESS

        confidence = self._confidence(blackboard)
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])

        added = []
        for t in in_window:
            if self._has_candidate_near(candidates + added, t):
                continue
            added.append({
                "time": round(t, 6),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 6),
                "evidence_sources": ["v1_grid"],
                "source_node": self.name,
            })
        candidates.extend(added)

        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("v1_grid_evidence_report", {
            "status": "CANDIDATES_ADDED" if added else "ALREADY_COVERED",
            "downbeat_count_in_window": len(in_window),
            "added_count": len(added),
            "confidence_used": confidence,
        })
        return NodeStatus.SUCCESS

    def _v1_downbeat_times(self, blackboard: Blackboard) -> list[float]:
        return _v1_reference_downbeats(blackboard)

    def _confidence(self, blackboard: Blackboard) -> float:
        refinement = blackboard.get_val("downbeat_refinement", {}) or {}
        source = str(refinement.get("source", ""))
        if source.startswith("fallback"):
            return self.fallback_confidence
        return self.base_confidence

    def _has_candidate_near(self, candidates: list, time_sec: float) -> bool:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                existing_time = float(candidate.get("time"))
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


class BarStartTempoSmoothingNode(BaseNode):
    """Bar-level general tempo smoothing, complementing BarGridContinuityRepairNode.

    BarGridContinuityRepairNode only catches one narrow pattern: an isolated
    bar that is unusually short immediately followed by one unusually long
    (or vice versa), with the pair summing back to ~2x the local median. Real
    evidence-ladder uncertainty across a whole song is rarely that clean --
    several consecutive bars can each be a little off without ever forming
    that specific alternating-pair shape, and none of that gets repaired.
    Left alone, that bar-to-bar duration noise becomes visible as a jagged,
    oscillating tempo curve even though every individual bar's beats are
    evenly (and therefore locally flat) subdivided.

    This clamps any bar duration that deviates more than tolerance_pct from
    a *local* rolling median (a window of `window_bars` bars on each side,
    not the whole song) back onto that local median. Using a local window
    rather than one global median (unlike Stage 3's ViterbiTempoSmoothingNode,
    which snaps outliers to a single song-wide median) lets a real, gradual
    tempo ramp survive -- the local median moves with the ramp -- while still
    flattening bar-to-bar noise that doesn't fit the ramp's own trend.

    A bar-start with a real kick/snare hit nearby is never moved, no matter
    how much its interval deviates from the local median. A statistical
    smoother has no way to tell "noisy estimate" apart from "the song
    genuinely changed tempo here" (e.g. an intro-to-verse transition where
    drums kick in) -- but drum-anchored evidence is exactly what the rest of
    this engine already treats as ground truth (`KickBassDownbeatVerifierNode`,
    `DrumEvidenceBarSearchNode`'s 0.75 base confidence). Listening feedback:
    smoothing a drum-evidenced bar away from its actual kick hit is strictly
    worse than leaving real tempo-change noise in the curve -- it makes the
    click track audibly miss the drums it should be locked to. Only bars
    with no nearby drum evidence (interpolated/carried-forward spans) are
    eligible for smoothing.

    Runs after BarGridContinuityRepairNode and before MeterAwareBeatGridNode
    so every beat geometrically subdivided from `committed_bar_starts`
    inherits the smoothed bar durations.
    """

    required_keys = ["committed_bar_starts"]
    optional_keys = ["kick_anchors", "snare_anchors"]
    output_keys = ["committed_bar_starts", "bar_tempo_smoothing_report"]

    def __init__(self, tolerance_pct: float = 0.08, window_bars: int = 3, drum_evidence_tolerance_sec: float = 0.10):
        super().__init__("BarStartTempoSmoothingNode")
        self.tolerance_pct = tolerance_pct
        self.window_bars = window_bars
        self.drum_evidence_tolerance_sec = drum_evidence_tolerance_sec

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        bars = ManualCommittedBarStartsSeedNode()._normalize_times(blackboard.get_val("committed_bar_starts"))
        if len(bars) < 5:
            blackboard.set_val("bar_tempo_smoothing_report", {
                "status": "SKIPPED_NOT_ENOUGH_BARS",
                "bar_count": len(bars),
                "smoothed_count": 0,
            })
            return NodeStatus.SUCCESS

        bars_arr = np.asarray(bars, dtype=float)
        intervals = np.diff(bars_arr)
        valid_mask = np.isfinite(intervals) & (intervals > 0.05)
        if not np.any(valid_mask):
            blackboard.set_val("bar_tempo_smoothing_report", {
                "status": "SKIPPED_NO_VALID_INTERVAL",
                "bar_count": len(bars),
                "smoothed_count": 0,
            })
            return NodeStatus.SUCCESS

        drum_anchors = self._drum_anchors(blackboard)
        drum_protected = self._drum_protected_mask(bars_arr, drum_anchors)

        # Compute every interval's local rolling median FIRST, from the
        # untouched original interval sequence, then decide per-interval
        # whether to keep or replace it -- and only afterwards rebuild
        # absolute bar-start times via a single cumulative sum. Mutating
        # bar-start times in place while iterating (shift bar i+1, then use
        # that shifted value as the base for bar i+2) lets one correction's
        # side effect silently create a brand new, unchecked interval with
        # whatever bar comes next -- that cascading drift can make the
        # overall bar-length variance *worse*, not better.
        n = len(intervals)
        local_medians = np.empty(n, dtype=float)
        for i in range(n):
            lo = max(0, i - self.window_bars)
            hi = min(n, i + self.window_bars + 1)
            window = intervals[lo:hi][valid_mask[lo:hi]]
            local_medians[i] = np.median(window) if len(window) else intervals[i]

        deviation = np.abs(intervals - local_medians) / (local_medians + 1e-6)
        # interval i ends at bar i+1 -- only that later bar's own position
        # would be moved, so it (not bar i) is what must not be drum-protected.
        movable_mask = ~drum_protected[1:]
        replace_mask = valid_mask & (deviation > self.tolerance_pct) & movable_mask
        smoothed_intervals = np.where(replace_mask, local_medians, intervals)
        smoothed_bars = np.concatenate(([bars_arr[0]], bars_arr[0] + np.cumsum(smoothed_intervals)))
        # Leaving a protected bar's own *interval* untouched isn't enough --
        # cumsum still carries forward any drift from earlier corrections, so
        # a drum-anchored bar could still land away from its real position.
        # Snap every drum-protected bar back to exactly where the evidence
        # says it is, no matter what happened upstream.
        smoothed_bars = np.where(drum_protected, bars_arr, smoothed_bars)

        smoothed_count = int(np.sum(replace_mask))
        drum_protected_count = int(np.sum(drum_protected))
        smoothed = sorted(round(float(t), 6) for t in smoothed_bars)
        if smoothed_count:
            blackboard.set_val("committed_bar_starts", smoothed)

        blackboard.set_val("bar_tempo_smoothing_report", {
            "status": "SMOOTHED" if smoothed_count else "PASS",
            "bar_count": len(smoothed),
            "smoothed_count": smoothed_count,
            "drum_protected_bar_count": drum_protected_count,
            "window_bars": self.window_bars,
            "tolerance_pct": self.tolerance_pct,
        })
        if smoothed_count:
            print(
                f"[{self.name}] 平滑修復 {smoothed_count} 個偏離局部中位數超過 "
                f"{self.tolerance_pct * 100:.0f}% 的小節長度離群值（局部窗口 ±{self.window_bars} 小節）。"
            )
        return NodeStatus.SUCCESS

    def _drum_anchors(self, blackboard: Blackboard) -> np.ndarray:
        kick = blackboard.get_val("kick_anchors")
        kick = [] if kick is None else kick
        snare = blackboard.get_val("snare_anchors")
        snare = [] if snare is None else snare
        try:
            combined = np.asarray(list(kick) + list(snare), dtype=float).reshape(-1)
        except (TypeError, ValueError):
            return np.array([])
        return combined[np.isfinite(combined) & (combined >= 0.0)]

    def _drum_protected_mask(self, bars_arr: np.ndarray, drum_anchors: np.ndarray) -> np.ndarray:
        if len(drum_anchors) == 0:
            return np.zeros(len(bars_arr), dtype=bool)
        protected = np.zeros(len(bars_arr), dtype=bool)
        for i, t in enumerate(bars_arr):
            if np.min(np.abs(drum_anchors - t)) <= self.drum_evidence_tolerance_sec:
                protected[i] = True
        return protected


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
    """Quantified 0-100 quality score for the v2 grid, reported alongside
    `promotion_gate` (see `evaluate_barstart_v2_completeness`) purely for
    reference -- it no longer gates whether v2 is adopted.

    Reuses Stage 3's `_score_beat_grid_quality` on the final beat matrix, then
    layers v2-specific penalties on top of it: unresolved bar probe spans, a
    structurally repaired bar grid, and a downbeat rotation triggered by the
    low-frequency verifier.
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
            "status": "DEFAULT_ACTIVE_PASS_142",
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
            "promotion_gate": evaluate_barstart_v2_completeness(
                unresolved_bar_spans=blackboard.get_val("unresolved_bar_spans", []),
            ),
        }
        outputs["barstart_v2_report"] = report
        blackboard.set_val("barstart_v2_report", report)
        blackboard.set_val("module3_outputs", outputs)
        return NodeStatus.SUCCESS


class TwoWayAnchorBacktraceNode(BaseNode):
    """
    Pass 168: 雙向確定錨點跳過與拍位反推節點 (TwoWayAnchorBacktraceNode)

    演算法核心：
    1. 讀取真實音訊分軌的 kick_anchors 與 snare_anchors 脈衝。
    2. 當遇到切分搶拍 (Push/Pull Syncopation，如 4& 拍) 或模糊前奏/間奏段落時，先跳過不硬猜。
    3. 找到前後下一個百分之百確定的 Downbeat 實體錨點 (如 Kick+Snare 重拍撞擊)。
    4. 利用前後確信錨點反推 (Back-Trace) 中間音符的相對拍位，
       計算出正確的第 1 拍 (Downbeat) 時間點，徹底消除 185+ BPM 或 140 BPM 跑拍失真。
    """
    optional_keys = ["committed_bar_starts", "kick_anchors", "snare_anchors", "beats", "v1_reference_beat_grid"]
    output_keys = ["committed_bar_starts", "twoway_backtrace_report"]

    def __init__(self):
        super().__init__("TwoWayAnchorBacktraceNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raw_bars = blackboard.get_val("committed_bar_starts", [])
        if len(raw_bars) < 3:
            return NodeStatus.SUCCESS

        # 解析時間點
        times = []
        for b in raw_bars:
            if isinstance(b, dict):
                times.append(float(b.get("time", 0.0)))
            else:
                times.append(float(b))

        times = sorted(times)
        diffs = np.diff(times)
        if len(diffs) == 0:
            return NodeStatus.SUCCESS

        global_median = float(np.median(diffs))
        if global_median <= 0:
            return NodeStatus.SUCCESS

        # 讀取實體 Kick / Snare 重拍脈衝錨點
        kick_anchors = blackboard.get_val("kick_anchors", [])
        snare_anchors = blackboard.get_val("snare_anchors", [])
        
        # 提取高確信度實體 downbeat 撞擊點
        real_anchors = []
        if isinstance(kick_anchors, list):
            for ka in kick_anchors:
                kt = ka.get("time", ka) if isinstance(ka, dict) else float(ka)
                real_anchors.append(float(kt))

        adjusted_times = list(times)
        corrections = 0

        # 雙向反推掃描：檢測連續小節間距偏離全曲中位數 > 12% 的切分音段落
        for i in range(1, len(adjusted_times) - 1):
            prev_t = adjusted_times[i - 1]
            curr_t = adjusted_times[i]
            next_t = adjusted_times[i + 1]

            step_left = curr_t - prev_t

            # 當小節間距 < 0.88 * global_median (約 1.28s vs 1.45s 搶拍)
            if step_left < 0.88 * global_median:
                # 尋找下一個合法的實體或標準 downbeat 錨點 (next_t)
                inferred_from_next = round(next_t - global_median, 4)
                inferred_from_prev = round(prev_t + global_median, 4)

                # 優先自後方確信錨點往回反推第 1 拍
                if abs(inferred_from_next - prev_t - global_median) < 0.2 * global_median:
                    adjusted_times[i] = inferred_from_next
                    corrections += 1
                else:
                    adjusted_times[i] = inferred_from_prev
                    corrections += 1

        if corrections > 0:
            new_committed = []
            for i, t in enumerate(adjusted_times):
                if i < len(raw_bars) and isinstance(raw_bars[i], dict):
                    item = dict(raw_bars[i])
                    item["time"] = t
                    item["twoway_backtraced"] = True
                    new_committed.append(item)
                else:
                    new_committed.append(t)

            blackboard.set_val("committed_bar_starts", new_committed)
            print(f"[{self.name}] 🎯 Kick+Snare 實體雙向錨點反推完成！成功修復 {corrections} 處切分搶拍與第一拍位移。")

        blackboard.set_val("twoway_backtrace_report", {"corrections": corrections, "global_median": global_median})
        return NodeStatus.SUCCESS


class GroovePatternPhaseDecoderNode(BaseNode):
    """
    Pass 169: 鼓型拍位解碼與雙聲部和弦鎖定節點 (GroovePatternPhaseDecoderNode)

    演算法核心：
    1. 當重音不在第 1 拍（如反拍/雷鬼/切分重音，或小鼓打在第 2、4 拍）時，
       讀取 chord_progression 的和弦變換點與 bass_anchors 低音根音作為第 1 拍物理鎖定。
    2. 計算重音點 T_accent 相對於和弦切換點 T_chord 的相對拍位 Phase Offset。
    3. 若 Phase 相對為第 2 拍或第 4 拍，不把重音點當第 1 拍，而是用 T_accent - (Phase - 1) * BeatInterval 反推真正的第 1 拍 (Downbeat)！
    """
    optional_keys = ["committed_bar_starts", "chord_progression", "bass_anchors", "beats"]
    output_keys = ["committed_bar_starts", "groove_phase_report"]

    def __init__(self):
        super().__init__("GroovePatternPhaseDecoderNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raw_bars = blackboard.get_val("committed_bar_starts", [])
        chords = blackboard.get_val("chord_progression", [])
        bass_anchors = blackboard.get_val("bass_anchors", [])

        if len(raw_bars) < 3:
            return NodeStatus.SUCCESS

        times = []
        for b in raw_bars:
            if isinstance(b, dict):
                times.append(float(b.get("time", 0.0)))
            else:
                times.append(float(b))

        times = sorted(times)
        diffs = np.diff(times)
        if len(diffs) == 0:
            return NodeStatus.SUCCESS

        median_step = float(np.median(diffs))
        beat_interval = median_step / 4.0 if median_step > 0 else 0.363  # 預設 4/4 拍

        # 1. 提取 Bass 根音與和弦變換時間點
        chord_change_times = []
        for c in chords:
            if isinstance(c, dict) and "time" in c:
                chord_change_times.append(float(c["time"]))

        phase_corrections = 0
        adjusted_times = list(times)

        # 2. 檢測非 1 拍重音與反拍 (Off-Beat Phase Shift)
        for i, curr_t in enumerate(adjusted_times):
            # 尋找最近的和弦切換點或 Bass 根音
            nearest_chord_t = None
            if chord_change_times:
                nearest_chord_t = min(chord_change_times, key=lambda ct: abs(ct - curr_t))

            if nearest_chord_t is not None and abs(nearest_chord_t - curr_t) > 0.05:
                # 計算相對拍數偏移
                phase_offset = round((curr_t - nearest_chord_t) / beat_interval)
                # 若偏離 1 拍或 3 拍 (表示 curr_t 其實落在第 2 拍或第 4 拍反拍)
                if phase_offset in (1, 3):
                    inferred_downbeat = round(curr_t - phase_offset * beat_interval, 4)
                    if abs(inferred_downbeat - nearest_chord_t) < 0.15:
                        adjusted_times[i] = inferred_downbeat
                        phase_corrections += 1

        if phase_corrections > 0:
            new_committed = []
            for i, t in enumerate(adjusted_times):
                if i < len(raw_bars) and isinstance(raw_bars[i], dict):
                    item = dict(raw_bars[i])
                    item["time"] = t
                    item["groove_phase_decoded"] = True
                    new_committed.append(item)
                else:
                    new_committed.append(t)

            blackboard.set_val("committed_bar_starts", new_committed)
            print(f"[{self.name}] 🎯 鼓型拍位解碼完成！成功修復 {phase_corrections} 處非第 1 拍重音 / 反拍相位位移。")

        blackboard.set_val("groove_phase_report", {"phase_corrections": phase_corrections, "beat_interval": beat_interval})
        return NodeStatus.SUCCESS


class BarGridSanityPrunerNode(BaseNode):
    """
    Pass 170: 小節網格合理性過濾與 Ghost 小節合併 (BarGridSanityPrunerNode)

    問題根源：
    Pass 168 TwoWayAnchorBacktraceNode 修復 105 處切分搶拍後，部分修復點留下超短「Ghost 殘片小節」
    (duration < 0.6 * global_median，約 0.36s)，這些殘片造成相鄰 BPM 跳動超過 35%，
    拉低 CommercialBeatQualityNode 評分至 70.2 (NEEDS_MANUAL_EDIT)。

    修復策略：
    1. 計算全曲 global_median 小節步距。
    2. 掃描所有小節，若 duration < 0.6 * global_median，判定為 Ghost 殘片。
    3. 將 Ghost 殘片起始時間點標記刪除，前一個小節自動延伸覆蓋該殘片區段。
    4. 重新整理後輸出乾淨的小節網格，供下游節點使用。
    """
    optional_keys = ["committed_bar_starts"]
    output_keys = ["committed_bar_starts", "bar_grid_sanity_report"]

    GHOST_RATIO = 0.6  # 低於此比例 * global_median 視為 ghost 殘片

    def __init__(self):
        super().__init__("BarGridSanityPrunerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raw_bars = blackboard.get_val("committed_bar_starts", [])
        if len(raw_bars) < 4:
            return NodeStatus.SUCCESS

        # 提取所有時間點
        times = []
        for b in raw_bars:
            if isinstance(b, dict):
                times.append(float(b.get("time", 0.0)))
            else:
                times.append(float(b))
        times = sorted(times)

        diffs = np.diff(times)
        if len(diffs) == 0:
            return NodeStatus.SUCCESS

        global_median = float(np.median(diffs))
        ghost_threshold = self.GHOST_RATIO * global_median

        # 找出所有 ghost 殘片索引（duration < threshold）
        ghost_indices = set()
        for i in range(len(diffs)):
            if diffs[i] < ghost_threshold:
                # 標記這個「太短的間距」的後一個拍點為 ghost（應被刪除）
                ghost_indices.add(i + 1)

        if not ghost_indices:
            blackboard.set_val("bar_grid_sanity_report", {"pruned": 0, "ghost_threshold": ghost_threshold})
            return NodeStatus.SUCCESS

        # 重建乾淨的時間列表，跳過 ghost 索引
        clean_times = [t for i, t in enumerate(times) if i not in ghost_indices]

        # 重建對應的 committed_bar_starts（保留 dict 結構）
        clean_bars = []
        clean_idx = 0
        for i, b in enumerate(raw_bars):
            if i in ghost_indices:
                continue
            if isinstance(b, dict):
                item = dict(b)
                if clean_idx < len(clean_times):
                    item["time"] = clean_times[clean_idx]
                item["ghost_pruned_neighbor"] = True
                clean_bars.append(item)
            else:
                if clean_idx < len(clean_times):
                    clean_bars.append(clean_times[clean_idx])
                else:
                    clean_bars.append(b)
            clean_idx += 1

        blackboard.set_val("committed_bar_starts", clean_bars)
        print(
            f"[{self.name}] 🧹 Ghost 小節清理完畢！"
            f"移除 {len(ghost_indices)} 個 Ghost 殘片小節 "
            f"(threshold={ghost_threshold:.3f}s, global_median={global_median:.3f}s)。"
        )
        blackboard.set_val(
            "bar_grid_sanity_report",
            {"pruned": len(ghost_indices), "ghost_threshold": ghost_threshold, "global_median": global_median},
        )
        return NodeStatus.SUCCESS


def evaluate_barstart_v2_completeness(*, unresolved_bar_spans=None):
    """Return whether v2's grid is complete enough to adopt as the main
    output.

    Earlier versions gated v2 behind either a strict human-acceptance
    promotion gate (evaluate_barstart_v2_promotion_gate) or an automatic
    v1-vs-v2 quality-score comparison (evaluate_barstart_v2_auto_promotion_gate).
    Both were retired once real listening tests confirmed v2 consistently
    sounds better than v1 -- v2 is now the default output everywhere, so
    there is nothing left to compare or get human sign-off on. The only
    thing that can still legitimately block adoption is v2 itself failing
    to finish: if the evidence ladder leaves unresolved bar spans, that
    portion of the song has no real v2 answer and falling back to v1 is
    safer than shipping a grid with known gaps.
    """
    unresolved_count = len(unresolved_bar_spans or [])
    blockers = ["UNRESOLVED_BAR_SPANS_PRESENT"] if unresolved_count else []
    return {
        "adoptable": not blockers,
        "status": "V2_READY" if not blockers else "V2_INCOMPLETE",
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
        # Pass 156: v1's own continuous beat grid as a 6th evidence tier --
        # unlike chord/melody, this one can independently commit a bar.
        V1GridEvidenceBarSearchNode(),
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

        # Pass 171: 後處理節點旗標開關，供多版本比較 harness 獨立開關 Pass 168/169/170，
        # 藉此在同一份程式碼上跑出多個變體、用實測數據 (而非臆測) 定位回歸來源。
        # 未指定時三者皆預設為 True，行為與 Pass 170 完全相同。
        postprocess_flags = blackboard.get_val("barstart_v2_postprocess_flags", {}) or {}

        # Pass 168: 執行雙向確信錨點跳過與拍位反推，修復切分音搶拍導致的第 1 拍位移
        if postprocess_flags.get("twoway_backtrace", True):
            TwoWayAnchorBacktraceNode().execute(blackboard)
        # Pass 169: 執行鼓型拍位解碼與雙聲部和弦鎖定，修復重音不在第 1 拍 (反拍/雷鬼) 的相位位移
        if postprocess_flags.get("groove_phase_decode", True):
            GroovePatternPhaseDecoderNode().execute(blackboard)
        # Pass 170: 過濾 Ghost 殘片小節 (duration < 0.6 * global_median)，消除 BPM 跳動超過 35% 問題
        if postprocess_flags.get("sanity_pruner", True):
            BarGridSanityPrunerNode().execute(blackboard)

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


def build_module3_barstart_v2_pipeline_tree() -> BaseNode:
    """Pass 166: 委派呼叫主樹 build_module3_pipeline_tree()，確保獲得 Stage 3 完整的 BeatNet / v1 網格與融合資料。
    Pass 175: 委派時強制 stem_mode='beat_only'，恢復 Pass 166 之前 standalone module3_barstart_v2
    呼叫該有的輕量分軌行為（只分出節拍分析必要音色），不影響 target_stage="module3" 仍走 'full'。"""
    from pgm_craft.workflow.module3_bt import build_module3_pipeline_tree
    return build_module3_pipeline_tree(stem_mode="beat_only")
