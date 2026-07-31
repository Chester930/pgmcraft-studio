"""
Frontend cleanup (user request): removed the standalone "🎹 MIDI 鋼琴卷軸預覽"
and "📦 PGM 工程素材包一鍵打包與下載" tabs. The packaging/download capability
itself was not deleted -- it is slated to move under the "📦 DAW 素材包"
placeholder (four-block narrative Block 3) once that gets wired up. Until
then, `piano_roll_html_box` / `file_zip_download` stay as real (hidden)
components so `analyze_btn.click()`'s fixed 17-value output contract
(PGM_OUTPUT_COUNT) is untouched.
"""

from pathlib import Path

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_piano_roll_and_zip_tabs_removed_from_frontend():
    assert 'with gr.TabItem("🎹 MIDI 鋼琴卷軸預覽")' not in APP_SOURCE
    assert 'with gr.TabItem("📦 PGM 工程素材包一鍵打包與下載")' not in APP_SOURCE


def test_underlying_components_kept_hidden_not_deleted():
    # kept for analyze_btn.click()'s output contract, just not user-visible
    assert "piano_roll_html_box = gr.HTML(visible=False)" in APP_SOURCE
    assert "file_zip_download = gr.File(visible=False)" in APP_SOURCE
    assert "piano_roll_html_box," in APP_SOURCE
    assert "file_zip_download" in APP_SOURCE


def test_hidden_components_are_direct_children_of_blocks_not_tabs():
    # gr.Tabs() only accepts gr.Tab()/gr.TabItem() as direct children; the
    # hidden components must be declared before `with gr.Tabs():` opens.
    tabs_idx = APP_SOURCE.index("with gr.Tabs():")
    piano_idx = APP_SOURCE.index("piano_roll_html_box = gr.HTML(visible=False)")
    zip_idx = APP_SOURCE.index("file_zip_download = gr.File(visible=False)")
    assert piano_idx < tabs_idx
    assert zip_idx < tabs_idx
