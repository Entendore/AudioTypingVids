# Pentatonic Convergence
# Western Major Pentatonic = Chinese Gong Scale
# Duration: 30 seconds

use_bpm 110
# C D E G A (Exact same notes in both traditions)
penta = scale(:c4, :major_pentatonic, num_octaves: 2)

live_loop :eastern_zither do
  use_synth :pluck
  16.times do
    play penta.choose, attack: 0, release: 0.5, amp: 1.2
    sleep [0.25, 0.5].choose
  end
  stop
end

live_loop :western_guitar do
  use_synth :fm
  use_synth_defaults attack: 0.5, release: 1, amp: 0.8
  # Western Pedal Point (bass note stays the same)
  play :c2, release: 4
  sleep 4
  stop
end

# Poly-rhythmic percussion (Western 3/4 feel over Eastern straight 8ths)
live_loop :rhythm do
  sample :perc_snap, amp: 0.7
  sleep 0.75
  sample :perc_snap, amp: 0.5
  sleep 0.75
  sample :drum_cymbal_closed, amp: 0.3
  sleep 0.5
  stop
end