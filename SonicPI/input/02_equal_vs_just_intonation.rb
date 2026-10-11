# Equal vs Just Intonation
# Pitting Western 12-TET against Eastern Just Intonation
# Duration: 30 seconds

use_bpm 100

# Western Equal Temperament (Standard Sonic Pi)
equal_triad = chord(:c4, :major)

# Eastern Just Intonation (Mathematically perfect ratios)
just_root = 261.63 # C4
just_third = just_root * (5/4.0) # 327.38
just_fifth = just_root * (3/2.0) # 392.44
just_triad = [just_root, just_third, just_fifth]

live_loop :equal_temperament do
  use_synth :prophet
  with_transpose -12 do
    play equal_triad, attack: 1, release: 1, amp: 1.5, pan: -0.8
  end
  sleep 2
  stop
end

live_loop :just_intonation do
  use_synth :prophet
  play just_triad.map { |f| f / 2.0 }, attack: 1, release: 1, amp: 1.5, pan: 0.8
  sleep 2
  stop
end

# Melody highlighting the "difference" (beating effect)
live_loop :melody do
  use_synth :tb303
  sync :equal_temperament
  15.times do
    play just_third, release: 0.3, cutoff: 80, amp: 0.8
    sleep 2
  end
  stop
end