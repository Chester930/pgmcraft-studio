"""
Pass 172 — Stage 3 BeatNet 決定性驗證

目的：確認 pgm_craft.determinism.enable_deterministic_mode() 是否真的能讓
BeatNetNode_TrackA 對同一份音訊重複跑出完全相同的拍點，藉此判斷 Pass 171 量到的
「119 vs 黃金版 121 小節」落差，是可修的程式碼回歸，還是黃金版本身就是一次
（Pass 155 決定性模式導入之前的）不可重現的隨機結果。

用法：
    python scratch/pass172_beatnet_determinism_check.py

不需要重跑分軌 —— 直接對黃金專案已經合成好的 Stage 3 節奏骨幹軌
(stems/submix/track_a_rhythm.wav，也就是 BeatNetNode_TrackA 的確切輸入) 跑兩次
BeatNet DBN 推論並比較結果。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.determinism import enable_deterministic_mode, compare_beat_outputs

RHYTHM_TRACK_PATH = (
    r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\stems\submix\track_a_rhythm.wav"
)


def run_beatnet_once(target_path: str):
    from BeatNet.BeatNet import BeatNet
    estimator = BeatNet(1, mode="offline", inference_model="DBN", plot=[], thread=False)
    return estimator.process(target_path)


def main():
    if not os.path.exists(RHYTHM_TRACK_PATH):
        print(f"[FATAL] 找不到黃金專案的節奏骨幹軌：{RHYTHM_TRACK_PATH}")
        sys.exit(1)

    report = enable_deterministic_mode()
    print(f"determinism report: {report}")

    print(f"\n[Run 1] BeatNet DBN on {RHYTHM_TRACK_PATH} ...")
    t0 = time.time()
    output1 = run_beatnet_once(RHYTHM_TRACK_PATH)
    print(f"Run 1: {len(output1)} beats ({time.time() - t0:.1f}s)")

    print(f"\n[Run 2] BeatNet DBN on {RHYTHM_TRACK_PATH} (same process, same seed) ...")
    t0 = time.time()
    output2 = run_beatnet_once(RHYTHM_TRACK_PATH)
    print(f"Run 2: {len(output2)} beats ({time.time() - t0:.1f}s)")

    result = compare_beat_outputs(output1, output2)
    print(f"\nbeat count match: {result['count_match']}")
    print(f"max per-beat timestamp delta: "
          f"{result['max_delta_sec'] if result['max_delta_sec'] is not None else 'N/A (count mismatch)'} sec")

    if result["verdict"] == "DETERMINISTIC":
        print("VERDICT: DETERMINISTIC — 兩次跑出的拍點數與時間戳完全一致")
    elif result["verdict"] == "MOSTLY_DETERMINISTIC":
        print(f"VERDICT: MOSTLY DETERMINISTIC — 拍點數一致，但時間戳有 "
              f"{result['max_delta_sec']*1000:.2f}ms 的微小差異")
    else:
        print(f"VERDICT: NON-DETERMINISTIC — 拍點數不一致 ({result['count1']} vs {result['count2']})，"
              "enable_deterministic_mode() 未能消除 GPU 推論的隨機性")


if __name__ == "__main__":
    main()
