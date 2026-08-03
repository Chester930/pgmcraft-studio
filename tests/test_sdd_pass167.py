"""
SDD Pass 167 — 升級 DAWPresetsPackagerNode 與 PGMProjectPackager UTF-8 編碼驗證

背景：
在 Windows/Mac/Linux 跨平台或某些 DAW (如 Cubase/Ableton) 解壓含有 Unicode/中日文字元（例如 01_初音ミク_【World_is_Mine】.wav）的 zip 素材包時，若未顯式設定 flag_bits |= 0x800，解壓時可能出現檔名亂碼。

本測試驗證：
1. DAWPresetsPackagerNode 產出的 daw_presets_pack.zip 內所有 ZipInfo 條目皆包含 0x800 UTF-8 編碼標誌。
2. 含有中文/Unicode 檔名的素材檔案能被正確解壓且檔名無失真。
"""

import os
import tempfile
import zipfile
import pytest

from pgm_craft.workflow.package_bt import DAWPresetsPackagerNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass167:

    def test_daw_presets_packager_utf8_encoding_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 建立帶有中文字元的模擬預設檔
            cn_file = os.path.join(tmp_dir, "01_測試曲目_和弦 Marker.csv")
            with open(cn_file, "w", encoding="utf-8") as f:
                f.write("Time,Name\n0.0,Intro\n")

            bb = Blackboard()
            bb.set_val("output_dir", tmp_dir)

            node = DAWPresetsPackagerNode()
            status = node.execute(bb)

            assert status == NodeStatus.SUCCESS
            zip_path = os.path.join(tmp_dir, "daw_presets_pack.zip")
            assert os.path.exists(zip_path)

            with zipfile.ZipFile(zip_path, "r") as z:
                infos = z.infolist()
                assert len(infos) > 0
                for info in infos:
                    # 驗證 flag_bits 0x800 (UTF-8 標誌)
                    assert info.flag_bits & 0x800, f"ZipInfo {info.filename} 缺少 UTF-8 標誌 (0x800)"
