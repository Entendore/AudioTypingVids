# INDIA vs WEST: Raga scale played through a rigid Western 16-step sequencer
# Duration: 30 seconds
use_bpm 140

# Bhairavi (Indian) roughly maps to Western Phrygian
raga_notes = scale(:c4, :phrygian, num_octaves: 2)

live_loop :western_grid do
  use_synth :tb303
  # Rigid 16th note western grid playing an eastern scale
  16.times do |i|
    # Western technique: Accents on beats 1, 5, 9, 13
    amp = (i % 4 == 0) ? 1.5 : 0.6
    cutoff = (i % 4 == 0) ? 110 : 80
    
    play raga_notes[i % raga_notes.length], release: 0.2, amp: amp, cutoff: cutoff, pan: -0.5
    sleep 0.25
  end
  stop
end

# Jazzy Western walking bass to contrast the static grid
live_loop :walking_bass do
  use_synth :fm
  4.times do
    play chord(:c2, :m7).choose, release: 0.4, amp: 1.5
    sleep 0.5
  end
  stop
end