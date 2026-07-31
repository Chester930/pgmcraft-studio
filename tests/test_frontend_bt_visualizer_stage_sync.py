"""
Regression test (frontend/backend consistency audit) — the "Workflow 執行與
診斷" tab's BT tree diagram was hardcoded to always render the full Stage
0-6 tree (`build_pgm_workflow_tree()`) regardless of what stage the user
picked in `diag_stage_select`. Fixed to use `build_master_pipeline_tree`
with the selected stage, and to refresh automatically on dropdown change.
"""

from pathlib import Path

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_bt_visualizer_uses_master_pipeline_tree_with_selected_stage():
    assert "build_master_pipeline_tree(target_stage=stage_mode)" in APP_SOURCE
    assert "build_master_pipeline_tree(target_stage=\"full\")" in APP_SOURCE


def test_bt_visualizer_refreshes_on_stage_dropdown_change():
    assert "diag_stage_select.change(fn=_refresh_bt_html" in APP_SOURCE
    assert "bt_refresh_btn.click(fn=_refresh_bt_html, inputs=[diag_stage_select]" in APP_SOURCE
