# Gamelan Slendro vs Western Chords
# Indonesian 5-tone Slendro (approximated) vs Western Suspended Chords
# Duration: 30 seconds

use_bpm 80

# Slendro is 5 notes roughly equidistant. We approximate with :minor_pentatonic
slendro = scale(:c4, :minor_pentatonic, num_octaves: 2)

live_loop :gamelan_metals do
  use_synth :blade
  4.times do
    play slendro.choose, attack: 0, release: 2, amp: 0.8, pan: rrand(-0.5, 0.5)
    sleep 1.5
  end
  stop
end

live_loop :western_sus_chords do
  use_synth :hollow
  # Sus chords lack the 3rd, so they don't clash with the pentatonic scale
  play chord(:c3, :sus4), attack: 2, release: 4, amp: 2
  sleep 4
  play chord(:f3, :sus2), attack: 2, release: 4, amp: 2
  sleep 4
  stop
end

live_loop :gong_agung do
  sample :gong, amp: 0.6, attack: 0, release: 4
  sleep 8
  stop
end