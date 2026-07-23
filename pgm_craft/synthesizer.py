"""
PGMCraft PGM Synthesizer Module
Synthesizes Click Tracks and exports MIDI Tempo Maps for DAW / Live PGM sync.
"""

import os
import numpy as np
import soundfile as sf
import librosa
import mido


TICKS_PER_BEAT = 480
MIN_BPM = 30.0
MAX_BPM = 300.0

class PGMSynthesizer:
    def synthesize_click(self, audio_path, beats, output_dir="outputs"):
        """Synthesizes high/low click track and mixes with original audio."""
        os.makedirs(output_dir, exist_ok=True)
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        total_samples = len(y)
        click_audio = np.zeros(total_samples)

        # High click (1000Hz) for Beat 1, Low click (600Hz) for Beats 2-4
        t_click = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
        high_click = 0.8 * np.sin(2 * np.pi * 1000 * t_click) * np.exp(-t_click * 60)
        low_click = 0.5 * np.sin(2 * np.pi * 600 * t_click) * np.exp(-t_click * 60)

        for timestamp, beat_num in beats:
            idx = int(timestamp * sr)
            if idx >= total_samples:
                continue
            click_wave = high_click if int(beat_num) == 1 else low_click
            end_idx = min(idx + len(click_wave), total_samples)
            actual_len = end_idx - idx
            click_audio[idx:end_idx] += click_wave[:actual_len]

        click_path = os.path.join(output_dir, "click_track.wav")
        mix_path = os.path.join(output_dir, "mix_with_click.wav")

        sf.write(click_path, click_audio, sr)
        mixed = 0.7 * y + 0.5 * click_audio
        max_val = np.max(np.abs(mixed))
        if max_val > 1.0:
            mixed /= max_val
        sf.write(mix_path, mixed, sr)

        return click_path, mix_path

    def _normalize_beats(self, beats):
        """Return sorted beat rows as (timestamp_seconds, beat_number)."""
        if beats is None:
            return []

        rows = []
        for row in beats:
            if len(row) < 2:
                continue
            timestamp = float(row[0])
            beat_num = int(row[1])
            if timestamp >= 0:
                rows.append((timestamp, beat_num))
        return sorted(rows, key=lambda item: item[0])

    def _tempo_from_interval(self, seconds_per_beat):
        if seconds_per_beat <= 0:
            bpm = 120.0
        else:
            bpm = 60.0 / seconds_per_beat
        bpm = min(MAX_BPM, max(MIN_BPM, bpm))
        return mido.bpm2tempo(bpm)

    def _tempo_events(self, beat_rows):
        if len(beat_rows) < 2:
            return [(0, mido.bpm2tempo(120.0))]

        first_interval = beat_rows[1][0] - beat_rows[0][0]
        first_tempo = self._tempo_from_interval(first_interval)
        seconds_per_tick = (first_tempo / 1_000_000.0) / TICKS_PER_BEAT
        lead_in_ticks = int(round(beat_rows[0][0] / seconds_per_tick)) if seconds_per_tick > 0 else 0

        events = [(0, first_tempo)]
        for index in range(1, len(beat_rows) - 1):
            interval = beat_rows[index + 1][0] - beat_rows[index][0]
            absolute_tick = lead_in_ticks + index * TICKS_PER_BEAT
            events.append((absolute_tick, self._tempo_from_interval(interval)))
        return events

    def _write_tempo_track(self, midi_file, beat_rows):
        tempo_track = mido.MidiTrack()
        midi_file.tracks.append(tempo_track)
        tempo_track.append(mido.MetaMessage("track_name", name="PGMCraft Tempo Map", time=0))
        tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

        last_tick = 0
        for absolute_tick, tempo in self._tempo_events(beat_rows):
            delta = max(0, absolute_tick - last_tick)
            tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=delta))
            last_tick = absolute_tick

        final_tick = self._final_tick(beat_rows)
        tempo_track.append(mido.MetaMessage("end_of_track", time=max(0, final_tick - last_tick)))

    def _lead_in_ticks(self, beat_rows):
        if len(beat_rows) < 2:
            return 0
        first_tempo = self._tempo_from_interval(beat_rows[1][0] - beat_rows[0][0])
        seconds_per_tick = (first_tempo / 1_000_000.0) / TICKS_PER_BEAT
        return int(round(beat_rows[0][0] / seconds_per_tick)) if seconds_per_tick > 0 else 0

    def _final_tick(self, beat_rows):
        if not beat_rows:
            return TICKS_PER_BEAT * 4
        return self._lead_in_ticks(beat_rows) + max(1, len(beat_rows)) * TICKS_PER_BEAT

    def export_midi_tempo_map(self, beats, output_dir="outputs"):
        """Exports a Standard MIDI File containing tempo meta events for DAW import."""
        os.makedirs(output_dir, exist_ok=True)
        beat_rows = self._normalize_beats(beats)
        midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
        self._write_tempo_track(midi, beat_rows)

        anchor_track = mido.MidiTrack()
        midi.tracks.append(anchor_track)
        anchor_track.append(mido.MetaMessage("track_name", name="PGMCraft Tempo Anchor", time=0))
        anchor_track.append(mido.Message("program_change", program=115, channel=0, time=0))
        anchor_track.append(mido.Message("note_on", note=60, velocity=1, channel=0, time=0))
        anchor_track.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=self._final_tick(beat_rows)))
        anchor_track.append(mido.MetaMessage("end_of_track", time=0))

        midi_path = os.path.join(output_dir, "tempo_map.mid")
        midi.save(midi_path)
        return midi_path

    def export_midi_click_guide(self, beats, output_dir="outputs"):
        """Exports MIDI click notes aligned to the generated tempo map."""
        os.makedirs(output_dir, exist_ok=True)
        beat_rows = self._normalize_beats(beats)
        midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
        self._write_tempo_track(midi, beat_rows)

        click_track = mido.MidiTrack()
        midi.tracks.append(click_track)
        click_track.append(mido.MetaMessage("track_name", name="PGMCraft Click Guide", time=0))
        click_track.append(mido.Message("program_change", program=115, channel=0, time=0))

        last_tick = 0
        note_length_ticks = max(1, int(TICKS_PER_BEAT * 0.12))
        lead_in_ticks = self._lead_in_ticks(beat_rows)
        for index, (_, beat_num) in enumerate(beat_rows):
            absolute_tick = lead_in_ticks + index * TICKS_PER_BEAT
            pitch = 76 if int(beat_num) == 1 else 77
            velocity = 115 if int(beat_num) == 1 else 85
            click_track.append(
                mido.Message("note_on", note=pitch, velocity=velocity, channel=0, time=max(0, absolute_tick - last_tick))
            )
            click_track.append(
                mido.Message("note_off", note=pitch, velocity=0, channel=0, time=note_length_ticks)
            )
            last_tick = absolute_tick + note_length_ticks

        click_track.append(mido.MetaMessage("end_of_track", time=max(0, self._final_tick(beat_rows) - last_tick)))
        midi_path = os.path.join(output_dir, "click_guide.mid")
        midi.save(midi_path)
        return midi_path

    def _chord_name_to_midi_notes(self, chord_name: str) -> list:
        """Maps a chord string (e.g., 'Cmaj', 'Am', 'G#min') to root/triad MIDI pitches."""
        note_offsets = {
            'C': 60, 'D': 62, 'E': 64, 'F': 65, 'G': 67, 'A': 69, 'B': 71
        }
        if not chord_name or chord_name == "N/A":
            return [60]

        root = chord_name[0].upper()
        base_pitch = note_offsets.get(root, 60)
        idx = 1
        if len(chord_name) > 1 and chord_name[1] in ('#', 'b'):
            if chord_name[1] == '#':
                base_pitch += 1
            elif chord_name[1] == 'b':
                base_pitch -= 1
            idx += 1

        suffix = chord_name[idx:].lower()
        if 'm' in suffix and 'maj' not in suffix:
            return [base_pitch, base_pitch + 3, base_pitch + 7]
        else:
            return [base_pitch, base_pitch + 4, base_pitch + 7]

    def export_midi_chord_guide(self, chord_progression, beats, output_dir="outputs"):
        """Exports MIDI chord guide notes and markers aligned to tempo map."""
        os.makedirs(output_dir, exist_ok=True)
        beat_rows = self._normalize_beats(beats)
        midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
        
        tempo_track = mido.MidiTrack()
        midi.tracks.append(tempo_track)
        tempo_track.append(mido.MetaMessage("track_name", name="PGMCraft Tempo & Markers", time=0))
        tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

        last_tick = 0
        lead_in_ticks = self._lead_in_ticks(beat_rows)

        for absolute_tick, tempo in self._tempo_events(beat_rows):
            delta = max(0, absolute_tick - last_tick)
            tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=delta))
            last_tick = absolute_tick

        if chord_progression:
            last_marker_tick = 0
            for item in chord_progression:
                m_num = item.get("measure", 1)
                chord_str = item.get("chord", "N/A")
                m_beat_idx = (m_num - 1) * 4
                abs_tick = lead_in_ticks + m_beat_idx * TICKS_PER_BEAT
                delta = max(0, abs_tick - last_marker_tick)
                tempo_track.append(mido.MetaMessage("marker", text=f"M{m_num:02d}: {chord_str}", time=delta))
                last_marker_tick = abs_tick

        final_tick = self._final_tick(beat_rows)
        tempo_track.append(mido.MetaMessage("end_of_track", time=max(0, final_tick - last_tick)))

        chord_track = mido.MidiTrack()
        midi.tracks.append(chord_track)
        chord_track.append(mido.MetaMessage("track_name", name="PGMCraft Chord Guide", time=0))
        chord_track.append(mido.Message("program_change", program=0, channel=0, time=0))

        last_chord_tick = 0
        if chord_progression:
            for item in chord_progression:
                m_num = item.get("measure", 1)
                chord_str = item.get("chord", "N/A")
                m_beat_idx = (m_num - 1) * 4
                abs_tick = lead_in_ticks + m_beat_idx * TICKS_PER_BEAT
                delta = max(0, abs_tick - last_chord_tick)
                
                pitches = self._chord_name_to_midi_notes(chord_str)
                note_dur = TICKS_PER_BEAT * 4
                
                for p in pitches:
                    chord_track.append(mido.Message("note_on", note=p, velocity=80, channel=0, time=delta if p == pitches[0] else 0))
                for p in pitches:
                    chord_track.append(mido.Message("note_off", note=p, velocity=0, channel=0, time=note_dur if p == pitches[0] else 0))

                last_chord_tick = abs_tick + note_dur

        chord_track.append(mido.MetaMessage("end_of_track", time=max(0, final_tick - last_chord_tick if chord_progression else final_tick)))

        midi_path = os.path.join(output_dir, "chord_guide.mid")
        midi.save(midi_path)
        return midi_path

