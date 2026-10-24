#!/usr/bin/env python3
"""Transcribe WAV files with local mlx-whisper large-v3-turbo. Run with the Whisper venv python.

usage: whisper_words.py <jobs.json> <result.json>
jobs.json: {"words": true, "jobs": [{"id": "1", "wav": "/abs/file.wav", "language": "ko"}]}   (language defaults to ko)
result:    {"1": {"text": "...", "words": [{"w": "...", "s": 0.0, "e": 0.4}]}}
"""
import json
import sys
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"


def main():
    import mlx_whisper

    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    words = bool(spec.get("words"))
    out = {}
    for job in spec["jobs"]:
        r = mlx_whisper.transcribe(job["wav"], path_or_hf_repo=MODEL, language=job.get("language", "ko"), temperature=0.0,
                                   condition_on_previous_text=False, word_timestamps=words, verbose=None)
        item = {"text": r["text"].strip()}
        if words:
            item["words"] = [{"w": w["word"].strip(), "s": round(float(w["start"]), 3), "e": round(float(w["end"]), 3)}
                             for seg in r.get("segments", []) for w in seg.get("words", [])]
        out[job["id"]] = item
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
