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
GOLDEN_PATH = ROOT / "outputs" / "pass228_grounded_score_production_verify" / AUDIO_NAME / "reports" / "measure_map.json"


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


def main() -> int:
    if not AUDIO_PATH.exists():
        raise SystemExit(f"missing audio: {AUDIO_PATH}")
    reuse_stems_cache()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    started = time.time()
    blackboard = PGMCraftEngine(enable_stem_separation=True).run(
        str(AUDIO_PATH),
        output_dir=str(OUTPUT_ROOT),
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        barstart_v2_promotion_approved=True,
        madmom_hybrid_approved=True,
    )
    elapsed = time.time() - started

    golden_payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    golden = [float(item["start_time"]) for item in golden_payload["measure_map"]]
    calibration = json.loads((ROOT / "scratch" / "pass236_offline_calibration.json").read_text(encoding="utf-8"))
    sections = calibration["sections"]
    final_grid = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
    v2_grid = blackboard.get_val("barstart_v2_grid_beats")
    madmom_report = blackboard.get_val("madmom_hybrid_report", {})
    module3_report = blackboard.get_val("barstart_v2_report", {})
    output = {
        "pass": "Pass237 madmom hybrid production verify",
        "elapsed_sec": round(elapsed, 2),
        "madmom_hybrid_report": madmom_report,
        "barstart_v2_report": {
            "quality_score": module3_report.get("quality_score"),
            "quality_comparison": module3_report.get("quality_comparison"),
        },
        "segment_residuals": {
            "hybrid_final": nearest_residuals(downbeats(final_grid), golden, sections),
            "v2_fallback": nearest_residuals(downbeats(v2_grid), golden, sections),
        },
        "source_paths": {
            "requested_audio": str(AUDIO_PATH),
            "madmom_analysis_audio": madmom_report.get("audio_path"),
            "target_analysis_path": blackboard.get_val("target_analysis_path"),
        },
    }
    report_path = OUTPUT_ROOT / "pass237_production_verify.json"
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"wrote={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
