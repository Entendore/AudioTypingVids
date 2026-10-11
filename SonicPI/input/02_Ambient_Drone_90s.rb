# TRACK 2: Ambient Cinematic Drone (1:30)
use_bpm 90

in_thread do
  use_synth :dark_ambience
  use_synth_defaults amp: 0.8, release: 8
  loop do
    notes = (scale :d, :dorian)
    play_chord chord(notes.choose, :minor), pan: rrand(-0.8, 0.8)
    sleep 8
  end
end

in_thread do
  use_synth :pretty_bell
  with_fx :echo, phase: 2, decay: 4 do
    loop do
      if one_in(3)
        play (scale :d, :dorian, num_octaves: 2).choose, release: 2, amp: 0.3
      end
      sleep 2
    end
  end
end

sleep 90
