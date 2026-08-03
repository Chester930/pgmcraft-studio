import os
import sys
import json
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pgm_craft.pipeline import PGMCraftEngine

audio_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\source\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav"
output_dir = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass168"

os.makedirs(output_dir, exist_ok=True)

print("🚀 開始執行 Pass 168 雙向確信錨點反推引擎測試...")
t0 = time.time()

engine = PGMCraftEngine(enable_stem_separation=True)
report = engine.run(
    audio_path,
    output_dir=output_dir,
    enable_stem=True,
    target_stage="full",
    user_meter_selection="4/4",
    allow_temporary_bar_delta=0,
)

t1 = time.time()
print(f"✅ Pass 168 對比測試執行完畢！耗時: {t1 - t0:.2f} 秒")

# 分析修復結果
mmap = report.get("measure_map", [])
gold_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\module3_pipeline_report.json"
with open(gold_path, "r", encoding="utf-8") as f:
    gold_mmap = json.load(f).get("measure_map", [])

def print_span(title, start_t, end_t):
    print(f"\n==================== {title} ({start_t}s ~ {end_t}s) ====================")
    n_measures = [m for m in mmap if start_t <= m.get("start_time", 0) <= end_t]
    print(f"Pass 168 雙向反推修復後小節數: {len(n_measures)}")
    for m in n_measures:
        st = m.get("start_time", 0)
        et = m.get("end_time", 0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  [Pass168] M{m.get('measure'):3d}: {st:6.3f}s ~ {et:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")

print_span("先前不行的區段 1: 前奏~主歌開頭", 0.0, 32.0)
print_span("先前不行的區段 2: 間奏段落 (1m35s ~ 2m05s)", 95.0, 125.0)

click_path = os.path.join(output_dir, "click", "mix_with_click.wav")
print(f"\n🎧 Pass 168 最新原曲+Click 預聽檔: {click_path}")
