// NRT Test: Frequency Sweep
(
var duration = __DURATION__;

var def = SynthDef(\nrt_sweep, { arg out=0, start=200, end=800, dur=4;
    var freq = XLine.kr(start, end, dur);
    var sig = Saw.ar(freq) * 0.2 * EnvGen.ar(Env.linen(0.1, 4.8, 0.1), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\d_recv, def]],
    [0.01, [\s_new, \nrt_sweep, 1001, 0, 0, \start, 200, \end, 800, \dur, 4]],
    [5.0, [\g_freeAll, 0]],
    [5.01, [\quit, 0]]
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
