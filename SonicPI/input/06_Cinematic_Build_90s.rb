# TRACK 6: Cinematic Synth Build (1:30)
use_bpm 100

in_thread do
  use_synth :blade
  use_synth_defaults amp: 0.6, release: 4
  loop do
    notes = (scale :a, :minor)
    play_chord chord(notes.choose, :minor), pan: rrand(-0.8, 0.8)
    sleep 4
  end
end

in_thread do
  use_synth :subpulse
  loop do
    play :a1, release: 1.5, amp: 0.8
    sleep 2
  end
end

sleep 90
