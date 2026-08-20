"""
Pass 174 — 驗證 Demucs 分軌決定性修復（reseed_for_inference）

Pass 173 證實 CascadedStemSeparator._demucs_separate() 呼叫 apply_model() 時吃
demucs 套件預設的 shifts=1，導致同一份輸入音訊每次重新分離都不是同一份
(max_abs_diff=0.234)。Pass 174 在呼叫前加了 reseed_for_inference()，本腳本驗證
修復後、走真實程式碼路徑（CascadedStemSeparator._demucs_separate()，不是繞過
快取直接呼叫 apply_model()）連續兩次分離是否變成 bit-exact。

用法：
    python scratch/pass174_demucs_reseed_fix_verification.py

會在 CLAUDE_JOB_DIR/tmp 或系統暫存目錄下建立兩個獨立的 output_dir（不同路徑，
繞開 CascadedStemSeparator 內建的 (path, size, model, output_dir) 快取鍵，
逼出兩次真正獨立的推論），逼真模擬「同一首歌重新分離兩次」的情境。
"""

import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.determinism import enable_deterministic_mode, compare_audio_arrays
from pgm_craft.separator import CascadedStemSeparator

DENOISED_SOURCE_PATH = (
    r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\source\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】_denoised.wav"
)


def main():
    if not os.path.exists(DENOISED_SOURCE_PATH):
        print(f"[FATAL] 找不到黃金專案的 denoised 來源音訊：{DENOISED_SOURCE_PATH}")
        sys.exit(1)

    report = enable_deterministic_mode()
    print(f"determinism report: {report}\n")

    tmp_root = tempfile.mkdtemp(prefix="pass174_demucs_reseed_check_")
    out_dir_1 = os.path.join(tmp_root, "run1")
    out_dir_2 = os.path.join(tmp_root, "run2")
    os.makedirs(out_dir_1, exist_ok=True)
    os.makedirs(out_dir_2, exist_ok=True)

    sep = CascadedStemSeparator()

    print(f"[Run 1] _demucs_separate -> {out_dir_1}")
    t0 = time.time()
    paths1 = sep._demucs_separate(DENOISED_SOURCE_PATH, out_dir_1, "htdemucs_ft", {"drums", "bass"})
    print(f"  done in {time.time() - t0:.1f}s -> {paths1}")

    print(f"\n[Run 2] _demucs_separate -> {out_dir_2} (different output_dir, 繞開內建快取)")
    t0 = time.time()
    paths2 = sep._demucs_separate(DENOISED_SOURCE_PATH, out_dir_2, "htdemucs_ft", {"drums", "bass"})
    print(f"  done in {time.time() - t0:.1f}s -> {paths2}")

    import soundfile as sf

    all_bit_exact = True
    for stem in ("drums", "bass"):
        arr1, sr1 = sf.read(paths1[stem])
        arr2, sr2 = sf.read(paths2[stem])
        result = compare_audio_arrays(arr1, arr2)
        print(f"\n[{stem}] sr_match={sr1 == sr2} bit_exact={result['bit_exact']} "
              f"max_abs_diff={result['max_abs_diff']}")
        all_bit_exact = all_bit_exact and result["bit_exact"]

    print("\n" + "=" * 60)
    if all_bit_exact:
        print("VERDICT: 修復成功 — reseed_for_inference() 讓連續兩次 Demucs 分離"
              "（走真實 CascadedStemSeparator._demucs_separate() 程式碼路徑）完全 bit-exact。")
    else:
        print("VERDICT: 修復未生效 — 仍有差異，需要進一步檢查。")

    shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
