# Verification

`make_audio.py` retries a sentence when local transcription suggests that its last word was lost. Its ending check is a heuristic. Listen to `CHECK` sentences; do not call a transcript check a listening review.

`briefing_video.py motion` checks every scene's final layout for overflow or overlap, then renders. A scene that moves should also be sampled during motion. Keep important meaning in narration and captions; motion should reveal structure rather than create distraction.

`briefing_video.py verify` checks audio/video duration, chapter count and loudness near -16 LUFS. It creates a frame contact sheet and transcribes short clips near selected cue starts. Review the report and the pictures. A successful structural result does not establish correct facts, perfect word timing or a complete human viewing/listening pass.

When delivering, state the duration, output path, checks actually run, any flagged sentences and whether a full playback review took place. Keep source evidence and synthetic examples distinguishable. Never publish internal data merely because it rendered correctly.
