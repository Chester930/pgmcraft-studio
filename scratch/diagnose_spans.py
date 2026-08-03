import json

gold_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\module3_pipeline_report.json"
new_path = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\comparison_test_pass167\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"

with open(gold_path, "r", encoding="utf-8") as f:
    gold_data = json.load(f)
gold_mmap = gold_data.get("measure_map", [])

with open(new_path, "r", encoding="utf-8") as f:
    raw_new = json.load(f)

if isinstance(raw_new, dict):
    new_mmap = raw_new.get("measure_map", [])
else:
    new_mmap = raw_new

def inspect_span(title, start_t, end_t):
    print(f"\n==================== {title} ({start_t}s ~ {end_t}s) ====================")
    g_measures = [m for m in gold_mmap if start_t <= m.get("start_time", 0) <= end_t]
    n_measures = [m for m in new_mmap if start_t <= m.get("start_time", 0) <= end_t]

    print(f"黃金版本 (Music/2) 數量: {len(g_measures)} 小節")
    for m in g_measures:
        st = m.get("start_time", 0)
        et = m.get("end_time", 0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  [Gold] M{m.get('measure'):3d}: {st:6.3f}s ~ {et:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")

    print(f"\n新版本 (Pass 167) 數量: {len(n_measures)} 小節")
    for m in n_measures:
        st = m.get("start_time", 0)
        et = m.get("end_time", 0)
        dur = et - st
        bpm = 60.0 / (dur / 4.0) if dur > 0 else 0
        print(f"  [New ] M{m.get('measure'):3d}: {st:6.3f}s ~ {et:6.3f}s | dur: {dur:5.3f}s | BPM: {bpm:5.1f}")

# 診斷區段 1: 0s ~ 32s (不行)
inspect_span("不行的區段 1: 前奏~主歌開頭", 0.0, 32.0)

# 診斷區段 2: 32s ~ 95s (還行)
inspect_span("還行的區段 1: 主歌~副歌", 32.0, 50.0)

# 診斷區段 3: 95s ~ 125s (1m35s ~ 2m05s 不行)
inspect_span("不行的區段 2: 間奏段落 (1m35s ~ 2m05s)", 95.0, 125.0)
