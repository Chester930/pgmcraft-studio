"""PASS-231: generalization check for Pass 230's transition_lambda=500
finding. Since transition_lambda=500 was tuned directly against World is
Mine's own golden reference, it risks overfitting to that one song. No
golden reference exists for these new songs, so this generates listenable
click tracks (default lambda=100 vs the tuned lambda=500) for the user to
judge by ear -- the established gold-standard verification method in this
whole project ("the user's ears are more reliable than any single metric").

Downbeats get a higher-pitched, louder click; regular beats get a lower,
quieter one, mixed under the original track at reduced volume.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "outputs", "pass231_madmom_generalization_click_tracks")
SOURCE_DIR = r"d:\Users\666\Music\4K YouTube to MP3"

SONGS = [
    "planetboom   Praise On Praise   Official Music Video.mp3",
    "Sparkle   Your Name AMV.mp3",
]

LAMBDA_VALUES = [100, 500]


def _click_burst(sr, freq, dur=0.045, amp=0.9):
    t = np.arange(int(sr * dur)) / sr
    envelope = np.exp(-t * 35)
    return (amp * envelope * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_click_track(y, sr, downbeats, beats):
    out = y.copy()
    if out.ndim > 1:
        out = out.mean(axis=1)
    out = out * 0.35  # duck the original track under the clicks
    db_click = _click_burst(sr, 1500, amp=0.95)
    beat_click = _click_burst(sr, 900, amp=0.5)
    downbeat_set = set(round(t, 3) for t in downbeats)
    for t in beats:
        is_down = round(t, 3) in downbeat_set
        click = db_click if is_down else beat_click
        start = int(t * sr)
        end = min(len(out), start + len(click))
        if start >= len(out):
            continue
        out[start:end] += click[: end - start]
    peak = np.max(np.abs(out))
    if peak > 1.0:
        out = out / peak * 0.98
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

    for song in SONGS:
        src_path = os.path.join(SOURCE_DIR, song)
        if not os.path.exists(src_path):
            print(f"[PASS-231] skip, missing: {src_path}")
            continue
        base_name = os.path.splitext(song)[0].strip()
        print(f"[PASS-231] === {base_name} ===")
        print("[PASS-231] running RNNDownBeatProcessor activation...")
        act = RNNDownBeatProcessor()(src_path)

        y, sr = sf.read(src_path)

        for lam in LAMBDA_VALUES:
            print(f"[PASS-231] decoding with transition_lambda={lam}...")
            dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100, transition_lambda=lam)
            result = dbn(act)
            beats = sorted(set(round(float(t), 6) for t, _ in result))
            downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))
            print(f"[PASS-231]   {len(downbeats)} downbeats, {len(beats)} beats total")

            click_audio = make_click_track(y, sr, downbeats, beats)
            out_path = os.path.join(OUT_DIR, f"{base_name}_lambda{lam}_click.wav")
            sf.write(out_path, click_audio, sr)
            print(f"[PASS-231]   wrote {out_path}")

    print(f"[PASS-231] all outputs in: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
