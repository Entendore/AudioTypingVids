# PHYSICS vs GROOVE: Harmonic Overtone series driving a 70s Western Funk band
# Duration: 30 seconds
use_bpm 110

root = :e2

live_loop :overtone_drone do
  use_synth :dark_ambience
  # Eastern static drone
  play root, attack: 8, release: 8, amp: 2
  play (midi_to_hz :e3), attack: 8, release: 8, amp: 1 # 2nd harmonic
  play (midi_to_hz :b3), attack: 8, release: 8, amp: 0.8 # 3rd harmonic
  sleep 8
  stop
end

live_loop :funk_guitar do
  use_synth :pluck
  # Western Funk: 16th note staccato strumming on harmonics
  16.times do
    play chord(:e3, :'m7'), release: 0.05, amp: rrand(0.5, 1.2) if spread(5, 8).tick
    sleep 0.25
  end
  stop
end

live_loop :synth_bass do
  use_synth :fm
  # Slap bass style playing root and 5th (harmonics 1 and 3)
  play :e2, release: 0.1, amp: 2.0
  sleep 0.25
  play :e2, release: 0.1, amp: 1.5
  sleep 0.25
  play :b2, release: 0.1, amp: 2.0
  sleep 0.5
  stop
end

live_loop :drums do
  sample :drum_heavy_kick, amp: 1.5
  sleep 0.5
  sample :drum_snare_hard, amp: 1.2
  sleep 0.5
  sample :drum_heavy_kick, amp: 1.5
  sleep 0.25
  sample :drum_heavy_kick, amp: 1.0
  sleep 0.75
  stop
end