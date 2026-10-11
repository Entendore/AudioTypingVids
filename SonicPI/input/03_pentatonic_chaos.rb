# CHINA vs WEST: Pentatonic notes in a chaotic 20th-century Western Avant-Garde style
# Duration: 30 seconds
use_bpm 60

# Chinese Pentatonic
penta = scale(:c4, :major_pentatonic, num_octaves: 3)

live_loop :avant_garde_piano do
  use_synth :piano
  8.times do
    # Western Avant-Garde technique: Extreme dynamics and random leaps
    note = penta.choose
    dyn = rrand(0.1, 2.5)
    play note, attack: 0.01, release: rrand(0.5, 3), amp: dyn, pan: rrand(-1, 1)
    sleep [0.25, 0.5, 1, 1.5].choose
  end
  stop
end

live_loop :prepared_piano_percussion do
  # John Cage style "prepared piano" sounds
  sample :perc_impact1, amp: rrand(0.2, 1), rate: rrand(0.5, 2) if one_in(2)
  sample :drum_cymbal_hard, amp: rrand(0.1, 0.5) if one_in(3)
  sleep 0.25
  stop
end