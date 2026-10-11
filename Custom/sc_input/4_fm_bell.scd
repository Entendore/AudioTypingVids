// NRT Test: FM Synthesis Bell
(
var duration = __DURATION__;

var def = SynthDef(\nrt_fm, { arg out=0, freq=440, car=1, mod=2, index=3, dur=3.5;
    var modulator = SinOsc.ar(freq * mod) * (freq * index);
    var sig = SinOsc.ar(freq * car + modulator) * 0.2 * EnvGen.ar(Env.perc(0.01, dur), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\d_recv, def]],
    [0.01, [\s_new, \nrt_fm, 1001, 0, 0, \freq, 440, \dur, 3.5]],
    [4.0, [\g_freeAll, 0]],
    [4.01, [\quit, 0]]
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
