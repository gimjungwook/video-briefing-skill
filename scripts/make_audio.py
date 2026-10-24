#!/usr/bin/env python3
"""Make briefing narration audio locally: Supertonic 3 speaks one sentence at a time, Whisper checks each take.

usage: make_audio.py <project>      build the audio for <project>
       make_audio.py --self-test    check the trim, ending and tempo rules
reads   narration.json   one string per slide; this is also the subtitle text
                         a slide with no Hangul is read in English by the same voice (for reading post texts aloud)
        spoken.json      optional [["23.5그램", "이십삼 점 오 그램"], ...] replacements used for speech only;
                         a third value "en" makes a pair apply to English slides only, e.g. ["→", "to", "en"]
        tempo.txt        optional speed of the finished narration, e.g. 1 for voice comparisons;
                         without it VB_TEMPO, then 1.0
writes  narration_spoken.json, audio/NN.wav (one per slide, at the tempo), audio/words.json (word times for the cues),
        audio/report.json (tempo, chosen takes, transcripts, ending checks). Raw takes are cached in audio/cache/.
        Unless the tempo is 1, the 1x slide audio and its word times stay in audio/1x/.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
import vb_env  # noqa: E402

# Preset voice; this does not clone a user voice.
VOICE = {"voice": "F1", "speed": 1.0, "steps": 8, "temperature": 1.2, "lang": "ko", "model": "supertonic-3"}
SEEDS = (7, 8, 9)  # a take whose ending is lost is made again with the next seed
SENTENCE = re.compile(r"(?<=[.!?])\s+")
UNSPEAKABLE = re.compile(r"\S*[^가-힣\s,.?!]\S*")
MAX_SENTENCE = 120  # longer inputs lose their last words
MAX_SENTENCE_EN = 200  # shortcut: not measured like Korean; the ending check catches lost words, measure if CHECKs appear
FRAME, FLOOR_DB, KEEP_BEFORE, KEEP_AFTER, MAX_PAUSE = 0.02, -45.0, 0.05, 0.08, 0.8
GAP, PAD_START, PAD_END = 0.55, 0.12, 0.15
TEMPO = 1.0  # Public release: normal speed unless tempo.txt or VB_TEMPO overrides it.


def hangul(s):
    return "".join(re.findall(r"[가-힣]", s))


def lang_of(text):
    """A slide whose narration has no Hangul is English."""
    return "ko" if hangul(text) else "en"


def ends_ok(sentence, heard):
    """True when the start of the sentence's last word is heard at the end of the take."""
    if lang_of(sentence) == "en":
        last = re.sub(r"[^a-z0-9]", "", sentence.split()[-1].lower())
        tail = re.sub(r"[^a-z0-9]", "", heard.lower())
        return not last or last[:3] in tail[-max(8, len(last) + 4):]
    last = hangul(sentence.split()[-1])
    tail = hangul(heard)
    if tail.endswith("감사합니다") and not hangul(sentence).endswith("감사합니다"):
        tail = tail[:-5]  # Whisper often adds a closing 감사합니다 that was never said
    return not last or last[:2] in tail[-max(6, len(last) + 3):]


def trim(x, sr):
    """Cut silence at both ends and shorten inner pauses to MAX_PAUSE. Returns (audio, pauses_cut); audio is None if silent."""
    fl = int(FRAME * sr)
    frames = x[:len(x) // fl * fl].astype(np.float32).reshape(-1, fl) / 32768
    on = np.flatnonzero(20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9) > FLOOR_DB)
    if not len(on):
        return None, 0
    half = int(MAX_PAUSE / 2 * sr)
    parts, pos, cut = [], max(0, on[0] * fl - int(KEEP_BEFORE * sr)), 0
    for g in np.flatnonzero(np.diff(on) > 1):
        a, b = (on[g] + 1) * fl, on[g + 1] * fl
        if b - a > MAX_PAUSE * sr:
            parts.append(x[pos:a + half])
            pos, cut = b - half, cut + 1
    parts.append(x[pos:min(len(x), (on[-1] + 1) * fl + int(KEEP_AFTER * sr))])
    return np.concatenate(parts), cut


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: need 16-bit mono")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def write_wav(path, x, sr):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.astype(np.int16).tobytes())


def take_key(text, seed, lang="ko"):
    # dict(VOICE, lang="ko") equals VOICE, so Korean takes keep their old cache keys
    return hashlib.sha1(json.dumps([text, seed, dict(VOICE, lang=lang)], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def tempo_of(proj):
    """Narration speed: tempo.txt in the project, else VB_TEMPO, else TEMPO."""
    path = proj / "tempo.txt"
    raw = path.read_text(encoding="utf-8").strip() if path.exists() else os.environ.get("VB_TEMPO") or str(TEMPO)
    try:
        tempo = float(raw)
    except ValueError:
        sys.exit(f"tempo must be a number such as 2 or 1, got {raw!r}")
    # shortcut: tempo above 2 needs chained atempo filters (each takes 0.5..100) in verify's slow-down; add them then
    if not 0.5 <= tempo <= 2:
        sys.exit(f"tempo {tempo} is outside 0.5..2")
    return tempo


def speed_up(x, sr, tempo):
    """Play x at tempo with ffmpeg atempo, which keeps the pitch. Times shrink by 1/tempo give or take 30 ms."""
    return np.frombuffer(subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "pipe:", "-af", f"atempo={tempo}",
         "-f", "s16le", "-ar", str(sr), "-ac", "1", "pipe:"],
        input=x.astype(np.int16).tobytes(), capture_output=True, check=True).stdout, dtype=np.int16)


def scale_words(words, tempo):
    """Word times heard in the 1x audio, moved onto the audio played at tempo."""
    return {k: dict(v, words=[dict(w, s=round(w["s"] / tempo, 3), e=round(w["e"] / tempo, 3)) for w in v["words"]])
            for k, v in words.items()}


def spoken_text(proj):
    narration = json.loads((proj / "narration.json").read_text(encoding="utf-8"))
    path = proj / "spoken.json"
    pairs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    pairs.sort(key=lambda p: -len(p[0]))  # longest first, so "2027년 3월" is replaced before "3월"
    spoken, problems = [], []
    for n, text in enumerate(narration, 1):
        lang = lang_of(text)
        for a, b, *only in pairs:
            if (only[0] if only else "ko") == lang:
                text = text.replace(a, b)
        text = " ".join(text.split())
        spoken.append(text)
        if not text:
            problems.append(f"slide {n}: empty narration")
        left = sorted(set(UNSPEAKABLE.findall(text))) if lang == "ko" else []
        if left:
            problems.append(f"slide {n}: add Hangul readings to spoken.json for {left}")
        limit = MAX_SENTENCE if lang == "ko" else MAX_SENTENCE_EN
        problems += [f"slide {n}: split this sentence ({len(s)} chars): {s[:40]}..."
                     for s in SENTENCE.split(text) if len(s) > limit]
    return spoken, problems


def main(proj):
    spoken, problems = spoken_text(proj)
    tempo = tempo_of(proj)
    if problems:
        sys.exit("\n".join(problems))
    (proj / "narration_spoken.json").write_text(json.dumps(spoken, ensure_ascii=False, indent=1), encoding="utf-8")
    audio, cache = proj / "audio", proj / "audio" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    items = [{"id": f"{n:02d}-{k:02d}", "slide": n, "text": s, "lang": lang_of(text), "takes": []}
             for n, text in enumerate(spoken, 1) for k, s in enumerate(SENTENCE.split(text), 1)]

    pending = items
    for seed in SEEDS:
        keys = {it["id"]: take_key(it["text"], seed, it["lang"]) for it in pending}
        wav = lambda it: cache / f"{keys[it['id']]}.wav"  # noqa: E731
        txt = lambda it: cache / f"{keys[it['id']]}.txt"  # noqa: E731
        new = [it for it in pending if not wav(it).exists()]
        if new:
            vb_env.run("VB_SUPERTONIC_PY", "supertonic_synth", dict(VOICE, jobs=[
                {"id": it["id"], "text": it["text"], "seed": seed, "out": str(wav(it)), "lang": it["lang"]} for it in new]),
                cache / "synth_jobs.json", cache / "synth_result.json")
        new = [it for it in pending if not txt(it).exists()]
        if new:
            heard = vb_env.run("VB_WHISPER_PY", "whisper_words", {"words": False, "jobs": [
                {"id": it["id"], "wav": str(wav(it)), "language": it["lang"]} for it in new]},
                cache / "asr_jobs.json", cache / "asr_result.json")
            for it in new:
                txt(it).write_text(heard[it["id"]]["text"], encoding="utf-8")
        for it in pending:
            x, sr = read_wav(wav(it))
            clip, cut = trim(x, sr)
            heard_text = txt(it).read_text(encoding="utf-8")
            it["takes"].append({"seed": seed, "sr": sr, "audio": clip, "cut": cut, "heard": heard_text,
                                "ok": clip is not None and ends_ok(it["text"], heard_text)})
        pending = [it for it in pending if not it["takes"][-1]["ok"]]
        if not pending:
            break

    rates = set()
    for it in items:
        it["use"] = next((t for t in it["takes"] if t["ok"]), it["takes"][0])  # no good take: keep the first, flag it
        if it["use"]["audio"] is None:
            sys.exit(f"{it['id']}: every take is silent: {it['text']}")
        rates.add(it["use"]["sr"])
    if len(rates) != 1:
        sys.exit(f"takes have mixed sample rates {sorted(rates)}")
    sr = rates.pop()

    def silence(sec):
        return np.zeros(int(round(sec * sr)), dtype=np.int16)

    # Whisper hears the 1x audio, then the times are divided by the tempo. At tempo 1 nothing changes.
    plain = audio if tempo == 1 else audio / "1x"
    plain.mkdir(exist_ok=True)
    report, jobs = {"voice": VOICE, "tempo": tempo, "sample_rate": sr, "slides": []}, []
    for n in range(1, len(spoken) + 1):
        its = [it for it in items if it["slide"] == n]
        parts = [silence(PAD_START)]
        for i, it in enumerate(its):
            parts += ([silence(GAP)] if i else []) + [it["use"]["audio"]]
        x = np.concatenate(parts + [silence(PAD_END)])
        write_wav(plain / f"{n:02d}.wav", x, sr)
        jobs.append({"id": str(n), "wav": str(plain / f"{n:02d}.wav"), "language": lang_of(spoken[n - 1])})
        if tempo != 1:  # the whole slide, so the pauses between sentences shrink with the speech
            x = speed_up(x, sr, tempo)
            write_wav(audio / f"{n:02d}.wav", x, sr)
        report["slides"].append({"slide": n, "seconds": round(len(x) / sr, 2), "sentences": [
            {"id": it["id"], "seed": it["use"]["seed"], "ending_ok": it["use"]["ok"], "pauses_cut": it["use"]["cut"],
             "text": it["text"], "heard": it["use"]["heard"]} for it in its]})
    words = vb_env.run("VB_WHISPER_PY", "whisper_words", {"words": True, "jobs": jobs}, audio / "words_jobs.json",
                       plain / "words.json")
    if tempo != 1:
        (audio / "words.json").write_text(json.dumps(scale_words(words, tempo), ensure_ascii=False), encoding="utf-8")
    flagged = [s for sl in report["slides"] for s in sl["sentences"] if not s["ending_ok"]]
    report["flagged"] = [s["id"] for s in flagged]
    (audio / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"slides {len(spoken)}, sentences {len(items)}, tempo {tempo:g}, "
          f"speech {sum(s['seconds'] for s in report['slides']):.1f}s, "
          f"retried {sum(len(it['takes']) > 1 for it in items)}, pauses cut {sum(it['use']['cut'] for it in items)}")
    for s in flagged:
        print(f"CHECK {s['id']} ending may be lost | text: {s['text']} | heard: {s['heard']}")


def self_test():
    assert ends_ok("검토를 제안합니다.", "검토를 제안합니다. 감사합니다.")
    assert not ends_ok("이상입니다.", "마지막으로 정리하면")
    assert lang_of("Test recording: 98.9s → 77.6s.") == "en" and lang_of("목요일 글이에요.") == "ko"
    assert ends_ok("Small change, but it feels like one product.", "Small change, but it feels like one product.")
    assert not ends_ok("Small change, but it feels like one product.", "Small change, but it feels like")
    assert take_key("가", 7) == take_key("가", 7, "ko") != take_key("가", 7, "en")
    sr, tone = 1000, (np.sin(np.arange(300) / 3) * 8000).astype(np.int16)
    x = np.concatenate([np.zeros(500, np.int16), tone, np.zeros(2000, np.int16), tone, np.zeros(500, np.int16)])
    y, cut = trim(x, sr)
    assert cut == 1 and len(y) == 50 + 300 + 800 + 300 + 80, (cut, len(y))
    assert trim(np.zeros(1000, np.int16), sr) == (None, 0)
    # tempo 2: length and the start of each tone halve, within 30 ms
    sr = 44100
    tone = (np.sin(np.arange(int(0.3 * sr)) * 2 * np.pi * 220 / sr) * 8000).astype(np.int16)
    x = np.concatenate([np.zeros(sr // 2, np.int16), tone, np.zeros(sr, np.int16), tone, np.zeros(sr * 4, np.int16), tone])
    y = speed_up(x, sr, 2.0)

    def starts(a):
        on = np.flatnonzero(np.abs(a.astype(np.int32)) > 2000)
        return np.array([on[0]] + [b for p, b in zip(on, on[1:]) if b - p > sr // 20]) / sr
    assert abs(len(y) - len(x) / 2) / sr < 0.03, (len(x) / sr, len(y) / sr)
    assert np.abs(starts(y) - starts(x) / 2).max() < 0.03, (starts(x), starts(y))
    w = scale_words({"1": {"text": "t", "words": [{"w": "가", "s": 1.0, "e": 1.5}]}}, 2.0)["1"]["words"][0]
    assert (w["s"], w["e"]) == (0.5, 0.75), w
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.pop("VB_TEMPO", None)
        try:
            assert tempo_of(Path(d)) == TEMPO
            os.environ["VB_TEMPO"] = "1.5"
            assert tempo_of(Path(d)) == 1.5
            (Path(d) / "tempo.txt").write_text("1\n")
            assert tempo_of(Path(d)) == 1.0  # tempo.txt wins over VB_TEMPO
        finally:
            os.environ.pop("VB_TEMPO", None)
            if old is not None:
                os.environ["VB_TEMPO"] = old
    print("self-test ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2:
        main(Path(sys.argv[1]).resolve())
    else:
        sys.exit(__doc__)
