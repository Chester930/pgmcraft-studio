"""
PGMCraft AI Model Loader & Environment Diagnostics.
提供單一存取點進行選用 AI 模型 (BeatNet, CREPE, Basic Pitch, Whisper, Demucs) 的動態加載與環境相容性檢查。
"""

import sys
import importlib

class AILoader:
    """選用 AI 模型動態加載器與狀態探針。"""
    
    SUPPORTED_MODELS = {
        "BeatNet": {"module": "BeatNet.BeatNet", "fallback": "LibrosaBeatNode"},
        "crepe": {"module": "crepe", "fallback": "Librosa pyin"},
        "basic_pitch": {"module": "basic_pitch.inference", "fallback": "Librosa STFT/Chroma"},
        "whisper": {"module": "whisper", "fallback": "Energy Peak Segmentation"},
        "demucs": {"module": "demucs", "fallback": "Local UVR5 / FFT Filter"}
    }

    @classmethod
    def is_model_available(cls, model_name: str) -> tuple[bool, str]:
        """檢查指定 AI 模型庫是否安裝可用，回傳 (is_available, message/fallback_reason)。"""
        if model_name not in cls.SUPPORTED_MODELS:
            return False, f"Unknown model name '{model_name}'"

        meta = cls.SUPPORTED_MODELS[model_name]
        mod_path = meta["module"]
        fallback = meta["fallback"]

        try:
            importlib.import_module(mod_path)
            return True, "Ready"
        except Exception as exc:
            return False, f"Unavailable ({exc}). Will use {fallback} guard."

    @classmethod
    def check_all_models(cls) -> dict[str, dict]:
        """巡檢所有支援的 AI 模型，產出詳細診斷字典。"""
        report = {}
        for name in cls.SUPPORTED_MODELS:
            avail, reason = cls.is_model_available(name)
            report[name] = {
                "is_available": avail,
                "status": "Available" if avail else "Unavailable",
                "fallback_reason": reason
            }
        return report


def get_model_status_report() -> dict[str, dict]:
    """快捷調用：取得 AI 模型現況報告。"""
    return AILoader.check_all_models()
