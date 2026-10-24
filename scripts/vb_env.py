"""Portable runtime paths. VB_* variables override the local defaults."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "video-briefing"
DEFAULTS = {
    "VB_NODE": shutil.which("node") or "node",
    "VB_SUPERTONIC_PY": sys.executable,
    "VB_WHISPER_PY": sys.executable,
    "VB_FONT": CACHE / "fonts/NotoSansKR.ttf",
    "VB_SUPERTONIC_CACHE": CACHE / "supertonic-3",
}


def get(key):
    return Path(os.environ.get(key) or DEFAULTS[key])


def child_env():
    env = dict(os.environ)
    env.update({"HF_HUB_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def run(py_key, script, spec, jobs_path, out_path):
    Path(jobs_path).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    subprocess.run([str(get(py_key)), str(SCRIPTS / f"{script}.py"), str(jobs_path), str(out_path)],
                   check=True, env=child_env())
    return json.loads(Path(out_path).read_text(encoding="utf-8"))
