import json
import sys

sys.path.insert(0, ".")
from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = r"outputs\pass198_default_pipeline_reverify\\" + AUDIO_NAME + r"\source\\" + AUDIO_NAME + ".wav"

act = RNNDownBeatProcessor()(AUDIO_PATH)
dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100)
result = dbn(act)
downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))

GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"
with open(GOLDEN_PATH, encoding="utf-8") as f:
    golden = json.load(f)["measure_map"]
golden_downbeats = [float(m["start_time"]) for m in golden]

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]

# Nearest-neighbor matching: for each golden downbeat, find the closest madmom
# downbeat (no index-alignment boundary artifact).
for name, start, end in SEGMENTS:
    g_seg = [g for g in golden_downbeats if start <= g < end]
    residuals = []
    unmatched = 0
    for g in g_seg:
        if not downbeats:
            unmatched += 1
            continue
        nearest = min(downbeats, key=lambda d: abs(d - g))
        residuals.append(nearest - g)
    n = len(residuals)
    mean_abs = sum(abs(r) for r in residuals) / n if n else None
    max_abs = max((abs(r) for r in residuals), default=None)
    within_50ms = sum(1 for r in residuals if abs(r) <= 0.05)
    print(f"{name:>10}: golden={len(g_seg):>3} mean_abs={mean_abs:.4f} max_abs={max_abs:.4f} within_50ms={within_50ms}/{n}")
