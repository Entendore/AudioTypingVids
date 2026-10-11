# MIDDLE EAST vs GERMANY: Arabic Maqam melody over rigid Berlin Techno
# Duration: 30 seconds
use_bpm 135

maqam = scale(:e4, :phrygian_major)

live_loop :four_on_the_floor do
  sample :bd_haus, amp: 2.5
  sleep 0.5
  stop
end

live_loop :hi_hat do
  sample :drum_cymbal_closed, amp: 0.8
  sleep 0.25
  stop
end

live_loop :arabic_synth_lead do
  use_synth :prophet
  with_fx :echo, phase: 0.375, decay: 4 do # 3/16 note echo for eastern feel
    # Quick ornamentation (grace notes) typical of Maqam performance
    play maqam[0], release: 0.1, amp: 1.2
    play maqam[1], release: 0.4, amp: 1.5
    sleep 0.5
    play maqam[3], release: 0.8, amp: 1.5
    sleep 1.5
    play maqam[4], release: 0.1, amp: 1.0
    play maqam[5], release: 0.6, amp: 1.4
    sleep 1.5
  end
  stop
end