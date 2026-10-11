# Makam Ussak & Lydian
# Turkish Makam Ussak (similar to Aeolian with raised 4th) mixed with Western Lydian
# Duration: 30 seconds

use_bpm 95

# A B C D# E F G A (Makam Ussak shares notes with Lydian, but different hierarchy)
ussak = scale(:a4, :lydian)

live_loop :lydian_pad do
  use_synth :dark_ambience
  # Western Lydian emphasis on the I and II chords
  play chord(:a3, :major7), attack: 3, release: 3, amp: 1.5
  sleep 4
  play chord(:b3, :major7), attack: 3, release: 3, amp: 1.2
  sleep 4
  stop
end

live_loop :makam_lead do
  use_synth :saw
  with_fx :reverb, room: 0.9 do
    # Eastern emphasis on the tonic (A), 4th (D#), and 5th (E)
    play :a4, release: 1.5, amp: 0.9
    sleep 1
    play :e4, release: 0.5, amp: 0.7
    sleep 0.5
    play :d5, release: 0.8, amp: 0.8 # D# acts as a leading tone
    sleep 1.5
    play :c5, release: 0.3, amp: 0.6
    sleep 0.5
    play :b4, release: 0.5, amp: 0.7
    sleep 0.5
  end
  stop
end