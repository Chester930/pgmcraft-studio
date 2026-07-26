import sys

checks = [
    ("torch",        "import torch; print(f'OK torch={torch.__version__} CUDA={torch.cuda.is_available()}')"),
    ("demucs",       "from demucs.pretrained import get_model; m=get_model('htdemucs_ft'); print('OK htdemucs_ft loaded')"),
    ("demucs_6s",    "from demucs.pretrained import get_model; m=get_model('htdemucs_6s'); print('OK htdemucs_6s loaded')"),
    ("librosa",      "import librosa; print(f'OK librosa={librosa.__version__}')"),
    ("soundfile",    "import soundfile; print(f'OK soundfile={soundfile.__version__}')"),
    ("mido",         "import mido; print(f'OK mido={mido.__version__}')"),
    ("scipy",        "import scipy; print(f'OK scipy={scipy.__version__}')"),
    ("whisper",      "import whisper; whisper.load_model('tiny'); print('OK whisper tiny loaded')"),
    ("basic_pitch",  "from basic_pitch.inference import predict_and_save; print('OK basic_pitch')"),
    ("crepe",        "import crepe; print(f'OK crepe={crepe.__version__}')"),
    ("madmom",       "import madmom; print(f'OK madmom={madmom.__version__}')"),
    ("pyannote",     "from pyannote.audio import Pipeline; print('OK pyannote.audio')"),
]

results = []
for name, code in checks:
    try:
        exec(code)
        results.append((name, "OK"))
    except Exception as e:
        print(f"[MISSING] {name}: {type(e).__name__}: {e}")
        results.append((name, f"MISSING: {e}"))

print("\n=== SUMMARY ===")
for name, status in results:
    icon = "✅" if status == "OK" else "❌"
    print(f"  {icon} {name}: {status}")
