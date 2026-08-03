# Pass 159 任務書：修復 Stage 2 分軌子樹的資料完整性 bug

**狀態**：待處理（尚未實作）
**交接原因**：使用者在本次 session 用量已達上限，將由另一個 agent／session 接手執行本任務。這份文件必須自包含——執行者不需要讀過先前的對話記錄，只需要這份文件與程式碼本身。

---

## 0. 給接手 agent 的快速定位

- 專案根目錄：`D:\Users\666\Desktop\UVR5 音檔\自動節拍器`（工作用 worktree：`.claude\worktrees\barstart-v2-strengthen`，分支 `worktree-barstart-v2-strengthen`）
- **先進入這個 worktree 再開始改動**（`EnterWorktree` 或確認目前 cwd 已經在其中）。
- 本專案的既有慣例（務必遵守，可參考 `tests/test_sdd_pass157.py`、`tests/test_sdd_pass158.py` 當格式範本）：
  1. 每個 Pass 對應一個 `tests/test_sdd_pass{N}.py`，檔案開頭要有完整的中文 docstring：背景／根因／修復方案／本測試驗證什麼。
  2. 修完後跑「先針對性回歸、再全套測試」：全套測試套件較大（約 750+ 項），**單一 pytest 指令跑全套常常會被外部機制中止**——已知可行的 workaround 是把 `tests/test_*.py` 依字母序切成 4 批，依序（不要同時跑多個涉及 GPU 的背景工作）分別執行。已知有 1 項既有、與本任務無關的失敗：`tests/test_cli_quiet.py::test_main_quiet_suppresses_stdout`，看到它失敗是正常的，不用修。
  3. `docs/BT-BUILD-PROGRESS.md` 是本專案的正式變更日誌——修完後要在「五、SDD Pass 總覽表」加一列，並在「七、變更日誌」加一段（格式完全比照 Pass 155–158 現有的寫法，中文、含背景/根因/修復/驗證數據）。
  4. Commit message 結尾要有：
     ```
     Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
     ```
  5. 完成後：commit → push → `git merge-tree` 確認能乾淨合併 origin/main → 開一個新 PR → merge。這是使用者在本 session 反覆確認過的標準流程，不需要每次都重新詢問是否要合併。
  6. 提交前不要 `--no-verify`、不要略過 hook。

---

## 1. 背景

使用者這個 session 花了好幾個 Pass（155–158）修節奏偵測（BarStart v2）的問題：先是決定性推論（Pass 155）、無鼓段落的 v1 網格回填（Pass 156–157）、再到「委任閘門沒檢查小節長度合理性，把每一拍都誤判成小節」（Pass 158）。Pass 158 修完、使用者實測後，接著提出「乾脆整個 BT 重新盤點」的要求，於是我們做了三輪唯讀研究（用 subagent），把 BarStart v2 子系統、module3_bt.py 的真實上游鏈、以及 Stage 2 分軌子樹（`build_stem_separation_tree()`）都完整文件化，整理成一份給使用者查閱的節點地圖。

在盤點 Stage 2 分軌子樹時，發現這棵樹雖然接線正確，但**有真實的資料完整性 bug**：某些 stem 的 blackboard key 存在，但實際檔案在管線跑到一半時就已經被自己的清理節點刪掉了。下游的節奏偵測、證據階梯等邏輯全部是透過 `stems["xxx"]` 這個 key 去判斷「這個音色有沒有可用資料」，如果 key 存在但檔案已經被刪，下游會誤以為有資料可用、實際讀檔時才會出錯或悄悄拿到空結果——這類問題會污染後續所有節奏偵測相關節點的行為，因此使用者要求先修好這一層，再開始逐節點檢視下游邏輯。

---

## 2. 根因（已在程式碼中逐行確認）

### Bug A（P0）：`StrictStemDirectoryGuardNode.WHITELIST_MAP` 的白名單檔名跟實際產出檔名不同步

檔案：`pgm_craft/workflow/stem_separation_bt.py`
類別：`StrictStemDirectoryGuardNode`（定義於 L751 附近，`WHITELIST_MAP` 在 L762-771）

這個節點會遍歷每個子目錄，把不在白名單裡的檔案直接 `os.remove()`。目前的白名單：

```python
WHITELIST_MAP = {
    "": {"no_vocals.wav", "instrumental.wav"},
    "vocals": {"vocals.wav", "lead_vocal.wav", "backing_vocals.wav", "vocals_debreathed.wav", "breath_noises.wav"},
    "drums": {"drums.wav", "kick.wav", "snare.wav", "hihat.wav"},        # <-- 問題在這裡
    "bass": {"bass.wav", "electric_bass.wav", "synth_bass_808.wav"},
    "guitars": {...},
    "pianos": {...},
    "strings": {...},
    "events": {"glass.wav", "applause.wav", "cheering.wav", "screaming.wav", "speech_subtitles.srt"}  # <-- 問題在這裡
}
```

實際情況：
- `drums` 子目錄裡真正產出的檔名是 **`hihat_cymbals.wav`**（見 `SubSplitDrumsNode`，`stem_separation_bt.py:450` 附近），不是 `hihat.wav`——白名單寫錯名字，導致這個檔案每次都被刪掉。下游 `stems["hihat"]` 這個 key 依然存在（由分離節點自己寫入），但指向一個已經不存在的路徑。
- `events` 子目錄裡實際會產出 **`count_in_voice.wav`**（`ExtractCountInVoiceNode`，L895 附近）與 **`claps_snaps.wav`**（`ExtractClapSnapEventsNode`，L928 附近），但這兩個檔名完全沒被列進白名單——兩者也是每次都被刪掉。

**修復**：
```python
"drums": {"drums.wav", "kick.wav", "snare.wav", "hihat_cymbals.wav"},
...
"events": {"glass.wav", "applause.wav", "cheering.wav", "screaming.wav", "speech_subtitles.srt", "count_in_voice.wav", "claps_snaps.wav"},
```

---

### Bug B（P0）：`separator.py` 的 `separate_guitar()` 例外處理路徑引用未定義變數，導致 Demucs 出錯時整個吉他分支必然失敗

檔案：`pgm_craft/separator.py`
函式：`separate_guitar()`（L450-484）

```python
def separate_guitar(self, audio_path, output_dir, is_already_instrumental=False):
    ...
    prepared_input = self.input_guard.prepare_prerequisite_audio(...)
    standardized_input = self.input_guard.standardize_audio_input(...)
    ...
    try:
        paths = self._demucs_separate(...)
        ...
        if residual_keys:
            ...
        else:
            shutil.copyfile(target_input, no_guitar_path)   # L479 <-- target_input 未定義
    except Exception as e:
        print(f"[Guitar Demucs Fallback] {e} — 降級為複製伴奏")
        shutil.copyfile(target_input, guitar_path)            # L482 <-- 同樣未定義
        shutil.copyfile(target_input, no_guitar_path)          # L483 <-- 同樣未定義
    return guitar_path, no_guitar_path
```

這個函式裡只定義了 `prepared_input` 與 `standardized_input`，從未定義過 `target_input`。只要 `_demucs_separate()` 丟出任何例外（例如 residual_keys 為空、或 Demucs 執行失敗），就會進到 except 分支，然後因為 `target_input` 未定義而拋出 `NameError`——這個新的例外會被上層 `PeelCoreTrioNode` 的 try/except（`stem_separation_bt.py`，`PeelCoreTrioNode` 內）吞掉、整個三重奏分支（guitar/piano/strings 全部一起）直接判定 FAILURE、走 passthrough——三者全部沒有輸出。

對照同一個檔案裡結構幾乎一樣的 `separate_piano()`（L486-518），它正確地全程使用 `standardized_input`：

```python
else:
    shutil.copyfile(standardized_input, no_piano_path)    # 對應 L513
except Exception as e:
    print(f"[Piano Demucs Fallback] {e} — 降級為複製伴奏")
    shutil.copyfile(standardized_input, piano_path)         # 對應 L516
    shutil.copyfile(standardized_input, no_piano_path)      # 對應 L517
```

**修復**：把 `separate_guitar()` 裡三處 `target_input`（L479, L482, L483）全部改成 `standardized_input`，跟 `separate_piano()` 保持一致。

---

### Bug C（P1，選做）：`sub_bass_808` 與 `synth_bass_808` 命名不一致

`pgm_craft/workflow/beat_tracking_bt.py` 與 `module3_barstart_v2_bt.py` 裡，`AnchorTransientSnapNode(anchor_key="bass_anchors", stem_keys=("sub_bass_808", "electric_bass", "bass"), ...)` 的呼叫把 `"sub_bass_808"` 列為第一優先，但整條分軌管線**只會產出 `synth_bass_808`**（`SubSplitBassNode`），從來不會產出 `sub_bass_808`——`sub_bass_808.wav` 只有 Tier-2（`PeelTier2HighConfidenceNode`）會寫，而且那個檔案本身也會被 Guard 清掉（`WHITELIST_MAP["bass"]` 沒有 `sub_bass_808.wav`）。

目前因為 `AnchorTransientSnapNode` 有 fallback chain（`sub_bass_808` 找不到就找 `electric_bass`，再找不到就找 `bass`），這個問題**不會造成功能性失敗**，只是死碼（第一優先永遠命不中）。

兩種修法擇一即可，不強制要求：
1. （較簡單）把 `WHITELIST_MAP["bass"]` 加上 `"sub_bass_808.wav"`，讓 Tier-2 產出的檔案能留下來。
2. （較乾淨）把所有 `AnchorTransientSnapNode(..., stem_keys=("sub_bass_808", "electric_bass", "bass"), ...)` 的 `stem_keys` 改成 `("synth_bass_808", "electric_bass", "bass")`，反映實際會被產出的檔名。

若時間有限，**P1 可以跳過**，只要在任務完成報告裡註記「已知、非阻塞、留待後續」即可。

---

## 3. 明確排除在本次範圍外（避免 scope creep）

以下問題在分軌子樹稽核時也有發現，**故意不在本 Pass 處理**，只需要在完成報告裡提一句「已知、不在本次範圍」：

- 好幾個「細分軌」其實是同一份音檔的位元複本（`lead_vocal`/`backing_vocals`/`vocals_debreathed`/`breath_noises` 都是 `vocals.wav` 複本；`electric_bass`/`synth_bass_808` 都是 `bass.wav` 複本）——這是分離演算法本身尚未真正實作，不是本 Pass 要修的「資料遺失」類 bug。
- Tier-2 的殘音級聯鏈斷開（`trio_residual_path` 從未寫進 blackboard，Tier-2 實際上是在完整伴奏上跑，不是在乾淨的殘音上跑）——這是演算法設計問題，範圍遠大於「修 bug」。
- `stems` dict 在同一個 `project_dir` 重跑時不會重置，可能混入舊資料——這是另一個獨立問題，需要單獨評估影響範圍。

---

## 4. 驗證方式

1. 撰寫 `tests/test_sdd_pass159.py`，比照 `tests/test_sdd_pass157.py` / `tests/test_sdd_pass158.py` 的格式（模組級中文 docstring 說明背景/根因/修復，然後是測試類別）。至少要涵蓋：
   - `StrictStemDirectoryGuardNode`：在 `drums/` 子目錄放一個 `hihat_cymbals.wav`，跑過節點後確認檔案還在（沒被誤刪）。
   - `StrictStemDirectoryGuardNode`：在 `events/` 子目錄放 `count_in_voice.wav` 與 `claps_snaps.wav`，跑過節點後確認兩者都還在。
   - 迴歸：原本白名單裡就有的合法檔案（例如 `drums.wav`、`kick.wav`）跑過節點後依然存在（沒有因為改動而被誤刪）；真正的異物檔案（不在白名單內、例如 `residual_something.wav`）依然會被正確刪除。
   - `separate_guitar()`：模擬 `_demucs_separate()` 拋出例外的情境（可以直接呼叫該方法並讓依賴的內部方法 raise），確認不再拋出 `NameError`，而是正常走到 fallback（複製 `standardized_input` 到 `guitar_path`/`no_guitar_path`）。
   - 如果有做 Bug C：對應驗證。

2. 針對性回歸（先跑這些，確認沒有連帶弄壞其他東西）：
   ```
   pytest tests/test_sdd_pass159.py tests/test_sdd_pass18.py tests/test_separator_prerequisites.py tests/test_sdd_pass22.py -q
   ```
   （`test_sdd_pass22.py` 是已知涵蓋 `StrictStemDirectoryGuardNode` 根目錄/vocals 子目錄的既有測試；`test_sdd_pass18.py`、`test_separator_prerequisites.py` 涵蓋分軌相關既有邏輯，務必確認不迴歸。）

3. 全套測試（batched，避免單一長跑指令被中止——參考 Pass 156/157/158 使用過的做法）：把 `tests/test_*.py` 依字母序切 4 批依序執行，確認總和跟既有基準一致（約 750+ passed，只有 `test_cli_quiet.py` 那 1 項既有失敗維持不變）。

4. 更新 `docs/BT-BUILD-PROGRESS.md`：在總覽表加 Pass 159 一列、在變更日誌加一段，格式比照 Pass 155–158。

5. Commit → push → `git merge-tree` 確認乾淨合併 → 開新 PR → merge。完成後可以直接告知使用者、提醒對方在自己的主要工作目錄 `git pull`。

---

## 5. 完成後怎麼確認「分軌真的完整了」

建議修完後，用一首真實歌曲（例如使用者常用的測試曲 World is Mine，`d:\Users\666\Music\...\stems`，如果這台機器上還在）重新跑一次「🎯 節奏定位」分頁的完整流程，检查輸出的 `stems/drums/hihat_cymbals.wav`、`stems/events/count_in_voice.wav`、`stems/events/claps_snaps.wav` 三個檔案是否都確實存在於磁碟上（而不只是 `stems` dict 裡有 key）。這是使用者原本提出這個任務時的驗收標準。
