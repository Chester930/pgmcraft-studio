"""
SDD Pass 159 — 修復 Stage 2 分軌子樹的資料完整性 bug

背景：
在 Pass 155–158 修完 BarStart v2 節奏偵測後，對整個 BT 做了完整盤點。
盤點 Stage 2 分軌子樹（build_stem_separation_tree()）時，發現兩個 P0 bug：
某些 stem 的 blackboard key 存在，但實際檔案已被自己的清理節點刪掉，
導致下游節奏偵測在讀檔時出錯或悄悄拿到空結果。

根因 A（WHITELIST_MAP 錯誤）：
StrictStemDirectoryGuardNode.WHITELIST_MAP 有以下錯誤：
1. drums 子目錄白名單寫的是 "hihat.wav"，但 SubSplitDrumsNode 實際產出
   的是 "hihat_cymbals.wav"——每次 Guard 執行後這個檔案都被誤刪。
2. events 子目錄白名單缺少 "count_in_voice.wav"（ExtractCountInVoiceNode
   產出）與 "claps_snaps.wav"（ExtractClapSnapEventsNode 產出）——兩者
   都會被 Guard 每次刪掉。

根因 B（separate_guitar NameError）：
separator.py 的 separate_guitar() 函式，在 else 分支（L479）與 except
fallback（L482-483）都使用了從未定義過的變數 target_input，只要
_demucs_separate() 丟出任何例外，就會在 except 區塊再拋出 NameError。
這個 NameError 被上層 PeelCoreTrioNode 吞掉，導致吉他/鋼琴/弦樂三重奏
全部失敗、走 passthrough，三者都沒有輸出。
對照 separate_piano() 的正確寫法，應使用 standardized_input。

修復：
A. WHITELIST_MAP["drums"]：hihat.wav → hihat_cymbals.wav
   WHITELIST_MAP["events"]：補上 count_in_voice.wav、claps_snaps.wav
B. separate_guitar() L479/482/483：target_input → standardized_input

本測試驗證：
1. Guard 修復後 hihat_cymbals.wav 不再被誤刪
2. Guard 修復後 count_in_voice.wav、claps_snaps.wav 不再被誤刪
3. 迴歸：既有合法檔案（drums.wav、kick.wav）仍保留；真正的異物仍被刪除
4. separate_guitar() Demucs 失敗時不再拋出 NameError，正確走 fallback
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.stem_separation_bt import StrictStemDirectoryGuardNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stems_dir():
    """建立暫時 stems 目錄，結束後清理。"""
    tmpdir = tempfile.mkdtemp()
    sd = os.path.join(tmpdir, "stems")
    os.makedirs(sd, exist_ok=True)
    yield sd
    shutil.rmtree(tmpdir, ignore_errors=True)


def _touch(path):
    """建立空白檔（必要時一併建立父目錄）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("fake")


def _run_guard(stems_dir_path):
    bb = Blackboard()
    bb.set_val("stems_dir", stems_dir_path)
    node = StrictStemDirectoryGuardNode()
    status = node.execute(bb)
    return status


# ---------------------------------------------------------------------------
# Bug A：WHITELIST_MAP 修正
# ---------------------------------------------------------------------------

class TestWhitelistMapFix:

    def test_hihat_cymbals_not_deleted(self, stems_dir):
        """hihat_cymbals.wav 是 SubSplitDrumsNode 實際產出的檔名，修復前被 Guard 誤刪。"""
        drums_dir = os.path.join(stems_dir, "drums")
        _touch(os.path.join(drums_dir, "drums.wav"))
        _touch(os.path.join(drums_dir, "kick.wav"))
        _touch(os.path.join(drums_dir, "snare.wav"))
        _touch(os.path.join(drums_dir, "hihat_cymbals.wav"))

        status = _run_guard(stems_dir)

        assert status == NodeStatus.SUCCESS
        assert os.path.exists(os.path.join(drums_dir, "hihat_cymbals.wav")), \
            "hihat_cymbals.wav 不應被 Guard 刪除（Pass 159 修復）"

    def test_count_in_voice_not_deleted(self, stems_dir):
        """count_in_voice.wav 是 ExtractCountInVoiceNode 產出，修復前不在白名單被誤刪。"""
        events_dir = os.path.join(stems_dir, "events")
        _touch(os.path.join(events_dir, "count_in_voice.wav"))

        status = _run_guard(stems_dir)

        assert status == NodeStatus.SUCCESS
        assert os.path.exists(os.path.join(events_dir, "count_in_voice.wav")), \
            "count_in_voice.wav 不應被 Guard 刪除（Pass 159 修復）"

    def test_claps_snaps_not_deleted(self, stems_dir):
        """claps_snaps.wav 是 ExtractClapSnapEventsNode 產出，修復前不在白名單被誤刪。"""
        events_dir = os.path.join(stems_dir, "events")
        _touch(os.path.join(events_dir, "claps_snaps.wav"))

        status = _run_guard(stems_dir)

        assert status == NodeStatus.SUCCESS
        assert os.path.exists(os.path.join(events_dir, "claps_snaps.wav")), \
            "claps_snaps.wav 不應被 Guard 刪除（Pass 159 修復）"

    def test_all_three_event_files_survive_together(self, stems_dir):
        """三個修復後的檔案同時存在時，Guard 執行後全部保留。"""
        drums_dir = os.path.join(stems_dir, "drums")
        events_dir = os.path.join(stems_dir, "events")
        _touch(os.path.join(drums_dir, "drums.wav"))
        _touch(os.path.join(drums_dir, "hihat_cymbals.wav"))
        _touch(os.path.join(events_dir, "count_in_voice.wav"))
        _touch(os.path.join(events_dir, "claps_snaps.wav"))

        status = _run_guard(stems_dir)

        assert status == NodeStatus.SUCCESS
        assert os.path.exists(os.path.join(drums_dir, "hihat_cymbals.wav"))
        assert os.path.exists(os.path.join(events_dir, "count_in_voice.wav"))
        assert os.path.exists(os.path.join(events_dir, "claps_snaps.wav"))


class TestWhitelistRegressions:
    """確認修改白名單後，既有合法檔案仍保留、真正的異物仍被清除。"""

    def test_existing_legal_drums_files_survive(self, stems_dir):
        """drums.wav、kick.wav、snare.wav 不受 Pass 159 改動影響。"""
        drums_dir = os.path.join(stems_dir, "drums")
        for fname in ("drums.wav", "kick.wav", "snare.wav"):
            _touch(os.path.join(drums_dir, fname))

        _run_guard(stems_dir)

        for fname in ("drums.wav", "kick.wav", "snare.wav"):
            assert os.path.exists(os.path.join(drums_dir, fname)), \
                f"{fname} 不應被 Guard 刪除"

    def test_foreign_file_in_drums_still_deleted(self, stems_dir):
        """drums 子目錄裡真正的異物（不在白名單的檔案）依然被刪除。"""
        drums_dir = os.path.join(stems_dir, "drums")
        _touch(os.path.join(drums_dir, "drums.wav"))
        _touch(os.path.join(drums_dir, "residual_something.wav"))

        _run_guard(stems_dir)

        assert not os.path.exists(os.path.join(drums_dir, "residual_something.wav")), \
            "residual_something.wav 應被 Guard 刪除（異物）"

    def test_foreign_file_in_events_still_deleted(self, stems_dir):
        """events 子目錄裡真正的異物依然被刪除，不因補白名單而漏網。"""
        events_dir = os.path.join(stems_dir, "events")
        _touch(os.path.join(events_dir, "count_in_voice.wav"))   # 合法
        _touch(os.path.join(events_dir, "claps_snaps.wav"))      # 合法
        _touch(os.path.join(events_dir, "mystery_file.wav"))     # 異物

        _run_guard(stems_dir)

        assert os.path.exists(os.path.join(events_dir, "count_in_voice.wav"))
        assert os.path.exists(os.path.join(events_dir, "claps_snaps.wav"))
        assert not os.path.exists(os.path.join(events_dir, "mystery_file.wav")), \
            "mystery_file.wav 應被 Guard 刪除"

    def test_old_hihat_wav_still_deleted(self, stems_dir):
        """修復前錯誤地允許的 hihat.wav（它不是任何節點的實際產出），
        修復後應被 Guard 視為異物刪除。"""
        drums_dir = os.path.join(stems_dir, "drums")
        _touch(os.path.join(drums_dir, "drums.wav"))
        _touch(os.path.join(drums_dir, "hihat.wav"))   # 修復前的錯誤白名單名稱

        _run_guard(stems_dir)

        assert not os.path.exists(os.path.join(drums_dir, "hihat.wav")), \
            "hihat.wav（非實際產出）應被 Guard 視為異物刪除"


# ---------------------------------------------------------------------------
# Bug B：separate_guitar NameError 修正
# ---------------------------------------------------------------------------

class TestSeparateGuitarFallback:

    def _make_separator(self, tmpdir):
        """建立最小化可執行的 CascadedStemSeparator stub，只 patch _demucs_separate 和 input_guard。"""
        from pgm_craft.separator import CascadedStemSeparator

        sep = CascadedStemSeparator.__new__(CascadedStemSeparator)

        # input_guard stub
        guard = MagicMock()
        guard.prepare_prerequisite_audio.return_value = os.path.join(tmpdir, "prepared.wav")
        standardized = os.path.join(tmpdir, "standardized.wav")
        # 建立一個真實的 fake wav（shutil.copyfile 需要來源存在）
        with open(standardized, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 40)  # 最小假 wav header
        guard.standardize_audio_input.return_value = standardized
        sep.input_guard = guard

        return sep, standardized

    def test_demucs_exception_does_not_raise_name_error(self, stems_dir):
        """_demucs_separate 拋出例外時，fallback 不再因 target_input 未定義而拋 NameError。"""
        sep, standardized = self._make_separator(stems_dir)

        with patch.object(sep, "_demucs_separate", side_effect=RuntimeError("demucs failed")):
            # 修復前：NameError 會在 except 區塊裡再拋出
            # 修復後：應正常走 fallback，複製 standardized_input 到輸出路徑
            guitar_path, no_guitar_path = sep.separate_guitar(
                os.path.join(stems_dir, "input.wav"),
                stems_dir,
                is_already_instrumental=True
            )

        assert os.path.exists(guitar_path), \
            "fallback 應將 standardized_input 複製到 guitar_path"
        assert os.path.exists(no_guitar_path), \
            "fallback 應將 standardized_input 複製到 no_guitar_path"

    def test_demucs_empty_residual_does_not_raise_name_error(self, stems_dir):
        """_demucs_separate 成功但 residual_keys 為空（else 分支）時，
        修復前 target_input 未定義，現在應正常使用 standardized_input。"""
        sep, standardized = self._make_separator(stems_dir)

        # 讓 _demucs_separate 回傳只有 guitar 鍵（residual_keys 為空）
        fake_guitar = os.path.join(stems_dir, "guitar.wav")
        shutil.copyfile(standardized, fake_guitar)

        with patch.object(sep, "_demucs_separate", return_value={"guitar": fake_guitar}):
            guitar_path, no_guitar_path = sep.separate_guitar(
                os.path.join(stems_dir, "input.wav"),
                stems_dir,
                is_already_instrumental=True
            )

        assert os.path.exists(no_guitar_path), \
            "else 分支（residual_keys 為空）應將 standardized_input 複製到 no_guitar_path"
