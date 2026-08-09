r"""
研究方向：鼓聲缺席段落（6.6s-11.6s）是否有其他樂器的清楚節奏線索可以
當替代證據來源。
"""

import os
import numpy as np
import librosa

PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness"
    r"\outputs\pass196_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\stems"
)

CANDIDATES = {
    "bass": os.path.join(PROJECT_DIR, "bass", "bass.wav"),
    "electric_bass": os.path.join(PROJECT_DIR, "bass", "electric_bass.wav"),
    "guitar": os.path.join(PROJECT_DIR, "guitars", "guitar.wav"),
    "piano": os.path.join(PROJECT_DIR, "pianos", "piano.wav"),
    "vocals": os.path.join(PROJECT_DIR, "vocals", "vocals.wav"),
    "lead_vocal": os.path.join(PROJECT_DIR, "vocals", "lead_vocal.wav"),
}

WINDOW_LO, WINDOW_HI = 5.5, 12.5


def analyze(path, label):
    if not os.path.exists(path):
        print(f"  [{label}] 檔案不存在：{path}")
        return
    y, sr = librosa.load(path, sr=22050, mono=True, offset=WINDOW_LO, duration=WINDOW_HI - WINDOW_LO)
    rms = librosa.feature.rms(y=y)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    avg_rms_db = float(np.mean(librosa.amplitude_to_db(rms, ref=1.0)))

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True, units="time")
    onsets = [round(WINDOW_LO + o, 3) for o in onsets]

    print(f"  [{label}] 平均音量(dBFS)={avg_rms_db:.1f}  6.5-11.5s 內偵測到 {len(onsets)} 個 onset：{onsets}")


def main():
    print(f"分析 {WINDOW_LO}s - {WINDOW_HI}s 這段鼓聲靜默區間，各樂器音軌的訊號強度與 onset：\n")
    for label, path in CANDIDATES.items():
        analyze(path, label)


if __name__ == "__main__":
    main()
