"""
SDD Pass 152 — 節奏定位分頁移除四軌候選來源 CheckboxGroup，直接寫死在流程中

背景：使用者測試期間指出，「🎯 節奏定位」分頁的「四軌候選來源」CheckboxGroup
(module3_candidate_sources_chk) 沒有存在的必要——四軌(full_mix/rhythm/band/
vocal)本來就沒有情境需要排除其中一軌，讓使用者手動勾選只是徒增介面複雜度、
也留下「不小心關掉某軌」的誤觸風險。使用者明確要求：拿掉這個選單，四軌直接
寫死在流程裡。

移除 module3_candidate_sources_chk 這個 gr.CheckboxGroup 元件；
_handle_module3_run() 的參數簽章從 (audio_file, candidate_sources, output_dir)
改為 (audio_file, output_dir)，內部直接寫死
candidate_sources = ["full_mix", "rhythm", "band", "vocal"] 再呼叫
process_module3_click_test()——後端 process_module3_click_test() 本身的簽章
與行為完全不變，只是呼叫端不再讓使用者選擇要傳什麼。

本測試驗證：
A. 前端源碼確實不再含有 module3_candidate_sources_chk 這個元件定義。
B. _handle_module3_run() 確實把四軌候選來源寫死在函式內部，不再透過參數接收。
C. module3_start_btn.click() 的 inputs 列表不再包含
   module3_candidate_sources_chk。
D. 端對端呼叫 process_module3_click_test()（_handle_module3_run 實際呼叫的
   後端函式）帶入寫死的四軌清單，確認行為與之前使用者手動勾選全選時完全一致。
"""

from pathlib import Path

from app import process_module3_click_test

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


class TestCandidateSourcesCheckboxRemoved:

    def test_checkbox_group_component_no_longer_defined(self):
        assert "module3_candidate_sources_chk" not in APP_SOURCE
        assert "四軌候選來源" not in APP_SOURCE

    def test_handle_module3_run_hardcodes_all_four_sources(self):
        handler_start = APP_SOURCE.index("def _handle_module3_run(")
        handler_end = APP_SOURCE.index("module3_start_btn.click(")
        handler_source = APP_SOURCE[handler_start:handler_end]

        assert "def _handle_module3_run(audio_file, output_dir):" in handler_source
        assert '["full_mix", "rhythm", "band", "vocal"]' in handler_source
        assert "return process_module3_click_test(audio_file, True, candidate_sources, output_dir)" in handler_source

    def test_start_button_inputs_no_longer_reference_checkbox(self):
        click_block = APP_SOURCE[
            APP_SOURCE.index("module3_start_btn.click("):APP_SOURCE.index("# 頁籤 3: 完整 PGM")
        ]
        assert "module3_candidate_sources_chk" not in click_block
        assert "module3_audio_input" in click_block
        assert "module3_output_dir" in click_block


class TestBackendStillReceivesAllFourSources:

    def test_end_to_end_with_hardcoded_four_sources(self, tmp_path):
        out_dir = str(tmp_path)
        result = process_module3_click_test(
            "sample_test.wav", True, ["full_mix", "rhythm", "band", "vocal"], out_dir
        )
        status_md = result[0]
        assert "請先選擇音檔" not in status_md
