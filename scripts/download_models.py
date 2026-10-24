#!/usr/bin/env python3
"""Explicit, one-time download of public model files and a font. No synthesis occurs here."""
import argparse
import urllib.request
from pathlib import Path
import vb_env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-model-licenses", action="store_true",
                        help="acknowledge the upstream licenses linked in THIRD_PARTY.md")
    args=parser.parse_args()
    if not args.accept_model_licenses:
        parser.error("Read THIRD_PARTY.md, then pass --accept-model-licenses to download.")
    from huggingface_hub import snapshot_download
    snapshot_download("Supertone/supertonic-3", local_dir=str(vb_env.get("VB_SUPERTONIC_CACHE")))
    snapshot_download("mlx-community/whisper-large-v3-turbo")
    font=vb_env.get("VB_FONT")
    font.parent.mkdir(parents=True,exist_ok=True)
    if not font.exists():
        url="https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
        temporary=font.with_suffix(".download")
        try:
            with urllib.request.urlopen(url,timeout=60) as response:
                temporary.write_bytes(response.read())
            from PIL import ImageFont
            ImageFont.truetype(str(temporary),44)
            temporary.replace(font)
        finally:
            temporary.unlink(missing_ok=True)
    print("Downloaded model files and font. Run scripts/check_env.py next.")


if __name__ == "__main__":
    main()
