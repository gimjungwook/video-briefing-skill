#!/usr/bin/env python3
"""Synthesize Korean or English sentences with Supertonic 3 on the CPU. Run with the Supertonic venv python.

usage: supertonic_synth.py <jobs.json> <result.json>
jobs.json: {"voice": "F1", "speed": 1.0, "steps": 8, "temperature": 1.2, "lang": "ko", "model": "supertonic-3",
            "jobs": [{"id": "01-01", "text": "...", "seed": 7, "out": "/abs/file.wav"}]}
The model starts each sentence from NumPy noise; seeding per sentence makes a take reproducible.
temperature multiplies that start noise: 1.0 is the plain model, a larger value lets pitch and rhythm move more.
"""
import json
import os
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import soundfile as sf


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    from supertonic import TTS, core

    temp = float(spec.get("temperature", 1.0))
    if temp != 1.0:
        plain = core.Supertonic.sample_noisy_latent

        def scaled(self, duration):
            noise, mask = plain(self, duration)
            return noise * temp, mask

        core.Supertonic.sample_noisy_latent = scaled
    t0 = time.time()
    import vb_env
    tts = TTS(model=spec.get("model", "supertonic-3"), model_dir=vb_env.get("VB_SUPERTONIC_CACHE"), auto_download=False)
    style = tts.get_voice_style(spec.get("voice", "F1"))
    load = time.time() - t0
    results = []
    for job in spec["jobs"]:
        np.random.seed((int(job.get("seed", 7)) + zlib.crc32(job["text"].encode("utf-8"))) % (2 ** 32))
        t1 = time.time()
        wav, _ = tts.synthesize(job["text"], voice_style=style, lang=job.get("lang", spec.get("lang", "ko")),
                                total_steps=int(spec.get("steps", 8)), speed=float(spec.get("speed", 1.0)))
        Path(job["out"]).parent.mkdir(parents=True, exist_ok=True)
        sf.write(job["out"], np.asarray(wav, dtype=np.float32).reshape(-1), tts.sample_rate, subtype="PCM_16")
        results.append({"id": job["id"], "seconds": round(time.time() - t1, 3)})
    Path(sys.argv[2]).write_text(json.dumps({"load_seconds": round(load, 3), "sample_rate": tts.sample_rate,
                                             "results": results}), encoding="utf-8")


if __name__ == "__main__":
    main()
    # ONNX Runtime can abort in static destructors during interpreter teardown on macOS; output is already written.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
