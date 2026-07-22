"""
PGMCraft Command Line Interface (CLI)
Allows running PGM Stem Separation & Audio Analysis via Terminal.
"""

import sys
import argparse
from pgm_craft.pipeline import PGMCraftEngine

def main():
    parser = argparse.ArgumentParser(
        description="PGMCraft Studio: AI Audio Stem Separation, Music Transcription & PGM Backing Track Suite"
    )
    parser.add_argument("--audio", "-a", required=True, help="Path to input audio file (.mp3 / .wav / .flac)")
    parser.add_argument("--output", "-o", default="outputs", help="Output directory path (default: ./outputs)")
    parser.add_argument("--stem", "-s", action="store_true", help="Enable Demucs AI stem separation")

    args = parser.parse_args()

    engine = PGMCraftEngine(enable_stem_separation=args.stem)
    report = engine.run(args.audio, output_dir=args.output)

    print("\n" + "=" * 50)
    print(" 🎛️  PGMCraft Studio Processing Report ")
    print("=" * 50)
    print(f" 音檔名稱: {report['audio_file']}")
    print(f" 音樂調性 (Key): {report['estimated_key']}")
    print(f" 平均速度 (BPM): {report['average_bpm']} (範圍: {report['min_bpm']} ~ {report['max_bpm']})")
    print(f" 總小節數: {report['total_measures']} 小節 | 總拍數: {report['total_beats']} 拍")
    print(f" 產出目錄: {args.output}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
