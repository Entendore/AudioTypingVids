// =================================================
// Song 3: "Digital Rain" — Electronic (~60s)
// Root: F2 | Scale: Phrygian
// Tempo: 125 BPM
// =================================================

(
var def_kick, def_hat, def_bass, def_pluck, def_pad;
var bundles, t, f, total_dur;
var node_counter = 5000, i;
var scale_notes, bass_line, melody_line;
var kick_pattern, hat_pattern;

"=== Song 3: Digital Rain ===".postln;
"Root: F2".postln;
"Scale: Phrygian".postln;
"Chord: Fm - Gb - Fm - Ebm".postln;
"Pattern: beat + bass + pluck_melody".postln;
"Instrument: kick+hat+bass+pluck+pad".postln;

var duration = __DURATION__;

// --- SynthDef 1: Kick drum ---
def_kick = SynthDef(\kick_r, {
    arg out=0, amp=0.8;
    var sig, env, click;
    env = EnvGen.ar(
        Env.perc(0.001, 0.15, 1, -10),
        doneAction: 2);
    click = EnvGen.ar(
        Env.perc(0.001, 0.01)) * WhiteNoise.ar(0.3);
    sig = SinOsc.ar(
        80 * EnvGen.ar(
            Env.perc(0.001, 0.08, 1, -8)))
        + click;
    Out.ar(out, sig * env * amp ! 2);
}).asBytes;

// --- SynthDef 2: Hi-hat ---
def_hat = SynthDef(\hat_r, {
    arg out=0, amp=0.3;
    var sig, env;
    env = EnvGen.ar(
        Env.perc(0.001, 0.05, 1, -6),
        doneAction: 2);
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
        Env.perc(0.002, 0.3, 1, -6),
        doneAction: 2);
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
        Env.linen(1.0, dur*0.4, 1.5),
        doneAction: 2);
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

// F Phrygian: F Gb Ab Bb C Db Eb
// (41 42 44 46 48 49 51)
// Beat at 0.125s (125 BPM 16th notes)
// Bar = 16 × 0.125 = 2.0s, 60s = 30 bars

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

// Schedule kick and hat (30 bars)
t = 0.3;
i = 0;
while({ t < 60.0 }, {
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
while({ t < 60.0 }, {
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
while({ t < 60.0 }, {
    var note = melody_line[
        i % melody_line.size];
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
while({ t < 60.0 }, {
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
