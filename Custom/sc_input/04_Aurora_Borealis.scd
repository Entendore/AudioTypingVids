// =================================================
// Song 4: "Aurora Borealis" — Ambient (~60s)
// Root: D3 | Scale: Lydian
// Mood: Cinematic, dreamy
// =================================================

(
var def_warm_pad, def_piano, def_sub;
var def_shimmer, def_arp, bundles;
var t, f, total_dur;
var node_counter = 5000, i;
var chord_prog, melody, arp_pattern;
var sub_pattern;

"=== Song 4: Aurora Borealis ===".postln;
"Root: D3".postln;
"Scale: Lydian".postln;
"Chord: D - C - G - A (Lydian)".postln;
"Pattern: pad+piano+sub+shimmer+arp".postln;
"Instrument: warm_pad+piano+sub+etc".postln;

var duration = __DURATION__;

// --- SynthDef 1: Warm evolving pad ---
def_warm_pad = SynthDef(\warm_pad, {
    arg out=0, freq=220, amp=0.2, dur=8.0;
    var sig, env, lfo1, lfo2;
    env = EnvGen.ar(
        Env.linen(2.0, dur*0.4, 2.0),
        doneAction: 2);
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
        Env.perc(0.003, 1.5, 1, -5),
        doneAction: 2);
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
        Env.linen(1.0, dur*0.6, 2.0),
        doneAction: 2);
    sig = SinOsc.ar(freq)
        + SinOsc.ar(freq * 1.001) * 0.5;
    Out.ar(out, sig * env * amp * 0.4 ! 2);
}).asBytes;

// --- SynthDef 4: Shimmer (high sparkle) ---
def_shimmer = SynthDef(\shimmer, {
    arg out=0, freq=1760, amp=0.15;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.5, 4.0, 1, -2),
        doneAction: 2);
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
        Env.perc(0.005, 0.6, 1, -4),
        doneAction: 2);
    sig = Pulse.ar(freq, 0.2)
        + Saw.ar(freq * 2) * 0.2;
    sig = LPF.ar(sig, 3000);
    Out.ar(out, sig * env * amp * 0.25 ! 2);
}).asBytes;

bundles = [];
bundles = bundles.add([0.0,
    [\d_recv, def_warm_pad]]);
bundles = bundles.add([0.0,
    [\d_recv, def_piano]]);
bundles = bundles.add([0.0,
    [\d_recv, def_sub]]);
bundles = bundles.add([0.0,
    [\d_recv, def_shimmer]]);
bundles = bundles.add([0.0,
    [\d_recv, def_arp]]);

// D Lydian: D E F# G# A B C#
// (50 52 54 56 57 59 61)
// Progression: D - C - G - A
// (each 8s = 32s, x2 = 64s)
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
sub_pattern = [38, 36, 31, 33,
               38, 36, 31, 33];

// === Schedule PADS (every 8s) ===
t = 0.3;
i = 0;
while({ t < 64.0 }, {
    var chord = chord_prog[
        i % chord_prog.size];
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
while({ t < 64.0 }, {
    var note = sub_pattern[
        i % sub_pattern.size];
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
// (starts at 4s, 0.5s per note)
t = 4.3;
i = 0;
while({ t < 60.0 }, {
    var note = melody[i % melody.size];
    // Skip every 8th note for phrasing
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

// === Schedule SHIMMER (every 4s) ===
t = 2.0;
i = 0;
while({ t < 60.0 }, {
    var note = [81, 86, 83, 88,
                81, 90, 86, 83];
    bundles = bundles.add(
        [t, [\s_new, \shimmer,
            node_counter, 0, 0,
            \freq, note[i % note.size]
                .midicps,
            \amp, 0.12]]);
    node_counter = node_counter + 1;
    t = t + 4.0;
    i = i + 1;
});

// === Schedule ARPEGGIO ===
// (starts at 16s, 0.125s per note)
t = 16.3;
i = 0;
while({ t < 60.0 }, {
    var note = arp_pattern[
        i % arp_pattern.size];
    // Vary velocity
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

total_dur = 66.0;
bundles = bundles.add(
    [total_dur, [\g_freeAll, 0]]);
bundles = bundles.add(
    [total_dur + 0.1, [\quit, 0]]);

f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[
        (sz >> 24) & 255,
        (sz >> 16) & 255,
        (sz >> 8) & 255,
        sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
0.exit;
)
