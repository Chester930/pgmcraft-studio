r"""Pass 211 follow-up: cross-check V2's 41 Chorus-1 bar starts (86.9-148.0s)
against the golden reference's 42 bar starts, both against real drum onsets
independently detected from the cached stems (not against each other's
labels -- the onsets are the actual ground truth).

For each bar index i, compare how close V2's bar[i] and golden's bar[i] each
land to the nearest real onset. This should reveal which specific bars in
this stretch V2 timed slightly long (worse onset match than golden), letting
the 1-bar cumulative deficit in this segment be pinned to the responsible
bar(s) instead of the whole 42-bar span.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEMS_DIR = os.path.join(
    ROOT, "outputs", "pass203_evidence_fusion_diagnosis",
    "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】", "stems",
)
GOLDEN_REPORT = (
    r"D:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\reports\module3_pipeline_report.json"
)
V2_REPORT = os.path.join(
    ROOT, "outputs", "pass211_promoted_production_verify",
    "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】",
    "reports", "module3_beat_click_report.json",
)

CHORUS_START = 86.907256
CHORUS_END = 147.977778


def load_onsets():
    node = SteadyPercussionCountAnchorNode()
    all_onsets = []
    for stem_key, rel in node.STEM_CANDIDATES + [node.WHOLE_DRUM_STEM]:
        path = os.path.join(STEMS_DIR, *rel)
        if not os.path.exists(path):
            continue
        for t in node._detect_onsets(path):
            all_onsets.append((stem_key, float(t)))
    return all_onsets


def nearest_onset(onsets, t, window=0.35):
    candidates = [(stem, abs(o - t), o) for stem, o in onsets if abs(o - t) <= window]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[1])


def main():
    onsets = load_onsets()
    print(f"total onsets loaded: {len(onsets)}")

    golden = json.load(open(GOLDEN_REPORT, encoding="utf-8"))
    golden_bars = [t for t in [m["start_time"] for m in golden["measure_map"]]
                   if CHORUS_START <= t < CHORUS_END]

    v2 = json.load(open(V2_REPORT, encoding="utf-8"))
    v2_bars = [t for t in v2["barstart_v2_report"]["committed_bar_starts"]
               if CHORUS_START <= t < CHORUS_END]

    print(f"golden bars in Chorus 1: {len(golden_bars)}")
    print(f"v2 bars in Chorus 1: {len(v2_bars)}")
    print()

    print(f"{'idx':>3} {'golden_t':>10} {'g_match':>8} {'g_dist_ms':>9}   "
          f"{'v2_t':>10} {'v2_match':>9} {'v2_dist_ms':>10}   flag")
    n = max(len(golden_bars), len(v2_bars))
    worse_count = 0
    for i in range(n):
        g_t = golden_bars[i] if i < len(golden_bars) else None
        v_t = v2_bars[i] if i < len(v2_bars) else None
        g_near = nearest_onset(onsets, g_t) if g_t is not None else None
        v_near = nearest_onset(onsets, v_t) if v_t is not None else None
        g_dist = g_near[1] * 1000 if g_near else None
        v_dist = v_near[1] * 1000 if v_near else None
        flag = ""
        if g_dist is not None and v_dist is not None and v_dist - g_dist > 60:
            flag = "<-- V2 worse onset match"
            worse_count += 1
        elif g_dist is not None and v_dist is not None and g_dist - v_dist > 60:
            flag = "<-- golden worse onset match"
        print(
            f"{i:3d} {g_t if g_t is not None else float('nan'):10.4f} "
            f"{(g_near[0] if g_near else '-'):>8} {g_dist if g_dist is not None else -1:9.1f}   "
            f"{v_t if v_t is not None else float('nan'):10.4f} "
            f"{(v_near[0] if v_near else '-'):>9} {v_dist if v_dist is not None else -1:10.1f}   {flag}"
        )
    print()
    print(f"bars where V2 has a meaningfully worse onset match than golden (>60ms): {worse_count}")


if __name__ == "__main__":
    main()
