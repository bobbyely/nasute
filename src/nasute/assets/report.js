// Draws every Nasute report page from the JSON block in the page (<script id="data">). One file for all four page kinds:
// overview (the dashboard), dataset, run, compare. No server, no network: it needs only this file, report.css and uPlot (uPlot.iife.min.js, vendored).
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
const K = (D.summary || D.compare || D).k;   // how many retrieved sources count; fills the "@k" in Hit rate@k and Recall@k
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
const crumbs = (...parts) => h("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, h("a", { href: UP + "index.html", text: "Nasute" }),
  parts.map(([href, text]) => [" / ", href ? h("a", { href, text }) : text]));
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

// A number that looks fine when it is bad is a trap: an error rate over 10%, or any other score under 0.5, is shown in the warning colour.
const WARN_ERR = 0.1, WARN_LOW = 0.5;
const warnClass = (m, v) => v == null ? "" : (m === "error_rate" ? v > WARN_ERR : v < WARN_LOW) ? "warn" : "";
const failedWords = v => `${Math.round(v * 100)}% of attempts failed`;

// A table you sort by clicking a heading. cols: {t: heading, get: item -> value to sort by, show: item -> cell content, left: left-aligned, desc: first click sorts high to low, cls: e.g. sm-hide}.
function sortable(cols, items, start = 0, dir = 1, cls = "") {
  const st = { i: start, dir }, head = h("tr"), body = h("tbody");
  const paint = () => {
    [...head.children].forEach((th, i) => th.setAttribute("aria-sort", i === st.i ? (st.dir > 0 ? "ascending" : "descending") : "none"));
    const v = it => cols[st.i].get(it);
    body.replaceChildren(...[...items].sort((a, b) => { const x = v(a), y = v(b); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * st.dir; })
      .map(it => h("tr", {}, cols.map(c => h("td", { class: (c.left ? "left " : "") + (c.cls || "") }, c.show(it))))));
  };
  cols.forEach((c, i) => {
    const b = h("button", { type: "button", class: "sort", text: c.t });
    b.addEventListener("click", () => { st.dir = st.i === i ? -st.dir : c.desc ? -1 : 1; st.i = i; paint(); });
    head.append(h("th", { class: (c.left ? "left " : "") + (c.cls || ""), "aria-sort": "none" }, b));
  });
  paint();
  return h("div", { class: "scroll" }, h("table", { class: "sortable " + cls }, h("thead", {}, head), body));
}
// A mean as a dot on a 0 to 1 track with a band for its 95% interval, the number beside it; the title says the same in words.
const rangeBar = (s, m) => {
  const lo = s.ci ? Math.max(0, s.ci[0]) : s.mean, hi = s.ci ? Math.min(1, s.ci[1]) : s.mean;
  return h("span", { class: "rb", title: `${f2(s.mean)}${s.ci ? `, 95% range ${f2(lo)} to ${f2(hi)}` : ""}` }, h("i", { style: `--lo:${lo.toFixed(3)};--hi:${hi.toFixed(3)};--v:${s.mean.toFixed(3)}` }), h("b", { class: warnClass(m, s.mean), text: f2(s.mean) }));
};

// The marker's latest check (looked up when the report is written): which set, how many items, when, how it scored, and the marks it got wrong.
function markerCheck(jc, since) {
  const when2 = when(jc.run.replace("judge-", ""));
  const ms = SCORES.filter(m => jc.metrics[m]);
  return [h("p", { class: "intro", text: `Checked on ${jc.dataset.name} v${ver(jc.dataset.version)}, ${plural(jc.items, "item")}${jc.aborted ? ` of ${jc.set_size} (stopped early: ${jc.aborted})` : ""}, ${when2}. Answers with known faults, marked by the same judge.${since ? " This check is newer than the run." : ""}` }),
    table("narrow", ["Measure", [name("accuracy") + " ", qmark("accuracy")], [name("kappa") + " ", qmark("kappa")]], ms.map(m => [[term(m), plainLine(m)], `${(jc.metrics[m].accuracy * 100).toFixed(0)}%`, jc.metrics[m].kappa == null ? "–" : jc.metrics[m].kappa.toFixed(2)])),
    jc.wrong.length ? more(`${plural(jc.wrong.length, "mark")} it got wrong`, h("ul", { class: "plain" }, jc.wrong.map(x => h("li", {}, h("b", { text: x.id }), ` ${name(x.metric)}: got ${x.got == null ? "no mark" : f2(x.got)}, expected ${f2(x.expected[0])}–${f2(x.expected[1])}`)))) : null];
}

// ---- per-question charts (run page) ---------------------------------------------------------------
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
// Can these runs be compared question by question? Only on the same dataset (fileToo: the same version of it, too).
const likeForLike = (rs, fileToo) => new Set(rs.map(r => fileToo ? r.dataset.sha256 : r.dataset.name)).size === 1;
// What became of one question in one run, from its mean score (P: correctness that counts as right; the same rule as outcome_word() in __init__.py): right, partly, wrong; declined or made something up; or a system error.
function outcome(v, unanswerable, errors, attempts, mode, P = 0.75) {
  if (attempts && errors === attempts) return { word: "system error", mark: "E", cls: "bad" };
  if (v == null) return { word: "not judged", mark: "?", cls: "na" };
  if (unanswerable) return v >= 1 ? { word: "declined", mark: "✓", cls: "good" } : v > 0 ? { word: "declined, with an error", mark: "½", cls: "part" } : { word: "made something up", mark: "✗", cls: "bad" };
  return v >= P ? { word: "right", mark: "✓", cls: "good" } : v > 0 ? { word: mode === "knowledge" ? "right, with an error" : "partly right", mark: "½", cls: "part" } : { word: "wrong", mark: "✗", cls: "bad" };
}
// A trend needs two points: the over-time chart of a score is drawn only when at least two runs measured it.
const enough = (rs, m) => rs.filter(r => r.metrics[m] && r.metrics[m].mean != null).length >= 2;
// The at-a-glance bars: how many questions in each group had each outcome. It counts q.out, the outcome the question list shows,
// so the bars and the list never disagree. groupsOf(q) gives a list: a question in two groups counts in both. -> [[group, {word: count}]].
function outcomeCounts(qs, groupsOf) {
  const out = new Map();
  for (const q of qs) for (const g of groupsOf(q)) { if (!out.has(g)) out.set(g, {}); const c = out.get(g); c[q.out.word] = (c[q.out.word] || 0) + 1; }
  return [...out];
}
// How to draw one group of a distribution chart. Scores often take only 0, 0.5 and 1, and a box of those is a line with dots on it,
// so a group of scores with three values or fewer is a strip (dots and a ring for the mean). Otherwise a box from four questions, else dots.
const FEW_VALUES = 3;
const distKind = (values, score) => score && new Set(values).size <= FEW_VALUES ? "strip" : values.length >= 4 ? "box" : "dots";
// Which distribution charts a run gets. The score chart needs two questions; seconds, tokens and cost need some question with a value;
// the score-against-seconds scatter needs a question with both. A value not measured is null and is left out, never drawn as 0.
function distCharts(qs, score) {
  const scored = q => score != null && q.means[score] != null;
  return [qs.length > 1 && qs.some(scored) ? "score" : null, ...["seconds", "tokens", "cost"].filter(k => qs.some(q => q.per[k] != null)),
    qs.some(q => scored(q) && q.per.seconds != null) ? "speed" : null].filter(Boolean);
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
const dotLines = (q, lines, who) => [...(who ? [who] : []), ...wrapText(shorten(q.reps[0].question)), "", ...lines.map(([v, m]) => `${typeof v === "string" ? v : f2(v)}  ${m}`), ...(q.cause ? [`${q.cause}  cause`] : [])];
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

// Distribution charts: the score, seconds, tokens out and cost of each question, by one group the reader picks (difficulty, each tag,
// topic, cause), and a scatter of score against seconds. One picker drives them all. Groups run down the page, so a long list of tags
// still fits a phone: the chart grows taller, never wider.
const boxScores = qs => ["correctness", "abstention", "faithfulness", "relevancy", "hit", "mrr"].filter(m => qs.some(q => q.means[m] != null));
// What the questions can be grouped by. A question with two tags is in both tag groups.
function categories(qs) {
  return [["difficulty", "difficulty", q => [q.difficulty || "unknown"]],
    qs.some(q => q.tags.length) && ["tag", "tag", q => q.tags.length ? q.tags : ["untagged"]],
    qs.some(q => q.topic) && ["topic", "topic", q => [q.topic || "untagged"]],
    qs.some(q => q.cause) && ["cause", "cause of failure", q => [q.cause || "none"]]].filter(Boolean);
}
const groupRank = k => k in DIFF ? DIFF[k] : NEUTRAL[k] ? 1e9 : 10;   // easy to hard first, grey groups last, the rest biggest first
const groupName = k => NEUTRAL[k] || k;
// The groups of one chart, each with its questions that have a value. A group with no values is left out.
function groupRows(qs, groupsOf, valueOf) {
  const m = new Map();
  for (const q of qs) { const v = valueOf(q); if (v != null) for (const g of groupsOf(q)) { if (!m.has(g)) m.set(g, []); m.get(g).push({ q, v }); } }
  return [...m].map(([key, items]) => ({ key, items })).sort((a, b) => groupRank(a.key) - groupRank(b.key) || b.items.length - a.items.length || a.key.localeCompare(b.key));
}
const whole = v => String(Math.round(v));
const MEASURES = {
  score: { title: "Score", axis: st => name(st.score), value: (q, st) => q.means[st.score], fmt: f2 },
  seconds: { title: "Seconds per answer", axis: () => "Seconds per answer (the system's time)", value: q => q.per.seconds, fmt: v => secs(v) },
  tokens: { title: "Tokens out", axis: () => "Tokens in the answer", value: q => q.per.tokens, fmt: whole },
  cost: { title: "Cost per answer", axis: () => "Cost per answer", value: q => q.per.cost, fmt: v => money(v) },
};
const rowHeight = n => 64 + n * (n > 6 ? 26 : 38);
const valueAxis = (T, text, score, fmt) => ({ ...(score ? { min: -0.04, max: 1.04, afterBuildTicks: ticks01 } : { beginAtZero: true }), title: { display: true, text, color: T.quiet, font: { family: T.font } },
  grid: { color: T.rule }, border: { color: T.rule }, ticks: { color: T.quiet, font: { family: T.font }, maxTicksLimit: 6, callback: score ? tickText : fmt } });

function distFigure(kind, st, qs, open) {
  const M = MEASURES[kind], score = kind === "score", head = h("h3"), canvas = h("canvas", { tabindex: "0", role: "img" }), wrap = h("div", { class: "plot" }, canvas),
    note = h("p", { class: "caption" }), live = h("p", { class: "sr", "aria-live": "polite" }), alt = h("div"), gate = tapGate(open);
  let chart = null;
  const draw = () => {
    const T = theme(), aN = M.axis(st), rows = groupRows(qs, st.cat[2], q => M.value(q, st));
    for (const r of rows) { const v = r.items.map(i => i.v); r.s = boxStats(v); r.kind = distKind(v, score); }
    head.textContent = `${M.title} by ${st.cat[1]}`;
    wrap.style.height = rowHeight(rows.length) + "px";
    const dots = rows.flatMap((r, i) => r.items.map(({ q, v }) => ({ x: v, y: i + jitter(q.id, kind) * (r.kind === "box" ? 0.3 : 0.6), o: i * 1e9 + v, q, v })));
    const rings = rows.flatMap((r, i) => r.kind === "strip" ? [{ x: r.s.mean, y: i }] : []);
    note.textContent = (score ? `Few values (${FEW_VALUES} or fewer): dots, ring = mean. ` : "") + "Box: the middle half, line = median, ring = mean, whiskers to 1.5 × the box. Under four questions: dots only." +
      (st.cat[0] === "tag" ? " A question with two tags is in both groups." : "");
    chart && chart.destroy();
    chart = new Chart(canvas, { type: "boxplot", data: { labels: rows.map((_, i) => i), datasets: [
      { label: "boxes", data: rows.map(r => r.kind === "box" ? { min: r.s.min, q1: r.s.q1, median: r.s.median, q3: r.s.q3, max: r.s.max, mean: r.s.mean, whiskerMin: r.s.lo, whiskerMax: r.s.hi, items: [], outliers: [] } : []),
        itemRadius: 0, outlierRadius: 0, backgroundColor: T.accent + "26", borderColor: T.ink, borderWidth: 1.5, medianColor: T.ink, meanRadius: 5, meanBackgroundColor: "transparent", meanBorderColor: T.ink, meanBorderWidth: 2, maxBarThickness: 26, coef: 1.5 },
      { type: "scatter", label: "means", data: rings, parsing: false, backgroundColor: "transparent", borderColor: T.ink, borderWidth: 2, pointRadius: 7, pointHoverRadius: 7, pointHitRadius: 0 },
      { type: "scatter", label: "questions", data: dots, dots: true, parsing: false, backgroundColor: T.accent + "b3", borderColor: T.paper, borderWidth: 1, pointRadius: 4, pointHoverRadius: 7, pointHitRadius: 8 }] },
    options: { indexAxis: "y", animation: false, responsive: true, maintainAspectRatio: false, interaction: { mode: "nearest", intersect: true },
      scales: { x: valueAxis(T, aN, score, M.fmt),
        y: { type: "linear", reverse: true, min: -0.5, max: rows.length - 0.5, afterBuildTicks: ax => { ax.ticks = rows.map((_, value) => ({ value })); }, grid: { display: false }, border: { color: T.rule },
          ticks: { color: T.ink, font: { family: T.font, size: 12 }, autoSkip: false, callback: v => rows[v] ? `${shorten(groupName(rows[v].key), 16)} · ${rows[v].s.n}` : "" } } },
      onClick: (_, els) => { const e = els.find(x => x.datasetIndex === 2); if (e) gate(dots[e.index].q.id); },
      plugins: { legend: { display: false }, tooltip: { ...T.tip, filter: c => c.datasetIndex === 2, callbacks: { title: c => c[0].raw.q.id, label: c => dotLines(c.raw.q, [[M.fmt(c.raw.v), aN]]), footer: hint } } } } });
    canvas.setAttribute("aria-label", `${M.title} by ${st.cat[1]}, ${rows.length} groups, ${dots.length} dots. Arrow keys move between dots, Enter opens the question.`);
    alt.replaceChildren(textAlt(`${M.title} by ${st.cat[1]}.`, [cap(st.cat[1]), "Questions", "Median", "Mean"], rows.map(r => [groupName(r.key), r.s.n, M.fmt(r.s.median), M.fmt(r.s.mean)])));
  };
  keyboard(canvas, () => chart, p => { live.textContent = `${p.q.id}. ${shorten(p.q.reps[0].question)}. ${M.title} ${M.fmt(p.v)}.`; }, open);
  return { kind, el: h("figure", {}, head, wrap, note, live, alt), draw };
}

// Do slow answers score better? One dot per question, coloured by its group: the three biggest groups get a colour, the rest grey.
function speedFigure(st, qs, open) {
  const head = h("h3"), canvas = h("canvas", { tabindex: "0", role: "img" }), wrap = h("div", { class: "plot short" }, canvas), legend = h("div", { class: "legend" }),
    note = h("p", { class: "caption", text: "One dot per question. Scores are nudged a little apart so they do not hide each other; the tooltip is exact. A question in two groups takes the colour of the first." }),
    live = h("p", { class: "sr", "aria-live": "polite" }), alt = h("div"), gate = tapGate(open);
  let chart = null;
  const draw = () => {
    const T = theme(), sN = name(st.score), groupsOf = st.cat[2], both = qs.filter(q => q.means[st.score] != null && q.per.seconds != null);
    const coloured = groupRows(both, groupsOf, () => 1).map(r => r.key).filter(k => !NEUTRAL[k]).slice(0, 3);
    const entries = [...coloured.map((k, i) => ({ key: k, label: k, c: i, shape: i })), { key: "", label: coloured.length ? "other" : "all", c: 3, shape: 3 }];
    const of = q => entries.find(e => groupsOf(q).includes(e.key)) || entries[entries.length - 1];
    const sets = entries.map(e => ({ label: e.label, e, dots: true, data: both.filter(q => of(q) === e).map(q => ({ x: q.per.seconds, y: nudge(q.means[st.score], q.id, "y"), o: q.per.seconds, q, s: q.means[st.score] })),
      pointStyle: POINT[e.shape], backgroundColor: T.cols[e.c], borderColor: T.paper, borderWidth: 1.5, pointRadius: 5, pointHoverRadius: 8, pointHitRadius: 10 })).filter(s => s.data.length);
    head.textContent = `${sN} against seconds per answer`;
    chart && chart.destroy();
    chart = new Chart(canvas, { type: "scatter", data: { datasets: sets }, options: { animation: false, responsive: true, maintainAspectRatio: false, interaction: { mode: "nearest", intersect: true },
      scales: { x: valueAxis(T, "Seconds per answer", false, secs), y: valueAxis(T, sN, true) }, onClick: (_, els) => { if (els.length) gate(sets[els[0].datasetIndex].data[els[0].index].q.id); },
      plugins: { legend: { display: false }, tooltip: { ...T.tip, callbacks: { title: c => c[0].raw.q.id, label: c => dotLines(c.raw.q, [[c.raw.s, sN], [secs(c.raw.x), "seconds"]]), footer: hint } } } } });
    canvas.setAttribute("aria-label", `${sN} against seconds per answer, ${both.length} questions. Arrow keys move between dots, Enter opens the question.`);
    legend.replaceChildren(...sets.map(s => h("span", { class: "key" }, swatch(s.e), `${s.label} (${s.data.length})`)));
    alt.replaceChildren(textAlt(`${sN} against seconds per answer.`, ["Question", "Seconds", sN], both.map(q => [q.id, secs(q.per.seconds), f2(q.means[st.score])])));
  };
  keyboard(canvas, () => chart, p => { live.textContent = `${p.q.id}. ${shorten(p.q.reps[0].question)}. ${name(st.score)} ${f2(p.s)}, ${secs(p.x)}.`; }, open);
  return { kind: "speed", el: h("figure", {}, head, wrap, legend, note, live, alt), draw };
}

// The distribution charts and their one shared picker. Null when none has anything to show.
function distSection(qs, open) {
  const scores = boxScores(qs), cats = categories(qs), st = { score: scores[0], cat: cats[0] };
  if (!distCharts(qs, st.score).length) return null;
  const figs = [...Object.keys(MEASURES).map(k => distFigure(k, st, qs, open)), speedFigure(st, qs, open)];
  const draw = () => { const show = distCharts(qs, st.score); for (const f of figs) { f.el.hidden = !show.includes(f.kind); if (!f.el.hidden) f.draw(); } };
  const pick = (label, opts, set) => { const s = h("select", { "aria-label": label }, opts.map(([v, t]) => h("option", { value: v, text: t }))); s.addEventListener("change", () => { set(s.value); draw(); }); return s; };
  const bar = h("div", { class: "bar" }, pick("Group by", cats.map(c => [c[0], "Group by " + c[1]]), v => { st.cat = cats.find(c => c[0] === v); }),
    scores.length > 1 ? pick("Score", scores.map(m => [m, name(m)]), v => { st.score = v; }) : null);
  return { el: h("div", { class: "charts" }, bar, figs.map(f => f.el)), draw };
}

// The section for a suite page: the latest run's questions, both charts, and one redraw when light/dark changes.
function chartsSection(qs, open) {
  const tagN = new Map();
  for (const q of qs) for (const t of q.tags) tagN.set(t, (tagN.get(t) || 0) + 1);
  // shortcut: datasets have no "origin" field, so it is read from the tags: the commonest tag after the first (the first is the topic); a lone tag is its own origin. Add a real field if datasets start to use one.
  for (const q of qs) q.origin = q.tags.length > 1 ? q.tags.slice(1).sort((a, b) => tagN.get(b) - tagN.get(a) || a.localeCompare(b))[0] : q.tags[0] || "untagged";
  // a chart with nothing in it is left out: the scatter needs both scores on some question, the box plots any score
  const figs = [qs.some(q => q.means.faithfulness != null && q.means.correctness != null) ? scatterFigure(qs, open) : null, distSection(qs, open)].filter(Boolean);
  if (!figs.length) return null;
  const all = () => figs.forEach(f => f.draw());
  requestAnimationFrame(all);   // after the figures are in the page, so the canvases have a width
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", all);
  return h("div", { class: "charts" }, figs.map(f => f.el));
}

// ---- shared by the dashboard and the dataset page: runs tables you can tick, and comparing the ticked runs -----------------------
const ORDER = ["correctness", "abstention", "relevancy", "faithfulness", "context_recall", "hit", "recall", "mrr", "error_rate"];   // main score first
const HEAD = ["correctness", "abstention", "faithfulness", "hit", "error_rate"];   // what a runs table has room for
const shown = (runs, list = HEAD) => list.filter(m => runs.some(r => r.metrics[m] && r.metrics[m].mean != null));   // a score no run measured gets no column
const mainOf = runs => shown(runs, ["correctness", "abstention", "faithfulness", "hit"])[0];
const perCost = r => r.usage && r.usage.per_answer ? r.usage.per_answer.cost : null;
const secs = x => x == null ? "–" : x < 10 ? `${x.toFixed(1)} s` : `${Math.round(x)} s`;
const na = () => h("span", { class: "na", text: "–", title: "not measured" });   // quiet, never the warning colour
const runHref = r => `${UP}${r.folder}/runs/${r.run}.html`;
const scoreCell = (r, m, bar, ci = true) => { const s = r.metrics[m]; return !s || s.mean == null ? na() : bar ? rangeBar(s, m) : [h("span", { class: warnClass(m, s.mean), text: f2(s.mean) }), ci && s.ci ? h("small", { class: "ci", text: " " + spread(s) }) : null]; };
const scoreCol = (m, bar, cls, ci = true) => ({ t: name(m), desc: m !== "error_rate", cls, get: r => (r.metrics[m] || {}).mean, show: r => scoreCell(r, m, bar, ci) });   // ci: the 95% range beside the number
// The main score shows everywhere; on a phone only it; on a middling screen also error rate and abstention, so cost and speed keep their room.
const side = (m, main) => m === main ? "" : ["error_rate", "abstention"].includes(m) ? "sm-hide" : "sm-hide md-hide";
const costCol = cls => ({ t: "Cost / answer", cls, get: perCost, show: r => perCost(r) == null ? na() : money(perCost(r)) });
const speedCol = cls => ({ t: "Seconds / answer", cls, get: r => r.answer_s, show: r => secs(r.answer_s) });
const runWords = r => `${r.judge_mode || "quick"} judge${r.profile ? ", " + r.profile : ""}${r.repeats > 1 ? ", ×" + r.repeats : ""}`;
const dateCell = (r, where) => [h("a", { href: runHref(r), text: when(r.run) }), h("small", { class: "sub sm-only", text: where === "all" ? `${r.dataset.name} · ${r.target_label}` : r.target_label }), r.label ? h("small", { class: "sub", text: `“${r.label}”` }) : null,
  r.aborted ? h("small", { class: "sub warn", text: "stopped early" }) : null, r.incomplete ? h("small", { class: "sub warn", text: "incomplete" }) : null];

// A sortable table of runs whose first column is a tick box. The ticks live in `picked` (run ids), so a re-sort keeps them.
function tickTable(runs, cols, picked, changed) {
  const box = { t: "Pick", get: r => picked.has(r.run) ? 0 : 1, show: r => {
    const b = h("input", { type: "checkbox", "aria-label": `Pick the run of ${when(r.run)}, ${r.target_label}` });
    b.checked = picked.has(r.run);
    b.addEventListener("change", () => { b.checked ? picked.add(r.run) : picked.delete(r.run); changed(); });
    return b; } };
  return sortable([box, ...cols], runs, 1, -1, "runs");
}
// The bar under a runs table: one button that compares the ticked runs, and a way to clear them.
function compareBar(picked, go, clear) {
  const btn = h("button", { type: "button", class: "primary" }), say = h("span", { class: "small" }), off = h("button", { type: "button", class: "link", text: "Clear ticks" });
  btn.addEventListener("click", go); off.addEventListener("click", clear);
  const bar = h("div", { class: "cmpbar" }, btn, say, off);
  const paint = () => { bar.classList.toggle("on", picked.size > 0); btn.textContent = picked.size > 1 ? `Compare ${picked.size} runs` : "Compare"; btn.disabled = picked.size < 2; say.textContent = picked.size < 2 ? "Tick two or more runs to compare them." : ""; off.hidden = !picked.size; };
  paint();
  return { el: bar, paint };
}
// Headline scores of any runs side by side, with cost and speed. Rows are scores; a score no run measured is left out.
function sideBySide(rs) {
  const ms = shown(rs, ORDER);
  const head = ["", ...rs.map(r => h("span", {}, h("a", { href: runHref(r), text: when(r.run) }), h("small", { class: "sub", text: r.target_label }), h("small", { class: "sub", text: `${r.dataset.name} v${ver(r.dataset.version)}` })))];
  const rows = [...ms.map(m => [term(m), ...rs.map(r => scoreCell(r, m))]),
    ["Cost / answer", ...rs.map(r => perCost(r) == null ? na() : money(perCost(r)))], ["Seconds / answer", ...rs.map(r => secs(r.answer_s))],
    ["Questions", ...rs.map(r => r.questions ?? "–")], ["Judge", ...rs.map(r => runWords(r))]];
  return table("side", head, rows);
}
const UP = { overview: "", dataset: "../", run: "../../", compare: "../../" }[D.page];

// ---- the dashboard ---------------------------------------------------------------------------------
// Each dataset with its systems ranked by their latest main score; then the recent runs of every dataset, to tick and compare.
const RECENT = 15;   // runs shown before "Show all"
function overview() {
  add(h("h1", { text: "Nasute" }), h("p", { class: "lede", text: "Each dataset with its systems ranked by their latest main score. Scores run from 0 (bad) to 1 (perfect). Tick runs below to compare them." }));
  if (!D.datasets.length) { add(h("p", { class: "empty", text: "No runs yet. Start one with: nasute run --profile smoke" })); finish(); return; }
  add(h("h2", { text: "Datasets" }), h("div", { class: "cards" }, D.datasets.map(card)));

  const picked = new Set(), panel = h("section", { class: "cmp", "aria-live": "polite" });
  let all = false, tbl;
  const cols = rs => [{ t: "Date", left: true, desc: true, get: r => r.run, show: r => dateCell(r, "all") }, { t: "Dataset", left: true, cls: "sm-hide", get: r => r.dataset.name, show: r => h("a", { href: `datasets/${datasetFile(r)}`, text: r.dataset.name }) },
    { t: "System", left: true, cls: "sm-hide", get: r => r.target_label.toLowerCase(), show: r => r.target_label }, ...shown(rs).map(m => scoreCol(m, false, side(m, "correctness"), m === "correctness")), costCol("sm-hide"), speedCol("sm-hide")];
  const host = h("div"), moreBtn = h("button", { type: "button", class: "link" });
  const draw = () => {
    const rs = all ? D.runs : D.runs.slice(0, RECENT);
    tbl = tickTable(rs, cols(rs), picked, () => bar.paint());
    host.replaceChildren(tbl);
    moreBtn.textContent = all ? "Show fewer" : `Show all ${D.runs.length} runs`; moreBtn.hidden = D.runs.length <= RECENT;
  };
  moreBtn.addEventListener("click", () => { all = !all; draw(); });
  const bar = compareBar(picked, () => {
    const rs = D.runs.filter(r => picked.has(r.run)), one = likeForLike(rs);
    panel.replaceChildren(h("h3", { text: `Comparing ${rs.length} runs` }),
      one ? h("p", { class: "intro" }, "Same dataset. ", h("a", { href: `datasets/${datasetFile(rs[0])}#compare=${rs.map(r => r.run).join(",")}`, text: "See them question by question, with the paired test" }), ".")
        : h("p", { class: "note", text: "These runs used different questions, so this is not a like-for-like test. Only the headline scores are shown side by side." }),
      sideBySide(rs));
    panel.scrollIntoView({ block: "start" });
  }, () => { picked.clear(); panel.replaceChildren(); draw(); bar.paint(); });
  add(h("h2", { text: "Recent runs" }), h("p", { class: "intro", text: "Newest first, across all datasets. Click a heading to sort." }), host, moreBtn, bar.el, panel);
  draw();
  for (const j of D.judges) {
    const jc = j.check, ms = jc ? SCORES.filter(m => jc.metrics[m]) : [];
    add(h("p", { class: "small" }, `Judge: ${j.model}, ${j.mode} mode. `, jc ? `Checked ${when(jc.run.replace("judge-", ""))} on ${jc.dataset.name} v${ver(jc.dataset.version)}: ` + ms.map(m => `${name(m)} ${(jc.metrics[m].accuracy * 100).toFixed(0)}% accurate`).join(", ") + ". " : "Not checked yet. "));
  }
  finish();
}
const datasetFile = r => (D.datasets.find(d => d.name === r.dataset.name) || {}).href.replace(/^datasets\//, "");

// One dataset on the dashboard: its systems' latest runs, best first, with cost and speed where known.
const TOP = 6;
function card(d) {
  const main = mainOf(d.latest), rs = [...d.latest].sort((a, b) => ((b.metrics[main] || {}).mean ?? -1) - ((a.metrics[main] || {}).mean ?? -1));
  const newest = d.latest.map(r => r.run).sort().pop();
  return h("article", { class: "card" }, h("h3", {}, h("a", { href: d.href, text: d.name })),
    h("p", { class: "small", text: `${plural(d.runs, "run")} on ${plural(d.latest.length, "system")}. Last run ${when(newest)}.${main ? ` Ranked by ${name(main, null).toLowerCase()}, latest run of each.` : ""}` }),
    h("ol", { class: "rank" }, rs.slice(0, TOP).map(r => h("li", {}, h("a", { class: "who", href: runHref(r), text: r.target_label }), main ? scoreCell(r, main, true) : na(),
      h("span", { class: "meta", text: [perCost(r) != null ? money(perCost(r)) + " / answer" : null, r.answer_s != null ? secs(r.answer_s) + " / answer" : null].filter(Boolean).join(" · ") })))),
    rs.length > TOP ? h("p", { class: "small" }, h("a", { href: d.href, text: `and ${rs.length - TOP} more` })) : null);
}

// ---- one dataset -----------------------------------------------------------------------------------
// Its systems ranked, every run on it (tick any to compare them question by question), then the over-time charts.
function dataset() {
  const runs = [...D.runs].reverse(), latest = D.systems.map(s => runs.find(r => r.target === s.target)).filter(Boolean), main = mainOf(latest);
  const versions = [...new Set(D.runs.map(r => ver(r.dataset.version)))];
  add(crumbs([null, D.name]), h("h1", { text: D.name }),
    h("p", { class: "lede", text: `${plural(runs.length, "run")} on ${plural(D.systems.length, "system")}. Questions: v${versions.join(", v")}${runs[0].questions != null ? `, ${runs[0].questions} in the latest run` : ""}.` }));

  add(h("h2", { text: "Latest by system" }), h("p", { class: "intro", text: main ? `Each system's latest run, best ${name(main, D.k).toLowerCase()} first.` : "Each system's latest run." }),
    sortable([{ t: "System", left: true, get: r => r.target_label.toLowerCase(), show: r => [h("a", { href: runHref(r), text: r.target_label }), h("small", { class: "sub", text: when(r.run) })] },
      ...shown(latest).map(m => scoreCol(m, m === main, side(m, main), false)), costCol("sm-hide"), speedCol("sm-hide"),
      { t: "Runs", cls: "sm-hide", desc: true, get: r => runs.filter(x => x.target === r.target).length, show: r => String(runs.filter(x => x.target === r.target).length) }], latest, main ? 1 : 0, -1));

  const picked = new Set(), panel = h("section", { class: "cmp", "aria-live": "polite" }), host = h("div");
  const cols = [{ t: "Date", left: true, desc: true, get: r => r.run, show: r => dateCell(r) }, { t: "System", left: true, cls: "sm-hide", get: r => r.target_label.toLowerCase(), show: r => [r.target_label, h("small", { class: "sub", text: `v${ver(r.dataset.version)}, ${runWords(r)}` })] },
    ...shown(runs).map(m => scoreCol(m, false, side(m, main), m === main)), costCol("sm-hide"), speedCol("sm-hide")];
  const draw = () => host.replaceChildren(tickTable(runs, cols, picked, () => bar.paint()));
  const go = () => { compareRuns(panel, runs.filter(r => picked.has(r.run)).reverse()); panel.scrollIntoView({ block: "start" }); };
  const bar = compareBar(picked, go, () => { picked.clear(); panel.replaceChildren(); draw(); bar.paint(); });
  add(h("h2", { id: "runs", text: "Runs" }), h("p", { class: "intro", text: "Newest first. Tap a date to open the run; tick two or more to compare them question by question." }), host, bar.el, panel);
  draw();
  const m = location.hash.match(/^#compare=([\w,]+)$/);
  if (m) { m[1].split(",").forEach(id => runs.some(r => r.run === id) && picked.add(id)); draw(); bar.paint(); if (picked.size > 1) requestAnimationFrame(go); }

  overTime(runs);
  add(h("h2", { class: "quiet", text: "Details" }),
    D.mislabels.length ? more(`${plural(D.mislabels.length, "question")} may be mislabelled`, h("ul", { class: "plain" }, D.mislabels.map(x => h("li", {}, h("b", { text: x.id }), ` labelled ${x.label}, but answered well ${x.passed} of ${x.attempts} times`)))) : null,
    h("p", { class: "small" }, "Download every run of a system (CSV): ", D.systems.map((s, i) => [i ? " · " : "", h("a", { href: `../${s.folder}/runs.csv`, download: "", text: s.target_label })]), "."));
  finish();
}

// Runs of this dataset compared: headline scores side by side, the paired test for two runs of the same questions, then question by question.
function compareRuns(panel, rs) {
  const sameFile = likeForLike(rs, true), pair = rs.length === 2 && D.paired[`${rs[0].run} ${rs[1].run}`];
  panel.replaceChildren(h("h3", { text: `Comparing ${rs.length} runs` }), sideBySide(rs));
  if (!sameFile) panel.append(h("p", { class: "note", text: "These runs used different versions of the questions. Shared questions are lined up by id, but the scores are not a like-for-like test." }));
  if (pair && !pair.warning) {
    const ms = ORDER.filter(m => pair.metrics[m]);
    panel.append(h("h3", { text: "Real change or noise?" }), caption(`Paired on the ${plural(pair.shared, "question")} both runs answered, older run first. A real change needs ${pair.min_pairs} or more.`),
      table("narrow", ["Measure", "Before", "After", "Change", ["95% CI of change ", qmark("ci")], ["Verdict ", qmark("paired")]], ms.map(m => { const p = pair.metrics[m];
        return [term(m), f2(p.a), f2(p.b), sgn(p.delta), p.ci ? h("span", { class: "ci", text: `${sgn(p.ci[0])} to ${sgn(p.ci[1])}` }) : "–", verdict(p.verdict)]; })));
    if (pair.notes.length) panel.append(h("ul", { class: "plain small" }, pair.notes.map(t => h("li", { text: t }))));
  } else if (pair && pair.warning) panel.append(h("p", { class: "note", text: pair.warning }));
  else if (rs.length === 2 && sameFile) panel.append(h("p", { class: "small", text: `No paired test here for these two. Run: nasute compare ${rs[0].run} ${rs[1].run}` }));
  panel.append(questionGrid(rs));
}

// Question by question: one row per question, one column per run, each cell a mark and a word (never colour alone).
function questionGrid(rs) {
  const ids = [...new Set([...Object.keys(D.questions), ...rs.flatMap(r => Object.keys(D.grid[r.run] || {}))])].filter(i => rs.some(r => (D.grid[r.run] || {})[i]));
  const cell = (r, i) => { const g = (D.grid[r.run] || {})[i]; return g ? outcome(g[0], g[1], g[2], g[3], r.judge_mode, D.pass_at) : null; };
  const differs = i => new Set(rs.map(r => (cell(r, i) || { word: "not asked" }).word)).size > 1;
  const only = h("input", { type: "checkbox", id: "only-diff" }); only.checked = true;
  const host = h("div");
  const draw = () => {
    const list = only.checked ? ids.filter(differs) : ids;
    host.replaceChildren(list.length ? table("grid", ["Question", ...rs.map(r => h("span", {}, when(r.run), h("small", { class: "sub", text: r.target_label })))],
      list.map(i => [h("span", {}, h("span", { class: "qtext", text: shorten(D.questions[i] || i, 90) }), h("span", { class: "qid", text: i })), ...rs.map(r => { const o = cell(r, i); return o ? mark(o) : h("span", { class: "na", text: "not asked" }); })]))
      : h("p", { class: "muted", text: "Every question had the same outcome in each run." }));
  };
  only.addEventListener("change", draw); draw();
  return h("div", {}, h("h3", { text: "Question by question" }),
    h("p", { class: "small", text: "✓ right (or, for a question with no answer, declined) · ½ partly right · ✗ wrong (or made something up) · E system error. Mean over repeats." }),
    h("p", { class: "bar" }, only, h("label", { for: "only-diff", text: " Only questions where the runs differ" })), host);
}

const mark = o => h("span", { class: "out " + o.cls }, h("b", { "aria-hidden": "true", text: o.mark }), " ", o.word);

// Every run on a timeline, one chart per score, for one system at a time. Left out with fewer than two runs: one dot is not a trend.
function overTime(runs) {
  const old = [...runs].reverse(), twoPlus = rs => rs.length >= 2;
  const sys = D.systems.filter(s => twoPlus(old.filter(r => r.target === s.target)));
  if (!sys.length) return;
  const want = (location.hash.match(/^#system=(.+)$/) || [])[1];
  let target = sys.some(s => s.target === want) ? want : sys[0].target, pick, profile;
  const pickSys = sys.length > 1 ? h("select", { "aria-label": "System" }, sys.map(s => h("option", { value: s.target, text: s.target_label }))) : null;
  if (pickSys) { pickSys.value = target; pickSys.addEventListener("change", () => { target = pickSys.value; profile = null; drawCharts(); }); }
  const tabs = h("div", { class: "tabs", role: "group", "aria-label": "Profile" }), box = h("div", { class: "figures" });
  const drawCharts = () => {
    charts.forEach(u => u.destroy()); charts = [];
    box.replaceChildren();
    const mine = old.filter(r => r.target === target), profiles = [...new Set(mine.map(r => r.profile || ""))].filter(p => twoPlus(mine.filter(r => (r.profile || "") === p)));
    if (!profiles.includes(profile)) profile = profiles.includes("deep") ? "deep" : profiles.includes("smoke") ? "smoke" : profiles[0];
    tabs.replaceChildren(...(profiles.length > 1 ? [h("span", { class: "small", text: "Profile: " }), ...profiles.map(p => { const b = h("button", { type: "button", class: p === profile ? "on" : "", "aria-pressed": p === profile ? "true" : "false", text: p || "no profile" }); b.addEventListener("click", () => { profile = p; drawCharts(); }); return b; })] : []));
    if (profile == null) { box.append(h("p", { class: "muted", text: "Fewer than two runs with the same profile: nothing to draw yet." })); return; }
    const rs = mine.filter(r => (r.profile || "") === profile);
    const ms = ORDER.filter(k => enough(rs, k));
    if (!ms.includes(pick)) pick = ms[0];
    if (phone.matches) box.append(h("div", { class: "tabs chips", role: "group", "aria-label": "Score" }, ms.map(m => { const b = h("button", { type: "button", class: m === pick ? "on" : "", "aria-pressed": m === pick ? "true" : "false", text: name(m) }); b.addEventListener("click", () => { pick = m; drawCharts(); }); return b; })));
    (phone.matches ? [pick] : ms).forEach((m, i) => {   // a phone gets one chart and a picker; a wide screen gets the main chart large, then the rest small
      const host = h("figure", { class: !phone.matches && i === 0 ? "lead" : "" });
      if (!phone.matches && i === 1) box.append(h("h3", { class: "span", text: "Other scores" }));
      box.append(host);
      const kept = rs.filter(r => r.metrics[m] && r.metrics[m].mean != null);
      drawChart(host, m, kept, runHref, !phone.matches && i === 0);
    });
  };
  add(h("h2", { id: "over-time", text: "Over time" }), h("p", { class: "intro", text: "One system at a time. Drag across a chart to zoom; double-click resets." }), pickSys ? h("div", { class: "bar" }, pickSys) : null, tabs, box);
  drawCharts();
  if (want) requestAnimationFrame(() => document.getElementById("over-time").scrollIntoView());
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawCharts);
  phone.addEventListener("change", drawCharts);
}

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

// ---- one run -------------------------------------------------------------------------------------
// Where the numbers are. First the answer (a sentence and the headline scores), then every question, then the charts, then the rest.
const GROUPS = [["Answers", ["correctness", "faithfulness", "relevancy", "abstention"]], ["Finding sources", ["hit", "recall", "mrr", "context_recall"]], ["Reliability", ["error_rate"]]];
const more = (summary, ...kids) => h("details", { class: "more" }, h("summary", { text: summary }), kids);
const DIFF = { easy: 0, medium: 1, hard: 2 };

// The headline: one sentence on the main score, then a tile per measured headline score (with its change on the reference run), cost and speed.
function headline(S, c) {
  const cm = S.metrics, mean = m => cm[m] && cm[m].mean, pm = c && !c.warning ? c.metrics : {}, refWord = D.vs_baseline ? "baseline" : "run before";
  const change = m => { const p = pm[m]; return !p || p.delta == null ? null : h("span", {}, sgn(p.delta), " ", verdict(p.verdict)); };
  const sentence = [], cor = cm.correctness, pc = pm.correctness, er = mean("error_rate");
  if (cor && cor.mean != null) {
    const how = !pc || pc.delta == null ? "." : pc.verdict === "real gain" || pc.verdict === "real drop" ? `, ${pc.verdict === "real gain" ? "a real gain" : "a real drop"} of ${sgn(pc.delta)} on the ${refWord}.` :
      pc.verdict === "within noise" ? `, no real change (${sgn(pc.delta)} on the ${refWord}).` : `; too few questions to tell if it changed since the ${refWord}.`;
    sentence.push(`${name("correctness")} (${G.correctness.plain}) is ${f2(cor.mean)}${cor.ci ? ` (95% CI ${f2(Math.max(0, cor.ci[0]))}–${f2(Math.min(1, cor.ci[1]))})` : ""}${how}`);
  }
  if (er != null && er > WARN_ERR) sentence.push(`${name("error_rate")} is high: ${failedWords(er)}.`);
  const u = S.usage || {}, pa = u.per_answer || {}, secsPer = answerSeconds(D.rows);
  const tile = (label, num, sub, cls = "", chg = null) => h("div", { class: "hero-item" }, h("span", { class: "hi-name" }, label), h("b", { class: "num " + cls, text: num }), h("span", { class: "hi-ci " + cls, text: sub }), h("span", { class: "hi-change" }, chg));
  return [sentence.length ? h("p", { class: "summary", text: sentence.join(" ") }) : null,
    h("div", { class: "hero-row" }, HEAD.filter(m => mean(m) != null).map(m => tile(term(m), f2(mean(m)), m === "error_rate" && mean(m) > WARN_ERR ? failedWords(mean(m)) : spread(cm[m]), warnClass(m, mean(m)), change(m) || (c && c.warning ? "not compared" : null))),
      pa.cost != null ? tile("Cost / answer", money(pa.cost), u.cost != null ? `${money(u.cost)} in all` : "") : null,
      secsPer != null ? tile("Seconds / answer", secs(secsPer), "the system's time, not the judge's") : null)];
}
const answerSeconds = rows => { const t = rows.map(r => r.total_s).filter(x => typeof x === "number"); return t.length ? t.reduce((a, b) => a + b, 0) / t.length : null; };

// What explains the headline: every measured score with its change, why questions failed, repeats, problems, the judge.
function runStats(S, c) {
  const cm = S.metrics, mean = m => cm[m] && cm[m].mean, pm = c && !c.warning ? c.metrics : {}, refWord = D.vs_baseline ? "baseline" : "run before";
  const vsHead = h("span", {}, `vs ${refWord}${c ? `, ${day(c.a)}` : ""}`, c && c.warning ? note(c.warning) : null, c ? c.notes.map(note) : null, " ", qmark("paired"));
  if (c && (c.errors.newly.length || c.errors.recovered.length)) vsHead.append(note((c.errors.newly.length ? `Newly failing: ${c.errors.newly.join(", ")}. ` : "") + (c.errors.recovered.length ? `Recovered: ${c.errors.recovered.join(", ")}.` : "")));
  const vs = m => { const p = pm[m]; return !p || p.delta == null ? h("span", { class: "flat", text: c && c.warning ? "not compared" : "–" }) : h("span", {}, sgn(p.delta), " ", verdict(p.verdict), p.ci ? h("small", { class: "ci", text: ` (${sgn(p.ci[0])} to ${sgn(p.ci[1])})` }) : null); };
  const rows = [];
  for (const [group, keys] of GROUPS) {
    const have = keys.filter(m => mean(m) != null);
    if (!have.length) continue;
    rows.push({ group });
    for (const m of have) {
      const s = cm[m], a = S.metrics_answered && S.metrics_answered[m];
      rows.push([[term(m), plainLine(m)], [h("span", { class: warnClass(m, s.mean), text: f2(s.mean) }), a && a.mean != null && S.counts.system_errors && Math.abs(a.mean - s.mean) >= 0.005 ? note(`${name(m)}: counting only answers the system gave, the score is ${f2(a.mean)}.`) : null],
        h("span", { class: "ci" }, lbl("95% CI "), spread(s) || "–"), h("span", {}, lbl(`vs ${refWord} `), vs(m))]);
    }
  }
  const out = [h("h2", { text: "Scores" }), caption("A system error counts as 0. Scores this run did not measure are left out."), table("narrow scores", ["Measure", "Score", ["95% CI ", qmark("ci")], vsHead], rows)];
  const tail = [], pw = S.power && (S.power.correctness || Object.values(S.power).find(Boolean));
  if (S.power && !pw && Object.keys(S.power).length) tail.push("Cannot estimate how many questions are needed: the scores have no spread.");
  if (pw) tail.push(`To see a ${c ? c.detect : 0.05} change in a score with 80% chance, about ${plural(pw.needed, "question")} are needed (${pw.basis === "repeats" ? "from how much one question wobbles between repeats" : "a rule of thumb, from the spread of the scores"}).`);
  if (c && !c.warning) tail.push(`A real change needs ${c.min_pairs} or more shared questions; this comparison has ${c.shared}.`);
  if (tail.length) out.push(h("p", { class: "small", text: tail.join(" ") }));
  const cs = S.causes;
  if (cs && cs.questions.length) out.push(h("h2", { text: "Why questions failed" }), h("p", { class: "intro", text: Object.entries(cs.counts).filter(e => e[1]).map(e => `${e[0]}: ${e[1]}`).join(", ") + ". Retrieval: the right page was not found. Generation: found, answered wrong. Judge?: the marking looks odd. System: it errored." }),
    h("ul", { class: "plain" }, cs.questions.map(q => h("li", {}, h("b", { text: q.id }), " ", h("em", { text: q.cause }), ". ", h("span", { class: "muted", text: q.why })))));
  const k = S.consistency;
  if (k) out.push(h("h2", { text: "Same answer every time?" }), h("p", {}, h("b", { text: (k.pass_all * 100).toFixed(0) + "%" }), ` of ${k.questions} questions were answered well on every repeat${k.left_out ? ` (${k.left_out} left out: a repeat was not scored)` : ""}. `, h("span", { class: "muted", text: G.pass_all.formula })),
    k.flaky.length ? h("ul", { class: "plain" }, k.flaky.map(x => h("li", {}, h("b", { text: x.id }), ` ${name("correctness")} between ${Math.min(...x.scores).toFixed(2)} and ${Math.max(...x.scores).toFixed(2)} (${x.scores.join(", ")})`))) : h("p", { class: "muted", text: "No flaky questions." }));
  if (S.failures && S.failures.length) out.push(h("h2", { text: "System errors" }), h("ul", { class: "plain" }, S.failures.map(x => h("li", {}, h("b", { text: x.id }), " ", h("span", { class: "muted", text: x.error })))));
  if (D.judge_check) out.push(h("h2", { text: "Judge reliability" }), markerCheck(D.judge_check, D.judge_checked_since));
  return out;
}

// Tokens and cost, where the system or the judge reported them (Nasute records them; it never needs them).
const money = c => c == null ? null : c > 0 && c < 0.0001 ? "under US$0.0001" : c < 0.01 ? `US$${c.toFixed(4)}` : `US$${c.toFixed(2)}`;
function useLine(tin, tout, cost, jtok, jcost) {
  const parts = [];
  if (tin != null || tout != null) parts.push(`${tin ?? "?"} tokens in, ${tout ?? "?"} out`);
  if (cost != null) parts.push(money(cost));
  if (jtok != null || jcost != null) parts.push(`judging ${jtok ?? "?"} tokens${jcost != null ? `, ${money(jcost)}` : ""}`);
  return parts.join("; ");
}

// One entry per question from its rows (one row per repeat). `n` is its place in the results file, which is the dataset's order (shortcut: results are written in dataset order; the id stays the real key, runs are paired by it): its tags, difficulty, the mean of each score over the repeats and its outcome.
function questions(rows, cause, worse = new Set(), mode, P = 0.75) {
  const by = new Map();
  for (const r of rows) { if (!by.has(r.id)) by.set(r.id, []); by.get(r.id).push(r); }
  return [...by].map(([id, reps], i) => {
    const means = {};
    for (const m of SCORES) { const v = reps.map(r => r.scores[m]).filter(x => x != null); means[m] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }
    const un = reps[0].answerable === false;
    const avg = k => { const v = reps.map(r => r[k]).filter(x => typeof x === "number"); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
    return { id, n: i + 1, reps, tags: reps[0].tags, difficulty: reps[0].difficulty, topic: reps[0].topic || "", means, cause: cause.get(id) || "", worse: worse.has(id),
      per: { seconds: avg("total_s"), tokens: avg("tokens_out"), cost: avg("cost") },
      out: outcome(un ? means.abstention : means.correctness, un, reps.filter(r => r.error).length, reps.length, mode, P) };
  });
}
const OUT_RANK = { bad: 0, part: 1, na: 2, good: 3 };
const FEW = 10;   // questions a phone shows before "Show all"
// Every outcome word outcome() can give, in the order the bars stack them, with its colour class (Okabe and Ito's colour-blind-safe set, in report.css).
// Not judged is pale grey, never a bad colour: nothing was measured.
const OUTCOMES = [["right", "o-right"], ["right, with an error", "o-part"], ["partly right", "o-part"], ["wrong", "o-wrong"], ["system error", "o-err"],
  ["declined", "o-dec"], ["declined, with an error", "o-decpart"], ["made something up", "o-made"], ["not judged", "o-na"]];
// At a glance: one stacked bar per group (easy, medium, hard, or one "all"), a segment per outcome. Tapping a segment filters the list.
function glance(groups, pick) {
  groups.sort((a, b) => groupRank(a[0]) - groupRank(b[0]));
  const total = {};
  const bars = groups.map(([g, c]) => {
    const n = Object.values(c).reduce((a, b) => a + b, 0);
    for (const [w, k] of Object.entries(c)) total[w] = (total[w] || 0) + k;
    return h("div", { class: "grow" }, h("span", { class: "glabel", text: `${groupName(g)} · ${n}` }), h("div", { class: "gbar" }, OUTCOMES.filter(([w]) => c[w]).map(([w, cls]) => {
      const b = h("button", { type: "button", class: "seg " + cls, text: c[w], title: `${groupName(g)}: ${c[w]} ${w}`, "aria-label": `${groupName(g)}: ${c[w]} ${w}. Show them in the list` });
      b.style.flexGrow = c[w];
      b.addEventListener("click", () => pick(g, w));
      return b;
    })));
  });
  return [h("h2", { text: "At a glance" }), h("div", { class: "glance" }, bars),
    h("div", { class: "legend" }, OUTCOMES.filter(([w]) => total[w]).map(([w, cls]) => h("span", { class: "key" }, h("span", { class: "sw " + cls, "aria-hidden": "true" }), `${w} ${total[w]}`))),
    caption(`${groups.length > 1 ? "A bar per difficulty; each" : "Each"} block is an outcome, as wide as its number of questions. Tap a block to list those questions.`)];
}

function run() {
  const S = D.summary, P = S.pass_at, cause = new Map((S.causes ? S.causes.questions : []).map(q => [q.id, q.cause])), worse = new Set(D.worse);
  const qs = questions(D.rows, cause, worse, S.judge_mode, P);
  const cols = SCORES.filter(m => qs.some(q => q.means[m] != null));
  const open = id => { location.hash = "q-" + encodeURIComponent(id); };   // the question view is the same page, shown for #q-<id>
  const list = h("div"), detail = h("div", { hidden: true });
  add(list, detail);
  const put = (...x) => list.append(...x.flat(Infinity).filter(c => c != null && c !== false));   // like add(), into the table view
  const home = [D.dataset_href, D.suite.dataset];
  put(crumbs(home, [null, when(S.run)]), h("h1", { text: D.suite.target_label || D.suite.target }),
    h("p", { class: "dateline" }, `Run of ${when(S.run)} on ${S.dataset.name} v${ver(S.dataset.version)}. ${runLabel(S)}${D.label ? `, “${D.label}”` : ""}${D.baseline ? ", the baseline" : ""}. ${S.counts_line}. `,
      S.aborted ? note(`Stopped early: ${S.aborted}. ${plain("aborted")}`) : null, S.incomplete ? note(`Incomplete: too many judge errors. ${plain("incomplete")}`) : null,
      D.compare_href ? [h("a", { href: D.compare_href, text: "What changed since the run before" }), ". "] : null),
    headline(S, D.compare));

  const state = { view: "all", cause: "", tag: "", text: "", sort: "n", dir: 1, page: 1, out: "", group: "", all: false };   // out, group: a tapped at-a-glance segment; all: the phone list opened past FEW
  const select = (label, key, options) => { const s = h("select", { "aria-label": label }, options.map(([v, t]) => h("option", { value: v, text: t }))); s.addEventListener("change", () => { state[key] = s.value; state.page = 1; render(); }); return s; };
  const search = h("input", { type: "search", placeholder: "Search id, question, answer", "aria-label": "Search" });
  search.addEventListener("input", () => { state.text = search.value.toLowerCase(); state.page = 1; render(); });
  const causes = [...new Set(qs.map(q => q.cause).filter(Boolean))], tags = [...new Set(qs.flatMap(q => q.tags))].sort();
  const count = h("span", { class: "small" }), tbody = h("tbody"), head = h("tr"), pagers = [h("div", { class: "pager" }), h("div", { class: "pager" })];
  const VIEWS = { all: () => true, bad: q => q.out.cls !== "good", good: q => q.out.cls === "good", failed: q => q.cause, worse: q => q.worse };
  const matches = q => VIEWS[state.view](q) && (!state.out || q.out.word === state.out) && (!state.group || glanceOf(q)[0] === state.group) && (!state.cause || q.cause === state.cause) && (!state.tag || q.tags.includes(state.tag)) &&
    (!state.text || [q.id, ...q.tags, ...q.reps.flatMap(r => [r.question, r.answer])].some(t => t.toLowerCase().includes(state.text)));
  // on a phone only the number, the question and its outcome show; the scores are a tap away on the question
  const heads = [["n", "#"], ["question", "Question"], ["out", "Outcome"], ...cols.map(m => [m, name(m)]), ["tags", "Topics"], ["difficulty", "Difficulty"], ["cause", "Cause"]];
  const LEFT = new Set(["question", "out", "tags", "cause", "difficulty"]), WIDE = new Set(["n", "question", "out"]), MID = new Set(["tags", "difficulty", "cause"]);   // MID: shown on a wide screen only
  const key = (q, k) => k === "n" ? q.n : k === "question" ? q.reps[0].question.toLowerCase() : k === "out" ? OUT_RANK[q.out.cls] * 10 + (q.out.word.length / 100) : k === "tags" ? q.tags.join(" ") : k === "difficulty" ? (DIFF[q.difficulty] ?? 3) : k === "cause" ? q.cause : q.means[k];
  const current = () => qs.filter(matches).sort((a, b) => { const x = key(a, state.sort), y = key(b, state.sort); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * state.dir || a.n - b.n; });
  const glanceOf = qs.some(q => q.difficulty) ? q => [q.difficulty || "unknown"] : () => ["all"];
  const filtered = h("p", { class: "small", hidden: true }), moreBtn = h("button", { type: "button", class: "link" });
  moreBtn.addEventListener("click", () => { state.all = true; render(); });
  const pickSegment = (group, word) => { Object.assign(state, { out: word, group: group === "all" ? "" : group, page: 1, all: true }); render(); document.getElementById("questions").scrollIntoView(); };
  put(glance(outcomeCounts(qs, glanceOf), pickSegment));
  const tally = new Map();
  for (const q of qs) tally.set(q.out.word, (tally.get(q.out.word) || 0) + 1);
  const order = [...tally].sort((a, b) => OUT_RANK[qs.find(q => q.out.word === b[0]).out.cls] - OUT_RANK[qs.find(q => q.out.word === a[0]).out.cls]);
  put(h("h2", { id: "questions", text: "Questions" }),
    h("p", { class: "tally" }, order.map(([w, n], i) => [i ? " · " : "", mark({ ...qs.find(q => q.out.word === w).out, word: `${n} ${w}` })])),
    caption(`Mean over repeats; right means ${name("correctness")} ${P} or more. Tap a question to read it, its answer and how it was marked.`),
    h("div", { class: "bar" }, select("Show", "view", [["all", "All questions"], ["bad", "Not right"], ["good", "Right"], ["failed", "Failed, with a cause"], ["worse", "Got worse"]]),
      causes.length ? select("Cause", "cause", [["", "Any cause"], ...causes.map(c => [c, c])]) : null, tags.length ? select("Topic", "tag", [["", "Any topic"], ...tags.map(t => [t, t])]) : null, search, count),
    filtered, pagers[0], h("div", { class: "scroll" }, h("table", { class: "q" }, h("thead", {}, head), tbody)), moreBtn, pagers[1]);
  heads.forEach(([k, t]) => {
    const b = h("button", { type: "button", class: "sort", text: t });
    b.addEventListener("click", () => { state.dir = state.sort === k ? -state.dir : 1; state.sort = k; state.page = 1; render(); });
    head.append(h("th", { "aria-sort": "none", "data-k": k, class: (LEFT.has(k) ? "left" : "") + (WIDE.has(k) ? "" : " sm-hide") + (MID.has(k) ? " md-hide" : "") }, b, G[k] ? qmark(k) : null));
  });
  function render() {
    head.querySelectorAll("th").forEach(th => th.setAttribute("aria-sort", th.dataset.k === state.sort ? (state.dir > 0 ? "ascending" : "descending") : "none"));
    const shown = current(), pr = pageRange(shown.length, state.page, PER_PAGE);
    state.page = pr.page;
    count.textContent = `Showing ${shown.length} of ${qs.length}`;
    // on a phone a long list stops at FEW rows with "Show all", so the charts and scores below are not thousands of pixels away
    const cut = phone.matches && !state.all && pr.to - pr.from > FEW ? pr.from + FEW : pr.to;
    moreBtn.hidden = cut === pr.to; moreBtn.textContent = `Show all ${pr.to - pr.from} questions`;
    filtered.hidden = !state.out;
    if (state.out) {
      const clear = h("button", { type: "button", class: "link", text: "Show every outcome" });
      clear.addEventListener("click", () => { Object.assign(state, { out: "", group: "", page: 1 }); render(); });
      filtered.replaceChildren(`Only ${state.out}${state.group ? ", " + state.group : ""}. `, clear);
    }
    for (const p of pagers) {
      const go = (to, text, off) => { const b = h("button", { type: "button", text, disabled: off }); b.addEventListener("click", () => { state.page = to; render(); }); return b; };
      p.replaceChildren(...(pr.pages > 1 ? [go(pr.page - 1, "← Previous", pr.page === 1), h("span", { class: "small", text: ` Page ${pr.page} of ${pr.pages}: questions ${pr.from + 1} to ${pr.to} ` }), go(pr.page + 1, "Next →", pr.page === pr.pages)] : []));
    }
    tbody.replaceChildren();
    for (const q of shown.slice(pr.from, cut)) {
      const tr = h("tr", { class: "item", "data-id": q.id }, h("td", { text: q.n }),
        h("td", { class: "left" }, h("a", { class: "qlink", href: "#q-" + encodeURIComponent(q.id), text: shorten(q.reps[0].question, 110) }), h("span", { class: "qid", text: q.id }), q.worse ? h("span", { class: "down flag", text: "worse" }) : null),
        h("td", { class: "left" }, mark(q.out)),
        cols.map(m => h("td", { class: "sm-hide " + (m === "correctness" && q.means[m] != null && q.means[m] < P ? "down" : ""), text: f2(q.means[m]) })),
        h("td", { class: "left small sm-hide md-hide wrap", text: q.tags.join(", ") }), h("td", { class: "left sm-hide md-hide", text: q.difficulty }), h("td", { class: "left sm-hide md-hide", text: q.cause }));
      tr.addEventListener("click", e => { if (!e.target.closest("a, .term")) open(q.id); });
      tbody.append(tr);
    }
  }
  const figs = chartsSection(qs, open);
  if (figs) put(h("h2", { text: "Charts" }), h("p", { class: "intro", text: "Each dot is one question. Click one to open it." }), figs);
  put(runStats(S, D.compare));
  put(h("h2", { class: "quiet", text: "Details" }),
    more("By topic and difficulty", groupTable(S.tags, "Topic"), h("div", { class: "gap" }), groupTable(S.difficulty || {}, "Difficulty")),
    h("p", { class: "small" }, "Download: ", h("a", { href: `${S.run}.csv`, download: "", text: "CSV" }), " · ", h("a", { href: `${S.run}.results.jsonl`, download: "", text: "JSON lines" }), " · ", h("a", { href: `${S.run}.summary.json`, download: "", text: "summary" }), "."),
    h("p", { class: "small", text: `System: ${S.target}, model ${S.answering_model}. Judge: ${S.judge_model} (${S.judge_mode}). Questions: ${S.dataset.name} v${ver(S.dataset.version)} (${S.dataset.sha256.slice(0, 8)}). Code ${S.commit}. Took ${Math.round(S.total_s)} s. ${S.usage && useLine(S.usage.tokens_in, S.usage.tokens_out, S.usage.cost, S.usage.judge_tokens, S.usage.judge_cost) ? `Whole run: ${useLine(S.usage.tokens_in, S.usage.tokens_out, S.usage.cost, S.usage.judge_tokens, S.usage.judge_cost)}. ` : ""}${D.vs ? `“Worse” is measured against the run of ${when(D.vs)}.` : "“Worse” needs an earlier run to measure against."}` }),
    D.judge_check ? null : h("p", { class: "small", text: "No judge check yet for this judge and mode. Run: nasute judge-check" }));

  // The question view: one question across the whole page, with Previous and Next in the order the table is showing.
  function question(q) {
    const ids = current().map(x => x.id), at = ids.indexOf(q.id), seq = at < 0 ? qs.map(x => x.id) : ids, i = seq.indexOf(q.id), r0 = q.reps[0];
    const go = (id, text) => id ? h("a", { href: "#q-" + encodeURIComponent(id), text }) : h("span", { class: "muted", text });
    const nav = () => h("p", { class: "qnav" }, go(seq[i - 1], "← Previous question"), " · ", go(seq[i + 1], "Next question →"), at < 0 ? h("span", { class: "muted", text: " (in dataset order: this question is hidden by the table's filters)" }) : null);
    detail.replaceChildren(crumbs(home, ["#", when(S.run)], [null, `Question ${q.n}`]),
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
      if (back && lastId) { const at = current().findIndex(x => x.id === lastId); if (at >= 0) { state.page = Math.floor(at / PER_PAGE) + 1; if (at % PER_PAGE >= FEW) state.all = true; } }
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
  add(crumbs([D.dataset_href, D.suite.dataset], [null, "What changed"]), h("h1", { text: "What changed" }), h("p", { class: "lede", text: D.suite.target_label }),
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

({ overview, dataset, run, compare })[D.page]();
