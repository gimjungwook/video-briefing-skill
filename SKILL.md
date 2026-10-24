---
name: video-briefing
description: Turn requested AI work reports or explanations into local narrated motion videos with captions and timed visual highlights. Use when the user asks for a video briefing or has explicitly opted into video reports.
---

# Video Briefing

Help the person understand what their agents did. Make a video that explains the result, evidence, changes, limits and next decision without requiring the viewer to read the chat first.

The renderer and speech pipeline run locally after setup. The agent preparing the outline may use the user's existing AI service. Do not describe that service, the hardware or electricity as free.

## Workflow

`S` is this skill folder. `P` is a new local working folder, outside the skill source.

1. Run `python S/scripts/check_env.py`. This release supports macOS on Apple Silicon, Python 3.11+, Node 22+, Chrome and FFmpeg. If dependencies are missing, use [README.md](README.md) to explain setup; do not switch to a paid API.
2. Write `P/outline.md`. Read [references/outline.md](references/outline.md) for scene types and syntax. Use the user's language. One scene should explain one idea. Use varied scenes for comparisons, decisions, steps and evidence rather than repeating lists.
3. Pick `theme: paper`, `terminal` or `studio` in the outline frontmatter. All three are included; none requires a private design repository.
4. Run `python S/scripts/motion_kit.py P`. It writes `plan.json`, `narration.json` and `cues.py`. Write pronunciation replacements in `P/spoken.json` if requested by `make_audio.py`.
5. Run `python S/scripts/make_audio.py P`. Narration is **1x by default**. For 2x, write `2` to `P/tempo.txt`; this changes audio and word timing together. Listen to any `CHECK` items and correct incomplete sentences.
6. Run `python S/scripts/briefing_video.py motion P`. The renderer checks layouts, then creates the MP4 with chapters, word-following captions, motion and timed emphasis. Fix layout errors before rendering.
7. Run `python S/scripts/briefing_video.py verify P`. Open the contact sheet and review the video and audio to the extent needed for the request. Structural checks and sampled frames do not establish a complete human viewing/listening review. Report the actual checks and unresolved issues.
8. Show `P/out/briefing.mp4` using the host's media preview. Keep the written response useful on its own.

## Content and publishing

- Preserve exact approved wording when reading a proposed post or other message aloud. Keep explanation separate from quotations.
- Distinguish verified results, proposals and pending actions. Do not invent measurements, approvals or completion.
- Use public or synthetic demo data. Avoid customer material, private accounts, secrets and private source screenshots in shareable videos.
- Generating a briefing does not authorize uploading it, sending messages or posting to social accounts.
- Use the included preset voice. This package does not clone the user's voice.
- The first setup downloads the third-party speech models and a font. Later synthesis/rendering are local. See [THIRD_PARTY.md](THIRD_PARTY.md) for the separate model licenses.

Read [references/verification.md](references/verification.md) when interpreting output checks or reviewing a shared video.
