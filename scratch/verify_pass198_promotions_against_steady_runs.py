r"""
Pass 198 追記驗證——把階段 A（_promote_intra_bar_downbeats）產生的每個
升格決策，拿去跟 SteadyPercussionCountAnchorNode 自己的偵測邏輯獨立找到
的「連續穩定鼓點段落」交叉核對。落在某段穩定鼓點邊界附近的升格視為有
真實證據支持；找不到的視為理論網格瞎猜，需要用使用者說的「連續穩定
鼓點是對齊提示」原則重新處理（見任務書 docs/PASS-198-*.md 第 7.6 節）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode

PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness"
    r"\outputs\pass198_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
STEMS_DIR = os.path.join(PROJECT_DIR, "stems")

KNOWN_BEAT_LENGTH_SEC = 0.364671  # 全曲穩健 median，跟 Pass 197/198 用同一個估計方式
MATCH_TOLERANCE_SEC = 0.05

# Pass 198 階段 A 真實回驗結果裡的升格時間點（來自 measure_map.json 的
# phase_reconciliation，reason == "intra_bar_downbeat_promotion"）。
PROMOTIONS = [9.482, 22.883, 24.343, 25.814, 33.834, 35.300, 36.706, 38.178, 39.652, 41.097]


def main():
    node = SteadyPercussionCountAnchorNode()
    all_runs = []
    for stem_key, rel in node.STEM_CANDIDATES + [node.WHOLE_DRUM_STEM]:
        path = os.path.join(STEMS_DIR, *rel)
        onsets = node._detect_onsets(path)
        for run in node._find_steady_runs(onsets, KNOWN_BEAT_LENGTH_SEC, []):
            all_runs.append((stem_key, run))

    for promoted_time in PROMOTIONS:
        best_stem, best_run, best_dist = None, None, float("inf")
        for stem_key, run in all_runs:
            dist = min(abs(promoted_time - run["start_time"]), abs(promoted_time - run["end_time"]))
            if dist < best_dist:
                best_stem, best_run, best_dist = stem_key, run, dist
        backed = best_dist <= MATCH_TOLERANCE_SEC
        verdict = "BACKED by steady run" if backed else "NOT backed (nearest run far away)"
        print(
            f"promoted {promoted_time:8.3f}s -> nearest steady run: {best_stem:6s} "
            f"{best_run['start_time']:.3f}-{best_run['end_time']:.3f} "
            f"(dist={best_dist*1000:.0f}ms)  [{verdict}]"
        )


if __name__ == "__main__":
    main()
