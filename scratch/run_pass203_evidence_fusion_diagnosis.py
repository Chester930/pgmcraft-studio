"""PASS-203: runtime diagnosis of BarStart V2 evidence fusion.

The production class is instrumented by a temporary Python wrapper at runtime;
no debug fields or logging hooks are committed to the production module. When
the requested fixture is present, one JSON object per commit tick is written
to ``scratch/debug_pass203_evidence_trace.jsonl`` and a markdown diagnosis is
generated from that trace.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = (
    ROOT / "outputs" / "pass198_default_pipeline_reverify" / AUDIO_NAME / "source" / f"{AUDIO_NAME}.wav"
)
TRACE_PATH = ROOT / "scratch" / "debug_pass203_evidence_trace.jsonl"
REPORT_PATH = ROOT / "scratch" / "pass203_evidence_fusion_diagnosis.md"
# Pass 203 fix (2nd run): use a fresh output dir, not the one from the first
# two (52-second) runs -- that folder's blackboard-derived JSON artifacts
# (measure_map.json, committed_bar_starts, etc.) reflect the earlier
# premature-stall state, and reusing the same project folder risks some
# node short-circuiting on "already exists" rather than genuinely
# re-deriving the full-song trace this run needs.
OUTPUT_ROOT = ROOT / "outputs" / "pass203_evidence_fusion_diagnosis_fullsong"
PRIOR_STEMS_SOURCE = ROOT / "outputs" / "pass203_evidence_fusion_diagnosis" / AUDIO_NAME / "stems"


SOURCE_KEYS = {
    "drum": "drum_bar_evidence_report",
    "drum_bass": "drum_bass_evidence_report",
    "chord": "harmonic_anchor_evidence_report",
    "melody": "phrase_anchor_evidence_report",
    "v1_grid": "v1_grid_evidence_report",
    "beat_this": "beat_this_candidate_report",
}

# Pass 203 fix (2nd run): the original needle-matching scheme
# (label.replace("_", "") searched against source_node/evidence_sources)
# never matches how DrumBassEvidenceBarSearchNode/ChordTrackPKNode/
# MelodyTrackPKNode actually tag their contribution -- confirmed by reading
# module3_barstart_v2_bt.py directly: bass/chord/melody evidence attaches as
# a *support tag* on an existing drum candidate (e.g. "bass_coincidence_support",
# "harmonic_anchor_support", "phrase_anchor_support") rather than producing an
# independently-tagged candidate in the common case. Match on the exact tags
# each node actually writes (both the "boosts an existing candidate" and
# "stands alone when no drum candidate exists" cases), not a generic needle.
SOURCE_TAGS = {
    "drum": {"drums", "kick", "drum_onset"},
    "drum_bass": {"bass_coincidence_support", "bass", "bass_onset"},
    "chord": {"harmonic_anchor_support", "harmonic_anchor"},
    "melody": {"phrase_anchor_support", "phrase_anchor"},
    "v1_grid": {"v1_grid"},
    "beat_this": {"beat_this"},
}
SOURCE_NODE_NAMES = {
    "drum": {"DrumEvidenceBarSearchNode"},
    "drum_bass": {"DrumBassEvidenceBarSearchNode"},
    "chord": {"ChordTrackPKNode"},
    "melody": {"MelodyTrackPKNode"},
    "v1_grid": {"V1GridEvidenceBarSearchNode"},
    "beat_this": {"BeatThisCandidateAdapterNode"},
}


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        return value.tolist()
    except AttributeError:
        return repr(value)


def _source_hits(candidates: list[dict]) -> dict:
    """For each conceptual source, count candidates it either produced
    standalone (source_node match) or contributed a support tag to (tag
    match) -- a source with zero standalone candidates but many support-tag
    hits is still active, just never wins the "who owns this candidate"
    question on its own."""
    result = {}
    for label in SOURCE_KEYS:
        tags = SOURCE_TAGS.get(label, set())
        node_names = SOURCE_NODE_NAMES.get(label, set())
        hits = []
        standalone = []
        for candidate in candidates:
            evidence = {str(item) for item in (candidate.get("evidence_sources", []) or [])}
            is_standalone = candidate.get("source_node") in node_names
            is_support = bool(evidence & tags)
            if is_standalone or is_support:
                hits.append(candidate)
            if is_standalone:
                standalone.append(candidate)
        result[label] = {
            "candidate_count": len(hits),
            "standalone_count": len(standalone),
            "candidates": hits,
        }
    return result


def _install_runtime_probe(trace: list[dict]):
    from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode

    original = BarStartCandidateCommitNode.execute

    def wrapped(self, blackboard):
        before = list(blackboard.get_val("bar_start_candidates", []) or [])
        record = {
            "tick": len(trace) + 1,
            "active_bar_probe_window": _json_safe(blackboard.get_val("active_bar_probe_window", {})),
            "all_candidates_before_commit": _json_safe(before),
            "candidate_count_before_commit": len(before),
            "upstream_sources": {},
            "threshold": blackboard.get_val("candidate_commit_confidence_threshold", 0.7),
        }
        source_hits = _source_hits(before)
        for label, key in SOURCE_KEYS.items():
            record["upstream_sources"][label] = {
                "blackboard_key": key,
                "report": _json_safe(blackboard.get_val(key, {})),
                "candidate_count": source_hits[label]["candidate_count"],
                "candidates": _json_safe(source_hits[label]["candidates"]),
            }
        status = original(self, blackboard)
        decision = blackboard.get_val("bar_start_decision_report", {}) or {}
        record.update({
            "node_status": str(getattr(status, "value", status)),
            "decision_report": _json_safe(decision),
            "best_candidate": _json_safe(decision.get("best_candidate")),
            "commit_succeeded": decision.get("status") == "COMMITTED",
            "final_threshold": decision.get("threshold", record["threshold"]),
        })
        trace.append(record)
        return status

    BarStartCandidateCommitNode.execute = wrapped
    return BarStartCandidateCommitNode, original


def _restore_runtime_probe(target, original):
    target.execute = original


# Pass 203 fix (2nd run): FullSongBarStartLoopNode's default stall_limit=3
# means three consecutive non-committing ticks trigger its own give-up
# logic, and when no provisional fallback exists it breaks the whole loop
# (stop_reason="stalled_no_recovery") -- the first diagnostic run only ever
# saw 9 ticks / the first 52 seconds because of exactly this. The probe
# window still advances tick-to-tick regardless of commit success, so
# raising stall_limit lets the diagnostic keep walking the rest of the song
# for data-collection purposes even where V2 itself would give up; this
# does not change what gets promoted to production (this script never
# touches the real pipeline's default construction, only this one instance
# for the duration of this run).
DIAGNOSTIC_STALL_LIMIT = 10_000


def _install_stall_override():
    from pgm_craft.workflow.module3_barstart_v2_bt import FullSongBarStartLoopNode

    original_init = FullSongBarStartLoopNode.__init__

    def patched_init(self, max_iterations: int = 500, stall_limit: int = 3):
        original_init(self, max_iterations=max_iterations, stall_limit=DIAGNOSTIC_STALL_LIMIT)

    FullSongBarStartLoopNode.__init__ = patched_init
    return FullSongBarStartLoopNode, original_init


def _restore_stall_override(target, original_init):
    target.__init__ = original_init


def _write_trace(trace: list[dict]):
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("w", encoding="utf-8") as handle:
        for record in trace:
            handle.write(json.dumps(_json_safe(record), ensure_ascii=False) + "\n")


def _write_blocked_report(reason: str, error: str | None = None):
    lines = [
        "# PASS-203 Evidence Fusion Diagnosis",
        "",
        "## Status",
        "",
        f"**BLOCKED** — {reason}",
        "",
        f"- Requested audio: `{AUDIO_PATH}`",
        f"- Runtime trace: `{TRACE_PATH}`",
        "- No production instrumentation was left behind.",
        "",
        "## What cannot be concluded",
        "",
        "The 15% genuine-commit rate cannot be attributed to a particular evidence "
        "source or confidence gap without the requested per-tick trace. Existing "
        "Pass-198 aggregate output is context only and is not substituted for this diagnosis.",
    ]
    if error:
        lines.extend(["", f"Runtime error: `{error}`"])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _summarise(trace: list[dict], elapsed_sec: float, pipeline_report: dict):
    total = len(trace)
    commits = [item for item in trace if item.get("commit_succeeded")]
    no_candidates = [
        item for item in trace
        if not item.get("best_candidate") and item.get("decision_report", {}).get("reason") == "no_candidates"
    ]
    below = [
        item for item in trace
        if item.get("best_candidate") and not item.get("commit_succeeded")
    ]
    gaps = [
        float(item["final_threshold"]) - float(item["best_candidate"]["confidence"])
        for item in below
        if item.get("best_candidate", {}).get("confidence") is not None
    ]
    source_tick_counts = {}
    source_candidate_counts = {}
    source_standalone_counts = {}
    for source in SOURCE_KEYS:
        values = [item["upstream_sources"][source] for item in trace]
        source_tick_counts[source] = sum(1 for value in values if value["candidate_count"] > 0)
        source_candidate_counts[source] = sum(value["candidate_count"] for value in values)
        source_standalone_counts[source] = sum(value.get("standalone_count", 0) for value in values)

    examples = sorted(
        below,
        key=lambda item: float(item["final_threshold"]) - float(item["best_candidate"]["confidence"]),
    )[:5]
    lines = [
        "# PASS-203 Evidence Fusion Diagnosis",
        "",
        "## Result",
        "",
        f"- Ticks: **{total}**; commits: **{len(commits)}**; no-candidate ticks: **{len(no_candidates)}**; candidate-but-below-threshold ticks: **{len(below)}**.",
        f"- Trace runtime: {elapsed_sec:.2f}s.",
        f"- Existing pipeline report: `{pipeline_report.get('workflow_status', 'unknown')}`.",
        "",
        "## Evidence-source activity",
        "",
        "(\"Candidate instances\" counts a source as active whenever it either produced its "
        "own candidate or attached a support tag to someone else's -- e.g. "
        "bass/harmonic/phrase evidence is designed to boost a drum candidate's confidence "
        "rather than stand alone, so \"standalone\" can be 0 while the source is still working.)",
        "",
        "| Source | Ticks with candidates | Candidate instances (incl. support tags) | Standalone candidates |",
        "|---|---:|---:|---:|",
    ]
    for source in SOURCE_KEYS:
        lines.append(
            f"| {source} | {source_tick_counts[source]} | {source_candidate_counts[source]} | "
            f"{source_standalone_counts[source]} |"
        )
    if gaps:
        lines.extend([
            "",
            "## Below-threshold gap",
            "",
            f"- Mean gap: {sum(gaps) / len(gaps):.4f}; minimum gap: {min(gaps):.4f}; maximum gap: {max(gaps):.4f}.",
            "- Representative near-miss ticks:",
        ])
        for item in examples:
            candidate = item["best_candidate"]
            lines.append(
                f"  - tick {item['tick']}: time={candidate.get('time')}, confidence={candidate.get('confidence')}, "
                f"threshold={item['final_threshold']}, sources={candidate.get('evidence_sources', [])}"
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This report separates no-evidence ticks from near misses; it does not tune "
        "any confidence formula. Any follow-up parameter or source change requires "
        "a separate decision after reviewing these concrete examples.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reuse_stems_cache() -> None:
    """Symlink/junction already-computed stems into this run's fresh project
    folder so demucs doesn't redo ~10 minutes of stem separation. Prefers the
    prior pass203 run's stems (already includes the extra PeelCoreTrio/
    submix layers this pipeline separates beyond the base demucs stems);
    falls back to Pass 198's if that's not there."""
    dst = OUTPUT_ROOT / AUDIO_NAME / "stems"
    if dst.exists():
        return
    src = PRIOR_STEMS_SOURCE if PRIOR_STEMS_SOURCE.exists() else (
        ROOT / "outputs" / "pass198_default_pipeline_reverify" / AUDIO_NAME / "stems"
    )
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(src, dst, target_is_directory=True)
    except OSError:
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], capture_output=True, text=True, check=False)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    if not AUDIO_PATH.exists():
        _write_trace([])
        _write_blocked_report(
            "the PASS-203 source WAV is not present in this worktree; the real target_stage=module3 run was not attempted."
        )
        print(f"[PASS-203] blocked: missing {AUDIO_PATH}")
        return 0

    from pgm_craft.pipeline import PGMCraftEngine

    _reuse_stems_cache()
    trace = []
    target, original = _install_runtime_probe(trace)
    stall_target, stall_original = _install_stall_override()
    started = time.time()
    try:
        pipeline_report = PGMCraftEngine(enable_stem_separation=True).run(
            str(AUDIO_PATH),
            output_dir=str(OUTPUT_ROOT),
            enable_stem=True,
            target_stage="module3",
            user_meter_selection="4/4",
            allow_temporary_bar_delta=0,
        )
    except Exception as exc:
        _write_trace(trace)
        _write_blocked_report("the instrumented pipeline run failed", f"{type(exc).__name__}: {exc}")
        print(f"[PASS-203] failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        _restore_runtime_probe(target, original)
        _restore_stall_override(stall_target, stall_original)

    _write_trace(trace)
    _summarise(trace, time.time() - started, pipeline_report)
    print(f"[PASS-203] ticks={len(trace)} trace={TRACE_PATH} report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
