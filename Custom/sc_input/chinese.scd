// =============================================================================
// Chinese Pentatonic (Optimized for NRT Visualizer)
// =============================================================================

(
// 1. ALL variables must be declared at the very top in SuperCollider
var duration, bundles, t, nodeID,
    guzhhengDef, erhuDef, diziDef, muyuDef,
    roots, pentatonic, guzhhengRhythm, diziMelody, diziRhythm,
    rawTotal, timeScale;

"Starting Chinese Pentatonic NRT Generation...".postln;

// 2. The NRT Visualizer replaces __DURATION__ with the typing animation length
duration = __DURATION__;
"Target Duration: ".post; duration.postln;

// 3. SynthDefs — Chinese instruments
guzhhengDef = SynthDef(\guzhheng, { arg out=0, freq=440, amp=0.2;
    var sig, env;
    env = EnvGen.kr(Env.perc(0.005, 2.5, 1, -4), doneAction: 2);
    sig = PMOsc.ar(freq, freq * 1.01, 2, 0, amp);
    sig = CombL.ar(sig, 0.05, 1/freq, 4);
    sig = RLPF.ar(sig, freq * 4, 0.6);
    Out.ar(out, sig * env ! 2);
});

erhuDef = SynthDef(\erhu, { arg out=0, freq=440, amp=0.15, gate=1;
    var sig, env, vibrato;
    vibrato = SinOsc.kr(5, 0, 0.008) * LFNoise1.kr(0.5).range(0, 1);
    env = EnvGen.kr(Env.adsr(0.8, 0.5, 0.8, 1.5), gate, doneAction: 2);
    sig = Saw.ar(freq * (1 + vibrato)) + Saw.ar(freq * (1.005 + vibrato));
    sig = BPF.ar(sig, freq * 2.5, 1.2);
    Out.ar(out, sig * env * amp ! 2);
});

diziDef = SynthDef(\dizi, { arg out=0, freq=440, amp=0.12, gate=1;
    var sig, env, breath;
    breath = WhiteNoise.ar(0.05 * LFNoise1.kr(8).range(0, 1));
    env = EnvGen.kr(Env.adsr(0.1, 0.2, 0.7, 0.5), gate, doneAction: 2);
    sig = Pulse.ar(freq, 0.4, 0.6) + breath;
    sig = HPF.ar(sig, 200);
    sig = LPF.ar(sig, freq * 6);
    Out.ar(out, sig * env * amp ! 2);
});

muyuDef = SynthDef(\muyu, { arg out=0, amp=0.3;
    var sig, env;
    env = EnvGen.kr(Env.perc(0.001, 0.08, 1, -10), doneAction: 2);
    sig = SinOsc.ar(800, 0, amp);
    Out.ar(out, sig * env ! 2);
});

"SynthDefs compiled.".postln;

// 4. Composition data — Chinese Pentatonic Progression (D, A, G, D)
roots          = [62, 69, 67, 62];               // D, A, G, D
pentatonic     = [0, 2, 4, 7, 9];                 // Pentatonic intervals
guzhhengRhythm  = [0.5, 0.5, 1.0, 0.5, 0.5, 1.0];
diziMelody     = [0, 2, 4, 7, 9, 7, 4, 2, 9, 7, 4, 2, 0, 2, 4, 7];
diziRhythm     = Array.fill(16, 0.25);

// 5. Calculate a time scaler so the whole piece fits inside `duration`
rawTotal = 16.0;
timeScale = max((duration - 0.5 - 1.0) / rawTotal, 0.05);

// 6. Initialize bundles array
bundles = [];
nodeID  = 1000;
t       = 0.0;

// 7. Lead-in bundle at t=0: send all SynthDefs + create default group
bundles = bundles.add([0.0, [\d_recv, guzhhengDef.asBytes]]);
bundles = bundles.add([0.0, [\d_recv, erhuDef.asBytes]]);
bundles = bundles.add([0.0, [\d_recv, diziDef.asBytes]]);
bundles = bundles.add([0.0, [\d_recv, muyuDef.asBytes]]);
bundles = bundles.add([0.0, [\g_new, 1, 0, 0]]);

t = 0.5; // start after defs load

// 8. Main composition loop — using .do for safety and idiomatic SC
roots.do({ arg root, i;
    var chordRoot   = root;
    var chordFifth  = root + 7;
    var sectionDur  = 4.0 * timeScale;
    var subTime     = 0.0;
    var erhuID1, erhuID2;

    // 8a. Erhu drone (sustained harmony)
    erhuID1 = nodeID;
    bundles = bundles.add([t + subTime,
        [\s_new, \erhu, erhuID1, 0, 1, \freq, chordRoot.midicps, \amp, 0.15]]);
    nodeID = nodeID + 1;

    erhuID2 = nodeID;
    bundles = bundles.add([t + subTime,
        [\s_new, \erhu, erhuID2, 0, 1, \freq, chordFifth.midicps, \amp, 0.12]]);
    nodeID = nodeID + 1;

    // 8b. Guzheng arpeggios + muyu woodblock
    guzhhengRhythm.do({ arg rhy, j;
        var note = pentatonic[j % pentatonic.size];
        var freq = (root + note).midicps;
        bundles = bundles.add([t + subTime,
            [\s_new, \guzhheng, nodeID, 0, 1, \freq, freq, \amp, 0.2]]);
        bundles = bundles.add([t + subTime,
            [\s_new, \muyu, nodeID + 1, 0, 1, \amp, 0.3]]);
        nodeID  = nodeID + 2;
        subTime = subTime + (rhy * timeScale);
    });

    // 8c. Dizi flourish
    subTime = 0.0;
    diziMelody.do({ arg note, k;
        var freq = (root + note + 12).midicps;
        bundles = bundles.add([t + subTime,
            [\s_new, \dizi, nodeID, 0, 1, \freq, freq, \amp, 0.12]]);
        nodeID  = nodeID + 1;
        subTime = subTime + (diziRhythm[k] * timeScale);
    });

    // 8d. Release erhu drones at end of section
    bundles = bundles.add([t + sectionDur, [\n_set, erhuID1, \gate, 0]]);
    bundles = bundles.add([t + sectionDur, [\n_set, erhuID2, \gate, 0]]);

    t = t + sectionDur;
});

"Composition data generated.".postln;

// 9. Final cleanup at exact requested duration
bundles = bundles.add([duration,      [\g_freeAll, 1]]);
bundles = bundles.add([duration + 0.01, [\c_set, 0, 0]]);  // NRT quit flag

// 10. Write raw OSC using built-in Score class
Score.write(bundles, "__SCORE_PATH__");

// 11. Signal Python the file is ready
"SCORE_WRITTEN".postln;
0.exit; // Force sclang to quit cleanly
)