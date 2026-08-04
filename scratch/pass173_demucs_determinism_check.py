"""
Pass 173 — Demucs (htdemucs_ft) 分軌決定性驗證

目的：Pass 172 證實 BeatNetNode_TrackA 對同一份音訊是 100% 決定性的（兩次都精確複現
黃金版 485 拍）。既然如此，Pass 171 那次重新分離出的 track_a_rhythm.wav 讓 BeatNet 只
抓到 477 拍，唯一合理的解釋就是「重新分離出來的 drums/bass 音訊本身跟黃金版不同」。

靜態比對 pgm_craft/separator.py 發現 `_demucs_separate()` 呼叫
`demucs.apply.apply_model()` 沒有指定 `shifts` 參數 —— demucs 的預設值是
`shifts=1`：每次呼叫都會對輸入做一次「隨機時間平移」再推論（用來提升 SDR 的
test-time augmentation），這個隨機平移的來源是全域 PyTorch RNG，而
`pgm_craft/determinism.py` 只在 pipeline 啟動時 seed 一次，不會在每次
`apply_model()` 呼叫前重新 seed，所以同一份輸入音訊，每次分離用掉的隨機平移量都不同。

本腳本直接呼叫 demucs.apply.apply_model() 兩次（繞開 CascadedStemSeparator 的
記憶體快取，因為快取只是省算力的捷徑，同一個 output_dir 命中快取不代表模型本身決定性）：
1. 對照組 A（shifts=1，目前 pipeline 的預設行為）：跑兩次，比較輸出是否 bit-exact。
2. 對照組 B（shifts=0，強制關閉隨機平移）：跑兩次，比較輸出是否 bit-exact。

如果 A 不 bit-exact、B bit-exact，就證實 Pass 173 假設：random-shift augmentation
是「477 vs 485」拍數落差的根本原因。

用法：
    python scratch/pass173_demucs_determinism_check.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.determinism import enable_deterministic_mode, compare_audio_arrays

DENOISED_SOURCE_PATH = (
    r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
    r"\source\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】_denoised.wav"
)


def load_model_and_wav(model_name: str):
    import torch
    import librosa
    import numpy as np
    from demucs.pretrained import get_model

    model = get_model(model_name)
    model.eval()
    wav_raw, sr = librosa.load(DENOISED_SOURCE_PATH, sr=model.samplerate, mono=False)
    if wav_raw.ndim == 1:
        wav_raw = np.stack([wav_raw, wav_raw])
    wav = torch.from_numpy(wav_raw).float().unsqueeze(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    wav = wav.to(device)
    return model, wav


def run_apply_model_once(model, wav, shifts: int):
    import torch
    from demucs.apply import apply_model

    with torch.no_grad():
        sources = apply_model(model, wav, shifts=shifts, progress=True)[0]
    return sources.cpu().numpy()


def compare_arrays(arr1, arr2, label: str):
    result = compare_audio_arrays(arr1, arr2)
    print(f"[{label}] bit_exact={result['bit_exact']}  max_abs_diff={result['max_abs_diff']:.8f}")
    return result["bit_exact"], result["max_abs_diff"]


def main():
    if not os.path.exists(DENOISED_SOURCE_PATH):
        print(f"[FATAL] 找不到黃金專案的 denoised 來源音訊：{DENOISED_SOURCE_PATH}")
        sys.exit(1)

    report = enable_deterministic_mode()
    print(f"determinism report: {report}\n")

    print("載入 htdemucs_ft 模型與音訊 (只做一次，兩組實驗共用同一份輸入張量) ...")
    model, wav = load_model_and_wav("htdemucs_ft")

    results = {}

    for shifts in (1, 0):
        label = f"shifts={shifts}"
        print(f"\n=== {label} ===")
        t0 = time.time()
        out_a = run_apply_model_once(model, wav, shifts=shifts)
        print(f"  run 1 done in {time.time() - t0:.1f}s")
        t0 = time.time()
        out_b = run_apply_model_once(model, wav, shifts=shifts)
        print(f"  run 2 done in {time.time() - t0:.1f}s")
        bit_exact, max_abs_diff = compare_arrays(out_a, out_b, label)
        results[shifts] = {"bit_exact": bit_exact, "max_abs_diff": max_abs_diff}

    print("\n" + "=" * 60)
    print("結論：")
    shifts1_exact = results[1]["bit_exact"]
    shifts0_exact = results[0]["bit_exact"]
    print(f"  shifts=1（目前 pipeline 預設）連續兩次分離 bit-exact: {shifts1_exact}"
          f"（max_abs_diff={results[1]['max_abs_diff']:.8f}）")
    print(f"  shifts=0（強制關閉隨機平移）連續兩次分離 bit-exact: {shifts0_exact}"
          f"（max_abs_diff={results[0]['max_abs_diff']:.8f}）")

    if (not shifts1_exact) and shifts0_exact:
        print("\nVERDICT: 假設成立 — Demucs 的 random-shift test-time augmentation "
              "(shifts=1) 是分軌不可複現的根本原因；shifts=0 可完全消除。")
    elif shifts1_exact and shifts0_exact:
        print("\nVERDICT: 兩組都 bit-exact — shifts 不是落差來源，"
              "需要往其他方向（如 cudnn 非決定性 kernel）查。")
    else:
        print("\nVERDICT: 兩組都不 bit-exact，或 shifts=0 也不穩定 — "
              "問題比預期更複雜，shifts 只是原因之一。")


if __name__ == "__main__":
    main()
