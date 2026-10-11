# TRACK 1: Synth Arpeggio (30 Seconds)
use_bpm 120

in_thread do
  use_synth :prophet
  with_fx :reverb, room: 0.8 do
    loop do
      play (scale :c, :minor).choose, release: 0.2, amp: 0.5, pan: rrand(-0.5, 0.5)
      sleep 0.5
    end
  end
end

in_thread do
  loop do
    sample :bd_haus, amp: 1.2
    sleep 1
  end
end

sleep 30
