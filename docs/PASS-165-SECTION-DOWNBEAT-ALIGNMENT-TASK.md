# Pass 165 任務書：升級 SectionDownbeatAlignmentNode 樂段小節號雙向對齊與 Safe Fallback

**狀態**：待處理（尚未實作）
**目標**：升級 Stage 4/5 樂段對齊節點 `SectionDownbeatAlignmentNode`，確保樂段結構對齊小節第 1 拍時同步更新 `start_time` 與 `measure` 小節號，並補齊 `sections` 為空時的 Safe Fallback。

---

## 0. 背景與問題

1. **小節號與時間點非同步問題**：原 `SectionDownbeatAlignmentNode` 在將樂段對齊至 `measure_map` 的 Downbeat 時僅更新了 `start_time`，未同步更新 `sec["measure"]`。後續 Stage 5 DAW 素材導出（MIDI Markers / CSV）若讀取 `measure` 小節號會造成 1 拍的位移。
2. **空資料未退回**：當 `sections` 為空時原節點直接 skip，導致 Blackboard 上的 `sections` 保持為空，依賴 downstream 各自補救。

---

## 1. 具體升級細節

### A. 樂段時間點與小節號雙向同步
在 `SectionDownbeatAlignmentNode.execute()` 對齊每一個 section 時：
- 找出最接近的 `measure_map` 小節。
- 同步更新 `sec["start_time"] = m_start` 與 `sec["measure"] = m_num`。

### B. 空樂段 Safe Fallback
- 若輸入的 `sections` 為空，自動建立全曲預設樂段 `[{"name": "Main", "start_time": 0.0, "measure": 1}]` 並寫回 Blackboard。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass165.py`：
   - 驗證樂段對齊後 `start_time` 與 `measure` 同步更新。
   - 驗證 `sections` 為空時 Safe Fallback 能正確產生並對齊預設樂段。
2. 執行單元測試與回歸測試。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
