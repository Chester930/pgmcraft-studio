import sys
import os
import argparse
from beat_tracker import BeatTrackingSystem

def generate_sample_test_audio(filename="sample_test.wav", duration_sec=10):
    """Generates a sample audio file with changing tempo for testing if no audio file is provided."""
    import numpy as np
    import soundfile as sf

    print(f"Generating test audio file: {filename} ({duration_sec}s)...")
    sr = 22050
    t = np.linspace(0, duration_sec, int(sr * duration_sec), False)
    
    # Base chord progression C - G - Am - F
    freqs = [261.63, 392.00, 440.00, 349.23] # C4, G4, A4, F4
    audio = np.zeros_like(t)

    # Varying tempo drum beats (120 BPM -> 150 BPM)
    beat_times = []
    curr_t = 0.5
    bpm = 120.0
    while curr_t < duration_sec:
        beat_times.append(curr_t)
        bpm += 2.0 # Accelerando
        dt = 60.0 / bpm
        curr_t += dt

    # Synthesize tones and beats
    for i, b_time in enumerate(beat_times):
        idx = int(b_time * sr)
        if idx < len(audio):
            dur = 0.15
            beat_t = np.linspace(0, dur, int(sr * dur), False)
            freq = 800 if (i % 4 == 0) else 400
            click = np.sin(2 * np.pi * freq * beat_t) * np.exp(-10 * beat_t)
            end_idx = min(idx + len(click), len(audio))
            audio[idx:end_idx] += click[:end_idx-idx]

    # Normalize
    audio = audio / (np.max(np.abs(audio)) + 1e-6)
    sf.write(filename, audio.astype(np.float32), sr)
    return filename


def main():
    parser = argparse.ArgumentParser(description="動態節拍追蹤、音樂分析與打點生成工具")
    parser.add_argument("input_audio", nargs="?", help="輸入 MP3 或 WAV 音檔路徑")
    parser.add_argument("--output_dir", default="outputs", help="輸出資料夾 (預設: outputs)")
    parser.add_argument("--no_beatnet", action="store_true", help="強制停用 BeatNet 模型，使用 Librosa")

    args = parser.parse_args()

    audio_path = args.input_audio

    # If no audio provided, check directory or generate test sample
    if not audio_path:
        # Check current dir for mp3/wav
        audio_files = [f for f in os.listdir(".") if f.lower().endswith(('.mp3', '.wav')) and not f.startswith("sample_test")]
        if audio_files:
            audio_path = audio_files[0]
            print(f"自動選取當前目錄音檔: {audio_path}")
        else:
            audio_path = generate_sample_test_audio()

    if os.path.isdir(audio_path):
        print(f"\n📁 檢測到輸入為資料夾路徑，啟動 Batch 批次 Processing 模式: {audio_path}")
        audio_exts = ('.wav', '.mp3', '.flac', '.m4a')
        target_files = [os.path.join(audio_path, f) for f in os.listdir(audio_path) if f.lower().endswith(audio_exts)]
        if not target_files:
            print(f"資料夾內無符合相容格式的音檔 ({audio_exts})")
            sys.exit(1)

        print(f"找到 {len(target_files)} 個音軌，開始執行批次全自動分析...")
        from pgm_craft.pipeline import PGMCraftEngine
        engine = PGMCraftEngine(enable_stem_separation=False)
        batch_results = []
        for i, file_p in enumerate(target_files, 1):
            print(f"\n[{i}/{len(target_files)}] 處理批次音軌 ➔ {os.path.basename(file_p)}")
            res = engine.run(file_p, output_dir=args.output_dir)
            batch_results.append({"file": file_p, "package": res.get("zip_archive")})

        summary_path = os.path.join(args.output_dir, "batch_summary.json")
        import json
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(batch_results, f, indent=2, ensure_ascii=False)
        print(f"\n🎉 批次處理完成！完成報告儲存於: {summary_path}")
        return

    if not os.path.exists(audio_path):
        print(f"錯誤：找不到音檔 '{audio_path}'")
        sys.exit(1)


    print(f"\n==========================================")
    print(f"開始處理音檔: {audio_path}")
    print(f"==========================================\n")

    tracker = BeatTrackingSystem(use_beatnet=not args.no_beatnet)
    report = tracker.run_full_pipeline(audio_path, output_dir=args.output_dir)

    print("\n[產出檔案列表]")
    for k, v in report["outputs"].items():
        print(f" - {k}: {os.path.abspath(v)}")

if __name__ == "__main__":
    main()
