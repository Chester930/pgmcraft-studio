# PASS-203 Evidence Fusion Diagnosis

## Result

- Ticks: **500**; commits: **5**; no-candidate ticks: **480**; candidate-but-below-threshold ticks: **15**.
- Trace runtime: 761.33s.
- Existing pipeline report: `SUCCESS`.

## Evidence-source activity

("Candidate instances" counts a source as active whenever it either produced its own candidate or attached a support tag to someone else's -- e.g. bass/harmonic/phrase evidence is designed to boost a drum candidate's confidence rather than stand alone, so "standalone" can be 0 while the source is still working.)

| Source | Ticks with candidates | Candidate instances (incl. support tags) | Standalone candidates |
|---|---:|---:|---:|
| drum | 21 | 572 | 0 |
| drum_bass | 20 | 506 | 0 |
| chord | 20 | 109 | 0 |
| melody | 21 | 389 | 0 |
| v1_grid | 21 | 203 | 0 |
| beat_this | 0 | 0 | 0 |

## Below-threshold gap

- Mean gap: -0.0340; minimum gap: -0.3000; maximum gap: 0.2500.
- Representative near-miss ticks:
  - tick 14: time=95.178594, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 16: time=126.862222, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 17: time=135.604535, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'expected_bar_interval', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 18: time=147.202902, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'expected_bar_interval', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']
  - tick 19: time=156.049705, confidence=1.0, threshold=0.7, sources=['drums', 'kick', 'snare_backbeat_support', 'outside_fill_exclusion', 'bass_coincidence_support', 'phrase_anchor_support']

## Interpretation

This report separates no-evidence ticks from near misses; it does not tune any confidence formula. Any follow-up parameter or source change requires a separate decision after reviewing these concrete examples.
