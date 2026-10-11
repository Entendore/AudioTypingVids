# TRACK 4: Lo-Fi Chillhop (1:30)
use_bpm 110

in_thread do
  sample :vinyl_hiss, amp: 0.2
  sleep 90
end

in_thread do
  use_synth :beep
  loop do
    play (scale :f, :major).choose, release: 0.5, amp: 0.4, pan: rrand(-0.5, 0.5)
    sleep 2
  end
end

in_thread do
  loop do
    sample :drum_bass_hard, amp: 1.0 if (look % 4) == 0
    sample :drum_snare_soft, amp: 0.8 if (look % 4) == 2
    sleep 1
  end
end

sleep 90
