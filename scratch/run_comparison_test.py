import os
import sys
import json
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pgm_craft.pipeline import PGMCraftEngine

audio_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\source\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav"
output_dir = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass167"

os.makedirs(output_dir, exist_ok=True)

print("🚀 開始使用最新引擎 (Pass 155-167 修復版) 跑全流程對比測試...")
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
print(f"✅ 全流程對比測試執行完畢！耗時: {t1 - t0:.2f} 秒")

# 分析產出特徵
print("\n=== 新版 (Pass 167) 產出特徵分析 ===")
mmap = report.get("measure_map", [])
print(f"Total measures: {len(mmap)}")

if mmap:
    st_times = [m["start_time"] for m in mmap]
    intervals = np.diff(st_times)
    bpms = 60.0 / (intervals / 4.0)
    print(f"Time range: {st_times[0]:.3f}s ~ {mmap[-1]['end_time']:.3f}s")
    print(f"Interval median: {np.median(intervals):.4f}s (BPM median: {np.median(bpms):.2f})")
    print(f"Interval min: {np.min(intervals):.4f}s, max: {np.max(intervals):.4f}s, std: {np.std(intervals):.4f}s")

    print("\n前 10 個小節明細:")
    for m in mmap[:10]:
        st = m.get("start_time", 0.0)
        et = m.get("end_time", 0.0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"Measure {m.get('measure'):2d}: {st:6.3f}s ~ {et:6.3f}s | Duration: {dur:5.3f}s | BPM: {bpm:5.1f}")

# 輸出路徑提醒
click_path = os.path.join(output_dir, "click", "mix_with_click.wav")
print(f"\n🎧 原曲+Click 預聽檔位置: {click_path}")
