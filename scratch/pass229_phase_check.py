import json
import sys

sys.path.insert(0, ".")
from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = r"outputs\pass198_default_pipeline_reverify\\" + AUDIO_NAME + r"\source\\" + AUDIO_NAME + ".wav"

act = RNNDownBeatProcessor()(AUDIO_PATH)
dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100)
result = dbn(act)

GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"
with open(GOLDEN_PATH, encoding="utf-8") as f:
    golden = json.load(f)["measure_map"]

v1_start, v1_end = 25.813243, 86.907256
golden_v1_beats = []
for m in golden:
    for b in m.get("beats", []):
        if v1_start <= b["time"] < v1_end:
            golden_v1_beats.append((b["time"], b["beat"]))

madmom_v1 = [(round(float(t), 3), int(round(pos))) for t, pos in result if v1_start <= t < v1_end]

print("First 12 madmom (time, beat_pos_in_bar) in Verse1:")
for t, pos in madmom_v1[:12]:
    print(f"   {t:.3f}  pos={pos}")
print()
print("First 12 golden (time, beat_num) in Verse1:")
for t, b in golden_v1_beats[:12]:
    print(f"   {t:.3f}  beat={b}")
