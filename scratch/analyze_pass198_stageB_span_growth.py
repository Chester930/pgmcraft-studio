r"""
Pass 198 階段 B 獨立驗證——量化「forced_44_interpolation_weak_evidence」
觸發的規模與範圍。用來確認階段 B 是否只在少數已知弱證據段落插值，還是
（如這次真實資料顯示）幾乎覆蓋全曲。
"""

import json

MEASURE_MAP_PATH = (
    r"outputs\pass198_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\reports\measure_map.json"
)
BEAT_SEC = 0.364671


def main():
    with open(MEASURE_MAP_PATH, encoding="utf-8") as f:
        data = json.load(f)

    recs = data["phase_reconciliation"]
    weak = [r for r in recs if "weak_evidence" in r["reason"]]

    print(f"phase_reconciliation 總決策數: {len(recs)}")
    print(f"其中 forced_44_interpolation_weak_evidence（階段 B）: {len(weak)}")
    if weak:
        span_start, span_end = weak[0]["anchor_time"], weak[-1]["interpolated_time"]
        print(f"覆蓋範圍: {span_start:.3f}s - {span_end:.3f}s")

    print("\n逐筆原始間隔（拍）:")
    for r in weak:
        span_beats = (r["next_anchor_time"] - r["anchor_time"]) / BEAT_SEC
        print(
            f"  anchor={r['anchor_time']:8.3f}s next_anchor={r['next_anchor_time']:8.3f}s "
            f"span_beats={span_beats:6.3f} interpolated={r['interpolated_time']:8.3f}s "
            f"reason={r['reason']}"
        )


if __name__ == "__main__":
    main()
