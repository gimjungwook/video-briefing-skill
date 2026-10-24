# Third-party components

This repository contains the briefing skill's original code and CSS templates. It does not bundle speech model weights, fonts, Chrome, FFmpeg, Python packages, or any private product design assets.

| Component | Role | Upstream license / source |
|---|---|---|
| Supertonic Python SDK | Local speech synthesis | [MIT](https://github.com/supertone-oss-archive/supertonic-py/blob/main/LICENSE) |
| Supertonic 3 model weights | Preset voice inference | [OpenRAIL-M](https://huggingface.co/Supertone/supertonic-3/blob/main/LICENSE), [model card](https://huggingface.co/Supertone/supertonic-3) |
| mlx-whisper | Local transcription and word times | [MIT source](https://github.com/ml-explore/mlx-examples/tree/main/whisper) |
| Whisper large-v3-turbo MLX model | Transcription weights | [model card](https://huggingface.co/mlx-community/whisper-large-v3-turbo) |
| Noto Sans KR | Korean and English glyphs | [SIL Open Font License](https://github.com/google/fonts/blob/main/ofl/notosanskr/OFL.txt) |
| NumPy | Audio arrays | [BSD license](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| Pillow | Images and font metrics | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| FFmpeg | Audio processing and MP4 encoding | [Build-dependent licensing](https://ffmpeg.org/legal.html) |
| Chrome / Chromium | Local frame rendering | [Chrome terms](https://www.google.com/chrome/terms/), [Chromium licensing](https://www.chromium.org/chromium-os/licenses/) |

The skill's MIT license does not replace these licenses. Check the upstream terms for your use. In particular, the model weights do not become MIT licensed just because this wrapper is MIT licensed.

`download_models.py` downloads model files into the user's cache and the font from Google Fonts. Review this file before opting into those downloads. The synthesis subprocess runs with Hugging Face offline mode enabled after setup.
