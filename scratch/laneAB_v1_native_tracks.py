r"""
Pass 177（延伸）— Track A / Track B：V1 正式雙軌融合的原始單軌證據

不是另外設計一套分析方式，是直接重用 V1 正式管線內部真正在跑的偵測邏輯
（pgm_craft/workflow/beat_tracking_bt.py 的 BeatNetSingleTrackNode /
LibrosaSingleTrackNode），分別對：

- Track A：stems/submix/track_a_rhythm.wav（鼓+貝斯節奏骨幹軌）
- Track B：stems/no_vocals.wav（無人聲全樂器伴奏軌）

單獨各跑一次融合前的原始偵測結果——這兩軌就是 BeatFusionArbitratorNode
實際拿去逐拍仲裁的輸入，讓審查介面上能看到「V1 現有雙軌融合，融合前的
兩個原始輸入分別長什麼樣子」，不是只有 scratch 這幾條自己發明的簡化分軌。

用法：
    python scratch/laneAB_v1_native_tracks.py --project-dir "<專案資料夾路徑>"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lane_common import load_mono, build_confidence_blocks, resolve_base_audio_path

TRACK_SPECS = [
    {
        "lane_id": "trackA_v1_rhythm",
        "relpath": os.path.join("stems", "submix", "track_a_rhythm.wav"),
    },
    {
        "lane_id": "trackB_v1_instrumental",
        "relpath": os.path.join("stems", "no_vocals.wav"),
    },
]


def _run_beatnet(path):
    from BeatNet.BeatNet import BeatNet
    estimator = BeatNet(1, mode="offline", inference_model="DBN", plot=[], thread=False)
    output = estimator.process(path)
    if output is not None and len(output) > 0:
        return output, "beatnet"
    raise RuntimeError("BeatNet 回傳空結果")


def _run_librosa_fallback(path):
    from pgm_craft.analyzer import MusicAnalyzer
    analyzer = MusicAnalyzer(use_beatnet=False)
    return analyzer._librosa_fallback(path), "librosa_fallback"


def detect_track_beats(path):
    """跟正式管線 BeatNetSingleTrackNode -> LibrosaSingleTrackNode 的
    fallback 順序完全一致，不是重新設計偵測方式。"""
    import numpy as np

    try:
        beats, method = _run_beatnet(path)
    except Exception as e:
        print(f"[TrackNative] BeatNet 失敗（{e}），改用 Librosa fallback（跟正式管線同一套 fallback）。")
        beats, method = _run_librosa_fallback(path)

    y, sr = load_mono(path)
    import librosa
    real_onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    duration = len(y) / float(sr)

    beats_list = []
    for row in beats:
        t = float(row[0])
        pos = row[1]
        pos = 1 if (pos is None or (isinstance(pos, float) and np.isnan(pos))) else int(round(float(pos)))
        beats_list.append([round(t, 6), pos])

    return {
        "beats": beats_list,
        "real_onsets": real_onsets,
        "duration": duration,
        "method": method,
    }


def main():
    parser = argparse.ArgumentParser(description="Pass 177 Track A/B（V1 正式融合前原始單軌）")
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    project_dir = args.project_dir
    base_audio_path = resolve_base_audio_path(project_dir)

    for spec in TRACK_SPECS:
        path = os.path.join(project_dir, spec["relpath"])
        if not os.path.exists(path):
            print(f"[FATAL] 找不到 {spec['lane_id']} 的來源音檔：{path}")
            continue

        lane_dir = os.path.join(project_dir, "lanes", spec["lane_id"])
        click_dir = os.path.join(lane_dir, "click")
        os.makedirs(click_dir, exist_ok=True)

        print(f"[{spec['lane_id']}] 對 {spec['relpath']} 跑 V1 正式單軌偵測（BeatNet，失敗才 fallback Librosa）...")
        result = detect_track_beats(path)
        print(f"[{spec['lane_id']}] 方法：{result['method']}，共 {len(result['beats'])} 拍。")

        blocks = build_confidence_blocks(result["beats"], result["real_onsets"], result["duration"])
        needs_review_count = sum(1 for b in blocks if b["needs_review"])
        print(f"[{spec['lane_id']}] 全曲合併成 {len(blocks)} 個區塊，其中 {needs_review_count} 個需複核。")

        with open(os.path.join(lane_dir, "blocks.json"), "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)
        with open(os.path.join(lane_dir, "beats.json"), "w", encoding="utf-8") as f:
            json.dump({"tempo": None, "method": result["method"], "beats": result["beats"]}, f, ensure_ascii=False, indent=2)

        print(f"[{spec['lane_id']}] 渲染 click 音檔（混在完整歌曲原始底本上，不是只有隔離的分軌）...")
        from pgm_craft.synthesizer import PGMSynthesizer
        synth = PGMSynthesizer()
        click_path, mix_path = synth.synthesize_click(base_audio_path, result["beats"], output_dir=click_dir)
        print(f"[{spec['lane_id']}] 完成：{mix_path}")


if __name__ == "__main__":
    main()
