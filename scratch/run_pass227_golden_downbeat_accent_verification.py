r"""PASS-227: independently verify the "golden" reference's own trustworthiness.

Context: every Pass 197-226 comparison in this whole investigation used
d:\...\World_is_Mine...\reports\measure_map.json as ground truth. Pass 219
already established this file is NOT independently human-annotated --
its generated_at timestamp predates commit 3f5827a (the first commit to
add module3_barstart_v2_bt.py), so it's a frozen snapshot of this
project's own LEGACY v1 pipeline output (commit ~793d8ba, 2026-07-29).
The user has never independently confirmed how much this "golden" can
actually be trusted -- every residual number reported across 8 passes
measures "how far V2 is from V1's own earlier guess", not "how far V2
is from the true downbeats".

This script runs an objective check that depends on NEITHER v1 NOR v2's
own logic: for every beat in golden's full measure_map (not just
downbeats -- beat 1/2/3/4 all have timestamps), sample librosa's onset
strength envelope (a raw acoustic accent measure) at each beat's time.
If golden's downbeat (beat==1) labeling is musically correct, beat-1
positions should show a systematically higher onset-strength accent
than beat-2/3/4 positions in the SAME measures (kick/bass emphasis on
the downbeat is standard in this genre). If that pattern holds cleanly
in Intro/Verse1 but breaks down in Chorus1/Outro (the two regions V2 has
been "drifting" in across this whole investigation), that's evidence
golden itself may be less reliable there -- reframing what "drift"
even means in those regions.

Uses the cached drums stem (cleaner rhythmic-accent signal than the
full mix) for onset strength.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import librosa
import numpy as np

GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
STEMS_DIR = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
DRUMS_PATH = os.path.join(STEMS_DIR, "drums", "drums.wav")
KICK_PATH = os.path.join(STEMS_DIR, "drums", "kick.wav")

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def main():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    measures = data["measure_map"]
    print(f"golden measure count: {len(measures)}")
    print(f"golden generated_at: {data.get('generated_at')}")
    print()

    def build_accent_fn(path, hop=256):
        y, sr = librosa.load(path, sr=22050, mono=True)
        rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

        def accent_at(t, window_sec=0.06):
            lo, hi = t - window_sec, t + window_sec
            mask = (times >= lo) & (times <= hi)
            if not np.any(mask):
                idx = int(np.argmin(np.abs(times - t)))
                return float(rms[idx])
            return float(np.max(rms[mask]))

        return accent_at

    print(f"[building accent signals] onset_strength(drums), RMS(kick isolated)...")
    y_drums, sr_d = librosa.load(DRUMS_PATH, sr=22050, mono=True)
    hop = 256
    onset_env = librosa.onset.onset_strength(y=y_drums, sr=sr_d, hop_length=hop)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr_d, hop_length=hop)

    def onset_accent_at(t, window_sec=0.06):
        lo, hi = t - window_sec, t + window_sec
        mask = (onset_times >= lo) & (onset_times <= hi)
        if not np.any(mask):
            idx = int(np.argmin(np.abs(onset_times - t)))
            return float(onset_env[idx])
        return float(np.max(onset_env[mask]))

    kick_accent_at = build_accent_fn(KICK_PATH)

    rows = []  # (segment, measure_num, beat, time, drums_onset_accent, kick_rms_accent)
    for m in measures:
        t0 = m["beats"][0]["time"] if m.get("beats") else m["start_time"]
        seg_name = next((name for name, s, e in SEGMENTS if s <= t0 < e), "?")
        for b in m.get("beats", []):
            rows.append((
                seg_name, m["measure"], b["beat"], b["time"],
                onset_accent_at(b["time"]), kick_accent_at(b["time"]),
            ))

    print(f"total beat samples: {len(rows)}")
    print()

    # Overall: beat 1 vs beat 2/3/4 accent comparison, for a given accent column
    def summarize(subset, label, col_idx, signal_name):
        by_beat = {1: [], 2: [], 3: [], 4: []}
        for row in subset:
            beat, acc = row[2], row[col_idx]
            if beat in by_beat:
                by_beat[beat].append(acc)
        print(f"--- {label} / signal={signal_name} (n={len(subset)}) ---")
        for beat in (1, 2, 3, 4):
            vals = by_beat[beat]
            if not vals:
                continue
            print(f"  beat {beat}: n={len(vals):>4} mean_accent={sum(vals)/len(vals):.4f}")
        by_measure = {}
        for row in subset:
            seg, mnum, beat = row[0], row[1], row[2]
            by_measure.setdefault((seg, mnum), {})[beat] = row[col_idx]
        wins = 0
        total = 0
        for key, beats in by_measure.items():
            if len(beats) < 4 or 1 not in beats:
                continue
            total += 1
            if beats[1] == max(beats.values()):
                wins += 1
        if total:
            print(f"  beat-1-is-loudest-in-its-own-measure: {wins}/{total} ({100*wins/total:.1f}%)")
        print()

    for col_idx, signal_name in ((4, "drums onset_strength"), (5, "kick RMS")):
        print(f"===== SIGNAL: {signal_name} =====")
        summarize(rows, "WHOLE SONG", col_idx, signal_name)
        for seg_name, _, _ in SEGMENTS:
            subset = [r for r in rows if r[0] == seg_name]
            summarize(subset, seg_name, col_idx, signal_name)


if __name__ == "__main__":
    raise SystemExit(main())
