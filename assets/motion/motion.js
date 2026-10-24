// Motion briefing runtime (2026-10-24). Builds one DOM scene per slide of plan.json and exposes seek(frame).
// Everything visible is a pure function of the frame number, so motion_render.mjs can capture frames one by one.
// seek() returns how many values changed; 0 means the frame equals the previous one and its image can be reused.
(() => {
  const D = window.MOTION, T = D.timeline, P = D.plan, A = D.assets, FPS = T.fps;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const easeInOut = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const back = (x) => { x = clamp(x); const c1 = 1.5, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  let writes = 0;
  const cache = new WeakMap();
  function set(el, key, value) {
    let m = cache.get(el); if (!m) cache.set(el, (m = {}));
    if (m[key] === value) return;
    m[key] = value; writes++;
    if (key === "text") el.textContent = value;
    else if (key === "html") el.innerHTML = value;
    else if (key === "class") el.className = value;
    else if (key.startsWith("--")) el.style.setProperty(key, value);
    else el.style[key] = value;
  }
  const num = (v, d = 3) => (Math.round(v * 10 ** d) / 10 ** d).toString();
  function icon(name, size = 34) {
    const shapes = {check:["M4 10l4 4 8-8"], code:["M7 5l-5 5 5 5M13 5l5 5-5 5"], clock:[{c:[10,10,8]},"M10 5v5l3 2"], video:["M2 5h11v10H2zM13 8l5-3v10l-5-3"]};
    const parts = shapes[name] || shapes.check;
    if (!parts) return "";
    const body = parts.map((p) => typeof p === "string" ? '<path d="' + p + '"/>'
      : "c" in p ? '<circle cx="' + p.c[0] + '" cy="' + p.c[1] + '" r="' + p.c[2] + '" fill="' + (p.fill ? "currentColor" : "none") + '"' + (p.fill ? ' stroke="none"' : "") + "/>"
      : '<path d="' + p.d + '" fill="currentColor" stroke="none"/>').join("");
    return '<svg viewBox="0 0 20 20" width="' + size + '" height="' + size + '" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>";
  }
  const art = (name) => A.root + "/art/" + name + ".png";
  const wordmark = () => '<span class="wm"><b>Video</b><span>Briefing</span></span>';
  const chipHtml = (label, tone = "ink") => '<span class="chip ' + tone + '">' + esc(label) + "</span>";

  const stage = document.getElementById("stage");
  const band = h("div", "band"), sub = h("div", "sub");
  band.appendChild(sub); stage.appendChild(band);

  // ---------- scenes ----------
  const scenes = P.slides.map((s, i) => {
    const el = h("section", "scene scene-" + s.t), actors = [], extra = [];
    const n = i + 1, info = T.slides[i];
    const sc = { s, el, actors, extra, f0: info.f0, f1: info.f1, dur: (info.f1 - info.f0) / FPS, first: {}, spans: {}, cues: [] };
    for (const c of T.cues) if (c.slide === n) {
      const a = (c.f0 - info.f0) / FPS, b = (c.f1 - info.f0) / FPS;
      sc.cues.push({ a, b, regions: c.regions });
      for (const r of c.regions) { if (!(r in sc.first)) sc.first[r] = a; (sc.spans[r] ||= []).push([a, b]); }
    }
    const add = (node, o = {}) => { node.classList.add("a"); actors.push({ el: node, region: o.region, kind: o.kind || "rise", idx: o.idx ?? actors.length, head: o.head, dur: o.dur }); return node; };
    const head = () => {
      if (s.ch) el.appendChild(add(h("div", "chap", esc(s.ch)), { head: true, idx: 0, kind: "fade" }));
      if (!s.title) return;
      const hd = h("div", "head");
      const tile = s.icon ? h("span", "tile", icon(s.icon, 40)) : null;
      if (tile) hd.appendChild(add(tile, { head: true, idx: 0, kind: "pop" }));
      const title = h("h1", null, esc(s.title));
      if (!tile) title.style.gridColumn = "1 / -1";
      hd.appendChild(add(title, { head: true, idx: 1, region: "title", kind: "rise" }));
      if (s.lead) hd.appendChild(add(h("p", "lead", esc(s.lead)), { head: true, idx: 2, kind: "rise" }));
      el.appendChild(hd);
    };
    const foot = () => { el.appendChild(h("div", "foot", wordmark() + "<span>" + esc(s.ch || "") + "&nbsp;&nbsp;" + n + " / " + P.slides.length + "</span>")); };
    const notes = (list, top) => {
      if (!list || !list.length) return;
      const side = h("div", "side"); if (top) side.style.top = top + "px";
      list.forEach((nt, k) => side.appendChild(add(h("div", "note", chipHtml(nt.label, nt.tone || "ink") + "<p>" + esc(nt.text) + "</p>"), { region: nt.region || "n" + k, kind: "slide" })));
      el.appendChild(side);
    };

    if (s.t === "cover") {
      el.appendChild(add(h("div", null, wordmark()).firstChild, { head: true, idx: 0, kind: "fade" }));
      const h1 = h("h1");
      s.title.split("\n").forEach((line, k) => h1.appendChild(add(h("span", "ln", esc(line)), { region: k === 0 ? "title" : undefined, idx: 1 + k, kind: "rise", dur: 0.7 })));
      el.appendChild(h1);
      el.appendChild(add(h("div", "sub0", esc(s.sub)), { region: "sub", idx: 3 }));
      el.appendChild(add(h("div", "meta", esc(s.meta)), { region: "meta", idx: 4, kind: "pop" }));
      for (let k = 0; k < 3; k++) { const rp = h("div", "ripple"); el.appendChild(rp); extra.push({ kind: "ripple", el: rp, k }); }
      const im = s.art ? h("img", "art") : h("div", "cover-orbit", '<i></i><i></i><i></i><b>PLAY<br>PAUSE<br>REPLAY</b>');
      if (s.art) im.src = art(s.art);
      el.appendChild(add(im, { idx: 2, kind: "rise", dur: 0.9 }));
      extra.push({ kind: "bob", el: im });
    } else if (s.t === "list") {
      head();
      const rows = h("div", "rows"); if (s.top) rows.style.top = s.top + "px";
      s.items.forEach((it, k) => rows.appendChild(add(h("div", "row tone-" + (it.tone || "ink"), '<span class="tile">' + icon(it.icon || "check", 38) + '</span><span class="k">' + esc(it.k) + '</span><span class="v">' + esc(it.v) + "</span>"), { region: "b" + k, kind: "slide" })));
      el.appendChild(rows); foot();
    } else if (s.t === "cards") {
      head();
      const cards = h("div", "cards"); cards.style.gridTemplateColumns = "repeat(" + s.cards.length + ", 1fr)";
      s.cards.forEach((c, k) => cards.appendChild(add(h("div", "card tone-" + (c.tone || "ink"), '<span class="tile">' + icon(c.icon || "check", 40) + "</span><h3>" + esc(c.h) + "</h3><p>" + esc(c.body) + "</p>"), { region: "c" + k, kind: "pop" })));
      el.appendChild(cards); foot();
    } else if (s.t === "toggles") {
      head();
      const box = h("div", "perms");
      s.perms.forEach((p, k) => {
        const right = p.state === "none" ? chipHtml(p.chip || "없음", p.chipTone || "clay")
          : p.state === "always" ? chipHtml(p.chip || "늘 켜짐", "ink") : (p.chip ? chipHtml(p.chip, p.chipTone || "amber") + "&nbsp;&nbsp;" : "") + '<span class="sw"><i></i></span>';
        const row = h("div", "perm" + (p.state === "none" ? " none" : ""), '<span class="tile">' + icon(p.icon || "check", 34) + '</span><span><b>' + esc(p.title) + "</b><small>" + esc(p.detail || "") + '</small></span><span style="display:flex;align-items:center">' + right + "</span>");
        box.appendChild(add(row, { region: "p" + k, kind: "slide" }));
        const sw = row.querySelector(".sw");
        if (sw) extra.push({ kind: "switch", el: sw, on: p.state === "on" ? 1 : 0, flip: p.flip });
      });
      el.appendChild(box); notes(s.notes); foot();
    } else if (s.t === "code") {
      head();
      // Reserve the final height before typing starts, then centre box + caption in the space under the header (230-980px),
      // so the caption never sits inside the growing box. Line box = 32px * 1.7, plus 2 * 44px padding.
      const code = h("div", "code"), codeH = Math.max(300, Math.round(s.lines.length * 54.4 + 88)), capH = s.cap ? 86 : 0;
      const top = Math.round(230 + Math.max(0, (750 - codeH - capH) / 2));
      code.style.top = top + "px"; code.style.minHeight = codeH + "px";
      el.appendChild(add(code, { region: "code", kind: "rise" }));
      extra.push({ kind: "type", el: code, lines: s.lines });
      if (s.cap) { const cap = h("div", "code-cap", esc(s.cap)); cap.style.top = (top + codeH + 40) + "px"; el.appendChild(add(cap, { region: "cap", kind: "rise" })); }
      foot();
    } else if (s.t === "step") {
      if (s.ch) el.appendChild(add(h("div", "chap", esc(s.ch)), { head: true, idx: 0, kind: "fade" }));
      el.appendChild(add(h("h2", "shot-title", esc(s.title)), { head: true, idx: 1, region: "title" }));
      const wrap = h("div", "shotwrap", '<div class="shotbar"><i></i><i></i><i></i><span>' + esc(s.url || "") + "</span></div>");
      const cam = h("div", "cam"); const im = h("img", "shot"); im.src = D.root + "/shots/" + s.shot;
      const focus = h("div", "focus"), cursor = h("img", "cursor"), click = h("div", "click");
      cursor.src = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 2l15 11-6.5 1.2L16 21l-3 1.4-3.4-6.6L4 20z" fill="#2b231e" stroke="#fffdf9" stroke-width="1.6" stroke-linejoin="round"/></svg>');
      cam.append(im, focus, click, cursor); wrap.appendChild(cam);
      el.appendChild(add(wrap, { idx: 1, kind: "pop", dur: 0.6 }));
      extra.push({ kind: "camera", img: im, focus, cursor, click, cfg: s });
      notes(s.notes, 196); foot();
    } else if (s.t === "flow") {
      head();
      const flow = h("div", "flow"); const W = 1704, nw = 470, gap = (W - nw * s.steps.length) / Math.max(1, s.steps.length - 1);
      s.steps.forEach((st, k) => {
        const x = k * (nw + gap);
        const node = h("div", "node", '<div class="n">' + (k + 1) + "</div><h3>" + esc(st.h) + "</h3><p>" + esc(st.v) + "</p>"); node.style.left = x + "px";
        flow.appendChild(add(node, { region: "s" + k, kind: "pop" }));
        if (k < s.steps.length - 1) {
          const pipe = h("div", "pipe"); pipe.style.left = (x + nw) + "px"; pipe.style.width = gap + "px"; flow.appendChild(pipe);
          const dots = [0, 1].map(() => { const d = h("div", "dot"); flow.appendChild(d); return d; });
          extra.push({ kind: "pipe", el: pipe, dots, from: x + nw, width: gap, next: "s" + (k + 1) });
        }
      });
      el.appendChild(flow);
      if (s.cap) el.appendChild(add(h("div", "flow-cap", esc(s.cap)), { region: "cap", kind: "rise" }));
      foot();
    } else if (s.t === "table") {
      head();
      const tbl = h("div", "tbl");
      s.rows.forEach((r, k) => {
        const v = esc(r.v).replace(/\{(\d+)\}/g, (_, d) => '<span class="num" data-count="' + d + '">' + d + "</span>");
        const row = h("div", "tr", '<span class="k">' + (r.mark ? '<img src="' + mark(r.mark) + '" alt="">' : "") + esc(r.k) + '</span><span class="v">' + v + "</span><span>" + (r.chip ? chipHtml(r.chip, r.chipTone || "kelp") : "") + "</span>");
        tbl.appendChild(add(row, { region: "r" + k, kind: "slide" }));
        row.querySelectorAll("[data-count]").forEach((c) => extra.push({ kind: "count", el: c, target: +c.dataset.count, region: "r" + k }));
      });
      el.appendChild(tbl); foot();
    } else if (s.t === "stats") {
      // Big numbers that count up as they are spoken. value "21" counts; "4.6s" or "53/53" counts its leading whole number.
      head();
      const box = h("div", "stats"); box.style.gridTemplateColumns = "repeat(" + s.items.length + ", 1fr)";
      s.items.forEach((it, k) => {
        const m = /^(\d+)(.*)$/.exec(String(it.value));
        const big = m ? '<span class="num" data-count="' + m[1] + '">' + m[1] + "</span>" + (m[2] ? "<small>" + esc(m[2]) + "</small>" : "") : esc(it.value);
        const card = h("div", "stat tone-" + (it.tone || "ink"), '<div class="big">' + big + '</div><div class="lbl">' + esc(it.label) + "</div>" + (it.sub ? '<div class="st-sub">' + esc(it.sub) + "</div>" : ""));
        box.appendChild(add(card, { region: "s" + k, kind: "pop" }));
        card.querySelectorAll("[data-count]").forEach((c) => extra.push({ kind: "count", el: c, target: +c.dataset.count, region: "s" + k }));
      });
      el.appendChild(box); foot();
    } else if (s.t === "compare") {
      // Before and after of the same screen: the after picture wipes across when "after" is spoken.
      head();
      const box = h("div", "cmp");
      const before = h("img", "before"), after = h("img", "after");
      before.src = D.root + "/shots/" + s.before.shot; after.src = D.root + "/shots/" + s.after.shot;
      box.append(before, after, h("div", "divider"), h("span", "lab l", esc(s.before.label || "Before")), h("span", "lab r", esc(s.after.label || "After")));
      el.appendChild(add(box, { idx: 1, kind: "pop", dur: 0.6 }));
      extra.push({ kind: "wipe", el: box, region: "after" });
      foot();
    } else if (s.t === "chat") {
      // A conversation: each message enters when it is spoken, and an AI message types itself in a box already at its final size.
      head();
      const box = h("div", "chat");
      s.messages.forEach((mm, k) => {
        const who = mm.who === "user" ? "user" : "ai";
        const msg = h("div", "msg " + who, '<div class="who">' + (who === "ai" ? icon(mm.icon || "chat", 24) : "") + esc(mm.name || (who === "user" ? "You" : "AI")) + "</div>" +
          '<div class="txt"><span class="ghost">' + esc(mm.text) + '</span><span class="typed"></span></div>' + (mm.tool ? '<span class="tool">' + esc(mm.tool) + "</span>" : ""));
        box.appendChild(add(msg, { region: "m" + k, kind: "rise" }));
        extra.push({ kind: "typeText", el: msg.querySelector(".typed"), text: String(mm.text), region: "m" + k, instant: who === "user" });
      });
      el.appendChild(box); foot();
    } else if (s.t === "checklist") {
      // Rows that tick themselves off as they are spoken; done: false leaves a row open.
      head();
      const box = h("div", "ticks");
      s.items.forEach((it, k) => {
        const row = h("div", "tickrow" + (it.done === false ? " open" : ""), '<span class="box"></span><span class="txt">' + esc(it.text) + "</span>" + (it.chip ? chipHtml(it.chip, it.chipTone || "kelp") : ""));
        box.appendChild(add(row, { region: "k" + k, kind: "slide" }));
        extra.push({ kind: "tick", el: row.querySelector(".box"), region: "k" + k, done: it.done !== false });
      });
      el.appendChild(box); foot();
    } else throw new Error("unknown slide type " + s.t);
    stage.insertBefore(el, band);
    return sc;
  });

  // ---------- time model ----------
  const enterAt = (sc, a) => {
    if (a.head) return a.idx * 0.07;
    if (a.region && a.region in sc.first) return Math.max(0, sc.first[a.region] - 0.15);
    return 0.12 + a.idx * 0.06;
  };
  const emphasis = (sc, region, t) => {
    let e = 0;
    for (const [a, b] of sc.spans[region] || []) e = Math.max(e, Math.min(clamp((t - a) / 0.22), clamp((b + 0.25 - t) / 0.25)));
    return e;
  };
  function cameraState(sc, x, t) {
    const cfg = x.cfg, focus = cfg.focus || {}, full = [0, 0, 1, 1];
    let target = focus.title || full, prev = target, at = -1, region = null;
    for (const c of sc.cues) {
      const key = c.regions.find((r) => r in focus);
      if (!key || c.a > t) continue;
      prev = target; target = focus[key]; at = c.a; region = key;
    }
    const p = at < 0 ? 1 : easeInOut((t - at) / 0.75);
    const rect = target.map((v, k) => prev[k] + (v - prev[k]) * p);
    return { rect, region };
  }
  function update(sc, t) {
    for (const a of sc.actors) {
      const p = easeOut((t - enterAt(sc, a)) / (a.dur || 0.5));
      set(a.el, "--o", num(p));
      if (a.kind === "rise") set(a.el, "--y", num((1 - p) * 30, 1) + "px");
      else if (a.kind === "slide") set(a.el, "--x", num((1 - p) * -56, 1) + "px");
      else if (a.kind === "pop") set(a.el, "--s", num(0.9 + 0.1 * back((t - enterAt(sc, a)) / (a.dur || 0.55))));
      if (a.region && !a.head) set(a.el, "--e", num(emphasis(sc, a.region, t)));
    }
    for (const x of sc.extra) {
      if (x.kind === "bob") set(x.el, "--y", num(Math.sin(t * 1.8) * 7, 1) + "px");
      else if (x.kind === "ripple") {
        const q = ((t * 0.32 + x.k / 3) % 1), size = 260 + q * 520;
        set(x.el, "width", num(size, 0) + "px"); set(x.el, "height", num(size * 0.36, 0) + "px");
        set(x.el, "left", num(1360 - size / 2, 0) + "px"); set(x.el, "top", num(905 - size * 0.18, 0) + "px"); set(x.el, "opacity", num(0.55 * (1 - q) * easeOut(t / 0.8)));
      } else if (x.kind === "switch") {
        let on = x.on;
        if (x.flip && x.flip.region in sc.first) on += ((x.flip.to === "on" ? 1 : 0) - x.on) * easeInOut((t - sc.first[x.flip.region] - 0.25) / 0.35);
        set(x.el, "--on", num(on));
      } else if (x.kind === "count") {
        const a = sc.first[x.region] ?? 0.1;
        set(x.el, "text", String(Math.round(x.target * easeOut((t - a) / 0.9))));
      } else if (x.kind === "type") {
        const full = x.lines.join("\n"), plain = full.replace(/\[\[|\]\]/g, "");
        const start = (sc.first.code ?? 0) + 0.2, dur = Math.min(2.2, plain.length * 0.018), shown = Math.round(plain.length * clamp((t - start) / dur));
        let out = "", seen = 0, inMark = false;
        for (let i = 0; i < full.length && seen < shown; i++) {
          if (full.startsWith("[[", i)) { out += "<mark>"; inMark = true; i++; continue; }
          if (full.startsWith("]]", i)) { out += "</mark>"; inMark = false; i++; continue; }
          out += full[i] === "\n" ? "<br>" : esc(full[i]); seen++;
        }
        if (inMark) out += "</mark>";
        const done = shown >= plain.length;
        set(x.el, "html", out + '<span class="caret"></span>');
        const markAt = sc.first.mark ?? (start + dur + 0.2);
        x.el.querySelectorAll("mark").forEach((m) => { m.style.setProperty("--m", num(easeOut((t - markAt) / 0.4))); });
        const caret = x.el.querySelector(".caret"); if (caret) caret.style.setProperty("--c", done ? (Math.floor(t * 2) % 2 ? "0" : "1") : "1");
        if (done) writes++;
      } else if (x.kind === "pipe") {
        const d = easeOut((t - (sc.first[x.next] ?? 0.4) + 0.05) / 0.45);
        set(x.el, "--d", num(d));
        x.dots.forEach((dot, j) => { const q = (t * 0.5 + j / 2) % 1; set(dot, "left", num(x.from + q * x.width, 1) + "px"); set(dot, "--do", num(d * Math.sin(q * Math.PI))); });
      } else if (x.kind === "wipe") {
        const at = sc.first[x.region], w = at === undefined ? 0 : easeInOut((t - at) / 1.1);
        set(x.el, "--w", num(w)); set(x.el, "--dv", num(at === undefined ? 0 : clamp((t - at) / 0.2) * clamp((at + 1.6 - t) / 0.4)));
      } else if (x.kind === "typeText") {
        const at = sc.first[x.region] ?? 0.1, n = x.instant ? x.text.length : Math.round(x.text.length * clamp((t - at - 0.1) / Math.min(1.8, x.text.length * 0.022)));
        set(x.el, "text", t < at - 0.15 ? "" : x.text.slice(0, Math.max(0, n)));
      } else if (x.kind === "tick") {
        const at = sc.first[x.region];
        set(x.el, "--k", num(x.done && at !== undefined ? clamp(back((t - at - 0.3) / 0.45), 0, 1.15) : 0));
      } else if (x.kind === "camera") {
        const img = x.img, nw = img.naturalWidth || 2400, nh = img.naturalHeight || 1500, cw = 1170, ch = 716, base = cw / nw;
        const { rect, region } = cameraState(sc, x, t);
        const rw = rect[2] * nw, rh = rect[3] * nh;
        const z = clamp(Math.min(cw / (rw * base), ch / (rh * base)) * 0.9, 1, 2.5), k = base * z;
        let tx = cw / 2 - (rect[0] * nw + rw / 2) * k, ty = ch / 2 - (rect[1] * nh + rh / 2) * k;
        tx = nw * k >= cw ? clamp(tx, cw - nw * k, 0) : (cw - nw * k) / 2; ty = nh * k >= ch ? clamp(ty, ch - nh * k, 0) : (ch - nh * k) / 2;
        set(img, "transform", "translate(" + num(tx, 1) + "px," + num(ty, 1) + "px) scale(" + num(k, 4) + ")");
        const fr = region && (x.cfg.frame || {})[region];
        if (fr) {
          set(x.focus, "left", num(tx + fr[0] * nw * k - 10, 1) + "px"); set(x.focus, "top", num(ty + fr[1] * nh * k - 10, 1) + "px");
          set(x.focus, "width", num(fr[2] * nw * k + 20, 1) + "px"); set(x.focus, "height", num(fr[3] * nh * k + 20, 1) + "px");
          set(x.focus, "--fo", num(emphasis(sc, region, t)));
        } else set(x.focus, "--fo", "0");
        const cur = x.cfg.cursor;
        if (cur) {
          const keys = Object.keys(cur).filter((r) => r in sc.first && sc.first[r] <= t).sort((p, q) => sc.first[p] - sc.first[q]);
          if (keys.length) {
            const key = keys.at(-1), a = sc.first[key], prevKey = keys.at(-2);
            const from = prevKey ? cur[prevKey] : [0.98, 1.05], to = cur[key], q = easeInOut((t - a) / 0.6);
            const px = from[0] + (to[0] - from[0]) * q, py = from[1] + (to[1] - from[1]) * q;
            const sx = tx + px * nw * k, sy = ty + py * nh * k;
            set(x.cursor, "transform", "translate(" + num(sx - 6, 1) + "px," + num(sy - 4, 1) + "px)"); set(x.cursor, "--co", num(clamp((t - a + 0.2) / 0.2)));
            const r = clamp((t - a - 0.6) / 0.5);
            set(x.click, "left", num(tx + to[0] * nw * k, 1) + "px"); set(x.click, "top", num(ty + to[1] * nh * k, 1) + "px");
            set(x.click, "--rs", num(0.3 + 0.9 * easeOut(r))); set(x.click, "--ro", num(r > 0 && r < 1 ? 1 - r : 0));
          } else set(x.cursor, "--co", "0");
        }
      }
    }
  }

  // ---------- subtitles ----------
  let cueIndex = 0, shownCue = -1;
  function subtitles(f) {
    while (cueIndex < T.cues.length - 1 && f >= T.cues[cueIndex].f1) cueIndex++;
    while (cueIndex > 0 && f < T.cues[cueIndex].f0) cueIndex--;
    const c = T.cues[cueIndex];
    if (!c || f < c.f0 || f >= c.f1) { set(sub, "html", ""); return; }
    if (shownCue !== cueIndex) {
      shownCue = cueIndex;
      set(sub, "html", c.words.length ? c.words.map(([, w], i) => '<span class="w" data-i="' + i + '">' + esc(w) + "</span>").join(" ") : esc(c.text));
    }
    sub.querySelectorAll(".w").forEach((w, i) => set(w, "class", "w" + (f >= c.words[i][0] ? " on" : "")));
    set(sub, "--so", num(clamp((f - c.f0 + 1) / 4)));
  }

  // ---------- frame ----------
  let visible = [];
  const TR = 0.35;
  window.seek = function seek(f) {
    writes = 0;
    let k = T.slides.findIndex((sl) => f >= sl.f0 && f < sl.f1);
    if (k < 0) k = T.slides.length - 1;
    const sc = scenes[k], t = (f - sc.f0) / FPS;
    const now = [k];
    const p = k > 0 ? easeOut(t / TR) : 1;
    if (k > 0 && t < TR) now.push(k - 1);
    for (const v of visible) if (!now.includes(v)) set(scenes[v].el, "display", "none");
    set(sc.el, "display", "block"); set(sc.el, "opacity", num(p)); set(sc.el, "transform", "translateY(" + num((1 - p) * 26, 1) + "px)"); set(sc.el, "zIndex", "2");
    update(sc, t);
    if (now.length > 1) {
      const pv = scenes[k - 1];
      set(pv.el, "display", "block"); set(pv.el, "opacity", num(1 - p)); set(pv.el, "transform", "translateY(" + num(-20 * p, 1) + "px)"); set(pv.el, "zIndex", "1");
      update(pv, pv.dur - 1 / FPS);
    }
    visible = now;
    subtitles(f);
    return writes;
  };
  // Layout check (motion_render.mjs --check): at a scene's last frame, blocks that leave the scene, blocks that overlap each other,
  // and single lines wider than their box. It returns plain descriptions; an empty list means the scene is clean.
  window.layoutProblems = function layoutProblems(i) {
    const sc = scenes[i], out = [], box = sc.el.getBoundingClientRect();
    const sel = [".head", ".rows", ".cards", ".stats", ".ticks", ".chat", ".tbl", ".code", ".code-cap", ".flow", ".flow-cap", ".shotwrap", ".side", ".cmp", ".perms", ".foot", "h1", ".sub0", ".meta"];
    const blocks = [...sc.el.children].filter((e) => sel.some((s) => e.matches(s)) && e.getBoundingClientRect().width > 0);
    const name = (e) => [...e.classList].filter((c) => c !== "a")[0] || e.tagName.toLowerCase();
    for (const e of blocks) {
      const r = e.getBoundingClientRect();
      if (r.left < box.left - 1 || r.right > box.right + 1 || r.top < box.top - 1 || r.bottom > box.bottom + 1) out.push(name(e) + " leaves the scene");
    }
    for (let a = 0; a < blocks.length; a++) for (let b = a + 1; b < blocks.length; b++) {
      const p = blocks[a].getBoundingClientRect(), q = blocks[b].getBoundingClientRect();
      if (Math.min(p.right, q.right) - Math.max(p.left, q.left) > 4 && Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top) > 4) out.push(name(blocks[a]) + " overlaps " + name(blocks[b]));
    }
    sc.el.querySelectorAll(".k, .v, .lbl, .txt, h3, .chip, .note p").forEach((e) => { if (e.scrollWidth > e.clientWidth + 2) out.push(name(e) + " is wider than its box: " + e.textContent.trim().slice(0, 40)); });
    sc.el.querySelectorAll(".stat, .card, .node, .msg, .tickrow, .row, .tr").forEach((e) => { if (e.scrollHeight > e.clientHeight + 2) out.push(name(e) + " content is taller than its box: " + e.textContent.trim().slice(0, 40)); });
    return out;
  };
  window.motionReady = Promise.all([...document.images].map((im) => im.decode().catch(() => {}))).then(() => document.fonts.ready).then(() => true);
})();
