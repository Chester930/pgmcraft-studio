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
OUTPUT_ROOT = ROOT / "outputs" / "pass203_evidence_fusion_diagnosis"


SOURCE_KEYS = {
    "drum": "drum_bar_evidence_report",
    "drum_bass": "drum_bass_evidence_report",
    "chord": "harmonic_anchor_evidence_report",
    "melody": "phrase_anchor_evidence_report",
    "v1_grid": "v1_grid_evidence_report",
    "beat_this": "beat_this_candidate_report",
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
    result = {}
    for label in SOURCE_KEYS:
        hits = []
        needle = label.replace("_", "").lower()
        for candidate in candidates:
            values = [candidate.get("source_node", "")]
            values.extend(candidate.get("evidence_sources", []) or [])
            if any(needle in str(value).replace("_", "").lower() for value in values):
                hits.append(candidate)
        result[label] = {
            "candidate_count": len(hits),
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
    for source in SOURCE_KEYS:
        values = [item["upstream_sources"][source] for item in trace]
        source_tick_counts[source] = sum(1 for value in values if value["candidate_count"] > 0)
        source_candidate_counts[source] = sum(value["candidate_count"] for value in values)

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
        "| Source | Ticks with candidates | Candidate instances |",
        "|---|---:|---:|",
    ]
    for source in SOURCE_KEYS:
        lines.append(f"| {source} | {source_tick_counts[source]} | {source_candidate_counts[source]} |")
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
    """Symlink/junction the already-computed Pass 198 stems into this run's
    project folder so demucs doesn't redo ~10 minutes of stem separation."""
    src = ROOT / "outputs" / "pass198_default_pipeline_reverify" / AUDIO_NAME / "stems"
    dst = OUTPUT_ROOT / AUDIO_NAME / "stems"
    if dst.exists() or not src.exists():
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

    _write_trace(trace)
    _summarise(trace, time.time() - started, pipeline_report)
    print(f"[PASS-203] ticks={len(trace)} trace={TRACE_PATH} report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
