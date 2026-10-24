#!/usr/bin/env python3
"""Check the macOS Apple Silicon release without downloading or changing anything."""
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path
import vb_env


def has_modules(python, names):
    try:
        return subprocess.run([str(python), "-c", ";".join("import " + n for n in names)],
                              capture_output=True, timeout=60, env=vb_env.child_env()).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    from os import environ
    chrome = Path(environ.get("VB_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    try:
        version = subprocess.check_output([str(vb_env.get("VB_NODE")), "-p", "process.versions.node.split('.')[0]"],text=True)
        node = int(version.strip()) >= 22
    except (OSError, ValueError, subprocess.CalledProcessError):
        node = False
    hub = Path(environ.get("HF_HUB_CACHE", Path(environ.get("HF_HOME", Path.home()/".cache/huggingface"))/"hub"))
    checks = [
        ("macOS Apple Silicon (supported release)", platform.system()=="Darwin" and platform.machine()=="arm64"),
        ("Python 3.11+", sys.version_info >= (3,11)),
        ("ffmpeg + ffprobe", bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))),
        ("Node 22+", node), ("Google Chrome (or VB_CHROME)", chrome.is_file()),
        ("numpy + Pillow", all(importlib.util.find_spec(n) for n in ("numpy","PIL"))),
        ("Supertonic + soundfile", has_modules(vb_env.get("VB_SUPERTONIC_PY"), ["supertonic","soundfile"])),
        ("mlx-whisper", has_modules(vb_env.get("VB_WHISPER_PY"), ["mlx_whisper"])),
        ("Supertonic model cache", (vb_env.get("VB_SUPERTONIC_CACHE")/"onnx").is_dir()),
        ("Whisper model cache", (hub/"models--mlx-community--whisper-large-v3-turbo"/"snapshots").is_dir()),
        ("subtitle font (VB_FONT)", vb_env.get("VB_FONT").is_file()),
    ]
    for name,ok in checks:
        print(("OK       " if ok else "MISSING  ")+name)
    return 0 if all(ok for _,ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
