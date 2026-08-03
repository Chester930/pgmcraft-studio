# Pass 168 任務書：實作雙向確信錨點跳過與拍位反推節點 (TwoWayAnchorBacktraceNode)

**狀態**：待處理（尚未實作）
**目標**：解決切分音（Push/Pull Syncopation）與模糊前奏/間奏段落的小節第一拍誤判問題。當遇到不確定小節第一拍時，先跳過不硬猜，找到下一個高確信度的第一拍錨點後，再雙向反推中間事件在小節內的拍位（如 4& 拍切分音），精確導回真正的第 1 拍 (Downbeat) 時間點。

---

## 0. 背景與問題

在 0s~32s (前奏吉他/切分音) 與 1m35s~2m05s (間奏鼓點切分音與吉他和聲過渡) 段落中：
- 舊邏輯易將切分音（如小節第 4 拍半 4& 提前搶拍）誤判為「下一個小節的第 1 拍」，導致小節長度突變至 1.28s (187 BPM) 或 1.70s (140 BPM) 發散跑拍。
- 使用硬拖/硬縮限制無法提升識別精度。

---

## 1. 雙向反推演算法架構 (`TwoWayAnchorBacktraceNode`)

1. **高信心度錨點檢測 (High-Confidence Anchors)**：
   - 提取帶有 Kick + Snare 重拍撞擊、樂段開頭或強音打點的事件作為高信心錨點 ($C \ge 0.85$)。
2. **跳過模糊區段與反向推算 (Skip Uncertain Gaps & Reverse-Phase Inference)**：
   - 對於兩個確定錨點之間的模糊/切分音區段，暫不直接劃分小節。
   - 計算該區段內音符/瞬態相對於前後確定錨點的時間相位。
   - 若瞬態落在切分拍位（如第 4 拍半 `4&`，相位偏置 $\approx 0.875 \text{ bar}$），判斷其為切分音，並透過公式 $\text{Downbeat} = T_{\text{event}} - (\text{BeatOffset} \times \text{TempoInterval})$ 精確反推出正確的第 1 拍位置。
3. **小節脈衝更新與網格寫回**：
   - 將雙向反推得到的精確 Downbeats 更新至 Blackboard 上的 `measure_map` 與 `beats`。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass168.py`：
   - 驗證切分音 (4& 搶拍) 情況下，節點能正確跳過並由下一個確定錨點反推出第 1 拍，而不把切分音當作第 1 拍。
   - 驗證前奏/間奏段落不再出現 185+ BPM 或 140 BPM 突變發散。
2. 執行全套測試回歸與實測音檔生成。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
