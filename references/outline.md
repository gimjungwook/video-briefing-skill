# Outline format

Start with frontmatter:

```text
---
title: A briefing title
output: briefing.mp4
lang: en
theme: paper
---
```

Use `lang: ko` for Korean. Narration currently chooses Korean when a scene contains Hangul and English otherwise. Separate English quotations into their own scenes. Other languages are not validated by this release.

Each `# type | title` begins a scene. A `> sentence` is spoken narration and appears in captions. Narration is attached to the title, then each scene item in order. For explicit timing, end a narration line with `{b0}` or `{b0+b1}` (the tags are not spoken).

```text
# list | What changed
ch: Results
lead: A short explanation
- Completed work | A checked result. | check | kelp
- Open decision | What the viewer still needs to choose. | clock | sea
> Here is what changed.
> This result is complete and checked.
> This decision is still open.
```

## Scene types

| Type | Fields / item syntax | Item timing regions |
|---|---|---|
| `cover` | `sub:`, `meta:`, optional `art:` filename in project `assets/art/` | `title`, `sub`, `meta` |
| `list` | `- key \| value \| icon \| tone` | `b0`, `b1`, … |
| `cards` | `- heading \| body \| icon \| tone` | `c0`, `c1`, … |
| `stats` | `- value \| label \| subtext \| tone` | `s0`, `s1`, … |
| `checklist` | `- text \| yes/no \| chip` | `k0`, `k1`, … |
| `chat` | `- user: text` or `- ai: text \| tool` | `m0`, `m1`, … |
| `flow` | `- heading \| text`, optional `cap:` | `s0`, `s1`, …, `cap` |
| `table` | `- key \| value \| chip \| tone \| mark` | `r0`, `r1`, … |
| `code` | fenced code, optional `cap:`, `[[highlight]]` | `code`, `mark`, `cap` |
| `compare` | `before: shot.png \| label`, `after: shot.png \| label` | `before`, `after` |
| `step` | `shot: shot.png`, `url:`, items below | item names |

Every scene can have `ch:`, `icon:` and `lead:`. Item scenes begin their timing regions with `title`. Supported icons are `check`, `clock`, `video`, `code`. Unknown icon names use the check icon. Tones include `ink`, `kelp`, `sea`, `tide`, `amber`, `clay`.

## Screenshots

Place images in `P/shots/`. A step item is:

```text
- target | focus-x,focus-y,focus-w,focus-h | frame-x,frame-y,frame-w,frame-h | cursor-x,cursor-y
```

Coordinates are fractions from 0 to 1. Alternatively use `@name` values with a matching `shots/shot.regions.json` mapping names to `[x,y,w,h]`. Keep screenshots public or synthetic for shareable examples.

## Speech and speed

Korean text containing numbers or English abbreviations needs a `spoken.json` replacement list, for example `[["AI", "에이아이"], ["2배속", "두 배속"]]`. Captions keep the original text. Add a third value `"en"` to replacements for English scenes.

Use short sentences. The audio tool rejects long sentences and unresolved Korean pronunciation symbols. Fix errors before rendering. Narration has a normal-speed default; use `tempo.txt` for optional 2x.
