"""
generate_examples.py
====================
Generates SuperCollider NRT example files directly in the 'sc_input/' folder.

Run this once (or whenever you want to reset the examples), then run nrt_visualizer.py.

Usage:
    python generate_examples.py
"""

import os
import sys

# Resolve the input directory relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "sc_input")

EXAMPLES = [
    {
        "filename": "1_simple_sine.scd",
        "code": r"""// NRT Test: Simple Sine Wave
(
var def = SynthDef(\nrt_sine, { arg out=0, freq=440;
    var sig = SinOsc.ar(freq) * 0.2 * EnvGen.ar(Env.linen(0.1, 2.8, 0.1), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\d_recv, def]],
    [0.01, [\s_new, \nrt_sine, 1001, 0, 0, \freq, 440]],
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
"""
    },
    {
        "filename": "2_major_chord.scd",
        "code": r"""// NRT Test: Major Chord (C-E-G)
(
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
"""
    },
    {
        "filename": "3_frequency_sweep.scd",
        "code": r"""// NRT Test: Frequency Sweep
(
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
"""
    },
    {
        "filename": "4_fm_bell.scd",
        "code": r"""// NRT Test: FM Synthesis Bell
(
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
"""
    }
]

def write_example(base_dir, example):
    file_path = os.path.join(base_dir, example["filename"])
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(example["code"])

    print(f"  [OK] {example['filename']}")

def main():
    print("=" * 60)
    print("  SuperCollider NRT Visualizer — Example Generator")
    print("=" * 60)
    print(f"  Input directory: {INPUT_DIR}")
    print()

    os.makedirs(INPUT_DIR, exist_ok=True)

    print("Writing examples:")
    for ex in EXAMPLES:
        write_example(INPUT_DIR, ex)

    print()
    print(f"Done! {len(EXAMPLES)} examples written to: {INPUT_DIR}")
    print()
    print("You can now:")
    print("  1. Add more .scd files directly to the sc_input/ folder")
    print("  2. Run nrt_visualizer.py to launch the visualizer")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)