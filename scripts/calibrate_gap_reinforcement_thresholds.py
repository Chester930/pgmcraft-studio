r"""
Pass 178 — GapReinforcementNode 門檻校準腳本

背景：
校準迴圈跟正式生產迴圈職責分離（見 docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION
-INTEGRATION-TASK.md）——人工標記不會即時介入生產結果，只累積成校準資料。這支
腳本讀取所有已經複核過的專案（每個專案自己 reports/gap_reinforcement/ 底下的
blocks.json + marks.json 配對），計算目前門檻參數的假陽性/假陰性率，提出調整
建議。**不自動套用**，只有明確加 --apply 才會寫回設定檔，而且寫回前一定會印出
修改前後的差異。

假陽性（信心機制誤判「沒問題」）：needs_review=False 的區塊，被人工標記
fail/fail_phase——代表 CONFIRM_RATIO_THRESHOLD 太寬鬆，該收緊（調高）。
假陰性（信心機制過度保守）：needs_review=True 的區塊，被人工標記 pass——代表
門檻太保守，浪費人工聽的時間，該放寬（調低）。

用法：
    python scripts/calibrate_gap_reinforcement_thresholds.py --projects-root "<專案根目錄>"
    python scripts/calibrate_gap_reinforcement_thresholds.py --projects-root "<...>" --apply
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_MIN_PROJECTS = 5
DEFAULT_MIN_BLOCKS = 30
FAIL_STATES = {"fail", "fail_phase"}

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pgm_craft", "config", "gap_reinforcement_thresholds.json",
)


def _find_review_pairs(projects_root: str):
    """在 projects_root 底下找每個專案的 reports/gap_reinforcement/
    blocks.json + marks.json 配對。回傳 [(project_name, blocks, marks), ...]。"""
    pairs = []
    pattern = os.path.join(projects_root, "*", "reports", "gap_reinforcement", "blocks.json")
    for blocks_path in sorted(glob.glob(pattern)):
        marks_path = os.path.join(os.path.dirname(blocks_path), "marks.json")
        if not os.path.exists(marks_path):
            continue
        try:
            with open(blocks_path, "r", encoding="utf-8") as f:
                blocks = json.load(f)
            with open(marks_path, "r", encoding="utf-8") as f:
                marks = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        project_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(blocks_path))))
        pairs.append((project_name, blocks, marks))
    return pairs


def _compute_rates(pairs):
    """回傳 (false_positive_rate, false_negative_rate, reviewed_block_count,
    project_count)。只統計人工實際標記過（非 unmarked）的區塊，未複核的
    區塊不算進假陽性/假陰性分母——那些還沒有人工判斷可以對照。"""
    fp = fn = reviewed = 0
    for _name, blocks, marks in pairs:
        for b in blocks:
            state = marks.get(b["id"], "unmarked")
            if state == "unmarked":
                continue
            reviewed += 1
            needs_review = bool(b.get("needs_review", True))
            if not needs_review and state in FAIL_STATES:
                fp += 1
            elif needs_review and state == "pass":
                fn += 1
    fp_rate = fp / reviewed if reviewed else 0.0
    fn_rate = fn / reviewed if reviewed else 0.0
    return fp_rate, fn_rate, reviewed, fp, fn


def _load_thresholds(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _propose_thresholds(current: dict, fp_rate: float, fn_rate: float) -> dict:
    """假陽性率高（門檻太寬鬆，誤放太多）→ 調高 CONFIRM_RATIO_THRESHOLD，
    收緊判定；假陰性率高（門檻太保守，誤攔太多）→ 調低。兩者都高的極端情況
    保守不動，交給人工判斷，不做自動決策。單次調整幅度限制在 ±0.05，避免
    一次校準就大幅改變行為。"""
    proposed = dict(current)
    step = 0.05
    fp_high = fp_rate > 0.10
    fn_high = fn_rate > 0.10
    if fp_high and not fn_high:
        proposed["confirm_ratio_threshold"] = round(min(0.9, current["confirm_ratio_threshold"] + step), 3)
    elif fn_high and not fp_high:
        proposed["confirm_ratio_threshold"] = round(max(0.1, current["confirm_ratio_threshold"] - step), 3)
    return proposed


def main():
    parser = argparse.ArgumentParser(description="Pass 178 GapReinforcementNode 門檻校準")
    parser.add_argument("--projects-root", required=True, help="包含多個歌曲專案資料夾的根目錄")
    parser.add_argument("--config-path", default=CONFIG_PATH, help="GapReinforcementNode 讀取的門檻設定檔路徑")
    parser.add_argument("--min-projects", type=int, default=DEFAULT_MIN_PROJECTS)
    parser.add_argument("--min-blocks", type=int, default=DEFAULT_MIN_BLOCKS)
    parser.add_argument("--apply", action="store_true", help="明確套用建議的門檻調整，寫回設定檔。不加這個旗標只印建議，不寫檔。")
    args = parser.parse_args()

    pairs = _find_review_pairs(args.projects_root)
    print(f"[校準] 找到 {len(pairs)} 個已複核過的專案：{[name for name, _, _ in pairs]}")

    fp_rate, fn_rate, reviewed, fp, fn = _compute_rates(pairs)
    print(f"[校準] 共 {reviewed} 個已人工複核的區塊（未標記的不計入）")
    print(f"[校準] 假陽性 {fp} 個（{fp_rate*100:.1f}%）——信心機制判定沒問題，人工發現有錯")
    print(f"[校準] 假陰性 {fn} 個（{fn_rate*100:.1f}%）——信心機制判定可疑，人工聽了覺得沒問題")

    if len(pairs) < args.min_projects or reviewed < args.min_blocks:
        print(
            f"[校準] 樣本不足（需要至少 {args.min_projects} 首歌、{args.min_blocks} 個已複核區塊），"
            f"目前只有 {len(pairs)} 首歌、{reviewed} 個區塊——不提出門檻調整建議，避免過度擬合少數幾首歌的特性。"
        )
        return

    current = _load_thresholds(args.config_path)
    proposed = _propose_thresholds(current, fp_rate, fn_rate)

    if proposed == current:
        print("[校準] 目前假陽性/假陰性率都在可接受範圍內，不建議調整門檻。")
        return

    print("[校準] 建議調整：")
    for key in current:
        if current[key] != proposed.get(key):
            print(f"  {key}: {current[key]} -> {proposed[key]}")

    if not args.apply:
        print("[校準] 未加 --apply，僅顯示建議，未寫回設定檔。確認建議合理後可加 --apply 套用，"
              "套用後務必跑一次黃金基準回歸比對再視為正式生效。")
        return

    with open(args.config_path, "w", encoding="utf-8") as f:
        json.dump(proposed, f, ensure_ascii=False, indent=2)
    print(f"[校準] 已寫回 {args.config_path}。請務必接著跑一次黃金基準回歸比對，確認沒有整體退步。")


if __name__ == "__main__":
    main()
