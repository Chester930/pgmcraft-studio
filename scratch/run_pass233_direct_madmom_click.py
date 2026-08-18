"""Pass 233: direct full-song madmom click, with no BarStart v2 arbitration."""

from __future__ import annotations

import json
import os
import shutil
import sys

from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.synthesizer import PGMSynthesizer


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME,
    "source", AUDIO_NAME + ".wav",
)
BACKING_PATH = os.path.join(
    ROOT, "outputs", "pass228_grounded_score_production_verify", AUDIO_NAME,
    "stems", "no_vocals.wav",
)
OUTPUT_DIR = os.path.join(ROOT, "outputs", "pass233_direct_madmom", AUDIO_NAME)
GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"
SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse1", 25.813243, 86.907256),
    ("Chorus1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    activations = RNNDownBeatProcessor()(AUDIO_PATH)
    result = DBNDownBeatTrackingProcessor(
        beats_per_bar=[4], fps=100, transition_lambda=500
    )(activations)
    beats = [(round(float(time_sec), 6), int(round(position))) for time_sec, position in result]

    click_source = BACKING_PATH if os.path.exists(BACKING_PATH) else AUDIO_PATH
    click_path, mix_path = PGMSynthesizer().synthesize_click(
        click_source,
        beats,
        output_dir=OUTPUT_DIR,
        prepend_count_in_bar=False,
    )
    direct_click = os.path.join(OUTPUT_DIR, "direct_madmom_click_track.wav")
    direct_mix = os.path.join(OUTPUT_DIR, "direct_madmom_mix_with_click.wav")
    shutil.copy2(click_path, direct_click)
    shutil.copy2(mix_path, direct_mix)

    with open(GOLDEN_PATH, encoding="utf-8") as handle:
        golden_downbeats = [float(item["start_time"]) for item in json.load(handle)["measure_map"]]
    downbeats = [time_sec for time_sec, position in beats if position == 1]
    segments = []
    for name, start, end in SEGMENTS:
        golden = [value for value in golden_downbeats if start <= value < end]
        residuals = [
            min((candidate - value for candidate in downbeats), key=abs)
            for value in golden
            if downbeats
        ]
        segments.append({
            "segment": name,
            "golden_count": len(golden),
            "mean_abs_residual_sec": round(sum(abs(value) for value in residuals) / len(residuals), 4) if residuals else None,
            "within_50ms": sum(abs(value) <= 0.05 for value in residuals),
            "matched": len(residuals),
        })

    report = {
        "mode": "direct_madmom_dbn_no_barstart_v2_arbitration",
        "transition_lambda": 500,
        "beat_count": len(beats),
        "downbeat_count": len(downbeats),
        "segments": segments,
        "click_source": click_source,
        "direct_click_track": direct_click,
        "direct_mix_with_click": direct_mix,
    }
    report_path = os.path.join(OUTPUT_DIR, "direct_madmom_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
