"""SDD Pass 198A — 小節內隱藏 downbeat 升格。"""

import numpy as np

from pgm_craft.workflow.audio_nodes import MeasureMapNode


def _rows(times, downbeats):
    downbeats = set(downbeats)
    return np.asarray([[time, 1 if index in downbeats else (index % 4) + 1]
                       for index, time in enumerate(times)])


class TestSDDPass198IntraBarPromotion:

    def test_promotes_candidate_near_theoretical_four_beat_boundary(self):
        beat = 0.3647
        times = [beat * index for index in range(10)]
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 9]))
        rows[4]["beat"] = 2
        protected = [(times[0], times[0]), (times[9], times[9])]

        rows, decisions = node._promote_intra_bar_downbeats(rows, [0, 9], protected)

        assert rows[4]["beat"] == 1
        assert decisions[0]["reason"] == "intra_bar_downbeat_promotion"
        assert decisions[0]["promoted_time"] == round(times[4], 6)
        assert decisions[0]["residual_beats"] <= 0.15

    def test_rejects_candidate_outside_conservative_tolerance(self):
        beat = 0.3647
        times = [beat * index for index in range(10)]
        times[4] += 0.1
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 9]))
        rows[4]["beat"] = 2
        protected = [(times[0], times[0]), (times[9], times[9])]

        rows, decisions = node._promote_intra_bar_downbeats(rows, [0, 9], protected)

        assert rows[4]["beat"] != 1
        assert decisions == []

    def test_unprotected_short_measure_behavior_is_unchanged(self):
        beat = 0.36
        times = [beat * index for index in range(11)]
        node = MeasureMapNode()
        rows = node._normalize_beats(_rows(times, [0, 6, 10]))

        rows, decisions = node._promote_intra_bar_downbeats(rows, [0, 6, 10], [])

        assert [row["beat"] for row in rows] == [1, 2, 3, 4, 1, 2, 1, 4, 1, 2, 1]
        assert decisions == []
