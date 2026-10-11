# Dorian Raga Blend
# Western Dorian Mode intersecting with an Indian Raga ascent/descent
# Duration: 30 seconds

use_bpm 90

# Raga-like scale (Ascent: D E F G A B C D, Descent: D C Bb A G F E D)
eastern_ascent = scale(:d4, :dorian)
western_descent = scale(:d4, :minor)

# Western chord progression
live_loop :western_chords do
  use_synth :hollow
  4.times do
    play chord(:d3, :m9), attack: 2, release: 2, amp: 1.5
    sleep 4
  end
  stop
end

# Eastern Raga-style melody
live_loop :raga_melody do
  use_synth :flute
  use_synth_defaults amp: 1.2, pan: rrand(-0.2, 0.2)
  
  # Ascent (Eastern flavor)
  8.times do |i|
    play eastern_ascent.choose, attack: 0.1, release: 0.4 if one_in(2)
    sleep [0.25, 0.5, 0.75].choose
  end
  
  # Descent (Western minor flavor)
  8.times do |i|
    play western_descent.choose, attack: 0.1, release: 0.4 if one_in(2)
    sleep [0.25, 0.5, 0.75].choose
  end
  
  stop
end

# Tanpura-like drone
live_loop :drone do
  use_synth :dark_ambience
  play :d2, attack: 4, release: 4, amp: 2
  play :a2, attack: 4, release: 4, amp: 1
  sleep 4
  stop
end