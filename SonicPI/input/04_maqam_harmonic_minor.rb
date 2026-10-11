# Maqam & Harmonic Minor
# Middle Eastern Maqam Hijaz (Phrygian Dominant) over Western V - i cadence
# Duration: 30 seconds

use_bpm 85
# E F G# A B C D (Hijaz / Phrygian Dominant)
maqam = scale(:e4, :phrygian_major)

live_loop :western_progression do
  use_synth :piano
  # V - i progression (F# major to B minor)
  play chord(:fs3, :major), attack: 0.5, release: 2, amp: 1.5
  sleep 3
  play chord(:b2, :minor), attack: 0.5, release: 2, amp: 1.5
  sleep 3
  stop
end

live_loop :eastern_melody do
  use_synth :koto
  6.times do
    play maqam.choose, attack: 0.05, release: 0.3, amp: 1.5 if one_in(2)
    sleep 0.5
    play maqam.choose, attack: 0.05, release: 0.6, amp: 1.2 if one_in(3)
    sleep 0.5
  end
  stop
end

# Arabic-style percussion (Darbuka)
live_loop :darbuka do
  sample :tabla_ghe3, amp: 1.2
  sleep 1.5
  sample :tabla_ke1, amp: 0.8
  sleep 1.5
  stop
end