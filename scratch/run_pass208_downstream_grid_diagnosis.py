"""PASS-208: instrument the downstream BarStart V2 grid stages.

This is an audit-only wrapper around the clean Pass-207 production run.  It
monkeypatches only node ``execute`` methods for the duration of this process,
records before/after snapshots, restores every method in ``finally``, and
leaves production code untouched.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.pipeline import PGMCraftEngine

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass208_downstream_grid_diagnosis")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
TRACE_PATH = os.path.join(ROOT, "scratch", "pass208_downstream_grid_trace.jsonl")
REPORT_PATH = os.path.join(ROOT, "scratch", "pass208_downstream_grid_diagnosis.json")


def safe_name(title):
    return re.sub(r"\s+", "_", re.sub(r'[\\/*?:"<>|]', "", title).strip())[:120]


def reuse_stems_cache():
    dst = os.path.join(OUTPUT_ROOT, AUDIO_NAME, "stems")
    if os.path.exists(dst) or not os.path.exists(STEMS_SOURCE):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.symlink(STEMS_SOURCE, dst, target_is_directory=True)
    except OSError:
        import subprocess

        subprocess.run(["cmd", "/c", "mklink", "/J", dst, STEMS_SOURCE], capture_output=True, text=True, check=False)


def _bar_times(raw):
    out = []
    for item in raw or []:
        try:
            value = item.get("time") if isinstance(item, dict) else item
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _snapshot(raw):
    bars = _bar_times(raw)
    intervals = [round(bars[i] - bars[i - 1], 6) for i in range(1, len(bars))]
    return {
        "bar_count": len(bars),
        "bars": [round(value, 6) for value in bars],
        "intervals": intervals,
        "short_intervals_lt_0_5": [
            {"index": i, "start": bars[i], "end": bars[i + 1], "interval": intervals[i]}
            for i in range(len(intervals))
            if intervals[i] < 0.5
        ],
        "large_intervals_gt_2_5": [
            {"index": i, "start": bars[i], "end": bars[i + 1], "interval": intervals[i]}
            for i in range(len(intervals))
            if intervals[i] > 2.5
        ],
    }


def install_stage_probe(trace):
    from pgm_craft.workflow import module3_barstart_v2_bt as v2
    from pgm_craft.workflow import beat_tracking_bt

    targets = [
        (v2.TwoWayAnchorBacktraceNode, "TwoWayAnchorBacktraceNode"),
        (v2.GroovePatternPhaseDecoderNode, "GroovePatternPhaseDecoderNode"),
        (v2.BarGridSanityPrunerNode, "BarGridSanityPrunerNode"),
        (v2.BarGridContinuityRepairNode, "BarGridContinuityRepairNode"),
        (v2.BarStartTempoSmoothingNode, "BarStartTempoSmoothingNode"),
        (v2.MeterAwareBeatGridNode, "MeterAwareBeatGridNode"),
        (beat_tracking_bt.KickBassDownbeatVerifierNode, "KickBassDownbeatVerifierNode"),
    ]
    originals = []
    occurrence = {}

    for cls, stage in targets:
        original = cls.execute
        originals.append((cls, original))

        def wrapped(self, blackboard, _original=original, _stage=stage):
            run_id = blackboard.get_val("barstart_v2_run_id")
            if not run_id:
                return _original(self, blackboard)
            occurrence[_stage] = occurrence.get(_stage, 0) + 1
            before = _snapshot(blackboard.get_val("committed_bar_starts", []))
            status = _original(self, blackboard)
            after = _snapshot(blackboard.get_val("committed_bar_starts", []))
            trace.append({
                "run_id": run_id,
                "stage": _stage,
                "occurrence": occurrence[_stage],
                "status": getattr(status, "value", str(status)),
                "before": before,
                "after": after,
                "repair_report": blackboard.get_val("bar_grid_repair_report", {}),
                "sanity_report": blackboard.get_val("bar_grid_sanity_report", {}),
            })
            return status

        cls.execute = wrapped

    def restore():
        for cls, original in originals:
            cls.execute = original

    return restore


def _first_stage_for_signature(events, signature_key, target):
    for event in events:
        if event.get("stage") not in target:
            continue
        if event.get("after", {}).get(signature_key):
            return {
                "stage": event["stage"],
                "occurrence": event["occurrence"],
                "items": event["after"][signature_key],
            }
    return None


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-208] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    trace = []
    restore = install_stage_probe(trace)
    started = time.time()
    try:
        report = PGMCraftEngine(enable_stem_separation=True).run(
            AUDIO_PATH,
            output_dir=OUTPUT_ROOT,
            enable_stem=True,
            target_stage="module3",
            user_meter_selection="4/4",
            allow_temporary_bar_delta=0,
        )
    finally:
        restore()

    project_dir = os.path.join(OUTPUT_ROOT, safe_name(AUDIO_NAME))
    click_report_path = os.path.join(project_dir, "reports", "module3_beat_click_report.json")
    with open(click_report_path, encoding="utf-8") as handle:
        full_report = json.load(handle)
    v2_report = full_report.get("barstart_v2_report", {})
    loop_report = v2_report.get("full_song_loop_report", {}) or {}
    loop_snapshot = _snapshot(loop_report.get("loop_committed_bar_starts", []))
    final_snapshot = _snapshot(v2_report.get("committed_bar_starts", []))
    events = trace
    output = {
        "pass": "Pass 208 downstream grid diagnosis",
        "elapsed_sec": round(time.time() - started, 3),
        "click_report_path": click_report_path,
        "stage_trace_path": TRACE_PATH,
        "loop_before_postprocess": loop_snapshot,
        "final_committed_bar_starts": final_snapshot,
        "stage_events": len(events),
        "events": events,
        "first_stage_with_short_intervals": _first_stage_for_signature(
            events, "short_intervals_lt_0_5", {"BarGridContinuityRepairNode", "BarStartTempoSmoothingNode", "MeterAwareBeatGridNode", "KickBassDownbeatVerifierNode"}
        ),
        "first_stage_with_large_intervals": _first_stage_for_signature(
            events, "large_intervals_gt_2_5", {"BarGridContinuityRepairNode", "BarStartTempoSmoothingNode", "MeterAwareBeatGridNode", "KickBassDownbeatVerifierNode"}
        ),
        "barstart_v2_report": {
            "status": v2_report.get("status"),
            "promotion_gate": v2_report.get("promotion_gate"),
            "quality_comparison": v2_report.get("quality_comparison"),
            "state_consistency": v2_report.get("state_consistency"),
        },
        "pipeline_status": report.get("status"),
    }
    with open(TRACE_PATH, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[PASS-208] report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
