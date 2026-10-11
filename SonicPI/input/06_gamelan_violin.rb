# INDONESIA vs AUSTRIA: Gamelan Slendro scale played by a Classical Violin ensemble
# Duration: 30 seconds
use_bpm 50

slendro = [:c4, :d4, :e4, :g4, :a4, :c5]

live_loop :classical_strings do
  use_synth :saw
  with_fx :reverb, room: 0.9 do
    # Western Classical Technique: Slow, swelling tremolo chords
    2.times do
      play chord(slendro.choose, :minor), attack: 2, release: 2, amp: 1.2, pan: rrand(-0.5, 0.5)
      sleep 4
    end
  end
  stop
end

live_loop :gamelan_kotekan do
  use_synth :pluck
  # Indonesian technique: Interlocking rapid patterns (Kotekan)
  16.times do
    play slendro.choose, release: 0.1, amp: 1.5 if spread(3, 8).tick
    sleep 0.25
  end
  stop
end