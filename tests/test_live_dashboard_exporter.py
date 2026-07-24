"""
LiveDashboardExporter 舞台主控指示儀表板導出器單元測試
"""

import unittest
from pgm_craft.daw_exporter import LiveDashboardExporter

class TestLiveDashboardExporter(unittest.TestCase):
    def test_live_dashboard_export_html(self):
        """測試 LiveDashboardExporter 能正常生成包含 Live 舞台控制與小節燈號的 HTML"""
        report = {
            "audio_file": "demo.wav",
            "estimated_key": "C Major",
            "average_bpm": 120.0,
            "total_measures": 16,
            "sections": [
                {"name": "Verse", "start_measure": 1, "end_measure": 8},
                {"name": "Chorus", "start_measure": 9, "end_measure": 16}
            ]
        }
        
        exporter = LiveDashboardExporter(report, theme="neon")
        html = exporter.to_html()
        
        self.assertIn("Live 舞台指示儀表板", html)
        self.assertIn("C Major", html)
        self.assertIn("120.0", html)
        self.assertIn("Chorus", html)

if __name__ == '__main__':
    unittest.main()
