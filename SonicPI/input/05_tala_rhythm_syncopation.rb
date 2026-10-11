# Tala Rhythm Syncopation
# Indian 7-beat Tala (Rupak) against a Western 4/4 drum loop
# Duration: 30 seconds

use_bpm 120

# Western 4/4 Drum kit
live_loop :western_kit do
  sample :bd_haus, amp: 1.5
  sleep 1
  sample :bd_haus, amp: 0.8
  sleep 1
  sample :bd_haus, amp: 0.8
  sleep 1
  sample :bd_haus, amp: 0.5
  sleep 1
  stop
end

# Eastern 7-beat Tala (3+2+2)
live_loop :tala_seven do
  sample :tabla_tun1, amp: 1.5 # Beat 1 (Sam - Downbeat)
  sleep 0.75
  sample :tabla_re, amp: 0.8   # Beat 2
  sleep 0.75
  sample :tabla_te2, amp: 0.8  # Beat 3
  sleep 0.75
  
  sample :tabla_na, amp: 1.0   # Beat 4
  sleep 0.75
  sample :tabla_na, amp: 1.0   # Beat 5
  sleep 0.75
  
  sample :tabla_tun1, amp: 0.9 # Beat 6
  sleep 0.75
  sample :tabla_re, amp: 0.7   # Beat 7
  sleep 0.75
  stop
end

# Droning bass to glue it together
live_loop :bass_glue do
  use_synth :fm
  play :c2, release: 3.5, amp: 1.5
  sleep 3.5
  stop
end