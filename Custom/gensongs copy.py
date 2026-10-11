import os

# Create a directory to store the supercollider files
output_dir = "sc_songs"
os.makedirs(output_dir, exist_ok=True)

# Dictionary containing the 4 songs
songs = {
    "01_Lunar_Tide.scd": r"""
// =================================================
// Song 1: "Lunar Tide" — Ambient (~60s)
// Root: C3 | Scale: Major Pentatonic
// Mood: Calm, evolving
// =================================================

(
var def_pad, def_bell, bundles, t, f, total_dur, duration;
var roots, chord_notes, bell_pattern;
var pad_dur, bell_dur, pad_amp, bell_amp;
var i, node_counter = 5000;

"=== Song 1: Lunar Tide ===".postln;
"Root: C3".postln;
"Scale: Major Pentatonic".postln;
"Chord: Maj7sus2".postln;
"Pattern: pad_chords + bell_arp".postln;
"Instrument: pad_bell + glass_bell".postln;

duration = __DURATION__;

// --- SynthDef 1: Lush pad with slow filter sweep ---
def_pad = SynthDef(\pad_bell, {
    arg out=0, freq=220, amp=0.3, dur=4.0;
    var sig, env, filt, lfo;
    env = EnvGen.ar(
        Env.linen(1.5, dur*0.5, 1.5), doneAction: 2);
    lfo = SinOsc.kr(0.3) * 0.5 + 0.5;
    sig = Saw.ar(freq)
        + Saw.ar(freq * 1.005)
        + Pulse.ar(freq * 0.5, 0.3);
    filt = LPF.ar(sig, 400 + (lfo * 800));
    Out.ar(out, (filt * 0.15) * env * amp ! 2);
}).asBytes;

// --- SynthDef 2: Glassy bell ---
def_bell = SynthDef(\glass_bell, {
    arg out=0, freq=880, amp=0.4;
    var sig, env, partials;
    env = EnvGen.ar(
        Env.perc(0.005, 2.5, 1, -4), doneAction: 2);
    partials = SinOsc.ar(freq) * 1.0
        + SinOsc.ar(freq * 2.0) * 0.5
        + SinOsc.ar(freq * 3.01) * 0.25
        + SinOsc.ar(freq * 4.7) * 0.1;
    sig = partials * env * amp * 0.3;
    Out.ar(out, sig ! 2);
}).asBytes;

bundles = [];

// Send both defs at time 0
bundles = bundles.add([0.0, [\d_recv, def_pad]]);
bundles = bundles.add([0.0, [\d_recv, def_bell]]);

// Chords: Cmaj7 - Am7 - Fmaj7 - G6
roots = [48, 45, 41, 43, 48, 45, 41, 43];
chord_notes = [
    [48, 52, 55, 59],  // Cmaj7
    [45, 48, 52, 55],  // Am7
    [41, 45, 48, 52],  // Fmaj7
    [43, 47, 50, 55],  // G6
    [48, 52, 55, 59],
    [45, 48, 52, 55],
    [41, 45, 48, 52],
    [43, 47, 50, 55],
];

pad_dur = 8.0;
pad_amp = 0.25;
bell_amp = 0.35;

// Schedule pad chords
t = 0.2;
i = 0;
while({ t < (duration - 1.0) }, {
    var chord = chord_notes[i % chord_notes.size];
    chord.do({ arg note, ni;
        bundles = bundles.add(
            [t, [\s_new, \pad_bell,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, pad_amp,
                \dur, pad_dur]]);
        node_counter = node_counter + 1;
    });
    t = t + pad_dur;
    i = i + 1;
});

// Bell arpeggios — pentatonic ascending
bell_pattern = [72, 76, 79, 81, 84, 81, 79, 76];
bell_dur = 0.5;
t = 0.5;
i = 0;
while({ t < (duration - 1.0) }, {
    var note = bell_pattern[i % bell_pattern.size];
    if(i % 8 == 4, { note = note + 5; });
    bundles = bundles.add(
        [t, [\s_new, \glass_bell,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, bell_amp]]);
    node_counter = node_counter + 1;
    t = t + bell_dur;
    i = i + 1;
});

// Occasional low bell hits
i = 0;
t = 4.0;
while({ t < (duration - 1.0) }, {
    bundles = bundles.add(
        [t, [\s_new, \glass_bell,
            node_counter, 0, 0,
            \freq, 36.midicps, \amp, 0.5]]);
    node_counter = node_counter + 1;
    t = t + 8.0;
    i = i + 1;
});

total_dur = duration;
bundles = bundles.add([total_dur, [\g_freeAll, 0]]);
bundles = bundles.add([total_dur + 0.01, [\c_set, 0, 0]]);

Score.write(bundles, "__SCORE_PATH__");
"SCORE_WRITTEN".postln;
0.exit;
)
""",

    "02_Voltage_Dance.scd": r"""
// =================================================
// Song 2: "Voltage Dance" — Synthwave (~60s)
// Root: A2 | Scale: Natural Minor
// Tempo: 120 BPM
// =================================================

(
var def_bass, def_lead, def_pad, bundles;
var t, f, total_dur, duration;
var bass_pattern, lead_pattern, pad_chords;
var bass_dur, lead_dur, pad_dur;
var node_counter = 5000, i;

"=== Song 2: Voltage Dance ===".postln;
"Root: A2".postln;
"Scale: Natural Minor".postln;
"Chord: Am - F - C - G".postln;
"Pattern: bass + arp_lead + pad".postln;
"Instrument: sb_bass + saw_lead + saw_pad".postln;

duration = __DURATION__;

// --- SynthDef 1: Punchy bass ---
def_bass = SynthDef(\sb_bass, {
    arg out=0, freq=110, amp=0.5;
    var sig, env, sub;
    env = EnvGen.ar(
        Env.perc(0.005, 0.3, 1, -4), doneAction: 2);
    sub = SinOsc.ar(freq * 0.5);
    sig = Saw.ar(freq) + sub;
    sig = LPF.ar(sig, 600);
    Out.ar(out, sig * env * amp * 0.4 ! 2);
}).asBytes;

// --- SynthDef 2: Saw lead with delay feel ---
def_lead = SynthDef(\saw_lead, {
    arg out=0, freq=440, amp=0.3;
    var sig, env, detune;
    env = EnvGen.ar(
        Env.perc(0.01, 0.4, 1, -3), doneAction: 2);
    detune = LFNoise0.kr(8, 0.005);
    sig = Saw.ar(freq * (1 + detune))
        + Saw.ar(freq * (1 - detune));
    sig = HPF.ar(sig, 200);
    Out.ar(out, sig * env * amp * 0.25 ! 2);
}).asBytes;

// --- SynthDef 3: Warm pad ---
def_pad = SynthDef(\saw_pad, {
    arg out=0, freq=220, amp=0.2, dur=2.0;
    var sig, env, filt;
    env = EnvGen.ar(
        Env.linen(0.5, dur*0.5, 0.5), doneAction: 2);
    sig = Saw.ar(freq)
        + Saw.ar(freq * 1.01)
        + Pulse.ar(freq * 2, 0.2);
    filt = LPF.ar(sig, 1200);
    Out.ar(out, filt * env * amp * 0.2 ! 2);
}).asBytes;

bundles = [];
bundles = bundles.add([0.0, [\d_recv, def_bass]]);
bundles = bundles.add([0.0, [\d_recv, def_lead]]);
bundles = bundles.add([0.0, [\d_recv, def_pad]]);

// A minor: A B C D E F G (45 47 48 50 52 53 55)
// Progression: Am - F - C - G
pad_chords = [
    [45, 48, 52],  // Am
    [41, 45, 48],  // F
    [48, 52, 55],  // C
    [43, 47, 50],  // G
];

// Bass: root notes, 8th notes at 120 BPM
bass_pattern = [
    45, 45, 52, 45, 45, 45, 50, 45,  // Am
    41, 41, 48, 41, 41, 41, 45, 41,  // F
    48, 48, 55, 48, 48, 48, 52, 48,  // C
    43, 43, 50, 43, 43, 43, 47, 43,  // G
];
bass_dur = 0.25;  // nice groove

// Lead: arpeggiated pattern (higher octave)
lead_pattern = [
    69, 72, 76, 72, 69, 72, 76, 79,
    65, 69, 72, 69, 65, 69, 72, 76,
    72, 76, 79, 76, 72, 76, 79, 84,
    67, 71, 74, 71, 67, 71, 74, 79,
];
lead_dur = 0.1875;  // triplet feel

// Schedule bass
t = 0.3;
i = 0;
while({ t < (duration - 1.0) }, {
    var note = bass_pattern[i % bass_pattern.size];
    bundles = bundles.add(
        [t, [\s_new, \sb_bass,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, 0.5]]);
    node_counter = node_counter + 1;
    t = t + bass_dur;
    i = i + 1;
});

// Schedule lead
t = 8.0;
i = 0;
while({ t < (duration - 1.0) }, {
    var note = lead_pattern[i % lead_pattern.size];
    if((i % 16) != 15, {
        bundles = bundles.add(
            [t, [\s_new, \saw_lead,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, 0.3]]);
        node_counter = node_counter + 1;
    });
    t = t + lead_dur;
    i = i + 1;
});

// Schedule pad chords
pad_dur = 2.0;
t = 0.3;
i = 0;
while({ t < (duration - 1.0) }, {
    var chord = pad_chords[i % pad_chords.size];
    chord.do({ arg note, ni;
        bundles = bundles.add(
            [t, [\s_new, \saw_pad,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, 0.2, \dur, pad_dur]]);
        node_counter = node_counter + 1;
    });
    t = t + pad_dur;
    i = i + 1;
});

total_dur = duration;
bundles = bundles.add([total_dur, [\g_freeAll, 0]]);
bundles = bundles.add([total_dur + 0.01, [\c_set, 0, 0]]);

Score.write(bundles, "__SCORE_PATH__");
"SCORE_WRITTEN".postln;
0.exit;
)
""",

    "03_Digital_Rain.scd": r"""
// =================================================
// Song 3: "Digital Rain" — Electronic (~60s)
// Root: F2 | Scale: Phrygian
// Tempo: 125 BPM
// =================================================

(
var def_kick, def_hat, def_bass, def_pluck, def_pad;
var bundles, t, f, total_dur, duration;
var node_counter = 5000, i;
var scale_notes, bass_line, melody_line;
var kick_pattern, hat_pattern;

"=== Song 3: Digital Rain ===".postln;
"Root: F2".postln;
"Scale: Phrygian".postln;
"Chord: Fm - Gb - Fm - Ebm".postln;
"Pattern: beat + bass + pluck_melody".postln;
"Instrument: kick+hat+bass+pluck+pad".postln;

duration = __DURATION__;

// --- SynthDef 1: Kick drum ---
def_kick = SynthDef(\kick_r, {
    arg out=0, amp=0.8;
    var sig, env, click;
    env = EnvGen.ar(
        Env.perc(0.001, 0.15, 1, -10), doneAction: 2);
    click = EnvGen.ar(
        Env.perc(0.001, 0.01)) * WhiteNoise.ar(0.3);
    sig = SinOsc.ar(
        80 * EnvGen.ar(Env.perc(0.001, 0.08, 1, -8)))
        + click;
    Out.ar(out, sig * env * amp ! 2);
}).asBytes;

// --- SynthDef 2: Hi-hat ---
def_hat = SynthDef(\hat_r, {
    arg out=0, amp=0.3;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.001, 0.05, 1, -6), doneAction: 2);
    sig = HPF.ar(WhiteNoise.ar(1), 7000);
    Out.ar(out, sig * env * amp * 0.5 ! 2);
}).asBytes;

// --- SynthDef 3: Sub bass ---
def_bass = SynthDef(\sub_bass, {
    arg out=0, freq=80, amp=0.5;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.01, 0.2, 1, -4), doneAction: 2);
    sig = SinOsc.ar(freq)
        + Saw.ar(freq * 0.5) * 0.3;
    sig = LPF.ar(sig, 300);
    Out.ar(out, sig * env * amp * 0.5 ! 2);
}).asBytes;

// --- SynthDef 4: Plucky melody ---
def_pluck = SynthDef(\pluck_r, {
    arg out=0, freq=440, amp=0.4;
    var sig, env, delay;
    env = EnvGen.ar(
        Env.perc(0.002, 0.3, 1, -6), doneAction: 2);
    sig = Pulse.ar(freq, 0.3)
        + Saw.ar(freq * 2) * 0.3;
    sig = LPF.ar(sig, 2000);
    delay = CombN.ar(sig, 0.3, 0.1875, 2);
    Out.ar(out,
        (sig + delay * 0.3) * env * amp * 0.2 ! 2);
}).asBytes;

// --- SynthDef 5: Dark pad ---
def_pad = SynthDef(\dark_pad, {
    arg out=0, freq=220, amp=0.15, dur=4.0;
    var sig, env;
    env = EnvGen.ar(
        Env.linen(1.0, dur*0.4, 1.5), doneAction: 2);
    sig = Saw.ar(freq)
        + Saw.ar(freq * 1.005)
        + SinOsc.ar(freq * 0.5);
    sig = LPF.ar(sig, 500);
    Out.ar(out, sig * env * amp * 0.25 ! 2);
}).asBytes;

bundles = [];
bundles = bundles.add([0.0, [\d_recv, def_kick]]);
bundles = bundles.add([0.0, [\d_recv, def_hat]]);
bundles = bundles.add([0.0, [\d_recv, def_bass]]);
bundles = bundles.add([0.0, [\d_recv, def_pluck]]);
bundles = bundles.add([0.0, [\d_recv, def_pad]]);

// F Phrygian: F Gb Ab Bb C Db Eb (41 42 44 46 48 49 51)
kick_pattern = [1,0,0,0, 0,0,0,0,
                1,0,0,0, 0,0,1,0];
hat_pattern  = [0,0,1,0, 0,0,1,0,
                0,0,1,0, 0,0,1,0];

// Bass: F Gb F Eb (phrygian riff)
bass_line = [
    41,41,41,41, 41,41,41,41,
    41,41,41,41, 41,41,41,41,  // F
    42,42,42,42, 42,42,42,42,
    42,42,42,42, 42,42,42,42,  // Gb
    41,41,41,41, 41,41,41,41,
    41,41,41,41, 41,41,41,41,  // F
    39,39,39,39, 39,39,39,39,
    39,39,39,39, 39,39,39,39,  // Eb
];

// Melody: phrygian riff, higher octave
melody_line = [
    65,67,65,64, 65,67,69,67,
    65,64,65,67, 65,64,62,60,
    66,67,66,65, 66,67,69,67,
    66,65,66,67, 66,65,62,61,
    65,67,65,64, 65,67,69,71,
    72,71,69,67, 65,64,62,60,
    63,65,63,62, 63,65,67,65,
    63,62,63,65, 67,65,63,62,
];

// Schedule kick and hat
t = 0.3;
i = 0;
while({ t < (duration - 1.0) }, {
    var step = i % 16;
    if(kick_pattern[step] == 1, {
        bundles = bundles.add(
            [t, [\s_new, \kick_r,
                node_counter, 0, 0,
                \amp, 0.7]]);
        node_counter = node_counter + 1;
    });
    if(hat_pattern[step] == 1, {
        bundles = bundles.add(
            [t, [\s_new, \hat_r,
                node_counter, 0, 0,
                \amp, 0.25]]);
        node_counter = node_counter + 1;
    });
    t = t + 0.125;
    i = i + 1;
});

// Schedule bass
t = 0.3;
i = 0;
while({ t < (duration - 1.0) }, {
    var note = bass_line[i % bass_line.size];
    bundles = bundles.add(
        [t, [\s_new, \sub_bass,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, 0.5]]);
    node_counter = node_counter + 1;
    t = t + 0.125;
    i = i + 1;
});

// Schedule pluck melody (starts at bar 4)
t = 8.3;
i = 0;
while({ t < (duration - 1.0) }, {
    var note = melody_line[i % melody_line.size];
    bundles = bundles.add(
        [t, [\s_new, \pluck_r,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, 0.35]]);
    node_counter = node_counter + 1;
    t = t + 0.125;
    i = i + 1;
});

// Schedule dark pad (every 8s)
t = 0.5;
i = 0;
while({ t < (duration - 2.0) }, {
    var chords = [
        [41,44,48], [42,46,49],
        [41,44,48], [39,44,47]];
    var chord = chords[i % 4];
    chord.do({ arg note, ni|
        bundles = bundles.add(
            [t, [\s_new, \dark_pad,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, 0.15, \dur, 8.0]]);
        node_counter = node_counter + 1;
    });
    t = t + 8.0;
    i = i + 1;
});

total_dur = duration;
bundles = bundles.add([total_dur, [\g_freeAll, 0]]);
bundles = bundles.add([total_dur + 0.01, [\c_set, 0, 0]]);

Score.write(bundles, "__SCORE_PATH__");
"SCORE_WRITTEN".postln;
0.exit;
)
""",

    "04_Aurora_Borealis.scd": r"""
// =================================================
// Song 4: "Aurora Borealis" — Ambient (~60s)
// Root: D3 | Scale: Lydian
// Mood: Cinematic, dreamy
// =================================================

(
var def_warm_pad, def_piano, def_sub;
var def_shimmer, def_arp, bundles;
var t, f, total_dur, duration;
var node_counter = 5000, i;
var chord_prog, melody, arp_pattern;
var sub_pattern;

"=== Song 4: Aurora Borealis ===".postln;
"Root: D3".postln;
"Scale: Lydian".postln;
"Chord: D - C - G - A (Lydian)".postln;
"Pattern: pad+piano+sub+shimmer+arp".postln;
"Instrument: warm_pad+piano+sub+etc".postln;

duration = __DURATION__;

// --- SynthDef 1: Warm evolving pad ---
def_warm_pad = SynthDef(\warm_pad, {
    arg out=0, freq=220, amp=0.2, dur=8.0;
    var sig, env, lfo1, lfo2;
    env = EnvGen.ar(
        Env.linen(2.0, dur*0.4, 2.0), doneAction: 2);
    lfo1 = SinOsc.kr(0.2) * 0.3 + 0.7;
    lfo2 = SinOsc.kr(0.13) * 0.5 + 0.5;
    sig = Saw.ar(freq)
        + Saw.ar(freq * 1.003)
        + Pulse.ar(freq * 0.5, 0.4);
    sig = LPF.ar(sig, 600 + (lfo2 * 600));
    sig = sig * lfo1;
    Out.ar(out, sig * env * amp * 0.15 ! 2);
}).asBytes;

// --- SynthDef 2: Piano-like (FM bell) ---
def_piano = SynthDef(\piano_t, {
    arg out=0, freq=440, amp=0.4;
    var sig, env, mod;
    env = EnvGen.ar(
        Env.perc(0.003, 1.5, 1, -5), doneAction: 2);
    mod = SinOsc.ar(freq * 2.0)
        * EnvGen.ar(Env.perc(0.001, 0.3)) * 2;
    sig = SinOsc.ar(freq + mod) * 0.7
        + SinOsc.ar(freq * 2.0) * 0.2
        + SinOsc.ar(freq * 3.0) * 0.1;
    Out.ar(out, sig * env * amp * 0.4 ! 2);
}).asBytes;

// --- SynthDef 3: Sub drone ---
def_sub = SynthDef(\sub_drone, {
    arg out=0, freq=55, amp=0.3, dur=8.0;
    var sig, env;
    env = EnvGen.ar(
        Env.linen(1.0, dur*0.6, 2.0), doneAction: 2);
    sig = SinOsc.ar(freq)
        + SinOsc.ar(freq * 1.001) * 0.5;
    Out.ar(out, sig * env * amp * 0.4 ! 2);
}).asBytes;

// --- SynthDef 4: Shimmer (high sparkle) ---
def_shimmer = SynthDef(\shimmer, {
    arg out=0, freq=1760, amp=0.15;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.5, 4.0, 1, -2), doneAction: 2);
    sig = SinOsc.ar(freq) * 0.5
        + SinOsc.ar(freq * 1.5) * 0.3
        + WhiteNoise.ar(0.02);
    sig = HPF.ar(sig, 1000);
    Out.ar(out, sig * env * amp * 0.5 ! 2);
}).asBytes;

// --- SynthDef 5: Arpeggio pluck ---
def_arp = SynthDef(\arp_pluck, {
    arg out=0, freq=440, amp=0.3;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.005, 0.6, 1, -4), doneAction: 2);
    sig = Pulse.ar(freq, 0.2)
        + Saw.ar(freq * 2) * 0.2;
    sig = LPF.ar(sig, 3000);
    Out.ar(out, sig * env * amp * 0.25 ! 2);
}).asBytes;

bundles = [];
bundles = bundles.add([0.0, [\d_recv, def_warm_pad]]);
bundles = bundles.add([0.0, [\d_recv, def_piano]]);
bundles = bundles.add([0.0, [\d_recv, def_sub]]);
bundles = bundles.add([0.0, [\d_recv, def_shimmer]]);
bundles = bundles.add([0.0, [\d_recv, def_arp]]);

// D Lydian: D E F# G# A B C# (50 52 54 56 57 59 61)
chord_prog = [
    [50, 54, 57, 61],  // Dmaj7#11
    [48, 52, 55, 59],  // Cmaj9
    [43, 47, 50, 54],  // Gmaj7
    [45, 49, 52, 56],  // Amaj7
    [50, 54, 57, 61],
    [48, 52, 55, 59],
    [43, 47, 50, 54],
    [45, 49, 52, 56],
];

// Piano melody (Lydian dreamy)
melody = [
    74, 76, 74, 71, 69, 71, 74, 76,
    78, 76, 74, 71, 69, 67, 69, 71,
    74, 78, 81, 78, 74, 71, 69, 67,
    69, 71, 74, 76, 78, 81, 78, 76,
    74, 76, 74, 71, 69, 71, 74, 76,
    78, 76, 74, 71, 69, 67, 69, 71,
    74, 78, 81, 86, 83, 81, 78, 74,
    81, 78, 74, 71, 69, 67, 66, 62,
];

// Arpeggio pattern (1 octave up)
arp_pattern = [
    62, 66, 69, 73, 62, 66, 69, 73,
    60, 64, 67, 71, 60, 64, 67, 71,
    55, 59, 62, 66, 55, 59, 62, 66,
    57, 61, 64, 68, 57, 61, 64, 68,
];

// Sub bass roots
sub_pattern = [38, 36, 31, 33, 38, 36, 31, 33];

// === Schedule PADS ===
t = 0.3;
i = 0;
while({ t < (duration - 2.0) }, {
    var chord = chord_prog[i % chord_prog.size];
    chord.do({ arg note, ni|
        bundles = bundles.add(
            [t, [\s_new, \warm_pad,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, 0.2, \dur, 8.0]]);
        node_counter = node_counter + 1;
    });
    t = t + 8.0;
    i = i + 1;
});

// === Schedule SUB DRONE ===
t = 0.3;
i = 0;
while({ t < (duration - 2.0) }, {
    var note = sub_pattern[i % sub_pattern.size];
    bundles = bundles.add(
        [t, [\s_new, \sub_drone,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, 0.3, \dur, 8.0]]);
    node_counter = node_counter + 1;
    t = t + 8.0;
    i = i + 1;
});

// === Schedule PIANO MELODY ===
t = 4.3;
i = 0;
while({ t < (duration - 2.0) }, {
    var note = melody[i % melody.size];
    if((i % 8) != 7, {
        bundles = bundles.add(
            [t, [\s_new, \piano_t,
                node_counter, 0, 0,
                \freq, note.midicps,
                \amp, 0.4]]);
        node_counter = node_counter + 1;
    });
    t = t + 0.5;
    i = i + 1;
});

// === Schedule SHIMMER ===
t = 2.0;
i = 0;
while({ t < (duration - 2.0) }, {
    var note = [81, 86, 83, 88, 81, 90, 86, 83];
    bundles = bundles.add(
        [t, [\s_new, \shimmer,
            node_counter, 0, 0,
            \freq, note[i % note.size].midicps,
            \amp, 0.12]]);
    node_counter = node_counter + 1;
    t = t + 4.0;
    i = i + 1;
});

// === Schedule ARPEGGIO ===
t = 16.3;
i = 0;
while({ t < (duration - 2.0) }, {
    var note = arp_pattern[i % arp_pattern.size];
    var amp_val = if(i % 4 == 0, 0.35, 0.2);
    bundles = bundles.add(
        [t, [\s_new, \arp_pluck,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, amp_val]]);
    node_counter = node_counter + 1;
    t = t + 0.125;
    i = i + 1;
});

total_dur = duration;
bundles = bundles.add([total_dur, [\g_freeAll, 0]]);
bundles = bundles.add([total_dur + 0.01, [\c_set, 0, 0]]);

Score.write(bundles, "__SCORE_PATH__");
"SCORE_WRITTEN".postln;
0.exit;
)
"""
}

# Write files to disk
for filename, code in songs.items():
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(code.strip() + "\n")
    print(f"Generated: {filepath}")

print("\nAll 4 SuperCollider scripts saved to 'sc_songs'.")
print("Each song's code lines kept close to 60 chars wide.")