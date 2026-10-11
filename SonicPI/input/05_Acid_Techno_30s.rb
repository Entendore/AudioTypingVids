# TRACK 5: Acid Techno (30 Seconds)
use_bpm 128

in_thread do
  use_synth :tb303
  with_fx :wobble, phase: 0.5 do
    loop do
      play (scale :g, :mixolydian).tick, release: 0.2, cutoff: 100, res: 0.8, amp: 0.7
      sleep 0.5
    end
  end
end

in_thread do
  loop do
    sample :bd_haus, amp: 1.5
    sample :drum_cymbal_closed, amp: 0.5 if (look % 2) == 1
    sleep 0.5
  end
end

sleep 30
