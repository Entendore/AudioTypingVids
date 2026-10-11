# Harmonic Series Drone
# Eastern static drone built entirely from Western physics (The Overtone Series)
# Duration: 30 seconds

use_bpm 60

# Fundamental frequency
root = :c2

live_loop :fundamental do
  use_synth :dsaw
  with_fx :rlpf, cutoff: 60 do
    play root, attack: 8, release: 8, amp: 2.5
  end
  sleep 8
  stop
end

live_loop :western_overtones do
  use_synth :sine
  # Playing the 3rd, 5th, and 7th harmonics (Perfect Fifth, Octave, Major 7th-ish)
  # In Eastern music, these overtones are often imitated by instruments like the sitar
  with_fx :reverb, room: 1 do
    play :g3, attack: 4, release: 4, amp: 1.2 # 3rd harmonic (Perfect 5th)
    sleep 4
    play :c4, attack: 4, release: 4, amp: 1.0 # 4th harmonic (Octave)
    sleep 4
    play :e4, attack: 2, release: 2, amp: 0.6 # 5th harmonic (Major 3rd)
    sleep 2
    play :bb4, attack: 2, release: 2, amp: 0.4 # 7th harmonic (Flat 7th)
    sleep 2
  end
  stop
end

live_loop :shimmering_eastern_fifth do
  use_synth :zawa
  # Eastern music loves the static perfect 5th
  play :g2, release: 8, amp: 1.5, phase: 0.5
  sleep 8
  stop
end