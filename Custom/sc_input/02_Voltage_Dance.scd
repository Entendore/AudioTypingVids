// =================================================
// Song 2: "Voltage Dance" — Synthwave (~60s)
// Root: A2 | Scale: Natural Minor
// Tempo: 120 BPM
// =================================================

(
var def_bass, def_lead, def_pad, bundles;
var t, f, total_dur;
var bass_pattern, lead_pattern, pad_chords;
var bass_dur, lead_dur, pad_dur;
var node_counter = 5000, i;

"=== Song 2: Voltage Dance ===".postln;
"Root: A2".postln;
"Scale: Natural Minor".postln;
"Chord: Am - F - C - G".postln;
"Pattern: bass + arp_lead + pad".postln;
"Instrument: sb_bass + saw_lead + saw_pad".postln;

var duration = __DURATION__;

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

// A minor: A B C D E F G
// (45 47 48 50 52 53 55)
// Progression: Am - F - C - G
// (each 4 beats = 2s, 8 bars = 16s, x4 = 64s)
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

// Schedule bass — repeat pattern 8 times
t = 0.3;
i = 0;
while({ t < 60.0 }, {
    var note = bass_pattern[
        i % bass_pattern.size];
    bundles = bundles.add(
        [t, [\s_new, \sb_bass,
            node_counter, 0, 0,
            \freq, note.midicps,
            \amp, 0.5]]);
    node_counter = node_counter + 1;
    t = t + bass_dur;
    i = i + 1;
});

// Schedule lead — starts at 8s
t = 8.0;
i = 0;
while({ t < 60.0 }, {
    var note = lead_pattern[
        i % lead_pattern.size];
    // Rest every 16th note for breathing room
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

// Schedule pad chords — every 2 seconds
pad_dur = 2.0;
t = 0.3;
i = 0;
while({ t < 60.0 }, {
    var chord = pad_chords[
        i % pad_chords.size];
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

total_dur = 62.0;
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
