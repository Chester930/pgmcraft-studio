"""
測試 Pass 193 相位連貫 4/4 重排效果
"""

import json
import glob

matches = glob.glob(r"outputs/pass192_default_pipeline_reverify/**/reports/measure_map.json", recursive=True)
if not matches:
    print("找不到 measure_map.json")
    exit(1)

path = matches[0]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

m_map = data.get("measure_map", [])
beat_grid = []
for m in m_map:
    beat_grid.extend(m.get("beats", []))
print(f"總拍點數：{len(beat_grid)}")

# 連貫 1-2-3-4 重標號模擬
# 找出第一個 beat == 1 的索引
first_db_idx = 0
for idx, b in enumerate(beat_grid):
    if b.get("beat") == 1:
        first_db_idx = idx
        break

print(f"第一個 Downbeat 索引：{first_db_idx}")

# 順向重標號
new_beats = [dict(b) for b in beat_grid]
for i in range(first_db_idx, len(new_beats)):
    if i == first_db_idx:
        new_beats[i]["beat"] = 1
    else:
        new_beats[i]["beat"] = ((new_beats[i-1]["beat"] - 1 + 1) % 4) + 1

# 逆向重標號
for i in range(first_db_idx - 1, -1, -1):
    new_beats[i]["beat"] = ((new_beats[i+1]["beat"] - 1 - 1) % 4) + 1

# 計算小節切分
db_idxs = [i for i, b in enumerate(new_beats) if b["beat"] == 1]
print(f"重新劃分的 Downbeat 數量：{len(db_idxs)}")

m_counts = []
for k in range(len(db_idxs)):
    n_idx = db_idxs[k+1] if k+1 < len(db_idxs) else len(new_beats)
    m_counts.append(n_idx - db_idxs[k])

print(f"劃分出的小節總數：{len(m_counts)}")
print("小節拍數分布：", set(m_counts))
