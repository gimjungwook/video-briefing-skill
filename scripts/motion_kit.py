#!/usr/bin/env python3
"""Turn a short outline into timed motion scenes, narration and cues.

usage: motion_kit.py <project>          reads <project>/outline.md

Outline (see references/outline.md):
    ---
    title: Video title
    output: Name.mp4
    lang: en
    ---
    # cover | First line / second line
    sub: One line under the title
    meta: Date · note
    > The first sentence goes with the title.
    > The second with sub, the third with meta.

    # stats | What changed
    ch: Server
    - 21 | MCP tools | one new | kelp
    > Narration for the title, then one line per item.
    > A line ending in {s0+s1} picks its parts explicitly.

Scene types and their items ("-" lines, fields split by |):
    list       - key | value | icon | tone                   parts b0, b1, ...
    cards      - heading | body | icon | tone                parts c0, ...
    stats      - value | label | sub | tone                  parts s0, ...   (value "21" counts up)
    checklist  - text | done (yes/no) | chip                 parts k0, ...
    chat       - user: text   or   - ai: text | tool         parts m0, ...
    flow       - heading | text          cap: caption        parts s0, ..., cap
    table      - key | value | chip | tone | mark            parts r0, ...   ({53} counts up)
    code       fenced lines ([[ ]] marks), cap: caption      parts code, mark, cap
    compare    before: shot.png | label    after: shot.png | label           parts before, after
    step       shot: file.png   url: address   - part | focus | frame | cursor (each "@name" or x,y,w,h / x,y)
               note: label | tone | text | part              parts title, the "-" parts, then notes
    cover      sub:, meta:, art:                              parts title, sub, meta
Every type except code takes icon: and lead: fields and starts its parts with title.
"""
import json
import re
import sys
from pathlib import Path

PARTS = {"list": "b", "cards": "c", "stats": "s", "checklist": "k", "chat": "m", "flow": "s", "table": "r"}
WARNINGS = []


def split(line):
    return [x.strip() for x in line.split("|")]


def numbers(text):
    return [float(x) for x in text.split(",")]


def scene(kind, title, fields, items, say, fence):
    s = {"t": kind, "title": title.replace(" / ", "\n") if kind == "cover" else title}
    for key in ("ch", "icon", "lead"):
        if key in fields:
            s[key] = fields[key]
    regions = ["title"]
    if kind == "cover":
        s.update(sub=fields.get("sub", ""), meta=fields.get("meta", ""), art=fields.get("art", ""))
        regions = ["title", "sub", "meta"]
    elif kind in ("list", "cards", "stats", "checklist", "flow", "table"):
        rows = []
        for it in items:
            f = split(it) + [""] * 5
            if kind == "list":
                rows.append({"k": f[0], "v": f[1], "icon": f[2] or "check", "tone": f[3] or "ink"})
            elif kind == "cards":
                rows.append({"h": f[0], "body": f[1], "icon": f[2] or "check", "tone": f[3] or "ink"})
            elif kind == "stats":
                rows.append({"value": f[0], "label": f[1], **({"sub": f[2]} if f[2] else {}), "tone": f[3] or "ink"})
            elif kind == "checklist":
                rows.append({"text": f[0], **({"done": False} if f[1].lower() in ("no", "false", "todo") else {}), **({"chip": f[2]} if f[2] else {})})
            elif kind == "flow":
                rows.append({"h": f[0], "v": f[1]})
            else:
                rows.append({"k": f[0], "v": f[1], **({"chip": f[2], "chipTone": f[3] or "kelp"} if f[2] else {}), **({"mark": f[4]} if f[4] else {})})
        key = {"list": "items", "cards": "cards", "stats": "items", "checklist": "items", "flow": "steps", "table": "rows"}[kind]
        s[key] = rows
        regions += [PARTS[kind] + str(i) for i in range(len(rows))]
        if kind == "flow" and fields.get("cap"):
            s["cap"] = fields["cap"]
            regions.append("cap")
    elif kind == "chat":
        msgs = []
        for it in items:
            who, _, rest = it.partition(":")
            f = split(rest)
            msgs.append({"who": "user" if who.strip().lower() == "user" else "ai", "text": f[0], **({"tool": f[1]} if len(f) > 1 and f[1] else {}),
                         **({"name": fields["user"]} if who.strip().lower() == "user" and fields.get("user") else {}),
                         **({"name": fields["ai"]} if who.strip().lower() != "user" and fields.get("ai") else {})})
        s["messages"] = msgs
        regions += ["m" + str(i) for i in range(len(msgs))]
    elif kind == "code":
        s["lines"] = fence
        if fields.get("cap"):
            s["cap"] = fields["cap"]
        regions = ["code", "mark", "cap"]
    elif kind == "compare":
        b, a = split(fields["before"]) + [""], split(fields["after"]) + [""]
        s.update(before={"shot": b[0], "label": b[1] or "Before"}, after={"shot": a[0], "label": a[1] or "After"})
        regions = ["title", "before", "after"]
    elif kind == "step":
        s.update(shot=fields["shot"], url=fields.get("url", ""), focus={}, frame={}, cursor={})
        for it in items:
            f = split(it) + ["", "", ""]
            part = f[0]
            regions.append(part)
            for key, value in (("focus", f[1]), ("frame", f[2]), ("cursor", f[3])):
                if value:
                    s[key][part] = value if value.startswith("@") else numbers(value)
        notes = []
        for i, line in enumerate(fields.get("notes", [])):
            f = split(line) + ["", "", "", ""]
            notes.append({"label": f[0], "tone": f[1] or "ink", "text": f[2], "region": f[3] or "n" + str(i)})
        if notes:
            s["notes"] = notes
            regions += [n["region"] for n in notes if n["region"] not in regions]
    else:
        raise SystemExit("unknown scene type: " + kind)
    pairs = []
    for i, line in enumerate(say):
        m = re.search(r"\s*\{([\w+]+)\}\s*$", line)
        pairs.append([line[:m.start()].strip(), m.group(1)] if m else [line.strip(), regions[min(i, len(regions) - 1)]])
    s["say"] = pairs
    # A part nobody speaks would appear at the scene's start, before the parts that are spoken.
    spoken = {r for _, rs in pairs for r in rs.split("+")}
    silent = [r for r in regions if r not in spoken and r not in ("title", "mark", "cap", "meta", "sub") and not (kind == "step" and r.startswith("n"))]
    if silent:
        WARNINGS.append(title.replace("\n", " ") + ": no narration for " + ", ".join(silent))
    return s


def read(path):
    text = path.read_text(encoding="utf-8")
    meta = {}
    if text.startswith("---"):
        head, _, text = text[3:].partition("\n---")
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    scenes, cur = [], None
    fence, infence = [], False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            infence = not infence
            continue
        if infence:
            cur["fence"].append(line)
            continue
        if line.startswith("# "):
            kind, _, title = line[2:].partition("|")
            cur = {"kind": kind.strip(), "title": title.strip(), "fields": {}, "items": [], "say": [], "fence": []}
            scenes.append(cur)
        elif not cur or not line.strip():
            continue
        elif line.startswith(">"):
            cur["say"].append(line[1:].strip())
        elif line.startswith("- "):
            cur["items"].append(line[2:].strip())
        elif re.match(r"^\w+:", line):
            k, _, v = line.partition(":")
            if k.strip() == "note":
                cur["fields"].setdefault("notes", []).append(v.strip())
            else:
                cur["fields"][k.strip()] = v.strip()
    built, ch = [], ""
    for c in scenes:
        ch = c["fields"].get("ch", ch)
        s = scene(c["kind"], c["title"], {**c["fields"], "ch": ch} if ch else c["fields"], c["items"], c["say"], c["fence"])
        if not s["say"]:
            raise SystemExit("scene without narration: " + c["title"])
        built.append(s)
    return meta, built


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    meta, slides = read(root / "outline.md")
    titles = [s["title"].replace("\n", " ") for s in slides]
    narr = [" ".join(x[0] for x in s["say"]) for s in slides]
    lang = meta.get("lang", "ko")
    theme = meta.get("theme", "paper")
    if theme not in ("paper", "terminal", "studio"):
        raise SystemExit("theme must be paper, terminal or studio")
    (root / "plan.json").write_text(json.dumps({"lang": lang, "theme": theme, "slides": slides, "titles": titles, "narration": narr}, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "narration.json").write_text(json.dumps(narr, ensure_ascii=False, indent=1), encoding="utf-8")
    cues = root / "cues.py"
    if not cues.exists() or "motion_kit" in cues.read_text(encoding="utf-8"):
        cues.write_text("# Written by motion_kit.py from outline.md; edit the outline, not this file.\n"
                        "import json\nfrom pathlib import Path\nR = Path(__file__).parent\n"
                        "PLAN = json.loads((R / \"plan.json\").read_text(encoding=\"utf-8\"))\nMOTION = True\n"
                        "TITLE = " + json.dumps(meta.get("title", titles[0]), ensure_ascii=False) + "\nTITLES = PLAN[\"titles\"]\n"
                        "OUTPUT = " + json.dumps(meta.get("output", "briefing.mp4"), ensure_ascii=False) + "\n"
                        "CUES = {n: [(text, region.split(\"+\")) for text, region in s[\"say\"]] for n, s in enumerate(PLAN[\"slides\"], 1)}\n", encoding="utf-8")
    words = sorted({w for t in narr if re.search(r"[가-힣]", t) for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9.:_\-]*", t)})
    print(json.dumps({"scenes": len(slides), "chars": sum(map(len, narr)), "lang": lang, "needs_readings": words, "unspoken": WARNINGS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
