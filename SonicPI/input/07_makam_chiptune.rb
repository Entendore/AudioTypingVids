# TURKEY vs JAPAN: Microtonal Makam bent into an 8-bit Chiptune
# Duration: 30 seconds
use_bpm 150

# Using a Japanese "In" scale (similar to Makam Karar) 
makam_8bit = scale(:a4, :minor_pentatonic, num_octaves: 1)

live_loop :nintendo_makam do
  use_synth :square
  with_fx :echo, phase: 0.75 do
    # Chiptune arpeggios using Makam notes
    4.times do
      play makam_8bit[0], release: 0.1, amp: 0.8
      play makam_8bit[2], release: 0.1, amp: 0.8
      play makam_8bit[4], release: 0.1, amp: 0.8
      sleep 0.5
    end
    play makam_8bit[3], release: 0.3, amp: 1.0
    sleep 0.5
    play makam_8bit[2], release: 0.3, amp: 1.0
    sleep 0.5
  end
  stop
end

live_loop :chip_bass do
  use_synth :square
  with_fx :lpf, cutoff: 60 do
    play :a2, release: 0.2, amp: 1.5
    sleep 0.5
    play :a2, release: 0.2, amp: 1.0
    sleep 0.5
    play :e2, release: 0.2, amp: 1.5
    sleep 0.5
    play :e2, release: 0.2, amp: 1.0
    sleep 0.5
  end
  stop
end