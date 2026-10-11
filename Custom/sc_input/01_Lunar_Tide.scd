// =================================================
// Song 1: "Lunar Tide" — Ambient (~60s)
// Root: C3 | Scale: Major Pentatonic
// Mood: Calm, evolving
// =================================================

(
var def_pad, def_bell, bundles, t, f, total_dur;
var roots, chord_notes, bell_pattern;
var pad_dur, bell_dur, pad_amp, bell_amp;
var i, node_counter = 5000;

"=== Song 1: Lunar Tide ===".postln;
"Root: C3".postln;
"Scale: Major Pentatonic".postln;
"Chord: Maj7sus2".postln;
"Pattern: pad_chords + bell_arp".postln;
"Instrument: pad_bell + glass_bell".postln;

var duration = __DURATION__;

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
// (each 8s, x2 = 64s)
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
chord_notes.do({ arg chord, ci;
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
});

// Bell arpeggios — pentatonic ascending
// C major pent: C D E G A (60 62 64 67 69)
bell_pattern = [72, 76, 79, 81, 84, 81, 79, 76];
bell_dur = 0.5;
t = 0.5;
i = 0;
while({ t < 60.0 }, {
    var note = bell_pattern[
        i % bell_pattern.size];
    // Add harmonic variation every 8 notes
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
while({ t < 60.0 }, {
    bundles = bundles.add(
        [t, [\s_new, \glass_bell,
            node_counter, 0, 0,
            \freq, 36.midicps, \amp, 0.5]]);
    node_counter = node_counter + 1;
    t = t + 8.0;
    i = i + 1;
});

total_dur = t + 4.0;
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
