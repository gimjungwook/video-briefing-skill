#!/usr/bin/env python3
"""Build a narrated briefing video with burned-in subtitles and highlights that follow the speech.

usage: briefing_video.py <mode> <project> [slide numbers]
  regions  draw the named regions on each slide into regions/ and regions/sheet.png; look before building
  cues     print the cue table: time, subtitle lines, regions, text
  build    write out/<OUTPUT> (default out/briefing.mp4)
  motion   write out/<OUTPUT> as motion graphics: every part enters as it is spoken, screenshots get a camera, subtitles
           follow each word (cues.py has MOTION = True; plan.json holds the scenes; no slides/regions steps)
  verify   check durations, chapters and loudness; sample frames; transcribe the audio at cue starts
<project>/cues.py defines TITLE, TITLES (one chapter name per slide), CUES, regions(n, h) and optionally OUTPUT.
audio/NN.wav and audio/words.json come from make_audio.py.
"""
import array
import difflib
import importlib.util
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import vb_env  # noqa: E402

FPS = 30
BAND, SUB_PX, LINE_H, MAXW = 168, 44, 60, 1760
INK, YELLOW, AMBER = (14, 27, 44), (255, 241, 168), (224, 160, 0)


def rgb(v):
    """A THEME colour: "#rrggbb" or an (r, g, b) tuple."""
    return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) if isinstance(v, str) else tuple(v)
KEEP = re.compile(r"[0-9A-Za-z가-힣]")


class Box:
    """Region helpers for one slide. Arguments are slide units (1280x720); results are pixel boxes."""

    def __init__(self, img, n):
        self.n, self.s = n, img.width / 1280
        a = np.asarray(img).astype(np.int16)
        self.mask = np.abs(a - a[4, 4]).max(axis=2) > 80  # ink: pixels that differ from the background corner

    def px(self, l, t, w, h):
        return [int(round(v * self.s)) for v in (l, t, l + w, t + h)]

    def raw(self, l, t, w, h):
        return tuple(self.px(l, t, w, h))

    def tight(self, l, t, w, h, pad=12):
        x0, y0, x1, y1 = self.px(l, t, w, h)
        ys, xs = np.where(self.mask[y0:y1, x0:x1])
        if not len(ys):
            raise ValueError(f"slide {self.n}: empty region {(l, t, w, h)}")
        return (x0 + xs.min() - pad, y0 + ys.min() - pad, x0 + xs.max() + pad, y0 + ys.max() + pad)

    def rowfit(self, l, t, w, h, pad=12):
        x0, _, x1, _ = self.px(l, t, w, h)
        _, y0, _, y1 = self.tight(l, t, w, h, pad)
        return (x0, y0, x1, y1)

    def lines(self, l, t, w, h, join=3):
        x0, y0, x1, y1 = self.px(l, t, w, h)
        m = self.mask[y0:y1, x0:x1]
        bands, start, gap, end = [], None, 0, 0
        for y, on in enumerate(m.any(axis=1)):
            if on:
                if start is None:
                    start = y
                gap, end = 0, y
            elif start is not None:
                gap += 1
                if gap > join:
                    bands.append((start, end))
                    start = None
        if start is not None:
            bands.append((start, end))
        out = []
        for a, b in bands:
            cols = np.where(m[a:b + 1].any(axis=0))[0]
            out.append((x0 + cols.min(), y0 + a, x0 + cols.max(), y0 + b))
        return out

    def bullets(self, l, t, w, h, pad=12):
        """One box per bullet item: a line starts a new item when it has ink where the bullet sits."""
        bx0, bx1 = int((l + 2) * self.s), int((l + 17) * self.s)
        groups = []
        for bx in self.lines(l, t, w, h):
            if self.mask[bx[1]:bx[3] + 1, bx0:bx1].any() or not groups:
                groups.append([bx])
            else:
                groups[-1].append(bx)
        return [self.padb(self.union(g), pad) for g in groups]

    @staticmethod
    def union(bs):
        return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))

    @staticmethod
    def padb(b, p):
        return (b[0] - p, b[1] - p, b[2] + p, b[3] + p)


def sheet(images, path):
    w, h = images[0].size
    out = Image.new("RGB", (w * 2, h * ((len(images) + 1) // 2)), (255, 255, 255))
    for i, im in enumerate(images):
        out.paste(im, ((i % 2) * w, (i // 2) * h))
    out.save(path)


def meta_escape(s):
    return re.sub(r"([=;#\\\n])", r"\\\1", str(s))


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        spec = importlib.util.spec_from_file_location("cues", self.root / "cues.py")
        self.cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cfg)
        self.narr = json.loads((self.root / "narration.json").read_text(encoding="utf-8"))
        self.n = len(self.narr)
        self.out = self.root / "out" / getattr(self.cfg, "OUTPUT", "briefing.mp4")
        self.font = ImageFont.truetype(str(vb_env.get("VB_FONT")), SUB_PX)
        # Optional static-slide theme: band, subtitle, highlight and outline colours.
        theme = getattr(self.cfg, "THEME", {})
        self.band, self.sub_color = rgb(theme.get("band", INK)), rgb(theme.get("subtitle", (255, 255, 255)))
        self.fill, self.outline = rgb(theme.get("highlight", YELLOW)), rgb(theme.get("outline", AMBER))
        # Motion frames come from assets/motion in isolated headless Chrome.
        self.motion = bool(getattr(self.cfg, "MOTION", False))
        self._img, self._reg, self._words = {}, {}, None

    def slide(self, n):
        if n not in self._img:
            self._img[n] = Image.open(self.root / f"slides/slide-{n:02d}.png").convert("RGB")
        return self._img[n]

    def regions(self, n):
        if n not in self._reg:
            self._reg[n] = self.cfg.regions(n, Box(self.slide(n), n))
        return self._reg[n]

    def tempo(self):
        """Narration tempo written by make_audio.py; missing reports use normal speed."""
        rep = self.root / "audio/report.json"
        return json.loads(rep.read_text(encoding="utf-8")).get("tempo", 1) if rep.exists() else 1

    def check(self):
        cfg, n, bad = self.cfg, self.n, []
        if len(cfg.TITLES) != n:
            bad.append(f"TITLES has {len(cfg.TITLES)} names for {n} slides")
        if sorted(cfg.CUES) != list(range(1, n + 1)):
            bad.append(f"CUES keys must be 1..{n}")
        if self.motion:
            if bad:
                sys.exit("\n".join(bad))
            return
        if not (self.root / f"slides/slide-{n:02d}.png").exists() or (self.root / f"slides/slide-{n + 1:02d}.png").exists():
            bad.append(f"slides/ must hold exactly {n} slides; supply the corresponding PNG files")
        if not bad:
            for k, cues in cfg.CUES.items():
                missing = {r for _, rs in cues for r in rs} - set(self.regions(k))
                if missing:
                    bad.append(f"slide {k}: unknown regions {sorted(missing)}")
        if bad:
            sys.exit("\n".join(bad))

    def wrap(self, s):
        """One line, or the most balanced two-line split at a space; None when two lines are not enough."""
        tw = self.font.getlength
        if tw(s) <= MAXW:
            return [s]
        best = None
        for i, c in enumerate(s):
            if c == " ":
                a, b = s[:i], s[i + 1:]
                wa, wb = tw(a), tw(b)
                if wa <= MAXW and wb <= MAXW and (best is None or max(wa, wb) < best[0]):
                    best = (max(wa, wb), [a, b])
        return best[1] if best else None

    def split_cue(self, text, i, j, regs):
        seg = text[i:j].strip()
        i += len(text[i:j]) - len(text[i:j].lstrip())
        ends = [k + 2 for k in range(len(seg) - 2) if seg[k:k + 2] == ". "]
        if ends:
            cut = ends[0]
            return self.split_cue(text, i, i + cut, regs) + self.split_cue(text, i + cut, i + len(seg), regs)
        if self.wrap(seg) is not None:
            return [(i, seg, regs)]
        mid = len(seg) / 2
        cands = [k + 2 for k in range(len(seg) - 2) if seg[k:k + 2] == ", "] or [k + 1 for k, c in enumerate(seg) if c == " "]
        cut = min(cands, key=lambda k: abs(k - mid))
        return self.split_cue(text, i, i + cut, regs) + self.split_cue(text, i + cut, i + len(seg), regs)

    def chunks(self, n):
        text, pos, starts = self.narr[n - 1], 0, []
        for phrase, regs in self.cfg.CUES[n]:
            i = text.find(phrase, pos)
            if i < 0:
                sys.exit(f"slide {n}: cue phrase not found in narration order: {phrase}")
            starts.append((i, regs))
            pos = i + len(phrase)
        if starts[0][0] != 0:
            sys.exit(f"slide {n}: the first cue phrase must start the narration")
        out = []
        for k, (i, regs) in enumerate(starts):
            j = starts[k + 1][0] if k + 1 < len(starts) else len(text)
            out.extend(self.split_cue(text, i, j, regs))
        return out

    def time_fn(self, n):
        """Map a character index of the narration to the start time of its word in the slide audio."""
        if self._words is None:
            self._words = json.loads((self.root / "audio/words.json").read_text(encoding="utf-8"))
        text, words = self.narr[n - 1], self._words[str(n)]["words"]
        o_chars, o_idx = [], []
        for i, ch in enumerate(text):
            if KEEP.match(ch):
                o_chars.append(ch.lower())
                o_idx.append(i)
        a_chars, a_word = [], []
        for wi, w in enumerate(words):
            for ch in w["w"]:
                if KEEP.match(ch):
                    a_chars.append(ch.lower())
                    a_word.append(wi)
        sm = difflib.SequenceMatcher(None, "".join(o_chars), "".join(a_chars), autojunk=False)
        o2a = [-1] * len(o_chars)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                o2a[a + k] = b + k

        def at(ci):
            k = next((q for q, oi in enumerate(o_idx) if oi >= ci), len(o_idx) - 1)
            for q in range(k, len(o_idx)):
                if o2a[q] >= 0:
                    return words[a_word[o2a[q]]]["s"]
            return words[-1]["e"]
        return at

    def segments(self):
        """Per slide: (lead samples, total samples), both whole video frames. Returns (sample rate, segments)."""
        segs, rates, tempo = [], set(), self.tempo()  # lead and tail shrink with the narration, like a faster playback
        for n in range(1, self.n + 1):
            with wave.open(str(self.root / f"audio/{n:02d}.wav"), "rb") as w:
                if w.getnchannels() != 1 or w.getsampwidth() != 2:
                    sys.exit(f"audio/{n:02d}.wav must be 16-bit mono")
                sr, frames = w.getframerate(), w.getnframes()
            rates.add(sr)
            spf = sr // FPS
            lead = int(round((0.8 if n == 1 else 0.4) / tempo * FPS)) * spf
            tail = int((2.0 if n == self.n else 0.7) / tempo * sr)
            segs.append((lead, -(-(lead + frames + tail) // spf) * spf))
        if len(rates) != 1 or sr % FPS:
            sys.exit(f"audio sample rates {sorted(rates)} must be one rate divisible by {FPS}")
        return sr, segs

    def cue_table(self):
        sr, segs = self.segments()
        t0, table = 0.0, []
        for n, (lead_s, total) in zip(range(1, self.n + 1), segs):
            lead, dur = lead_s / sr, total / sr
            at = self.time_fn(n)
            rows, prev = [], None
            for k, (ci, txt, regs) in enumerate(self.chunks(n)):
                rel = -lead if k == 0 else max(at(ci) - 0.15, prev + 0.6)
                prev = rel
                rows.append([int(round((t0 + lead + rel) * FPS)), n, txt, regs])
            end = int(round((t0 + dur) * FPS))
            for k, row in enumerate(rows):
                nxt = rows[k + 1][0] if k + 1 < len(rows) else end
                table.append({"f0": row[0], "f1": nxt, "slide": n, "text": row[2], "regions": row[3], "first": k == 0})
            t0 += dur
        return table

    def render(self, n, regs, sub):
        base = self.slide(n).copy()
        W, H = base.size
        reg = self.regions(n)
        boxes = [reg[k] for k in regs]
        if boxes:
            # Highlight only selected boxes; preserve the original appearance elsewhere.
            layer = Image.new("RGB", (W, H), (255, 255, 255))
            d = ImageDraw.Draw(layer)
            for bx in boxes:
                d.rounded_rectangle(bx, radius=14, fill=self.fill)
            base = Image.fromarray((np.asarray(base).astype(np.uint16) * np.asarray(layer) // 255).astype(np.uint8))
            d = ImageDraw.Draw(base)
            for bx in boxes:
                d.rounded_rectangle(bx, radius=14, outline=self.outline, width=4)
        canvas = Image.new("RGB", (W, H + BAND), self.band)
        canvas.paste(base, (0, 0))
        if sub:
            ls = self.wrap(sub)
            y = H + (BAND - LINE_H * len(ls)) / 2 - 4
            d = ImageDraw.Draw(canvas)
            for line in ls:
                d.text((W / 2, y + LINE_H / 2), line, font=self.font, fill=self.sub_color, anchor="mm")
                y += LINE_H
        return canvas

    def build_audio(self, sr, segs, vid):
        pcm = array.array("h")
        for n, (lead, total) in zip(range(1, self.n + 1), segs):
            with wave.open(str(self.root / f"audio/{n:02d}.wav"), "rb") as w:
                data = array.array("h", w.readframes(w.getnframes()))
            pcm.extend(array.array("h", bytes(2 * lead)))
            pcm.extend(data)
            pcm.extend(array.array("h", bytes(2 * (total - lead - len(data)))))
        raw = vid / "full.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        p1 = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(raw), "-af",
                             "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                            capture_output=True, text=True, check=True).stderr
        m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1, re.S).group(0))
        norm = vid / "full_norm.wav"
        af = ("loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:"
              "measured_thresh={input_thresh}:offset={target_offset}:linear=true:print_format=summary").format(**m)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, "-ar", "48000", "-ac", "1", str(norm)],
                       check=True)
        meta, t = vid / "chapters.txt", 0
        with open(meta, "w", encoding="utf-8") as f:
            f.write(f";FFMETADATA1\ntitle={meta_escape(getattr(self.cfg, 'TITLE', ''))}\n")
            for n, ((_, total), title) in enumerate(zip(segs, self.cfg.TITLES), 1):
                d = total * 1000 // sr
                f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={t}\nEND={t + d}\ntitle={meta_escape(f'{n}. {title}')}\n")
                t += d
        return norm, meta, m["input_i"]

    def build(self):
        self.check()
        sr, segs = self.segments()
        vid = self.root / "video"
        (vid / "frames").mkdir(parents=True, exist_ok=True)
        norm, meta, li = self.build_audio(sr, segs, vid)
        lst = []
        for k, c in enumerate(self.cue_table()):
            if c["f1"] <= c["f0"]:
                continue
            p = vid / "frames" / f"{k:03d}.png"
            self.render(c["slide"], c["regions"], c["text"]).save(p, compress_level=1)
            lst.append((p, (c["f1"] - c["f0"]) / FPS))
        with open(vid / "frames.txt", "w", encoding="utf-8") as f:
            for p, d in lst:
                f.write(f"file '{p}'\nduration {d:.6f}\n")
            f.write(f"file '{lst[-1][0]}'\n")
        total = sum(t for _, t in segs) / sr
        self.out.parent.mkdir(parents=True, exist_ok=True)
        # -t, not -shortest: -shortest once let the video run past the audio
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(vid / "frames.txt"),
                        "-i", str(norm), "-i", str(meta), "-map", "0:v", "-map", "1:a", "-map_metadata", "2",
                        "-map_chapters", "2", "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "20", "-tune", "stillimage", "-c:a", "aac", "-b:a", "160k", "-ac", "2",
                        "-movflags", "+faststart", "-t", f"{total:.3f}", str(self.out)], check=True)
        print(json.dumps({"cues": len(lst), "total": round(total, 3), "loudnorm_input_i": li, "out": str(self.out)},
                         ensure_ascii=False))

    def draw_regions(self, which):
        out = self.root / "regions"
        out.mkdir(exist_ok=True)
        fnt = ImageFont.truetype(str(vb_env.get("VB_FONT")), 22)
        cues = getattr(self.cfg, "CUES", {})
        thumbs = []
        for n in which or range(1, self.n + 1):
            im = self.slide(n).copy()
            d = ImageDraw.Draw(im)
            used, names = {r for _, rs in cues.get(n, []) for r in rs}, self.regions(n)
            for name, bx in names.items():
                col = (220, 30, 30) if name in used else (150, 150, 150)
                d.rectangle(bx, outline=col, width=3)
                d.text((bx[0] + 4, bx[1] + 2), name, font=fnt, fill=col)
            im.save(out / f"slide-{n:02d}.png")
            thumbs.append(im.resize((im.width // 2, im.height // 2)))
            if used - set(names):
                print(f"slide {n}: CUES use unknown regions {sorted(used - set(names))}")
        sheet(thumbs, out / "sheet.png")
        print(out / "sheet.png")

    def motion_build(self):
        """Motion graphics: the same audio, chapters and cue timing as build, with every word's frame for the subtitles.
        scripts/motion_render.mjs draws plan.json in headless Chrome frame by frame and muxes the result."""
        self.check()
        sr, segs = self.segments()
        vid = self.root / "video"
        mo = vid / "motion"
        mo.mkdir(parents=True, exist_ok=True)
        norm, meta, li = self.build_audio(sr, segs, vid)
        spf, t0, frame, slides, cues = sr // FPS, 0.0, 0, [], []
        for n, (lead_s, total) in zip(range(1, self.n + 1), segs):
            lead, dur, count = lead_s / sr, total / sr, total // spf
            slides.append({"n": n, "f0": frame, "f1": frame + count})
            at, rows, prev = self.time_fn(n), [], None
            for k, (ci, txt, regs) in enumerate(self.chunks(n)):
                rel = -lead if k == 0 else max(at(ci) - 0.15, prev + 0.6)
                prev = rel
                words = [[int(round((t0 + lead + at(ci + m.start())) * FPS)), m.group(0)] for m in re.finditer(r"\S+", txt)]
                rows.append((int(round((t0 + lead + rel) * FPS)), txt, regs, words))
            end = frame + count
            for k, (f0, txt, regs, words) in enumerate(rows):
                f1 = rows[k + 1][0] if k + 1 < len(rows) else end
                cues.append({"slide": n, "f0": f0, "f1": f1, "regions": regs, "text": txt,
                             "words": [[max(f0, min(w, f1 - 1)), token] for w, token in words]})
            t0, frame = t0 + dur, frame + count
        self.out.parent.mkdir(parents=True, exist_ok=True)
        timeline = {"fps": FPS, "width": 1920, "height": 1080 + BAND, "frames": frame, "tempo": self.tempo(), "slides": slides,
                    "cues": cues, "audio": str(norm), "chapters": str(meta), "out": str(self.out)}
        (mo / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        here = Path(__file__).resolve().parent
        node, render = str(vb_env.get("VB_NODE")), str(here / "motion_render.mjs")
        # Check every final scene layout before the long render starts.
        checked = subprocess.run([node, render, str(self.root), "--check"])
        if checked.returncode == 3:
            sys.exit("layout problems above (video/check-layout/report.json); fix the plan")
        checked.check_returncode()
        subprocess.run([node, render, str(self.root)], check=True)
        print(json.dumps({"cues": len(cues), "frames": frame, "total": round(frame / FPS, 3), "loudnorm_input_i": li, "out": str(self.out)},
                         ensure_ascii=False))

    def verify(self):
        self.check()
        sr, segs = self.segments()
        expected = sum(t for _, t in segs) / sr
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-show_chapters", "-of", "json",
             str(self.out)], capture_output=True, text=True, check=True).stdout)
        dur = {s["codec_type"]: float(s["duration"]) for s in probe["streams"]}
        ebur = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(self.out), "-map", "0:a", "-af", "ebur128",
                               "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
        lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", ebur)[-1])
        tab, chk = self.cue_table(), self.root / "video" / "check"
        chk.mkdir(parents=True, exist_ok=True)
        frames = []
        for i, k in enumerate(sorted({round(q * (len(tab) - 1) / 9) for q in range(10)})):
            c, p = tab[k], chk / f"frame-{i:02d}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(c['f0'] + c['f1']) / 2 / FPS:.3f}", "-i",
                            str(self.out), "-frames:v", "1", "-vf", "scale=640:-2", str(p)], check=True)
            frames.append(Image.open(p).convert("RGB"))
        sheet(frames, chk / "contact.png")
        mids = [c for c in tab if not c["first"]] or tab  # first cues start at the slide, not at a word
        picks = [mids[k] for k in sorted({round(q * (len(mids) - 1) / 3) for q in range(4)})]
        tempo = self.tempo()
        # Whisper often mishears fast speech, so the same stretch of speech is slowed back to 1x before transcribing.
        slow = [] if tempo == 1 else ["-af", f"atempo={1 / tempo:g}"]
        for i, c in enumerate(picks):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['f0'] / FPS:.3f}", "-t", f"{2.6 / tempo:g}", "-i",
                            str(self.out), "-vn", "-ac", "1", "-ar", "16000", *slow, str(chk / f"cue-{i}.wav")], check=True)
        heard = vb_env.run("VB_WHISPER_PY", "whisper_words", {"words": False, "jobs": [
            {"id": str(i), "wav": str(chk / f"cue-{i}.wav"), "language": "ko" if re.search(r"[가-힣]", c["text"]) else "en"}
            for i, c in enumerate(picks)]},
            chk / "cue_jobs.json", chk / "cue_result.json")

        def norm(s):
            return "".join(ch.lower() for ch in s if KEEP.match(ch))
        cue_checks = [{"at": round(c["f0"] / FPS, 2), "cue": c["text"][:30], "heard": heard[str(i)]["text"][:40],
                       "match": norm(c["text"])[:3] in norm(heard[str(i)]["text"])[:8]} for i, c in enumerate(picks)]
        hard = {"durations_ok": max(abs(dur.get("video", 0) - expected), abs(dur.get("audio", 0) - expected)) < 0.1,
                "chapters_ok": len(probe["chapters"]) == self.n, "loudness_ok": abs(lufs + 16) <= 0.5}
        print(json.dumps(dict(expected_s=round(expected, 3), video_s=dur.get("video"), audio_s=dur.get("audio"),
                              chapters=len(probe["chapters"]), lufs=lufs, **hard, cue_checks=cue_checks,
                              contact_sheet=str(chk / "contact.png")), ensure_ascii=False, indent=1))
        if not all(hard.values()):
            sys.exit(1)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("regions", "cues", "build", "motion", "verify"):
        sys.exit(__doc__)
    mode, root = sys.argv[1], sys.argv[2]
    p = Project(root)
    if mode == "regions":
        p.draw_regions([int(x) for x in sys.argv[3:]])
    elif mode == "cues":
        p.check()
        for c in p.cue_table():
            print(c["slide"], f'{c["f0"] / FPS:7.2f}-{c["f1"] / FPS:7.2f}', len(p.wrap(c["text"])), c["regions"], c["text"])
    elif mode == "build":
        p.build()
    elif mode == "motion":
        p.motion_build()
    else:
        p.verify()


if __name__ == "__main__":
    main()
