"""Pass237 production verification for the opt-in madmom hybrid output."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pgm_craft.pipeline import PGMCraftEngine


AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = ROOT / "outputs" / "pass198_default_pipeline_reverify" / AUDIO_NAME / "source" / f"{AUDIO_NAME}.wav"
OUTPUT_ROOT = ROOT / "outputs" / "pass237_madmom_hybrid_production_verify"
STEMS_SOURCE = ROOT / "outputs" / "pass203_evidence_fusion_diagnosis" / AUDIO_NAME / "stems"
# Pass238 finding: outputs/pass228_.../measure_map.json is NOT golden -- it's
# the legacy MeasureMapNode's own output (unrelated to BarStart V2/madmom,
# byte-identical across pipeline runs since nothing touches that code path).
# The real golden lives outside the repo; only fall back to the legacy copy
# if that external path is unavailable in this environment.
GOLDEN_PATH = Path(r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json")
LOCAL_GOLDEN_PATH = ROOT / "outputs" / "pass228_grounded_score_production_verify" / AUDIO_NAME / "reports" / "measure_map.json"


def safe_name(title: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r'[\*?:"<>|]', "", title).strip())[:120]


def reuse_stems_cache() -> None:
    destination = OUTPUT_ROOT / AUDIO_NAME / "stems"
    if destination.exists() or not STEMS_SOURCE.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.symlink_to(STEMS_SOURCE, target_is_directory=True)
    except OSError:
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(destination), str(STEMS_SOURCE)],
            capture_output=True,
            text=True,
            check=False,
        )


def downbeats(grid):
    rows = []
    for row in grid if grid is not None else []:
        if len(row) < 2 or abs(float(row[1]) - 1.0) < 1e-6:
            rows.append(float(row[0]))
    return rows


def nearest_residuals(candidate, golden, sections):
    result = {}
    for name, (start, end) in sections.items():
        reference = [value for value in golden if start <= value <= end]
        values = [value for value in candidate if start - 1.0 <= value <= end + 1.0]
        residuals = [min(abs(value - other) for other in values) for value in reference if values]
        result[name] = {
            "golden_count": len(reference),
            "mean_abs_residual_sec": round(sum(residuals) / len(residuals), 4) if residuals else None,
            "within_50ms": sum(value <= 0.05 for value in residuals),
        }
    return result


def load_golden() -> list[float]:
    path = GOLDEN_PATH if GOLDEN_PATH.exists() else LOCAL_GOLDEN_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [float(item["start_time"]) for item in payload["measure_map"]]


def reconstruct_final_downbeats(madmom_hybrid_report: dict, v2_downbeats: list[float]) -> list[float]:
    """Re-derive the true final downbeat set from the splice report + V2
    fallback, since PGMCraftEngine.run()'s returned summary dict does not
    carry the post-splice grid (only Module3OutputSummaryNode's own
    module3_beat_click_report.json does, and even that has no flat downbeat
    array -- only the per-span edit list)."""
    from pgm_craft.workflow.madmom_hybrid import _run_madmom_dbn, _downbeat_times

    audio_path = madmom_hybrid_report.get("audio_path")
    transition_lambda = int(madmom_hybrid_report.get("transition_lambda", 500))
    grid = _run_madmom_dbn(audio_path, transition_lambda=transition_lambda)
    madmom_downbeats = _downbeat_times(grid)
    trim_offset = float(madmom_hybrid_report.get("trim_offset_sec", 0.0) or 0.0)
    if trim_offset:
        madmom_downbeats = [value + trim_offset for value in madmom_downbeats]

    removed = set()
    inserted = []
    for span in madmom_hybrid_report.get("replaced_spans", []):
        removed.update(span.get("madmom_removed_downbeats", []))
        inserted.extend(span.get("fallback_inserted_downbeats", []))
    final = sorted(v for v in madmom_downbeats if v not in removed) + inserted
    return sorted(final)


def main() -> int:
    if not AUDIO_PATH.exists():
        raise SystemExit(f"missing audio: {AUDIO_PATH}")
    reuse_stems_cache()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    started = time.time()
    # PGMCraftEngine.run() returns the pgm_report.json summary dict, NOT the
    # raw Blackboard -- and that summary dict does not even carry
    # madmom_hybrid_report (only Module3OutputSummaryNode's separate
    # module3_beat_click_report.json does). Read that file from disk after
    # the run instead of relying on the return value for hybrid-specific data.
    PGMCraftEngine(enable_stem_separation=True).run(
        str(AUDIO_PATH),
        output_dir=str(OUTPUT_ROOT),
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        barstart_v2_promotion_approved=True,
        madmom_hybrid_approved=True,
    )
    elapsed = time.time() - started

    click_report_path = OUTPUT_ROOT / AUDIO_NAME / "reports" / "module3_beat_click_report.json"
    click_report = json.loads(click_report_path.read_text(encoding="utf-8"))
    madmom_report = click_report.get("madmom_hybrid_report", {})
    barstart_v2_report = click_report.get("barstart_v2_report", {})
    v2_downbeats = barstart_v2_report.get("committed_bar_starts", [])

    golden = load_golden()
    calibration = json.loads((ROOT / "scratch" / "pass236_offline_calibration.json").read_text(encoding="utf-8"))
    sections = calibration["sections"]

    final_downbeats = reconstruct_final_downbeats(madmom_report, v2_downbeats)

    output = {
        "pass": "Pass237/238/239 madmom hybrid production verify",
        "elapsed_sec": round(elapsed, 2),
        "golden_path_used": str(GOLDEN_PATH if GOLDEN_PATH.exists() else LOCAL_GOLDEN_PATH),
        "golden_count": len(golden),
        "madmom_hybrid_report": madmom_report,
        "barstart_v2_report": {
            "status": barstart_v2_report.get("status"),
            "quality_comparison": barstart_v2_report.get("quality_comparison"),
        },
        "segment_residuals": {
            "hybrid_final": nearest_residuals(final_downbeats, golden, sections),
            "v2_fallback": nearest_residuals(v2_downbeats, golden, sections),
        },
        "source_paths": {
            "requested_audio": str(AUDIO_PATH),
            "madmom_analysis_audio": madmom_report.get("audio_path"),
        },
    }
    report_path = OUTPUT_ROOT / "pass237_production_verify.json"
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"wrote={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
