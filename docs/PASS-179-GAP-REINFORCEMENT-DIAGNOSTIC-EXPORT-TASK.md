# Pass 179 任務書：GapReinforcementNode 診斷輸出落盤，接通校準迴圈

**狀態**：已完成
**目標**：補上 Pass 178 設計文件裡寫了、但實作時漏掉的一塊——`GapReinforcementNode`
執行後要把診斷資料存成審查工具看得懂的格式，讓正式生產的輸出可以直接餵給
`scratch/gap_review_server.py` 複核，不需要 scratch 腳本重跑。沒有這一塊，校準
迴圈完全接不上生產迴圈，人工標記永遠餵不到門檻調整。

---

## 0. 背景

Pass 178 完成 `GapReinforcementNode` 本體實作（缺口偵測、逐輪疊加證據、品質
守門），但只在 blackboard 上寫了一份給程式內部用的 `gap_reinforcement_report`，
沒有落盤成 `blocks.json`/`beats.json` 這組審查工具原生看得懂的格式——這是
`docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md` 第 1.1 節
「診斷輸出相容審查工具格式」明確要求、但實作時遺漏的部分。

## 1. 設計

### 1.1 落盤內容

`GapReinforcementNode` 執行完（不管最後是 `APPLIED` 還是
`REJECTED_NOT_BETTER`）都落盤，存進這首歌自己的專案資料夾：

- `reports/gap_reinforcement/blocks.json`：對**最終決定採用的 beats**（`APPLIED`
  用補強後的、`REJECTED_NOT_BETTER` 用原始融合結果）套用跟 Lane1-5 一致的信心
  評分（`_confidence_segments`，從 `_confirmation_gap_ranges` 拆出共用邏輯），
  輸出全曲完整的 `[{id, start, end, needs_review}, ...]`——不是只有缺口，全曲
  都要有，跟審查工具的 `blocks.json` 格式定義完全一致。
- `reports/gap_reinforcement/beats.json`：`{tempo, beats}`，tempo 從最終 beats
  的拍距中位數換算，beats 就是最終決定採用的那組。

沒有 `project_dir`（blackboard 沒有這個 key，例如單元測試環境）時安全跳過落盤，
不影響節點原本的 SUCCESS 回傳。

### 1.2 審查工具接上正式生產輸出

`scratch/gap_review_server.py` 的 `discover_lanes()` 新增一種 Lane 來源：專案
資料夾下 `reports/gap_reinforcement/blocks.json` 存在時，加一條新 Lane——**音檔
沿用「目前管線 (V1)」那條的 `click/mix_with_click.wav`**，不是另外渲染一份：
`GapReinforcementNode` 補強出來的拍點，最終會流進同一條 pipeline 繼續跑完精修
鏈、變成同一份 `mix_with_click.wav` 的一部分，不是一個獨立產物，沒有必要（也
不應該）另外渲染音檔。

新 Lane 的分類標記為 `疊加證據鏈（正式生產）`，跟 scratch 的 Lane1-5（標記
`疊加證據鏈`）用同一個色系但文字區分開來，讓使用者一眼看出這是真正生產出來
的診斷，不是探索性腳本模擬的。

## 2. 驗證方式

1. 單元測試：合成音訊跑一次 `GapReinforcementNode.execute()`（帶
   `project_dir`），驗證 `reports/gap_reinforcement/blocks.json`/`beats.json`
   確實落盤，且格式跟審查工具 `_resolve_submeasure()`/`load_blocks()` 預期的
   欄位（`id`/`start`/`end`/`needs_review`、`tempo`/`beats`）完全相容。
2. 驗證沒有 `project_dir` 時不丟例外、正常回傳 SUCCESS。
3. `scratch/gap_review_server.py` 手動驗證：指向一個有
   `reports/gap_reinforcement/blocks.json` 的假專案資料夾，確認新 Lane 能被
   discover_lanes() 找到、正確共用 `current` 的音檔路徑。
