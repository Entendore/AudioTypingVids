# TUNING: Just Intonation vs Equal Temperament using a heavy Dubstep wobble
# Duration: 30 seconds
use_bpm 90

# Equal Temperament C (Standard Western)
eq_c = 130.81
eq_e = 164.81
eq_g = 196.00

# Just Intonation C (Pure mathematical ratios)
just_c = 130.81
just_e = just_c * (5/4.0)  # 163.52 (Noticeably flatter)
just_g = just_c * (3/2.0)  # 196.21

live_loop :wobble_war do
  use_synth :dsaw
  with_fx :wobble, phase: 0.5, wave: 0, cutoff_min: 60, cutoff_max: 120 do
    # Pan them hard left and right to hear the "beating" phase cancellation
    play [eq_c, eq_e, eq_g], release: 2, amp: 1.8, pan: -0.8
    play [just_c, just_e, just_g], release: 2, amp: 1.8, pan: 0.8
  end
  sleep 2
  stop
end

live_loop :kick do
  sample :bd_tek, amp: 2
  sleep 1
  stop
end