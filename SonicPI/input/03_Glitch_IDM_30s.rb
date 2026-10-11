# TRACK 3: Glitchy IDM (30 Seconds)
use_bpm 140

in_thread do
  use_synth :fm
  loop do
    if one_in(2)
      play (scale :e, :pentatonic).choose, release: 0.1, amp: 0.6, pan: rrand(-1, 1)
    end
    sleep 0.25
  end
end

in_thread do
  loop do
    if one_in(3)
      sample :elec_blip, rate: rrand(0.5, 2.5), amp: 0.4
    end
    sleep 0.5
  end
end

sleep 30
