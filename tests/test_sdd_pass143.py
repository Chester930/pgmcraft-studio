"""
SDD Pass 143 — 補上「一鍵生成」的 BarStart v2 採用狀態可見度

背景：使用者問「所以我現在可以怎麼測試」（Pass 141/142 打通並簡化 v1/v2 合併
邏輯後）。稽核發現：「🎯 節奏定位」分頁的狀態文字會顯示 barstart_v2_report
（Module3BarStartV2MergeNode 寫入），但「⚡ 一鍵生成」主管線用的是
BarStartV2AutoMergeNode，寫入的是不同的欄位 barstart_v2_auto_report——這個
欄位過去完全沒有被匯出到 JSON 報告或前端畫面，使用者跑一鍵生成時無從確認
v2 是否真的被採用。

修復：
1. pgm_craft/pipeline.py 的 PGMCraftEngine.run() 在組裝 report dict 時，
   新增 barstart_v2_auto_report 欄位（與既有 barstart_v2_report 並列）。
2. app.py 的 process_pgm() 狀態文字新增「節拍網格來源」一行，顯示
   `BarStart v2` 或 `原版 (v1)`，以及 auto merge 的狀態與 unresolved
   bar span 數量。

本測試驗證：
A. PGMCraftEngine.run() 回傳的 report 確實包含 barstart_v2_auto_report。
B. process_pgm() 狀態文字包含「節拍網格來源」一行，且能正確反映 v2 是否
   被採用（AUTO_PROMOTED → 顯示 BarStart v2；未採用 → 顯示 原版 (v1)）。
"""

from app import process_full_auto_pgm


def test_pgm_report_includes_barstart_v2_auto_report(tmp_path):
    report_holder = {}
    import pgm_craft.pipeline as pipeline_module
    original_run = pipeline_module.PGMCraftEngine.run

    def _spy_run(self, *args, **kwargs):
        result = original_run(self, *args, **kwargs)
        report_holder["report"] = result
        return result

    pipeline_module.PGMCraftEngine.run = _spy_run
    try:
        process_full_auto_pgm(None, "sample_test.wav", str(tmp_path))
    finally:
        pipeline_module.PGMCraftEngine.run = original_run

    assert "barstart_v2_auto_report" in report_holder["report"]


def test_status_text_shows_beat_grid_source_and_promotion(tmp_path):
    status_md = process_full_auto_pgm(None, "sample_test.wav", str(tmp_path))[0]
    assert "節拍網格來源" in status_md
    assert ("BarStart v2" in status_md) or ("原版 (v1)" in status_md)
