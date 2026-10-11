// NRT Test: Major Chord (C-E-G)
(
var duration = __DURATION__;
var def = SynthDef(\nrt_chord, { arg out=0, freq=440;
    var sig = SinOsc.ar(freq) * 0.15 * EnvGen.ar(Env.linen(0.5, 2.0, 0.5), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\d_recv, def]],
    [0.01, [\s_new, \nrt_chord, 1001, 0, 0, \freq, 261.63]],
    [0.01, [\s_new, \nrt_chord, 1002, 0, 0, \freq, 329.63]],
    [0.01, [\s_new, \nrt_chord, 1003, 0, 0, \freq, 392.00]],
    [3.0, [\g_freeAll, 0]],
    [3.01, [\quit, 0]]
];

var f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[(sz >> 24) & 255, (sz >> 16) & 255, (sz >> 8) & 255, sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
0.exit;
)
