"""
SDD Pass 146 — 節奏定位分頁新增 v1/v2 A/B 比較試聽

背景：稽核發現「7/30 16:00 版本」（使用者記憶中「95分」的基準）實際上是
Module3BarStartV2MergeNode 尚未誠實合併前的舊版——當時的「v2」輸出其實是
v1 自己的 measure_map 重新幾何切分後貼牌，寫死 88（v1）vs 95（v2）分數，
從未真正跑過 v2 引擎。使用者要求：在前端同時列出 v1 原版與 v2 BarStart 的
成果，方便直接 A/B 聽感比較，抓出目前 v2 到底輸給 v1 多少、輸在哪裡。

後端本來就已經在算這兩份資料（Module3BarStartV2MergeNode 的
_write_legacy_artifacts/_write_barstart_v2_artifacts，寫入
module3_outputs 的 module3_legacy_click_track/module3_legacy_mix_with_click
與 barstart_v2_click_track/barstart_v2_mix_with_click），只是從未被
app.py 前端讀取顯示——同一個 session 反覆出現的「算了但沒展示」模式。

本次新增：
1. 「節奏定位」分頁新增 4 個 Audio 播放器（v1 原曲+Click／v1 Click Only／
   v2 原曲+Click／v2 Click Only）與一段說明 v2 設計原理的文字。
2. process_module3_click_test() 回傳值從 11 個擴充到 15 個，新增
   v1_mix_path/v1_click_path/v2_mix_path/v2_click_path，從
   module3_outputs 讀取並驗證檔案存在。
3. 更新 tests/test_sdd_pass114.py 兩個既有測試：Pass 114 當時的設計意圖是
   「只顯示單一贏家輸出」，這次使用者的明確要求推翻了那個決定，測試斷言
   從「comparison 播放器不應存在」改為「comparison 播放器確實存在且接在
   同一個 click handler」。

本測試驗證：
A. 前端確實新增了 4 個比較用 Audio 元件，且都接在 module3_start_btn.click()
   的 outputs 裡。
B. process_module3_click_test() 的無音檔早退路徑回傳值數量與正常路徑一致
   （15 個），避免 Gradio outputs 數量不匹配。
C. 端對端真實跑一次（sample_test.wav）：v1/v2 比較路徑確實從
   module3_outputs 正確擷取、檔案確實存在。
"""

import inspect
import os
import tempfile

from app import process_module3_click_test


class TestComparisonUIWiring:

    def test_frontend_has_four_comparison_audio_players(self):
        import app
        source = inspect.getsource(app)
        assert 'module3_v1_mix_player = gr.Audio(label="v1 原版：原曲 + Click")' in source
        assert 'module3_v1_click_player = gr.Audio(label="v1 原版：Click Only")' in source
        assert 'module3_v2_mix_player = gr.Audio(label="v2 BarStart：原曲 + Click")' in source
        assert 'module3_v2_click_player = gr.Audio(label="v2 BarStart：Click Only")' in source

    def test_comparison_players_wired_into_start_button_outputs(self):
        import app
        source = inspect.getsource(app)
        click_block = source[source.index("module3_start_btn.click("):source.index("# 頁籤 3: 完整 PGM")]
        for name in (
            "module3_v1_mix_player",
            "module3_v1_click_player",
            "module3_v2_mix_player",
            "module3_v2_click_player",
        ):
            assert name in click_block


class TestReturnContract:

    def test_no_audio_early_return_matches_output_count(self):
        result = process_module3_click_test(None, True, ["full_mix"], tempfile.mkdtemp())
        assert len(result) == 15

    def test_end_to_end_populates_v1_v2_comparison_paths(self):
        out_dir = tempfile.mkdtemp()
        result = process_module3_click_test("sample_test.wav", True, ["full_mix", "rhythm", "band", "vocal"], out_dir)
        assert len(result) == 15
        (
            status_md, debug_payload, v2_report, tempo_curve, mix, click, backing,
            mix_file, click_file, backing_file, report_file,
            v1_mix, v1_click, v2_mix, v2_click,
        ) = result

        for path in (v1_mix, v1_click, v2_mix, v2_click):
            assert path is not None
            assert os.path.exists(path)

        assert v1_mix.endswith("legacy_mix_with_click.wav")
        assert v1_click.endswith("legacy_click_track.wav")
        assert v2_mix.endswith("barstart_v2_mix_with_click.wav")
        assert v2_click.endswith("barstart_v2_click_track.wav")
