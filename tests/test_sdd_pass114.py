"""
SDD Pass 114 - Module 3 BarStart v2 frontend comparison contract.
"""

from pathlib import Path


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")
MODULE3_UI_SOURCE = APP_SOURCE[APP_SOURCE.index("with gr.TabItem(\"🎯 節奏定位\")"):APP_SOURCE.index("# 頁籤 3: 完整 PGM")]
LAUNCH_SOURCE = Path("launch_app_7860.py").read_text(encoding="utf-8")


def test_frontend_uses_single_module3_execution_entry():
    # module3_start_btn wires through a thin wrapper (_handle_module3_run) that
    # forces enable_stem=True (stem separation is mandatory, not a checkbox
    # anymore) before calling process_module3_click_test -- still the single
    # real execution entry into the v1/v2 comparison engine.
    assert "fn=_handle_module3_run" in APP_SOURCE
    assert "return process_module3_click_test(audio_file, True, candidate_sources, output_dir)" in APP_SOURCE
    assert "module3_start_btn = gr.Button" in APP_SOURCE
    assert "module3_enable_stem_chk" not in APP_SOURCE
    assert "BarStart v2 實驗入口" not in APP_SOURCE
    assert "module3_v2_meter_select" not in APP_SOURCE
    assert "module3_v2_bar_delta" not in APP_SOURCE
    assert "module3_v2_manual_starts" not in APP_SOURCE
    assert "module3_v2_start_btn" not in APP_SOURCE
    assert 'fn=process_module3_barstart_v2_test' not in APP_SOURCE


def test_frontend_single_run_outputs_barstart_v2_main_only():
    assert 'module3_v2_report_json = gr.JSON(label="BarStart v2 診斷報告")' in APP_SOURCE
    assert 'module3_mix_player = gr.Audio(label="主要輸出：原曲 + Click")' in APP_SOURCE
    assert 'module3_click_player = gr.Audio(label="主要輸出：Click Only")' in APP_SOURCE
    assert "原版比較" not in MODULE3_UI_SOURCE
    assert "legacy_" not in MODULE3_UI_SOURCE


def test_frontend_main_callback_updates_single_final_outputs():
    main_click = APP_SOURCE[APP_SOURCE.index("module3_start_btn.click("):APP_SOURCE.index("# 頁籤 3: 完整 PGM")]
    assert "module3_v2_report_json" in main_click
    assert "module3_mix_player" in main_click
    assert "module3_click_player" in main_click
    assert "module3_backing_player" in main_click
    assert "module3_v2_mix_player" not in main_click
    assert "module3_v2_click_player" not in main_click
    assert "module3_v2_mix_file" not in main_click
    assert "module3_v2_click_file" not in main_click


def test_frontend_v2_uses_model_for_bar_starts():
    assert "BarStart v2 合併診斷" in APP_SOURCE
    assert "主輸出節拍來源" in APP_SOURCE
    assert "module3_v2_manual_starts" not in APP_SOURCE


def test_final_frontend_port_is_7860_only():
    assert "server_port=7860" in APP_SOURCE
    assert "server_port=7860" in LAUNCH_SOURCE
    assert not Path("launch_app_7861.py").exists()
    assert not Path("launch_app_7862.py").exists()
    assert not Path("launch_app_7863.py").exists()
