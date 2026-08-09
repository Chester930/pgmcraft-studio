"""
測試 Pass 192 過長小節拆分與不膨脹合併新邏輯
"""

import json
import glob

matches = glob.glob(r"outputs/pass191_default_pipeline_reverify/**/measure_map.json", recursive=True)
if not matches:
    print("找不到 measure_map.json")
    exit(1)

path = matches[0]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])
common_length = 4

print("原始不規則小節數：", sum(1 for m in m_map if m.get("is_variable_length")))

# 模擬 Pass 192 拆分過長小節 (5, 6, 7 拍拆分成 4 拍 + 剩餘)
new_measures = []
for m in m_map:
    beats = m.get("beats", [])
    b_count = len(beats)
    if b_count > common_length and not m.get("is_incomplete"):
        # 拆分：前 common_length 拍為一個標準小節
        m1_beats = beats[:common_length]
        m1 = {
            "measure": len(new_measures) + 1,
            "start_time": m1_beats[0]["time"],
            "end_time": beats[common_length]["time"] if len(beats) > common_length else m["end_time"],
            "beat_count": common_length,
            "beats": [{"beat": j+1, "time": b["time"]} for j, b in enumerate(m1_beats)],
            "is_variable_length": False,
            "is_incomplete": False,
            "source": m.get("source"),
        }
        new_measures.append(m1)

        rem_beats = beats[common_length:]
        if rem_beats:
            m2 = {
                "measure": len(new_measures) + 1,
                "start_time": rem_beats[0]["time"],
                "end_time": m["end_time"],
                "beat_count": len(rem_beats),
                "beats": [{"beat": j+1, "time": b["time"]} for j, b in enumerate(rem_beats)],
                "is_variable_length": len(rem_beats) != common_length,
                "is_incomplete": False,
                "source": m.get("source"),
            }
            new_measures.append(m2)
    else:
        m["measure"] = len(new_measures) + 1
        new_measures.append(m)

print(f"拆分後總小節數：{len(new_measures)}")
print("拆分後不規則小節數：", sum(1 for m in new_measures if m.get("is_variable_length")))

# 模擬新 _merge_short_measures（不膨脹標準小節，或只併入未滿 4 拍小節）
final_measures = []
for m in new_measures:
    if final_measures and m["beat_count"] < common_length and not m.get("is_incomplete"):
        prev = final_measures[-1]
        # 只有在 prev 也是短小節 (beat_count < common_length) 時才進行合併！
        if prev["beat_count"] < common_length and prev["beat_count"] + m["beat_count"] <= common_length:
            merged_count = prev["beat_count"] + m["beat_count"]
            merged_beats = prev["beats"] + [{"beat": prev["beat_count"] + j + 1, "time": b["time"]} for j, b in enumerate(m["beats"])]
            final_measures[-1] = {
                "measure": prev["measure"],
                "start_time": prev["start_time"],
                "end_time": m["end_time"],
                "beat_count": merged_count,
                "beats": merged_beats,
                "is_variable_length": merged_count != common_length,
                "is_incomplete": prev.get("is_incomplete", False),
                "source": prev.get("source"),
            }
            continue
    final_measures.append(m)

# 重新編號
for idx, m in enumerate(final_measures):
    m["measure"] = idx + 1

irreg_final = [m for m in final_measures if m.get("is_variable_length")]
print(f"\n最終模擬結果：")
print(f"  總小節數：{len(final_measures)}")
print(f"  不規則小節數：{len(irreg_final)}")
for m in irreg_final:
    print(f"  不規則小節 #{m['measure']}: beat_count={m['beat_count']}, start={m['start_time']}s, end={m['end_time']}s")
