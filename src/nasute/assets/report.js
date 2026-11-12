// Draws every Nasute report page from the JSON block in the page (<script id="data">). One file for all four page kinds:
// overview, suite, run, compare. No server, no network: it needs only this file, report.css and uPlot (uPlot.iife.min.js, vendored).
// All text from datasets, answers and the judge goes in with textContent (through h()), never as HTML, and no handler is written into markup.
// The pages are laid out like a short paper: tables with three rules, numbered figures, footnote-style notes, definitions in a popover.
// uPlot 1.6.32 (MIT), from npm; SHA-256 of uPlot.iife.min.js: 19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const G = D.glossary;
const app = document.getElementById("app");
const add = (...x) => app.append(...x.flat(Infinity).filter(c => c != null && c !== false));

// ---- small helpers -------------------------------------------------------------------------------
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c);
  return e;
}
const SCORES = ["hit", "recall", "mrr", "faithfulness", "correctness", "relevancy", "context_recall", "abstention", "error_rate"];
const HEADLINE = ["correctness", "faithfulness", "hit", "abstention", "error_rate"];
// Every name and definition comes from the glossary in the page data (one source, so another wording or language is a data change).
const K = (D.latest || D.summary || D.compare || {}).k;   // how many retrieved sources count; fills the "@k" in Hit rate@k and Recall@k
const name = (m, k = K) => G[m].term.replace("@k", k ? "@" + k : "@k");
const cap = t => t[0].toUpperCase() + t.slice(1);
const plain = m => cap(G[m].plain) + ".";
const plainLine = m => h("span", { class: "plain-line", text: G[m].plain });
const f2 = x => x == null ? "–" : x.toFixed(2);
const sgn = x => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(2);
const iso = id => id.replace(/^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)Z$/, "$1-$2-$3T$4:$5:$6Z");
const when = id => new Date(iso(id)).toLocaleString("en-AU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).replace(",", "").replace(/ /g, "\u00a0");   // "28 Oct 20:30", never split over lines
const day = id => new Date(iso(id)).toLocaleString("en-AU", { day: "numeric", month: "short" });
// "± 0.12" when the interval is symmetric around the mean, else the interval itself, shown within 0 to 1
const spread = s => {
  if (!s || !s.ci) return "";
  const lo = Math.max(0, s.ci[0]), hi = Math.min(1, s.ci[1]);
  return Math.abs((s.mean - s.ci[0]) - (s.ci[1] - s.mean)) < 0.005 && s.ci[0] >= 0 && s.ci[1] <= 1 ? `± ${((hi - lo) / 2).toFixed(2)}` : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
};
const runLabel = r => `${r.profile ? r.profile + " profile" : "no profile"}, ${r.judge_mode || "quick"} judge${r.repeats > 1 ? ", " + r.repeats + " repeats" : ""}`;
const verdictClass = v => v === "real gain" ? "up" : v === "real drop" ? "down" : "flat";
const verdict = v => h("span", { class: "verdict " + verdictClass(v), text: v });
const quote = text => h("blockquote", {}, h("p", { text }));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tick = (ok, what) => h("span", { class: ok ? "yes" : "no", text: ok ? "✓" : "✗", title: `${what}: ${ok ? "yes" : "no"}`, "aria-label": `${what}: ${ok ? "yes" : "no"}` });
const ver = v => typeof v === "number" ? `${v}.0.0` : v;   // an old run stored 2; it reads as 2.0.0
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const phone = matchMedia("(max-width: 640px)");
let charts = [];   // live uPlot objects, rebuilt when the profile tab or the light/dark setting changes

// A score with its 95% interval beside it, small and quiet.
const score = s => !s || s.mean == null ? "–" : [f2(s.mean), s.ci ? h("small", { class: "ci", text: " " + spread(s) }) : null];

// Booktabs table: head cells and rows are arrays of text or nodes; the first column is left-aligned, the rest right-aligned.
// `hide` lists columns left out on a phone; `lbl` is a small label shown only on a phone (see .scores in the CSS).
const table = (cls, head, rows, hide = []) => h("div", { class: "scroll" }, h("table", { class: cls }, h("thead", {}, h("tr", {}, head.map((c, i) => h("th", { class: hide.includes(i) ? "sm-hide" : "" }, c)))),
  h("tbody", {}, rows.map(r => Array.isArray(r) ? h("tr", {}, r.map((c, i) => h("td", { class: hide.includes(i) ? "sm-hide" : "" }, c))) : h("tr", { class: "group" }, h("td", { colspan: head.length, text: r.group }))))));   // {group} is a heading row
const lbl = text => h("span", { class: "lbl", text });
const heading = (text, intro) => [h("h2", { text }), intro ? h("p", { class: "intro", text: intro }) : null];
const caption = text => h("p", { class: "caption", text });

// ---- notes: warnings as numbered footnotes, referenced where they apply ------------------------------
const notes = [];
function note(text) {
  const n = notes.includes(text) ? notes.indexOf(text) + 1 : notes.push(text);   // a table re-sorted draws its notes again: same text, same number
  return h("sup", { class: "fn" }, h("a", { href: "#note-" + n, text: String(n), "aria-label": "Note " + n }));
}
function notesSection() {
  return notes.length ? h("section", { class: "notes" }, h("h2", { text: "Notes" }), h("ol", {}, notes.map((t, i) => h("li", { id: "note-" + (i + 1), text: t })))) : null;
}

// ---- definitions: a dotted-underline term opens a short popover in place -------------------------------
const pop = h("div", { class: "pop", role: "dialog", hidden: true });
let popFor = null;
function closePop() { pop.hidden = true; if (popFor) popFor.setAttribute("aria-expanded", "false"); popFor = null; }
function openPop(btn, key) {
  const g = G[key];
  pop.replaceChildren(h("b", { text: name(key) }), h("p", { text: plain(key) }), h("p", { class: "how", text: g.formula }));
  pop.hidden = false; pop.style.left = "0px"; pop.style.top = "0px";
  const r = btn.getBoundingClientRect(), w = pop.offsetWidth;
  pop.style.left = Math.max(8, Math.min(r.left + scrollX, scrollX + document.documentElement.clientWidth - w - 8)) + "px";
  pop.style.top = r.bottom + scrollY + 6 + "px";
  btn.setAttribute("aria-expanded", "true"); popFor = btn;
}
const term = (key, text, cls) => {
  const b = h("button", { type: "button", class: "term " + (cls || ""), "aria-expanded": "false", text: text || name(key), title: name(key) });
  b.addEventListener("click", e => { e.stopPropagation(); const same = popFor === b; closePop(); if (!same) openPop(b, key); });
  return b;
};
const qmark = key => term(key, "?", "qm");
document.addEventListener("click", e => { if (!pop.contains(e.target)) closePop(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closePop(); });

function reading() {
  return h("details", { class: "reading" }, h("summary", { text: "Reading this report" }),
    h("dl", {}, Object.keys(G).map(m => [h("dt", { text: name(m) }), h("dd", { text: `${plain(m)} ${G[m].formula}` })])));
}

// ---- page frame -----------------------------------------------------------------------------------------
const crumbs = (...parts) => h("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, h("a", { href: (D.page === "overview" ? "" : "../".repeat(D.page === "suite" ? 1 : 2)) + "index.html", text: "Nasute" }),
  parts.map(([href, text]) => [" / ", href ? h("a", { href, text }) : text]));
const suiteName = S => `${S.dataset} · asked of ${S.target_label || S.target}`;   // a suite is one dataset asked of one system
function finish(...more) { add(more, notesSection(), reading(), pop); }

function groupTable(groups, first) {
  const keys = Object.keys(groups), cols = SCORES.filter(m => keys.some(k => groups[k][m] != null));
  if (!keys.length) return h("p", { class: "empty", text: "None." });
  return table("", [first, ...cols.map(m => term(m))], keys.map(t => [t, ...cols.map(m => f2(groups[t][m]))]));
}

// ---- charts (uPlot) ------------------------------------------------------------------------------
// One figure per score: the mean as a line, the 95% interval as a shaded band between two hidden series (uPlot "bands").
// x is the run's place in the list (so runs are evenly spaced); a dashed line marks where the dataset changed version.
function plainTable(rs, m) {
  return table("", ["Run", name(m), "95% CI"], rs.map(r => [when(r.run), f2(r.metrics[m].mean), spread(r.metrics[m])]));
}

function drawChart(host, m, rs, runHref, big) {
  const readout = h("p", { class: "readout" });
  const plot = h("div", { class: "plot" });
  const changed = rs.some((r, i) => i && ver(r.dataset.version) !== ver(rs[i - 1].dataset.version));
  host.append(h("h3", {}, name(m), qmark(m)), h("p", { class: "plain-line" }, G[m].plain), plot, h("figcaption", { text: "By run · shaded: 95% CI" + (changed ? " · dashed: new question version" : "") + (rs.some(r => r.label) ? " · ▼ labelled run" : "") }), readout);
  const show = i => {
    const r = rs[i], s = r.metrics[m];
    readout.replaceChildren(h("b", { text: when(r.run) + ". " }), `${f2(s.mean)}${s.ci ? ` (${f2(Math.max(0, s.ci[0]))}–${f2(Math.min(1, s.ci[1]))})` : ""}. ${runLabel(r)}${r.label ? `, “${r.label}”` : ""}${r.baseline ? ", baseline" : ""}. `,
      h("a", { href: runHref(r), text: "Open this run" }), ".");
  };
  show(rs.length - 1);   // until the pointer moves, the newest run; it stays after the pointer leaves, so its link can be clicked
  if (typeof uPlot === "undefined") { plot.append(plainTable(rs, m)); return; }
  try {
    const ink = css("--quiet"), line = css("--rule"), accent = css("--accent"), font = "11px " + getComputedStyle(document.body).fontFamily;
    const lo = rs.map(r => r.metrics[m].ci ? Math.max(0, r.metrics[m].ci[0]) : r.metrics[m].mean), hi = rs.map(r => r.metrics[m].ci ? Math.min(1, r.metrics[m].ci[1]) : r.metrics[m].mean);
    const axis = { stroke: ink, font, labelFont: font, grid: { stroke: line, width: 1 }, ticks: { stroke: line, width: 1 } };
    const versions = u => {
      const c = u.ctx, k = devicePixelRatio;
      c.save();
      c.strokeStyle = ink; c.fillStyle = ink; c.setLineDash([4 * k, 4 * k]); c.font = `${11 * k}px ${getComputedStyle(document.body).fontFamily}`;
      rs.forEach((r, i) => {
        if (i && ver(r.dataset.version) !== ver(rs[i - 1].dataset.version)) {
          const x = Math.round(u.valToPos(i - 0.5, "x", true));
          c.beginPath(); c.moveTo(x, u.bbox.top); c.lineTo(x, u.bbox.top + u.bbox.height); c.stroke();
          c.fillText("v" + ver(r.dataset.version), x + 4 * k, u.bbox.top + 12 * k);
        }
      });
      c.setLineDash([]); c.fillStyle = accent;   // a small triangle at the top of the plot over every labelled run; its label is in the readout
      rs.forEach((r, i) => { if (r.label) { const x = u.valToPos(i, "x", true), y = u.bbox.top + 2 * k; c.beginPath(); c.moveTo(x - 5 * k, y); c.lineTo(x + 5 * k, y); c.lineTo(x, y + 9 * k); c.closePath(); c.fill(); } });
      c.restore();
    };
    const size = () => ({ width: plot.clientWidth, height: big ? 280 : phone.matches ? 160 : 190 });
    const u = new uPlot({
      ...size(), legend: { show: false },
      cursor: { drag: { x: true, y: false, setScale: true }, points: { size: 8 } },
      scales: { x: { time: false, range: (_, lo2, hi2) => [lo2 - 0.5, hi2 + 0.5] }, y: { range: [0, 1] } },
      axes: [{ ...axis, label: "Run date", labelSize: 16, size: 34, incrs: [1, 2, 5, 10, 20, 50, 100, 200, 500], values: (_, splits) => splits.map(i => Number.isInteger(i) && rs[i] ? day(rs[i].run) : "") },
        { ...axis, label: "Score, 0 to 1", labelSize: 16, size: 46, values: (_, splits) => splits.map(v => v.toFixed(1)) }],
      series: [{},
        { label: name(m), stroke: accent, width: 2, points: { size: 6, fill: accent, stroke: accent } },
        { label: "interval top", stroke: "transparent", points: { show: false } },
        { label: "interval bottom", stroke: "transparent", points: { show: false } }],
      bands: [{ series: [2, 3], fill: css("--band") }],
      hooks: { setCursor: [x => { if (x.cursor.idx != null && rs[x.cursor.idx]) show(x.cursor.idx); }], draw: [versions] },
    }, [rs.map((_, i) => i), rs.map(r => r.metrics[m].mean), hi, lo], plot);
    new ResizeObserver(() => u.setSize(size())).observe(plot);
    charts.push(u);
  } catch (e) {
    plot.replaceChildren(plainTable(rs, m));   // the chart failed: the numbers are still here
  }
}

// ---- overview ------------------------------------------------------------------------------------
// A small line of one score over the runs, with its first and last value written beside it (the labels make it readable).
function spark(runs, m, W = 90) {
  const pts = runs.map((r, i) => [i, r.metrics[m] && r.metrics[m].mean]).filter(p => p[1] != null);
  if (!pts.length) return "–";
  const H = 24, x = i => runs.length < 2 ? W / 2 : 3 + i * (W - 6) / (runs.length - 1), y = v => H - 3 - v * (H - 6);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H); svg.setAttribute("class", "spark"); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${name(m)}, first to last run: ${f2(pts[0][1])} to ${f2(pts[pts.length - 1][1])}`);
  // colours go in as style so they follow the light/dark setting (var() does not work in SVG attributes)
  const el = (t, a, style) => { const e = document.createElementNS("http://www.w3.org/2000/svg", t); for (const k in a) e.setAttribute(k, a[k]); Object.assign(e.style, style); svg.append(e); };
  el("line", { x1: 0, x2: W, y1: y(0), y2: y(0) }, { stroke: "var(--rule)" });
  if (pts.length > 1) el("polyline", { fill: "none", "stroke-width": 1.5, points: pts.map(p => x(p[0]) + "," + y(p[1])).join(" ") }, { stroke: "var(--accent)" });
  const last = pts[pts.length - 1];
  el("circle", { cx: x(last[0]), cy: y(last[1]), r: 2.5 }, { fill: "var(--accent)" });
  return h("span", { class: "sparkwrap" }, h("span", { class: "end", text: f2(pts[0][1]) }), svg, h("span", { class: "end", text: f2(last[1]) }));
}

// A number that looks fine when it is bad is a trap: an error rate over 10%, or any other score under 0.5, is shown in the warning colour.
const WARN_ERR = 0.1, WARN_LOW = 0.5;
const warnClass = (m, v) => v == null ? "" : (m === "error_rate" ? v > WARN_ERR : v < WARN_LOW) ? "warn" : "";
const failedWords = v => `${Math.round(v * 100)}% of attempts failed`;

// A table you sort by clicking a heading. cols: {t: heading, get: item -> value to sort by, show: item -> cell content, left: left-aligned, desc: first click sorts high to low}.
function sortable(cols, items, start = 0, dir = 1) {
  const st = { i: start, dir }, head = h("tr"), body = h("tbody");
  const paint = () => {
    [...head.children].forEach((th, i) => th.setAttribute("aria-sort", i === st.i ? (st.dir > 0 ? "ascending" : "descending") : "none"));
    const v = it => cols[st.i].get(it);
    body.replaceChildren(...[...items].sort((a, b) => { const x = v(a), y = v(b); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * st.dir; })
      .map(it => h("tr", {}, cols.map(c => h("td", { class: c.left ? "left" : "" }, c.show(it))))));
  };
  cols.forEach((c, i) => {
    const b = h("button", { type: "button", class: "sort", text: c.t });
    b.addEventListener("click", () => { st.dir = st.i === i ? -st.dir : c.desc ? -1 : 1; st.i = i; paint(); });
    head.append(h("th", { class: c.left ? "left" : "", "aria-sort": "none" }, b));
  });
  paint();
  return h("div", { class: "scroll" }, h("table", { class: "sortable" }, h("thead", {}, head), body));
}
// A mean as a dot on a 0 to 1 track with a band for its 95% interval, the number beside it; the title says the same in words.
const rangeBar = (s, m) => {
  const lo = s.ci ? Math.max(0, s.ci[0]) : s.mean, hi = s.ci ? Math.min(1, s.ci[1]) : s.mean;
  return h("span", { class: "rb", title: `${f2(s.mean)}${s.ci ? `, 95% range ${f2(lo)} to ${f2(hi)}` : ""}` }, h("i", { style: `--lo:${lo.toFixed(3)};--hi:${hi.toFixed(3)};--v:${s.mean.toFixed(3)}` }), h("b", { class: warnClass(m, s.mean), text: f2(s.mean) }));
};
const metricCol = (m, get, k, bar) => ({ t: name(m, k), desc: m !== "error_rate", get: r => (get(r)[m] || {}).mean, show: r => { const s = get(r)[m]; return s && s.mean != null ? bar ? rangeBar(s, m) : [h("span", { class: warnClass(m, s.mean), text: f2(s.mean) }), s.ci ? h("small", { class: "ci", text: " " + spread(s) }) : null] : "–"; } });

function overview() {
  add(crumbs(), h("h1", { text: "Nasute" }), h("p", { class: "lede", text: "Each row is one set of questions tested on one system, with all its runs. Click a heading to sort, a run count to see its runs. Scores run from 0 (bad) to 1 (perfect)." }));
  if (!D.suites.length) { add(h("p", { class: "empty", text: "No runs yet. Start one with: nasute run --profile smoke" })); finish(); return; }
  const last = s => s.runs[s.runs.length - 1];
  // shortcut: the trend is the sparkline of the answer-correctness means, nothing more (no paired test here; the suite page has the real one).
  const cols = [
    { t: "Dataset", left: true, get: s => s.dataset.toLowerCase(), show: s => `${s.dataset} v${ver(last(s).dataset.version)}` },
    { t: "Tested on", left: true, get: s => (s.target_label || s.target).toLowerCase(), show: s => s.target_label || s.target },
    { t: "Last run", desc: true, get: s => last(s).run, show: s => [h("a", { href: `${s.folder}/runs/${last(s).run}.html`, text: when(last(s).run) }), last(s).aborted ? h("small", { class: "sub", text: "stopped early" }) : null, last(s).incomplete ? h("small", { class: "sub", text: "incomplete" }) : null] },
    metricCol("correctness", s => last(s).metrics, K, true), metricCol("faithfulness", s => last(s).metrics, K, true), metricCol("error_rate", s => last(s).metrics, K),
    { t: "Trend", get: s => s.runs.length < 2 ? null : (last(s).metrics.correctness || {}).mean - (s.runs[0].metrics.correctness || {}).mean, show: s => s.runs.length > 1 ? spark(s.runs, "correctness", 90) : h("span", { class: "muted", text: "Only one run so far" }) },
    { t: "Runs", desc: true, get: s => s.runs.length, show: s => h("a", { href: `${s.folder}/index.html#runs`, text: plural(s.runs.length, "run") }) },
    { t: "Questions", get: () => null, show: s => h("a", { href: `${s.folder}/runs/${last(s).run}.html`, text: "Latest run →" }) }];
  add(sortable(cols, D.suites, 2, -1));
  for (const j of D.judges) {
    const jc = j.check, ms = jc ? SCORES.filter(m => jc.metrics[m]) : [];
    add(h("p", { class: "small" }, `Judge: ${j.model}, ${j.mode} mode. `, jc ? `Checked ${when(jc.run.replace("judge-", ""))} on ${jc.dataset.name} v${ver(jc.dataset.version)}: ` + ms.map(m => `${name(m)} ${(jc.metrics[m].accuracy * 100).toFixed(0)}% accurate`).join(", ") + ". " : "Not checked yet. ",
      j.folder ? h("a", { href: `${j.folder}/index.html`, text: "Details" }) : null, j.folder ? "." : null));
  }
  finish();
}

// The marker's latest check (looked up when the report is written): which set, how many items, when, how it scored, and the marks it got wrong.
function markerCheck(jc, since) {
  const when2 = when(jc.run.replace("judge-", ""));
  const ms = SCORES.filter(m => jc.metrics[m]);
  return [h("p", { class: "intro", text: `Checked on ${jc.dataset.name} v${ver(jc.dataset.version)}, ${plural(jc.items, "item")}${jc.aborted ? ` of ${jc.set_size} (stopped early: ${jc.aborted})` : ""}, ${when2}. Answers with known faults, marked by the same judge.${since ? " This check is newer than the run." : ""}` }),
    table("narrow", ["Measure", [name("accuracy") + " ", qmark("accuracy")], [name("kappa") + " ", qmark("kappa")]], ms.map(m => [[term(m), plainLine(m)], `${(jc.metrics[m].accuracy * 100).toFixed(0)}%`, jc.metrics[m].kappa == null ? "–" : jc.metrics[m].kappa.toFixed(2)])),
    jc.wrong.length ? more(`${plural(jc.wrong.length, "mark")} it got wrong`, h("ul", { class: "plain" }, jc.wrong.map(x => h("li", {}, h("b", { text: x.id }), ` ${name(x.metric)}: got ${x.got == null ? "no mark" : f2(x.got)}, expected ${f2(x.expected[0])}–${f2(x.expected[1])}`)))) : null];
}

// ---- per-question charts (suite page) ---------------------------------------------------------------
// Two canvas charts of the latest run, drawn with Chart.js and its boxplot plugin (both vendored in assets/, see the README):
// a scatter of one score against another (faithfulness against correctness), and box plots of one score by group. Every dot is a question and
// opens it in the table below. Colours come from the CSS (--c0..--c2 plus grey), so light and dark follow the device.
// Names of scores come from the glossary. Question text only ever reaches the page through h() or Chart.js text drawing.
// stats:start (pure helpers, run on their own by the tests: they must not touch the page)
// A link from a target is followed only when it is http(s) or starts with a single "/"; javascript:, data: and the rest stay plain text.
const safeUrl = u => typeof u === "string" && (/^https?:\/\/[^\s]/i.test(u) || /^\/(?![\/\\])\S/.test(u)) ? u : null;
const quantile = (s, p) => { const i = (s.length - 1) * p, lo = Math.floor(i); return s[lo] + (s[Math.min(lo + 1, s.length - 1)] - s[lo]) * (i - lo); };   // linear, the plugin's default
// Box statistics: quartiles, and whiskers out to the most extreme value within 1.5 x the box length of the box (the rest are outliers).
function boxStats(values) {
  const s = [...values].sort((a, b) => a - b), q1 = quantile(s, 0.25), q3 = quantile(s, 0.75), fence = 1.5 * (q3 - q1), inside = s.filter(v => v >= q1 - fence && v <= q3 + fence);
  return { n: s.length, mean: s.reduce((a, b) => a + b, 0) / s.length, min: s[0], max: s[s.length - 1], q1, median: quantile(s, 0.5), q3, lo: inside[0], hi: inside[inside.length - 1], out: s.length - inside.length };
}
// The same number for the same key every time (so a redraw never shuffles the dots), spread over -0.5 to 0.5.
function jitter(key, salt) {
  let x = 2166136261;
  for (const c of key + salt) x = Math.imul(x ^ c.charCodeAt(0), 16777619);
  x ^= x >>> 15; x = Math.imul(x, 2246822519); x ^= x >>> 13;
  return (x >>> 0) / 4294967296 - 0.5;
}
// A score nudged by up to 0.07 (scores pile up at 0, 0.5 and 1), but never across 0.5 (the quadrant line) and never outside 0 to 1, so a dot stays in its quadrant.
function nudge(v, key, salt) {
  const lo = v >= 0.5 ? 0.5 : 0, hi = v >= 0.5 ? 1 : 0.5, x = v + jitter(key, salt) * 0.14;
  return Math.min(hi, Math.max(lo, x < lo ? 2 * lo - x : x > hi ? 2 * hi - x : x));
}
// The part of a list of `total` items to show on page `page` (counted from 1, kept inside 1 to the last page): -> {page, pages, from, to}, a slice's ends.
const PER_PAGE = 50;
function pageRange(total, page, per = PER_PAGE) {
  const pages = Math.max(1, Math.ceil(total / per)), p = Math.min(pages, Math.max(1, Math.floor(page) || 1));
  return { page: p, pages, from: (p - 1) * per, to: Math.min(total, p * per) };
}
// stats:end

const GROUPERS = {
  difficulty: ["Difficulty", q => q.difficulty || "unknown", ["easy", "medium", "hard"]],
  origin: ["Origin tag", q => q.origin],
  topic: ["Topic", q => q.tags[0] || "untagged"],
  cause: ["Cause", q => q.cause || "none"],
};
const NEUTRAL = { none: "no cause", unknown: "unknown", untagged: "untagged" };   // groups that get grey, not a colour
const POINT = ["circle", "rect", "triangle", "rectRot", "circle"];   // a second channel beside colour; the last is the hollow grey "other"
// Colours: the first three slots of the validated categorical palette (all-pairs safe); a fourth group and beyond folds into grey "other".
// Groups are coloured by their order in the run, not by what is switched on, so a legend click never repaints the rest.
function grouping(qs, by) {
  const [, get, order] = GROUPERS[by], n = new Map();
  for (const q of qs) n.set(get(q), (n.get(get(q)) || 0) + 1);
  const rank = k => order ? (order.includes(k) ? order.indexOf(k) : 99) : 0;
  const keys = [...n.keys()].sort((a, b) => rank(a) - rank(b) || n.get(b) - n.get(a) || a.localeCompare(b)), coloured = keys.filter(k => !NEUTRAL[k]), entries = new Map();
  coloured.slice(0, 3).forEach((k, i) => entries.set(k, { key: k, label: k, c: i, shape: i }));
  for (const k of keys) if (NEUTRAL[k]) entries.set(k, { key: k, label: NEUTRAL[k], c: 3, shape: 3 });
  if (coloured.length > 3) entries.set("other", { key: "other", label: by === "cause" ? "other causes" : "other", c: 3, shape: 4 });
  return { entries: [...entries.values()], of: q => entries.get(get(q)) || entries.get("other") };
}

const shorten = (t, n = 110) => t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t;
const wrapText = (t, n = 44) => { const out = []; let line = ""; for (const w of t.split(/\s+/)) { if (line && (line + " " + w).length > n) { out.push(line); line = w; } else line = line ? line + " " + w : w; } return line ? [...out, line] : out; };
const coarse = matchMedia("(pointer: coarse)");   // a touch screen: the first tap shows the tooltip, a second tap on the same dot opens it
const quadWords = { tr: "grounded and right", br: "grounded but wrong", tl: "right but not backed", bl: "neither" };
const swatch = (e, off) => h("span", { class: "sw s" + e.shape + " m" + e.c + (off ? " off" : ""), "aria-hidden": "true" });

function theme() {
  const t = { ink: css("--ink"), quiet: css("--quiet"), rule: css("--rule"), paper: css("--paper"), faint: css("--faint"), accent: css("--accent"), cols: [0, 1, 2, "x"].map(i => css("--c" + i)) };
  const font = css("--sans");
  return { ...t, font, tip: { backgroundColor: t.paper, titleColor: t.ink, bodyColor: t.ink, footerColor: t.quiet, borderColor: t.quiet, borderWidth: 1, displayColors: false, padding: 10, cornerRadius: 6, caretSize: 5, titleFont: { family: font, weight: "600" }, bodyFont: { family: font }, footerFont: { family: font, weight: "400" } } };
}
// Hidden text for screen readers and keyboard users: one table per chart (group, count, medians, means), and a line announced as a dot is chosen.
function textAlt(caption, head, rows) {
  return h("div", { class: "sr" }, h("table", {}, h("caption", { text: caption }), h("thead", {}, h("tr", {}, head.map(t => h("th", { scope: "col", text: t })))), h("tbody", {}, rows.map(r => h("tr", {}, r.map(c => h("td", { text: String(c) })))))));
}
// Arrow keys step through the visible dots (left to right, or row by row), Enter opens the question. Dots carry a sort key `o`.
function keyboard(canvas, chart, say, open) {
  let at = -1;
  const list = () => { const out = []; chart().data.datasets.forEach((d, di) => { if (d.dots && chart().isDatasetVisible(di)) d.data.forEach((p, i) => out.push({ datasetIndex: di, index: i, p })); }); return out.sort((a, b) => a.p.o - b.p.o); };
  const pick = l => {
    const ch = chart(), el = ch.getDatasetMeta(l.datasetIndex).data[l.index], act = [{ datasetIndex: l.datasetIndex, index: l.index }];
    ch.setActiveElements(act); ch.tooltip.setActiveElements(act, { x: el.x, y: el.y }); ch.update("none"); say(l.p);
  };
  canvas.addEventListener("keydown", e => {
    const l = list(); if (!l.length) return;
    const to = { ArrowRight: at + 1, ArrowDown: at + 1, ArrowLeft: at - 1, ArrowUp: at - 1, Home: 0, End: l.length - 1 }[e.key];
    if (to != null) { e.preventDefault(); at = Math.max(0, Math.min(l.length - 1, to)); pick(l[at]); }
    else if ((e.key === "Enter" || e.key === " ") && l[at]) { e.preventDefault(); open(l[at].p.q.id); }
    else if (e.key === "Escape") { at = -1; chart().setActiveElements([]); chart().tooltip.setActiveElements([], {}); chart().update("none"); }
  });
  canvas.addEventListener("blur", () => { at = -1; if (chart()) { chart().setActiveElements([]); chart().tooltip.setActiveElements([], {}); chart().update("none"); } });
}
// A click on a dot: with a mouse it opens at once; on a touch screen the first tap only shows the tooltip.
const tapGate = open => { let armed = null; return id => { if (coarse.matches && armed !== id) { armed = id; return; } armed = null; open(id); }; };
const dotLines = (q, lines, who) => [...(who ? [who] : []), ...wrapText(shorten(q.reps[0].question)), "", ...lines.map(([v, m]) => `${f2(v)}  ${m}`), ...(q.cause ? [`${q.cause}  cause`] : [])];
const hint = () => coarse.matches ? "Tap again to open the question" : "Click to open the question";
const ticks01 = ax => { ax.ticks = [0, 0.25, 0.5, 0.75, 1].map(value => ({ value })); };
const tickText = v => String(v);   // Chart.js would round 0.25 to 0.3

function scatterFigure(qs, open) {
  const st = { per: "question", by: "difficulty", off: new Set() }, fN = name("faithfulness"), cN = name("correctness");
  const canvas = h("canvas", { tabindex: "0", role: "img" }), wrap = h("div", { class: "plot square" }, canvas), legend = h("div", { class: "legend" }), note = h("p", { class: "caption" }),
    live = h("p", { class: "sr", "aria-live": "polite" }), alt = h("div"), gate = tapGate(open);
  let chart = null;
  const draw = () => {
    const T = theme(), g = grouping(qs, st.by), q1 = st.per === "question";
    const items = q1 ? qs.map(q => ({ q, f: q.means.faithfulness, c: q.means.correctness, key: q.id, who: "" })) :
      qs.flatMap(q => q.reps.map(r => ({ q, f: r.scores.faithfulness, c: r.scores.correctness, key: q.id + "#" + r.repeat, who: `Attempt ${r.repeat} of ${q.reps.length}` })));
    const kept = items.filter(i => i.f != null && i.c != null), left = items.length - kept.length, unit = q1 ? "questions" : "attempts";
    note.textContent = (left ? `${left} of ${items.length} ${unit} are left out: they have no ${fN} score (an unanswerable question has none, or it could not be judged). ` : "") +
      "Dots are nudged a little apart so they do not hide each other; the scores in the tooltip are exact.";
    const sets = g.entries.map(e => {
      const pts = kept.filter(i => g.of(i.q) === e).map(i => ({ x: nudge(i.f, i.key, "x"), y: nudge(i.c, i.key, "y"), o: i.f * 1000 + i.c, q: i.q, f: i.f, c: i.c, who: i.who }));
      const hollow = e.shape === 4, col = T.cols[e.c];
      return { label: e.label, e, data: pts, dots: true, pointStyle: POINT[e.shape], backgroundColor: hollow ? T.paper : col, borderColor: hollow ? col : T.paper, borderWidth: hollow ? 2 : 1.5, pointRadius: 5.5, pointHoverRadius: 8, pointHitRadius: 12, hidden: st.off.has(e.key) };
    });
    const shown = sets.filter(s => !s.hidden).flatMap(s => s.data), cnt = { tr: 0, br: 0, tl: 0, bl: 0 };
    for (const p of shown) cnt[p.f >= 0.5 ? (p.c >= 0.5 ? "tr" : "br") : (p.c >= 0.5 ? "tl" : "bl")]++;
    const quad = { id: "quad", beforeDatasetsDraw(ch) {   // the two guide lines at 0.5 and a corner label (with its count) in each quadrant
      const { ctx, chartArea: a, scales: { x, y } } = ch, mx = x.getPixelForValue(0.5), my = y.getPixelForValue(0.5);
      ctx.save(); ctx.strokeStyle = T.quiet; ctx.globalAlpha = 0.5; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(mx, a.top); ctx.lineTo(mx, a.bottom); ctx.moveTo(a.left, my); ctx.lineTo(a.right, my); ctx.stroke(); ctx.globalAlpha = 1;
      ctx.font = `12px ${T.font}`; ctx.fillStyle = T.quiet; ctx.strokeStyle = T.paper; ctx.lineWidth = 3; ctx.lineJoin = "round";
      for (const [k, px, py, al] of [["tl", a.left + 8, a.top + 16, "left"], ["tr", a.right - 8, a.top + 16, "right"], ["bl", a.left + 8, a.bottom - 8, "left"], ["br", a.right - 8, a.bottom - 8, "right"]]) {
        ctx.textAlign = al; ctx.strokeText(`${quadWords[k]} · ${cnt[k]}`, px, py); ctx.fillText(`${quadWords[k]} · ${cnt[k]}`, px, py);
      }
      ctx.restore();
    } };
    const axis = (text, pad = 0.06) => ({ min: -pad, max: 1 + pad, afterBuildTicks: ticks01, title: { display: true, text, color: T.quiet, font: { family: T.font } }, grid: { color: T.rule }, border: { color: T.rule }, ticks: { color: T.quiet, font: { family: T.font }, callback: tickText } });
    chart && chart.destroy();
    chart = new Chart(canvas, { type: "scatter", data: { datasets: sets }, plugins: [quad], options: { animation: false, responsive: true, maintainAspectRatio: false, interaction: { mode: "nearest", intersect: true },
      scales: { x: axis(fN), y: axis(cN, 0.1) }, onClick: (_, els) => { if (els.length) gate(sets[els[0].datasetIndex].data[els[0].index].q.id); },
      plugins: { legend: { display: false }, tooltip: { ...T.tip, callbacks: { title: c => c[0].raw.q.id, label: c => dotLines(c.raw.q, [[c.raw.f, fN], [c.raw.c, cN]], c.raw.who), footer: hint } } } } });
    canvas.setAttribute("aria-label", `${fN} against ${cN}, one dot per ${q1 ? "question" : "attempt"}, ${shown.length} dots. Arrow keys move between dots, Enter opens the question.`);
    legend.replaceChildren(...g.entries.map((e, i) => {
      const b = h("button", { type: "button", class: "key", "aria-pressed": st.off.has(e.key) ? "false" : "true" }, swatch(e, st.off.has(e.key)), `${e.label} (${sets[i].data.length})`);
      b.addEventListener("click", () => { st.off.has(e.key) ? st.off.delete(e.key) : st.off.add(e.key); draw(); });
      return b;
    }));
    const med = (a, k) => a.length ? f2(quantile(a.map(p => p[k]).sort((x, y) => x - y), 0.5)) : "–", avg = (a, k) => a.length ? f2(a.reduce((s, p) => s + p[k], 0) / a.length) : "–";
    alt.replaceChildren(textAlt(`${fN} against ${cN} by ${GROUPERS[st.by][0].toLowerCase()}. Quadrants: ${Object.entries(quadWords).map(([k, w]) => `${w} ${cnt[k]}`).join(", ")}.`,
      [GROUPERS[st.by][0], unit, `Median ${fN}`, `Mean ${fN}`, `Median ${cN}`, `Mean ${cN}`], sets.map(s => [s.label, s.data.length, med(s.data, "f"), avg(s.data, "f"), med(s.data, "c"), avg(s.data, "c")])));
  };
  keyboard(canvas, () => chart, p => { live.textContent = `${p.q.id}. ${shorten(p.q.reps[0].question)}. ${fN} ${f2(p.f)}, ${cN} ${f2(p.c)}.`; }, open);
  const toggle = h("div", { class: "tabs" }, [["question", "per question"], ["attempt", "per attempt"]].map(([v, t]) => {
    const b = h("button", { type: "button", class: v === st.per ? "on" : "", "aria-pressed": v === st.per ? "true" : "false", text: t });
    b.addEventListener("click", () => { st.per = v; toggle.querySelectorAll("button").forEach(x => { x.className = x === b ? "on" : ""; x.setAttribute("aria-pressed", x === b ? "true" : "false"); }); draw(); });
    return b;
  }));
  const by = h("select", { "aria-label": "Colour by" }, ["difficulty", "origin", "topic", "cause"].map(k => h("option", { value: k, text: "Colour by " + GROUPERS[k][0].toLowerCase() })));
  by.addEventListener("change", () => { st.by = by.value; st.off.clear(); draw(); });
  const fig = h("figure", {}, h("h3", { text: `${fN} against ${cN}` }), h("div", { class: "bar" }, toggle, by), wrap, legend, note, live, alt);
  return { el: fig, draw: () => { try { draw(); } catch (e) { fig.append(h("p", { class: "no", text: "This chart could not be drawn." })); throw e; } } };
}

// Hover for the box plots: a dot if the pointer is on one, otherwise the box summary for the group's whole column. Boxes are thin,
// dots cover them and a group where every question scored the same has a box of no width, so hitting the box itself is too fiddly.
if (window.Chart && !Chart.Interaction.modes.boxRow) Chart.Interaction.modes.boxRow = (chart, e, opts, useFinal) => {
  const dots = Chart.Interaction.modes.nearest(chart, e, { intersect: true }, useFinal).filter(x => x.datasetIndex === 1);
  if (dots.length) return dots;
  const a = chart.chartArea, row = Math.round(chart.scales.x.getValueForPixel(e.x)), el = chart.getDatasetMeta(0).data[row];
  const box = chart.data.datasets[0].data[row];   // a group's statistics, or [] when it is too small for a box
  return e.y >= a.top && e.y <= a.bottom && el && box && !Array.isArray(box) ? [{ element: el, datasetIndex: 0, index: row }] : [];
};
function boxFigure(qs, open) {
  const scores = ["correctness", "faithfulness", "relevancy", "hit", "mrr"].filter(m => qs.some(q => q.means[m] != null));
  const st = { score: scores[0], by: "difficulty" };
  const canvas = h("canvas", { tabindex: "0", role: "img" }), wrap = h("div", { class: "plot" }, canvas), note = h("p", { class: "caption" }), live = h("p", { class: "sr", "aria-live": "polite" }), alt = h("div"), gate = tapGate(open);
  let chart = null;
  const draw = () => {
    const T = theme(), [gName, get, order] = GROUPERS[st.by], sN = name(st.score), byKey = new Map();
    for (const q of qs) if (q.means[st.score] != null) { const k = get(q); if (!byKey.has(k)) byKey.set(k, []); byKey.get(k).push(q); }
    const rows = [...byKey].map(([key, items]) => ({ key, items, s: boxStats(items.map(q => q.means[st.score])) }));
    const rank = k => order && order.includes(k) ? order.indexOf(k) : 99;
    rows.sort(order ? (a, b) => rank(a.key) - rank(b.key) : (a, b) => a.s.mean - b.s.mean || a.key.localeCompare(b.key));   // weakest group first, easy to hard for difficulty
    const many = rows.length > (innerWidth < 700 ? 4 : 12);   // with many groups only the name fits under each box, slanted; n and mean move to the hover
    const label = r => many ? shorten(NEUTRAL[r.key] || r.key, 12) : [shorten(NEUTRAL[r.key] || r.key, 12), `n = ${r.s.n}`, `mean ${f2(r.s.mean)}`];
    const dots = rows.flatMap((r, i) => r.items.map(q => ({ x: i + jitter(q.id, "x") * 0.5, y: q.means[st.score], o: i * 10 + q.means[st.score], q, s: q.means[st.score] })));
    note.textContent = `Weakest group on the left${order ? " (easy to hard)" : ""}. Tukey box plot: box = interquartile range (IQR, Q1 to Q3, the middle half of questions); line = median; ring = mean; whiskers = the furthest question within 1.5 × IQR of the box; dots beyond them are outliers. A box needs n ≥ 4; with fewer, only the dots show.`;
    // the boxes are given our own numbers (below), so the box, the whiskers and the tooltip cannot disagree: the plugin's own whisker rule has a 0.01 tolerance
    chart && chart.destroy();
    chart = new Chart(canvas, { type: "boxplot", data: { labels: rows.map((_, i) => i), datasets: [
      { label: "boxes", data: rows.map(r => r.s.n >= 4 ? { min: r.s.min, q1: r.s.q1, median: r.s.median, q3: r.s.q3, max: r.s.max, mean: r.s.mean, whiskerMin: r.s.lo, whiskerMax: r.s.hi, items: [], outliers: [] } : []), itemRadius: 0, outlierRadius: 0, backgroundColor: T.accent + "26", borderColor: T.ink, borderWidth: 1.5, medianColor: T.ink,
        meanRadius: 4, meanBackgroundColor: T.paper, meanBorderColor: T.ink, meanBorderWidth: 1.5, maxBarThickness: 56, coef: 1.5 },
      { type: "scatter", label: "questions", data: dots, dots: true, parsing: false, backgroundColor: T.accent + "cc", borderColor: T.paper, borderWidth: 1.5, pointRadius: 4.5, pointHoverRadius: 7, pointHitRadius: 10 }] },
    options: { animation: false, responsive: true, maintainAspectRatio: false, interaction: { mode: "boxRow", intersect: true },
      scales: { y: { min: -0.04, max: 1.04, afterBuildTicks: ticks01, title: { display: true, text: sN, color: T.quiet, font: { family: T.font } }, grid: { color: T.rule }, border: { color: T.rule }, ticks: { color: T.quiet, font: { family: T.font }, callback: tickText } },
        x: { type: "linear", min: -0.5, max: rows.length - 0.5, afterBuildTicks: ax => { ax.ticks = rows.map((_, value) => ({ value })); }, grid: { display: false }, border: { color: T.rule }, ticks: { color: T.ink, font: { family: T.font, size: 12 }, padding: 6, minRotation: many ? 40 : 0, maxRotation: many ? 40 : 0, autoSkip: false, callback: v => rows[v] ? label(rows[v]) : "" } } },
      onClick: (_, els) => { const e = els.find(x => x.datasetIndex === 1); if (e) gate(dots[e.index].q.id); },
      plugins: { legend: { display: false }, tooltip: { ...T.tip, callbacks: {
        title: c => c[0].datasetIndex === 1 ? c[0].raw.q.id : NEUTRAL[rows[c[0].dataIndex].key] || rows[c[0].dataIndex].key,
        label: c => { if (c.datasetIndex === 1) return dotLines(c.raw.q, [[c.raw.s, sN]]); const r = rows[c.dataIndex], s = r.s, out = r.items.filter(q => q.means[st.score] < s.lo || q.means[st.score] > s.hi).map(q => q.id);
          return [`n = ${s.n}`, `Median ${f2(s.median)}`, `Mean ${f2(s.mean)}`, `IQR ${f2(s.q1)} to ${f2(s.q3)} (Q1 to Q3)`, `Whiskers ${f2(s.lo)} to ${f2(s.hi)} (1.5 × IQR)`,
            out.length ? `Outliers ${out.length}: ${shorten(out.join(", "), 40)}` : "Outliers 0"]; },
        footer: c => c[0].datasetIndex === 1 ? hint() : "" } } } } });
    canvas.setAttribute("aria-label", `${sN} by ${gName.toLowerCase()}, ${rows.length} groups, ${dots.length} questions. Arrow keys move between dots, Enter opens the question.`);
    alt.replaceChildren(textAlt(`${sN} by ${gName.toLowerCase()}.`, [gName, "Questions", "Median", "Mean", "Middle half"], rows.map(r => [NEUTRAL[r.key] || r.key, r.s.n, f2(r.s.median), f2(r.s.mean), `${f2(r.s.q1)} to ${f2(r.s.q3)}`])));
  };
  keyboard(canvas, () => chart, p => { live.textContent = `${p.q.id}. ${shorten(p.q.reps[0].question)}. ${name(st.score)} ${f2(p.s)}.`; }, open);
  const pick = (label, opts, key) => { const s = h("select", { "aria-label": label }, opts.map(([v, t]) => h("option", { value: v, text: t }))); s.addEventListener("change", () => { st[key] = s.value; draw(); }); return s; };
  const fig = h("figure", {}, h("h3", { text: "Scores by group" }), h("div", { class: "bar" }, pick("Score", scores.map(m => [m, name(m)]), "score"), pick("Group by", ["difficulty", "origin", "topic", "cause"].map(k => [k, "by " + GROUPERS[k][0].toLowerCase()]), "by")), wrap, note, live, alt);
  return { el: fig, draw };
}

// The section for a suite page: the latest run's questions, both charts, and one redraw when light/dark changes.
function chartsSection(qs, open) {
  const tagN = new Map();
  for (const q of qs) for (const t of q.tags) tagN.set(t, (tagN.get(t) || 0) + 1);
  // shortcut: datasets have no "origin" field, so it is read from the tags: the commonest tag after the first (the first is the topic); a lone tag is its own origin. Add a real field if datasets start to use one.
  for (const q of qs) q.origin = q.tags.length > 1 ? q.tags.slice(1).sort((a, b) => tagN.get(b) - tagN.get(a) || a.localeCompare(b))[0] : q.tags[0] || "untagged";
  const figs = [scatterFigure(qs, open), boxFigure(qs, open)];
  const all = () => figs.forEach(f => f.draw());
  requestAnimationFrame(all);   // after the figures are in the page, so the canvases have a width
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", all);
  return h("div", { class: "charts" }, figs.map(f => f.el));
}

// ---- suite ---------------------------------------------------------------------------------------
// Three levels: the answer (title, one sentence, three big numbers), then what explains it (scores by group, charts, failures), then details folded away.
const GROUPS = [["Answers", ["correctness", "faithfulness", "relevancy", "abstention"]], ["Finding sources", ["hit", "recall", "mrr", "context_recall"]], ["Reliability", ["error_rate"]]];
const more = (summary, ...kids) => h("details", { class: "more" }, h("summary", { text: summary }), kids);

function suite() {
  const runs = D.runs, latest = D.latest, c = D.compare, S = D.suite, byId = Object.fromEntries(runs.map(r => [r.run, r]));
  const lr = byId[latest.run], ref = c && byId[c.a], refWord = ref && ref.baseline ? "baseline" : "previous run";
  const cm = latest.metrics, mean = m => cm[m] && cm[m].mean, pm = c && !c.warning ? c.metrics : {};
  const change = m => { const p = pm[m]; return !p || p.delta == null ? null : h("span", {}, sgn(p.delta), " ", verdict(p.verdict)); };
  add(crumbs([null, suiteName(S)]), h("h1", { text: suiteName(S) }));

  // 1. the answer
  const cor = cm.correctness, pc = pm.correctness, er = mean("error_rate");
  const sentence = [];
  if (cor && cor.mean != null) {
    const how = !pc || pc.delta == null ? "." : pc.verdict === "real gain" || pc.verdict === "real drop" ? `, ${pc.verdict === "real gain" ? "a real gain" : "a real drop"} of ${sgn(pc.delta)} on the ${refWord}.` :
      pc.verdict === "within noise" ? `, no real change (${sgn(pc.delta)} on the ${refWord}).` : `; too few questions to tell if it changed since the ${refWord}.`;
    sentence.push(`${name("correctness")} (${G.correctness.plain}) is ${f2(cor.mean)}${cor.ci ? ` (95% CI ${f2(Math.max(0, cor.ci[0]))}–${f2(Math.min(1, cor.ci[1]))})` : ""}${how}`);
  }
  if (er != null && er > WARN_ERR) sentence.push(`${name("error_rate")} is high: ${failedWords(er)}.`);
  if (sentence.length) add(h("p", { class: "summary", text: sentence.join(" ") }));
  add(h("div", { class: "hero-row" }, ["correctness", "faithfulness", "error_rate"].filter(m => mean(m) != null).map(m => h("div", { class: "hero-item" }, h("span", { class: "hi-name" }, term(m)), plainLine(m),
    h("b", { class: "num " + warnClass(m, mean(m)), text: f2(mean(m)) }), h("span", { class: "hi-ci " + warnClass(m, mean(m)), text: m === "error_rate" && mean(m) > WARN_ERR ? failedWords(mean(m)) : spread(cm[m]) }), h("span", { class: "hi-change" }, change(m) || (c && c.warning ? "not compared" : null))))));
  add(h("p", { class: "small dateline" }, `Latest run ${when(latest.run)}. ${runLabel(latest)}${lr.label ? `, “${lr.label}”` : ""}${lr.baseline ? ", the baseline" : ""}. ${plural(runs.length, "run")} so far. Questions: ${latest.dataset.name} v${ver(latest.dataset.version)}. ${latest.counts_line}${latest.attempts > latest.questions ? ` (${latest.questions} questions, each asked ${latest.repeats} times)` : ""}. `,
    latest.aborted ? note(`Stopped early: ${latest.aborted}. ${plain("aborted")}`) : null, latest.incomplete ? note(`Incomplete: ${(latest.judge_error_rate * 100).toFixed(0)}% of answers could not be judged. ${plain("incomplete")}`) : null,
    h("a", { href: `runs/${latest.run}.html`, text: "Every question of this run" }), D.compare_href ? [". ", h("a", { href: D.compare_href, text: "Questions that changed" })] : null, ". ", h("a", { href: "runs.csv", download: "", text: "Download all runs (CSV)" }), "."));

  // 1b. every run on a timeline, one chart per score (the question-by-question charts are on each run's page)
  const profiles = [...new Set(runs.map(r => r.profile || ""))];
  let pick, profile = profiles.includes("deep") ? "deep" : profiles.includes("smoke") ? "smoke" : profiles[0];
  const tabs = h("div", { class: "tabs", role: "group", "aria-label": "Profile" }), box = h("div", { class: "figures" });
  const drawCharts = () => {
    charts.forEach(u => u.destroy()); charts = [];
    box.replaceChildren();
    const rs = runs.filter(r => (r.profile || "") === profile);
    tabs.replaceChildren(h("span", { class: "small", text: "Profile: " }), ...profiles.map(p => { const b = h("button", { type: "button", class: p === profile ? "on" : "", "aria-pressed": p === profile ? "true" : "false", text: p || "no profile" }); b.addEventListener("click", () => { profile = p; drawCharts(); }); return b; }));
    const ms = ["correctness", ...SCORES.filter(k => k !== "correctness")].filter(k => rs.some(r => r.metrics[k] && r.metrics[k].mean != null));
    if (!ms.includes(pick)) pick = ms[0];
    if (phone.matches) box.append(h("div", { class: "tabs chips", role: "group", "aria-label": "Score" }, ms.map(m => { const b = h("button", { type: "button", class: m === pick ? "on" : "", "aria-pressed": m === pick ? "true" : "false", text: name(m) }); b.addEventListener("click", () => { pick = m; drawCharts(); }); return b; })));
    (phone.matches ? [pick] : ms).forEach((m, i) => {   // a phone gets one chart and a picker; a wide screen gets the main chart large, then the rest small
      const host = h("figure", { class: !phone.matches && m === "correctness" ? "lead" : "" });
      if (!phone.matches && i === 1) box.append(h("h3", { class: "span", text: "Other scores" }));
      box.append(host);
      drawChart(host, m, rs.map(r => ({ ...r, metrics: { ...r.metrics, [m]: r.metrics[m] || { mean: null, ci: null } } })), r => `runs/${r.run}.html`, !phone.matches && m === "correctness");
    });
  };
  add(h("h2", { text: "Over time" }), h("p", { class: "intro", text: "Drag across a chart to zoom; double-click resets." }), tabs, box);
  drawCharts();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawCharts);
  phone.addEventListener("change", drawCharts);
  // 1c. every run, newest first, sortable; each row opens the run page
  add(h("h2", { id: "runs", text: "Runs" }), sortable([
    { t: "Run", left: true, desc: true, get: r => r.run, show: r => [h("a", { href: `runs/${r.run}.html`, text: when(r.run) }), r.label ? ` “${r.label}”` : "", r.baseline ? h("small", { class: "sub", text: "baseline" }) : null,
      r.aborted ? note(`${when(r.run)}: stopped early, ${r.aborted}.`) : null, r.incomplete ? note(`${when(r.run)}: incomplete, too many answers could not be judged.`) : null] },
    { t: "Profile", left: true, get: r => r.profile || "", show: r => `${r.profile || "no profile"}, ${r.judge_mode || "quick"}${r.repeats > 1 ? ", ×" + r.repeats : ""}` },
    { t: "Questions", get: r => r.questions, show: r => r.questions == null ? "–" : r.questions },
    metricCol("correctness", r => r.metrics, K, true), metricCol("faithfulness", r => r.metrics, K, true), metricCol("error_rate", r => r.metrics, K)], runs, 0, -1));

  // 2. what explains it: scores by group, then failures
  const vsHead = h("span", {}, `vs ${refWord}${c ? `, ${day(c.a)}` : ""}`, c && c.warning ? note(c.warning) : null, c ? c.notes.map(note) : null, " ", qmark("paired"));
  if (c && (c.errors.newly.length || c.errors.recovered.length)) vsHead.append(note((c.errors.newly.length ? `Newly failing: ${c.errors.newly.join(", ")}. ` : "") + (c.errors.recovered.length ? `Recovered: ${c.errors.recovered.join(", ")}.` : "")));
  const vs = m => {
    const p = pm[m];
    if (!p || p.delta == null) return h("span", { class: "flat", text: c && c.warning ? "not compared" : "–" });
    return h("span", {}, sgn(p.delta), " ", verdict(p.verdict), p.ci ? h("small", { class: "ci", text: ` (${sgn(p.ci[0])} to ${sgn(p.ci[1])})` }) : null);
  };
  const rows = [];
  for (const [group, keys] of GROUPS) {
    const have = keys.filter(m => mean(m) != null);
    if (!have.length) continue;
    rows.push({ group });
    for (const m of have) {
      const s = cm[m], a = latest.metrics_answered && latest.metrics_answered[m];
      rows.push([[term(m), plainLine(m)], [h("span", { class: warnClass(m, s.mean), text: f2(s.mean) }), a && a.mean != null && latest.counts.system_errors && Math.abs(a.mean - s.mean) >= 0.005 ? note(`${name(m)}: counting only answers the system gave, the score is ${f2(a.mean)}.`) : null],
        h("span", { class: "ci" }, lbl("95% CI "), spread(s) || "–"), h("span", {}, lbl(`vs ${refWord} `), vs(m))]);
    }
  }
  add(h("h2", { text: "Scores" }), caption("A system error counts as 0."), table("narrow scores", ["Measure", "Score", ["95% CI ", qmark("ci")], vsHead], rows));
  const tail = [];
  const pw = latest.power && (latest.power.correctness || Object.values(latest.power).find(Boolean));
  if (latest.power && !pw && Object.keys(latest.power).length) tail.push("Cannot estimate how many questions are needed: the scores have no spread.");
  if (pw) tail.push(`To see a ${c ? c.detect : 0.05} change in a score with 80% chance, about ${plural(pw.needed, "question")} are needed (${pw.basis === "repeats" ? "from how much one question wobbles between repeats" : "a rule of thumb, from the spread of the scores"}).`);
  if (c && !c.warning) tail.push(`A real change needs ${c.min_pairs} or more shared questions; this comparison has ${c.shared}.`);
  if (tail.length) add(h("p", { class: "small", text: tail.join(" ") }));


  const cs = latest.causes;
  if (cs && cs.questions.length) add(h("h2", { text: "Why questions failed" }), h("p", { class: "intro", text: Object.entries(cs.counts).filter(e => e[1]).map(e => `${e[0]}: ${e[1]}`).join(", ") + ". Retrieval: the right page was not found. Generation: found, answered wrong. Judge?: the marking looks odd. System: it errored." }),
    h("ul", { class: "plain" }, cs.questions.map(q => h("li", {}, h("b", { text: q.id }), " ", h("em", { text: q.cause }), ". ", h("span", { class: "muted", text: q.why })))));
  const k = latest.consistency;
  if (k) add(h("h2", { text: "Same answer every time?" }), h("p", {}, h("b", { text: (k.pass_all * 100).toFixed(0) + "%" }), ` of ${k.questions} questions were answered well on every repeat${k.left_out ? ` (${k.left_out} left out: a repeat was not scored)` : ""}. `, h("span", { class: "muted", text: G.pass_all.formula })),
    k.flaky.length ? h("ul", { class: "plain" }, k.flaky.map(x => h("li", {}, h("b", { text: x.id }), ` ${name("correctness")} between ${Math.min(...x.scores).toFixed(2)} and ${Math.max(...x.scores).toFixed(2)} (${x.scores.join(", ")})`))) : h("p", { class: "muted", text: "No flaky questions." }));
  if (latest.failures.length) add(h("h2", { text: "Problems in the latest run" }), h("ul", { class: "plain" }, latest.failures.map(x => h("li", {}, h("b", { text: x.id }), " ", h("span", { class: "muted", text: x.error })))));

  // 3. details, folded away
  const jc = D.judge_check;
  if (jc) add(h("h2", { text: "Judge reliability" }), markerCheck(jc, D.judge_checked_since));
  add(h("h2", { class: "quiet", text: "Details" }),
    more("By topic and difficulty", groupTable(latest.tags, "Topic"), h("div", { class: "gap" }), groupTable(latest.difficulty || {}, "Difficulty")),
    D.mislabels.length ? more(`${plural(D.mislabels.length, "question")} may be mislabelled`, h("ul", { class: "plain" }, D.mislabels.map(x => h("li", {}, h("b", { text: x.id }), ` labelled ${x.label}, but answered well ${x.passed} of ${x.attempts} times`)))) : null,
    h("p", { class: "small", text: `System: ${S.target_label || S.target}, model ${lr.answering_model}. Judge: ${lr.judge_model}.` }),
    jc ? null : h("p", { class: "small", text: "No judge check yet for this marker and mode. Run: nasute judge-check" }));
  finish();
}

// ---- one run -------------------------------------------------------------------------------------
const DIFF = { easy: 0, medium: 1, hard: 2 };

function claimsBlock(d) {
  if (!d) return null;
  const item = (text, marks, why) => h("li", {}, marks, text, why ? h("span", { class: "muted", text: ` — ${why}` }) : null);
  const none = h("li", { class: "muted", text: "The answer states no facts." });
  if (d.claims) {   // quick mode
    return [h("h4", { text: "Claims in the answer" }), h("ol", { class: "claims" }, d.claims.length ? d.claims.map(c => item(c.claim, [tick(c.supported === "yes", "backed by the extracts"), c.vs_reference === "agrees" ? tick(true, "agrees with the reference") : c.vs_reference === "contradicts" ? tick(false, "agrees with the reference") : h("span", { class: "muted", text: "–", title: "not in the reference" }), " "], c.why)) : [none]),
      h("p", { class: "small", text: "First mark: backed by the extracts. Second: agrees with the reference (– means the reference does not cover it)." })];
  }
  if (d.answer_claims) {   // claims mode
    const v = (list, i) => list[i] ? tick(list[i].supported, "") : h("span", { class: "muted", text: "–" });
    return [h("h4", { text: "Claims in the answer" }), h("ol", { class: "claims" }, d.answer_claims.length ? d.answer_claims.map((c, i) => item(c, [v(d.answer_vs_extracts, i), v(d.answer_vs_reference, i), " "], (d.answer_vs_reference[i] || {}).why)) : [none]),
      h("p", { class: "small", text: "First mark: backed by the extracts. Second: matches the reference." }),
      h("h4", { text: "Facts in the reference" }), h("ol", { class: "claims" }, d.reference_claims.map((c, i) => item(c, [v(d.reference_vs_extracts, i), v(d.reference_vs_answer, i), " "], (d.reference_vs_answer[i] || {}).why))),
      h("p", { class: "small", text: "First mark: backed by the extracts. Second: the answer says it." })];
  }
  if (d.verdict) return [h("h4", { text: "Judge" }), h("p", { text: `${d.verdict === "declined" ? "Declined" : "Made something up"}: ${d.why}` })];
  return null;
}

// Source titles, each a link (new tab) when its address is safe; "; " between them.
function sourceList(titles, links) {
  return titles.map((t, i) => [i ? "; " : "", safeUrl((links || [])[i]) ? h("a", { href: links[i], target: "_blank", rel: "noopener noreferrer", text: t }) : t]);
}

function repeatBlock(r, many) {
  const metrics = SCORES.filter(m => r.scores[m] != null);
  return h("div", { class: "rep" },
    many ? h("h4", { class: "repeat", text: `Repeat ${r.repeat}` }) : null,
    r.error ? h("p", { class: "no", text: "System error: " + r.error }) : null, r.judge_error ? h("p", { class: "no", text: "Judge error: " + r.judge_error }) : null,
    h("h4", { text: "Answer" }), quote(r.answer || "(none)"),
    r.sources.length ? h("p", { class: "small" }, "Sources it found: ", sourceList(r.sources, r.links), ".") : null,
    r.extracts.length ? h("details", {}, h("summary", { text: `Extracts it read (${r.extracts.length})` }), r.extracts.map(x => h("pre", { text: x }))) : null,
    h("h4", { text: "Scores, and how each was counted" }), h("ul", { class: "plain" }, metrics.map(m => h("li", {}, h("b", { text: `${name(m)} ${f2(r.scores[m])}` }), h("span", { class: "muted", text: r.reasons[m] ? ` — ${r.reasons[m]}` : "" })))),
    claimsBlock(r.judge_detail),
    h("p", { class: "small", text: `Answer took ${r.total_s ?? "–"} s${r.first_text_s != null ? ` (first text after ${r.first_text_s} s)` : ""}${r.judge_s != null ? `, judging ${r.judge_s} s` : ""}.${useLine(r.tokens_in, r.tokens_out, r.cost, r.judge_tokens, r.judge_cost) ? " " + useLine(r.tokens_in, r.tokens_out, r.cost, r.judge_tokens, r.judge_cost) + "." : ""}` }));
}

// Tokens and cost, where the system or the judge reported them (Nasute records them; it never needs them).
const money = c => c == null ? null : c < 0.01 ? `US$${c.toFixed(4)}` : `US$${c.toFixed(2)}`;
function useLine(tin, tout, cost, jtok, jcost) {
  const parts = [];
  if (tin != null || tout != null) parts.push(`${tin ?? "?"} tokens in, ${tout ?? "?"} out`);
  if (cost != null) parts.push(money(cost));
  if (jtok != null || jcost != null) parts.push(`judging ${jtok ?? "?"} tokens${jcost != null ? `, ${money(jcost)}` : ""}`);
  return parts.join("; ");
}

// One entry per question from its rows (one row per repeat). `n` is its place in the results file, which is the dataset's order (shortcut: results are written in dataset order; the id stays the real key, runs are paired by it): its tags, difficulty and the mean of each score over the repeats.
function questions(rows, cause, worse = new Set()) {
  const by = new Map();
  for (const r of rows) { if (!by.has(r.id)) by.set(r.id, []); by.get(r.id).push(r); }
  return [...by].map(([id, reps], i) => {
    const means = {};
    for (const m of SCORES) { const v = reps.map(r => r.scores[m]).filter(x => x != null); means[m] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }
    return { id, n: i + 1, reps, tags: reps[0].tags, difficulty: reps[0].difficulty, means, cause: cause.get(id) || "", worse: worse.has(id) };
  });
}

function run() {
  const S = D.summary, P = S.pass_at, cause = new Map(S.causes.questions.map(q => [q.id, q.cause])), worse = new Set(D.worse);
  const qs = questions(D.rows, cause, worse);
  const cols = SCORES.filter(m => qs.some(q => q.means[m] != null));
  const open = id => { location.hash = "q-" + encodeURIComponent(id); };   // the question view is the same page, shown for #q-<id>
  const list = h("div"), detail = h("div", { hidden: true });
  add(list, detail);
  const put = (...x) => list.append(...x.flat(Infinity).filter(c => c != null && c !== false));   // like add(), into the table view
  put(crumbs(["../index.html", suiteName(D.suite)], [null, "Run"]), h("h1", { text: `Run ${when(S.run)}` }),
    h("p", { class: "dateline" }, `${runLabel(S)}${D.label ? `, “${D.label}”` : ""}${D.baseline ? ", the baseline" : ""}. Questions: ${S.dataset.name} v${ver(S.dataset.version)} (${S.dataset.sha256.slice(0, 8)}). ${S.counts_line}. `,
      S.aborted ? note(`Stopped early: ${S.aborted}. ${plain("aborted")}`) : null, S.incomplete ? note(`Incomplete: too many judge errors. ${plain("incomplete")}`) : null,
      D.compare_href ? [h("a", { href: "../" + D.compare_href, text: "What changed since the run before" }), ". "] : null),
    D.judge_check ? h("p", { class: "small", text: `Marker check (${D.judge_check.dataset.name} v${ver(D.judge_check.dataset.version)}, ${plural(D.judge_check.items, "item")}, ${when(D.judge_check.run.replace("judge-", ""))}): ` +
      SCORES.filter(m => D.judge_check.metrics[m]).map(m => `${name(m)} ${(D.judge_check.metrics[m].accuracy * 100).toFixed(0)}% accurate`).join(", ") + `.${D.judge_checked_since ? " This check is newer than the run." : ""}${D.judge_check.aborted ? " That check was stopped early." : ""}` }) : null,
    h("p", { class: "small" }, "Download: ", h("a", { href: `${S.run}.csv`, download: "", text: "CSV" }), " · ", h("a", { href: `${S.run}.results.jsonl`, download: "", text: "JSON lines" }), " · ", h("a", { href: `${S.run}.summary.json`, download: "", text: "summary" }), "."),
    h("p", { class: "small", text: `System: ${S.target}, model ${S.answering_model}. Marker: ${S.judge_model} (${S.judge_mode}). Code ${S.commit}. Took ${Math.round(S.total_s)} s. ${S.usage && useLine(S.usage.tokens_in, S.usage.tokens_out, S.usage.cost, S.usage.judge_tokens, S.usage.judge_cost) ? `Whole run: ${useLine(S.usage.tokens_in, S.usage.tokens_out, S.usage.cost, S.usage.judge_tokens, S.usage.judge_cost)}. ` : ""}${D.vs ? `“Worse” is measured against the run of ${when(D.vs)}.` : "“Worse” needs an earlier run to measure against."}` }));


  const state = { view: "all", cause: "", tag: "", text: "", sort: "n", dir: 1, page: 1 };
  const sels = {};
  const select = (label, key, options) => { const s = h("select", { "aria-label": label }, options.map(([v, t]) => h("option", { value: v, text: t }))); s.addEventListener("change", () => { state[key] = s.value; state.page = 1; render(); }); sels[key] = s; return s; };
  const search = h("input", { type: "search", placeholder: "Search id, question, answer", "aria-label": "Search" });
  search.addEventListener("input", () => { state.text = search.value.toLowerCase(); state.page = 1; render(); });
  const causes = [...new Set(qs.map(q => q.cause).filter(Boolean))], tags = [...new Set(qs.flatMap(q => q.tags))].sort();
  const count = h("span", { class: "small" }), tbody = h("tbody"), head = h("tr"), pagers = [h("div", { class: "pager" }), h("div", { class: "pager" })];
  const matches = q => (state.view === "all" || (state.view === "failed" ? q.cause : q.worse)) && (!state.cause || q.cause === state.cause) && (!state.tag || q.tags.includes(state.tag)) &&
    (!state.text || [q.id, ...q.tags, ...q.reps.flatMap(r => [r.question, r.answer])].some(t => t.toLowerCase().includes(state.text)));
  const heads = [["n", "#"], ["question", "Question"], ["tags", "Topics"], ["difficulty", "Difficulty"], ...cols.map(m => [m, name(m)]), ["cause", "Cause"]];
  const key = (q, k) => k === "n" ? q.n : k === "question" ? q.reps[0].question.toLowerCase() : k === "tags" ? q.tags.join(" ") : k === "difficulty" ? (DIFF[q.difficulty] ?? 3) : k === "cause" ? q.cause : q.means[k];
  // Every filter and the sort apply to all the questions; only then is the list cut into pages.
  const current = () => qs.filter(matches).sort((a, b) => { const x = key(a, state.sort), y = key(b, state.sort); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * state.dir || a.n - b.n; });
  put(h("h2", { text: "Question by question" }), h("p", { class: "intro", text: "Each dot is one question. Click one to open the question." }), chartsSection(qs, open),
    h("h2", { text: "Every question" }), caption("Mean over repeats. Click a heading to sort, a row to read the question and its answers."),
    h("div", { class: "bar" }, select("Show", "view", [["all", "All questions"], ["failed", "Failed"], ["worse", "Got worse"]]),
      select("Cause", "cause", [["", "Any cause"], ...causes.map(c => [c, c])]), select("Topic", "tag", [["", "Any topic"], ...tags.map(t => [t, t])]), search, count),
    pagers[0], h("div", { class: "scroll tall" }, h("table", { class: "q" }, h("thead", {}, head), tbody)), pagers[1]);
  heads.forEach(([k, t]) => {
    const b = h("button", { type: "button", class: "sort", text: t });
    b.addEventListener("click", () => { state.dir = state.sort === k ? -state.dir : 1; state.sort = k; state.page = 1; render(); });
    head.append(h("th", { "aria-sort": "none", "data-k": k, class: k === "question" || k === "tags" || k === "cause" ? "left" : "" }, b, G[k] ? qmark(k) : null));
  });
  function render() {
    head.querySelectorAll("th").forEach(th => th.setAttribute("aria-sort", th.dataset.k === state.sort ? (state.dir > 0 ? "ascending" : "descending") : "none"));
    const shown = current(), pr = pageRange(shown.length, state.page, PER_PAGE);
    state.page = pr.page;
    count.textContent = `Showing ${shown.length} of ${qs.length}`;
    for (const p of pagers) {
      const go = (to, text, off) => { const b = h("button", { type: "button", text, disabled: off }); b.addEventListener("click", () => { state.page = to; render(); }); return b; };
      p.replaceChildren(...(pr.pages > 1 ? [go(pr.page - 1, "← Previous", pr.page === 1), h("span", { class: "small", text: ` Page ${pr.page} of ${pr.pages}: questions ${pr.from + 1} to ${pr.to} ` }), go(pr.page + 1, "Next →", pr.page === pr.pages)] : []));
    }
    tbody.replaceChildren();
    for (const q of shown.slice(pr.from, pr.to)) {
      const tr = h("tr", { class: "item", "data-id": q.id }, h("td", { text: q.n }),
        h("td", { class: "left" }, h("a", { class: "qlink", href: "#q-" + encodeURIComponent(q.id), text: shorten(q.reps[0].question, 110) }), h("span", { class: "qid", text: q.id }), q.worse ? h("span", { class: "down flag", text: "worse" }) : null),
        h("td", { class: "left small", text: q.tags.join(", ") }), h("td", { class: "left", text: q.difficulty }),
        cols.map(m => h("td", { class: m === "correctness" && q.means[m] != null && q.means[m] < P ? "down" : "", text: f2(q.means[m]) })), h("td", { class: "left", text: q.cause }));
      tr.addEventListener("click", e => { if (!e.target.closest("a, .term")) open(q.id); });
      tbody.append(tr);
    }
  }

  // The question view: one question across the whole page, with Previous and Next in the order the table is showing.
  function question(q) {
    const ids = current().map(x => x.id), at = ids.indexOf(q.id), seq = at < 0 ? qs.map(x => x.id) : ids, i = seq.indexOf(q.id), r0 = q.reps[0];
    const go = (id, text) => id ? h("a", { href: "#q-" + encodeURIComponent(id), text }) : h("span", { class: "muted", text });
    const nav = () => h("p", { class: "qnav" }, go(seq[i - 1], "← Previous question"), " · ", go(seq[i + 1], "Next question →"), at < 0 ? h("span", { class: "muted", text: " (in dataset order: this question is hidden by the table's filters)" }) : null);
    detail.replaceChildren(crumbs(["../index.html", suiteName(D.suite)], ["#", `Run ${when(S.run)}`], [null, `Question ${q.n}`]),
      h("h1", { tabindex: "-1", text: `Question ${q.n}` }),
      h("p", { class: "small" }, h("span", { class: "qid inline", text: q.id }), ` ${q.difficulty}${q.tags.length ? ", " + q.tags.join(", ") : ""}${q.cause ? `. Cause of failure: ${q.cause}` : ""}.`), nav(),
      h("div", { class: "qview" }, h("h4", { text: "Question" }), quote(r0.question),
        h("h4", { text: "Reference answer" }), quote(r0.answerable === false ? "(none: the library holds no answer, so a good reply says so)" : r0.reference),
        r0.expected.length ? h("p", { class: "small" }, "Expected sources: ", sourceList(r0.expected, r0.expected.map(t => { for (const r of q.reps) { const k = r.sources.indexOf(t); if (k >= 0 && (r.links || [])[k]) return r.links[k]; } return null; })), ".") : null,
        q.reps.map(r => repeatBlock(r, q.reps.length > 1))), nav());
  }
  // The address decides the view. Leaving a question returns to the table on the page that holds it, where it was scrolled.
  let scrollAt = 0, lastId = null;
  function route() {
    let id = null;
    try { id = location.hash.startsWith("#q-") ? decodeURIComponent(location.hash.slice(3)) : null; } catch (e) { /* a broken link shows the table */ }
    const q = id && qs.find(x => x.id === id);
    if (q) {
      if (!list.hidden) scrollAt = scrollY;
      lastId = q.id; list.hidden = true; detail.hidden = false; question(q); scrollTo(0, 0); detail.querySelector("h1").focus({ preventScroll: true });
    } else {
      const back = !detail.hidden, was = state.page;
      detail.hidden = true; list.hidden = false;
      if (back && lastId) { const at = current().findIndex(x => x.id === lastId); if (at >= 0) state.page = Math.floor(at / PER_PAGE) + 1; }
      render();
      if (back) { const tr = [...tbody.children].find(r => r.dataset.id === lastId); state.page === was ? scrollTo(0, scrollAt) : tr && tr.scrollIntoView({ block: "center" }); }
    }
  }
  history.scrollRestoration = "manual";   // the page puts the scroll back itself (the table is only hidden while a question is open)
  addEventListener("hashchange", route);
  route();
  finish();
}

// ---- compare -------------------------------------------------------------------------------------
function compare() {
  const c = D.compare, L = D.labels;
  add(crumbs(["../index.html", suiteName(D.suite)], [null, "What changed"]), h("h1", { text: "What changed" }),
    h("p", { class: "dateline" }, `${when(c.a)}${L[c.a] ? ` “${L[c.a]}”` : ""} to ${when(c.b)}${L[c.b] ? ` “${L[c.b]}”` : ""}. ${plural(c.shared, "question")} answered in both. `, c.warning ? note(c.warning) : null, c.notes.map(note),
      c.errors.newly.length ? note(`Newly failing: ${c.errors.newly.join(", ")}.`) : null, c.errors.recovered.length ? note(`Recovered: ${c.errors.recovered.join(", ")}.`) : null));
  if (!c.warning) {
    const rows = SCORES.filter(m => c.metrics[m].delta != null);
    add(h("h2", { text: "Real change or noise?" }), caption(`A real change needs ${c.min_pairs} or more shared questions; this comparison has ${c.shared}.`),
      table("narrow", ["Measure", "Before", "After", "Change", ["95% CI of change ", qmark("ci")], ["Verdict ", qmark("paired")]], rows.map(m => {
        const p = c.metrics[m];
        return [term(m), f2(p.a), f2(p.b), sgn(p.delta), p.ci ? h("span", { class: "ci", text: `${sgn(p.ci[0])} to ${sgn(p.ci[1])}` }) : "–", verdict(p.verdict)];
      })));
  }
  add(h("h2", { text: "Questions that changed" }));
  if (!D.items.length) add(h("p", { class: "muted", text: c.warning ? "Not compared question by question." : "No question changed enough to list." }));
  const changes = id => c.worse.concat(c.better).filter(w => w.id === id);
  D.items.forEach((it, n) => {
    const worse = c.worse.some(w => w.id === it.id), ms = changes(it.id);
    const side = (r, label) => h("div", {}, h("h4", { text: label }), r ? [quote(r.answer || "(none)"), r.error ? h("p", { class: "no", text: "System error: " + r.error }) : null,
      h("ul", { class: "plain" }, ms.map(w => h("li", {}, h("b", { text: `${name(w.metric)} ${f2(r.scores[w.metric])}` }), h("span", { class: "muted", text: r.reasons[w.metric] ? ` — ${r.reasons[w.metric]}` : "" }))))] : h("p", { class: "muted", text: "Not asked." }));
    add(h("article", { class: "entry" }, h("h3", {}, `${n + 1}. `, h("span", { class: "qid", text: it.id }), " ", h("span", { class: "verdict " + (worse ? "down" : "up"), text: worse ? "got worse" : "got better" })), quote(it.question),
      h("p", { class: "small", text: ms.map(w => `${name(w.metric)} ${w.a} to ${w.b}`).join(". ") + ". Answer shown: repeat 1." }),
      h("div", { class: "sides" }, side(it.a, "Before"), side(it.b, "After"))));
  });
  finish();
}

({ overview, suite, run, compare })[D.page]();
