# INDIA vs WEST: 7-beat Tala rhythm vs standard 4/4 March
# Duration: 30 seconds
use_bpm 160

# Western March Snare (Strict 4/4)
live_loop :march_snare do
  4.times do
    sample :sn_dolf, amp: 1.5
    sleep 1
  end
  stop
end

# Indian Tala (7 beats: 3+2+2)
live_loop :tala_seven do
  # Beat 1 (Heavy)
  sample :tabla_ghe3, amp: 2.0
  sleep 1.0
  # Beat 2
  sample :tabla_re, amp: 1.0
  sleep 0.5
  # Beat 3
  sample :tabla_te2, amp: 1.0
  sleep 0.5
  # Beat 4 & 5
  sample :tabla_na, amp: 1.2
  sleep 0.5
  sample :tabla_na, amp: 1.2
  sleep 1.0
  # Beat 6 & 7
  sample :tabla_ke1, amp: 0.8
  sleep 0.5
  sample :tabla_te_ne, amp: 0.8
  sleep 1.0
  stop
end

# Bass marking the 28-beat cycle where both rhythms align
live_loop :cycle_root do
  use_synth :fm
  play :c2, release: 6, amp: 2
  sleep 7 # 7 beats at 160bpm
  stop
end