# Ambient Dreams
use_bpm 60

with_fx :reverb, room: 0.9 do
  live_loop :pad do
    use_synth :prophet
    play chord(:E3, :minor), release: 8, amp: 0.5
    sleep 4
    play chord(:A3, :minor), release: 8, amp: 0.5
    sleep 4
  end
end

with_fx :echo, phase: 0.75, decay: 6 do
  live_loop :melody do
    use_synth :pluck
    play :E5, release: 2, amp: 0.3
    sleep 1.5
    play :B4, release: 2, amp: 0.3
    sleep 1.5
    play :G4, release: 2, amp: 0.3
    sleep 1
    play :A4, release: 2, amp: 0.3
    sleep 2
  end
end