"""The report: a folder of static pages that open straight from disk (file://) or from any web server.

What it does: turns the saved runs into three levels of page. index.html is the dashboard: each dataset with its systems
ranked by their latest main score, and a table of recent runs across all datasets that can be ticked and compared.
datasets/<name>.html is one dataset: its systems, every run on it (tick any to compare them question by question, with the
paired statistics), and the over-time charts. <suite>/runs/<run>.html is one run: its scores, every question, then the charts.
<suite>/compare/<a>-<b>.html is the full comparison of a suite's latest run with its reference run.
<suite>/index.html, the old suite page, is now a small page that sends the reader on to the dataset page, so old links work.
How it runs: nasute calls write() after every run and for `nasute report`. Nothing runs in the background.
Reads: the runs folder (summary.json, results.jsonl, index.json). Writes: the report folder, and only these things:
the pages, assets/ (copied from this folder's assets/), datasets/ (rebuilt every time) and, in each suite folder (marked by
a .nasute-suite file), runs/ and compare/, which are rebuilt every time, and runs.csv. Beside each run page go its downloads: <run>.csv,
<run>.results.jsonl and <run>.summary.json (the same CSV code as `nasute runs export`). A suite folder with no runs left is removed, but only if it carries
that marker. A leftover index.json from the old report is removed. Nothing is written through a symlink or outside the
report folder. Give the report its own folder.
A score with nothing to show is left out of every page (see measured() in __init__.py): the saved runs are not changed, only what is drawn.
shortcut: a suite folder made before the .nasute-suite marker existed is never removed by itself; delete it by hand once.
Each page holds its data as JSON in one <script type="application/json"> block (a "<" is written \\u003c, so text from a
dataset or an answer can never end the block) and assets/report.js draws it. All text goes in with textContent.
shortcut: every page embeds all its data, about 15 KB per answer in claims mode (a 32-question, 3-repeat deep run is about
1.5 MB). Past a few MB a page gets slow, and write() logs a warning at 2 MB; the fix then is the run's data in a .json beside the page and `serve`.
"""
import hashlib
import html
import json
import math
import re
import shutil
from pathlib import Path

import nasute as N

HERE = Path(__file__).resolve().parent
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" type="image/png" href="{up}assets/favicon.png">
<link rel="apple-touch-icon" href="{up}assets/apple-touch-icon.png">
<link rel="stylesheet" href="{up}assets/uPlot.min.css">
<link rel="stylesheet" href="{up}assets/report.css">
</head>
<body>
<main id="app"><noscript>This page needs JavaScript to show its data.</noscript></main>
<script id="data" type="application/json">{data}</script>
{charts}<script src="{up}assets/uPlot.iife.min.js"></script>
<script src="{up}assets/report.js"></script>
</body>
</html>
"""
# Chart.js and its boxplot plugin (vendored, see README) are loaded only by the run page, which draws the per-question charts.
CHART_SCRIPTS = '<script src="{up}assets/chart.umd.min.js"></script>\n<script src="{up}assets/chartjs-chart-boxplot.umd.min.js"></script>\n'
BIG = 2_000_000   # bytes: a page over this gets a warning in the log


MARK = ".nasute-suite"


def slug(suite):
    """The suite's folder name: the id itself when it is plain (always, for ids made from allowed names). Otherwise a cleaned
    copy plus a short hash of the id, so two different ids never share a folder."""
    plain = re.sub(r"[^\w.@-]", "_", suite)
    return suite if plain == suite and re.match(r"\w", suite) and ".." not in suite else plain.lstrip(".") + "~" + hashlib.sha1(suite.encode()).hexdigest()[:8]   # "~" is not allowed in a name, so this never equals a real id


def finite(node):
    """NaN and Infinity become None: JSON.parse refuses them, and one bad number would blank the whole page (runs saved before 0.1.0 may hold them)."""
    if isinstance(node, float) and not math.isfinite(node):
        return None
    if isinstance(node, dict):
        return {k: finite(v) for k, v in node.items()}
    return [finite(x) for x in node] if isinstance(node, list) else node


def embed(data):
    return json.dumps(finite(data), ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")


# The old suite page's address: a page with no script that sends the reader on to the dataset page.
MOVED = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url={href}">
<title>Moved · Nasute</title>
</head>
<body>
<p>This page has moved to <a href="{href}">{text}</a>.</p>
</body>
</html>
"""
PAIRS_MAX = 30   # runs per dataset whose every pair gets paired statistics on the dataset page


def masked(s, rows, keep):
    """A copy of the summary and rows with every score not in `keep` set to None, for the page only (the saved run is unchanged)."""
    gone = [m for m in N.METRICS if m not in keep]
    groups = lambda g: {k: {m: (None if m in gone else v) for m, v in d.items()} for k, d in (g or {}).items()}
    s = {**{k: v for k, v in s.items() if k != "settings"}, "k": s["settings"].get("k"), "measured": keep,
         "metrics": {m: ({"mean": None, "ci": None} if m in gone else v) for m, v in s["metrics"].items()},
         "metrics_answered": {m: v for m, v in (s.get("metrics_answered") or {}).items() if m not in gone},
         "tags": groups(s.get("tags")), "difficulty": groups(s.get("difficulty"))}
    return s, [{**r, "scores": {m: (None if m in gone else v) for m, v in r["scores"].items()}} for r in rows]


def answer_seconds(rows):
    """Mean seconds the system took per answer (not the judging), or None."""
    t = [r["total_s"] for r in rows if isinstance(r.get("total_s"), (int, float))]
    return round(sum(t) / len(t), 2) if t else None


def slim(s, meta, suite, info, rows):
    """What the dashboard, the dataset page and the charts need from a run: names, scores (masked), cost and speed."""
    return {"run": s["run"], "suite": suite, "folder": info["folder"], "target": info["target"], "target_label": info["target_label"],
            "profile": s.get("profile", ""), "judge_mode": s.get("judge_mode"), "repeats": s.get("repeats"), "counts_line": s.get("counts_line", ""),
            "aborted": s.get("aborted"), "questions": s.get("questions"), "incomplete": s.get("incomplete"), "dataset": {k: s["dataset"][k] for k in ("name", "version", "sha256")}, "total_s": s.get("total_s"),
            "metrics": {m: {"mean": v.get("mean"), "ci": v.get("ci")} for m, v in s["metrics"].items()}, "measured": s["measured"], "label": meta["labels"].get(s["run"], ""),
            "baseline": meta["baselines"].get(suite) == s["run"], "answering_model": s.get("answering_model"), "judge_model": s.get("judge_model"), "k": s.get("k"), "usage": s.get("usage"),
            "answer_s": answer_seconds(rows)}


def grid_entry(rows):
    """One run's question-by-question outcome for the dataset page's compare: {id: [score, unanswerable 0/1, system errors, attempts]}.
    The score is correctness for a question with an answer, abstention for one without, each the mean over repeats."""
    out = {}
    for r in rows:
        out.setdefault(r["id"], []).append(r)
    def mean(v):
        v = [x for x in v if x is not None]
        return round(sum(v) / len(v), 3) if v else None
    return {i: [mean([r["scores"].get("abstention" if r.get("answerable", True) is False else "correctness") for r in reps]),
                int(reps[0].get("answerable", True) is False), sum(1 for r in reps if r.get("error")), len(reps)] for i, reps in out.items()}


def paired_brief(c, keep):
    """The parts of a compare() the dataset page shows for a pair of runs: headline verdicts, notes, no per-question lists."""
    return {"warning": c["warning"], "notes": c["notes"], "shared": c["shared"], "min_pairs": c["min_pairs"],
            "metrics": {m: {k: p.get(k) for k in ("a", "b", "delta", "ci", "verdict")} for m, p in c["metrics"].items() if m in keep and p.get("delta") is not None}}


def judge_lines(cfg, sums, run_folder):
    """For the line under the dashboard: each judge model, mode and set of prompts seen in runs, with its latest judge check. Names, dates and scores only."""
    judges = {}
    for run_id, s in sums.items():
        if s.get("judge_model"):
            p = s.get("judge_prompts")
            j = judges.setdefault((s["judge_model"], s.get("judge_mode") or "quick", json.dumps(p, sort_keys=True)),
                                  {"model": s["judge_model"], "mode": s.get("judge_mode") or "quick", "prompts": p, "custom": (p or {}).get("custom", []), "fence": bool((p or {}).get("fence")), "runs": 0})
            j.update(runs=j["runs"] + 1, last_run=run_id, folder=run_folder.get(run_id))
    return [{**{k: v for k, v in j.items() if k != "prompts"}, "check": N.latest_judge_check(cfg, j["model"], j["mode"], j["prompts"], full=True)} for j in judges.values()]


def write(cfg):
    """-> the suites written: {suite: [run ids]}."""
    out = N.folder(cfg["report"])
    out.mkdir(parents=True, exist_ok=True)
    root = out.resolve()

    def guard(path):
        """Stop rather than write or delete through a symlink, or anywhere outside the report folder."""
        if path.resolve() != root / path.relative_to(out):
            raise SystemExit(f"{path} is a symlink or leads outside the report folder; the report was not written")
        return path

    guard(out / "assets").mkdir(exist_ok=True)
    for f in (HERE / "assets").iterdir():
        shutil.copyfile(f, guard(out / "assets" / f.name))
    (out / "index.json").unlink(missing_ok=True)

    def emit(path, title, data):
        guard(path)
        up = "../" * (len(path.relative_to(out).parts) - 1)
        text = PAGE.format(title=title.replace("&", "&amp;").replace("<", "&lt;"), up=up, charts=CHART_SCRIPTS.format(up=up) if data["page"] == "run" else "", data=embed({"glossary": N.GLOSSARY, **data}))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if len(text.encode()) > BIG:
            N.log("page_large", 30, page=str(path.relative_to(out)), bytes=len(text.encode()))

    def export(folder, run_id, s, rows):
        """Beside the run page: its attempts as CSV, its saved results, and its summary (through public() again, so no header value or key can get out)."""
        folder.mkdir(exist_ok=True)
        with guard(folder / f"{run_id}.csv").open("w", newline="", encoding="utf-8") as f:
            N.run_csv(s, rows, f)
        results = N.folder(cfg["runs"]) / run_id / "results.jsonl"
        guard(folder / f"{run_id}.results.jsonl").write_text(results.read_text() if results.exists() else "")
        # usage is only numbers we recorded (tokens, cost), not settings: kept out of public(), which hides anything named like "token"
        guard(folder / f"{run_id}.summary.json").write_text(json.dumps({**N.public({k: v for k, v in s.items() if k != "usage"}), "usage": s.get("usage")}, indent=1))

    target_label = lambda t: str((cfg["targets"].get(t) or {}).get("label") or t)   # a label is only a display name
    sums, meta = N.summaries(cfg), N.run_meta(cfg)

    def marker_check(s):
        """The newest judge-check for this run's judge model, mode and prompts, looked up now (not when the run was made), so an old run shows a later check too."""
        jc = N.latest_judge_check(cfg, s.get("judge_model"), s.get("judge_mode"), s.get("judge_prompts"), full=True)
        return {"judge_check": jc, "judge_checked_since": bool(jc) and jc["run"] != (s.get("judge_reliability") or {}).get("run")}
    dataset_href = lambda name, up: f"{up}datasets/{slug(name)}.html"
    suites, run_folder = {}, {}
    for run_id, s in sums.items():
        suites.setdefault(N.suite_of(s), []).append(run_id)
    infos, slims, keeps, grids, texts, written = {}, {}, {}, {}, {}, set()
    for key, ids in suites.items():
        first = sums[ids[0]]
        info = {"id": key, "folder": slug(key), "dataset": first["dataset"]["name"], "target": first.get("target", ""), "target_label": target_label(first.get("target", ""))}
        infos[key] = info
        base = guard(out / info["folder"])
        for sub in ("runs", "compare"):
            shutil.rmtree(guard(base / sub), ignore_errors=True)
        base.mkdir(exist_ok=True)
        guard(base / MARK).write_text("made by nasute pages.py; removed when the suite has no runs left\n")
        latest = ids[-1]
        ref = N.reference_run(cfg, sums, latest)
        c = N.compare(cfg, ref, latest) if ref else None
        href = f"compare/{ref}-{latest}.html" if c else None
        pairs = []
        for run_id in ids:
            run_folder[run_id] = info["folder"]
            s, rows = N.read_run(cfg, run_id)
            pairs.append((s, rows))
            export(guard(base / "runs"), run_id, s, rows)
            keep = keeps[run_id] = N.measured(rows)
            ms, mrows = masked(s, rows, keep)
            slims[run_id] = slim(ms, meta, key, info, rows)
            grids[run_id] = grid_entry(mrows)
            for r in rows:
                texts.setdefault(info["dataset"], {}).setdefault(r["id"], r["question"])
            r = N.reference_run(cfg, sums, run_id)
            vs = N.compare(cfg, r, run_id) if r else None
            emit(base / "runs" / f"{run_id}.html", f"Run {run_id} · {key} · Nasute", {
                "page": "run", "suite": info, "dataset_href": dataset_href(info["dataset"], "../../"), "summary": ms, "rows": mrows, "label": meta["labels"].get(run_id, ""),
                "baseline": meta["baselines"].get(key) == run_id, "vs": r if vs and not vs["warning"] else None, "worse": sorted({w["id"] for w in vs["worse"]}) if vs else [],
                "compare": vs, "vs_baseline": bool(r) and meta["baselines"].get(key) == r, "compare_href": f"../{href}" if run_id == latest and href else None, "pass_at": cfg["pass_at"], **marker_check(s)})
            if run_id == latest:
                latest_rows = rows
        if c:
            ra = {r["id"]: r for r in reversed(N.read_run(cfg, ref)[1])}   # first repeat of each question
            rb = {r["id"]: r for r in reversed(latest_rows)}
            keep = lambda r: r and {k: r[k] for k in ("answer", "sources", "scores", "reasons", "error")}
            changed = sorted({w["id"] for w in c["worse"] + c["better"]})
            emit(base / href, f"{ref} to {latest} · {key} · Nasute", {
                "page": "compare", "suite": info, "dataset_href": dataset_href(info["dataset"], "../../"), "compare": c, "labels": {ref: meta["labels"].get(ref, ""), latest: meta["labels"].get(latest, "")},
                "items": [{"id": i, "question": rb[i]["question"], "reference": rb[i]["reference"], "a": keep(ra.get(i)), "b": keep(rb.get(i))} for i in changed if i in rb]})
        with guard(base / "runs.csv").open("w", newline="", encoding="utf-8") as f:
            N.suite_csv(pairs, f)
        moved = html.escape(dataset_href(info["dataset"], "../") + "#system=" + info["target"])
        guard(base / "index.html").write_text(MOVED.format(href=moved, text=html.escape(info["dataset"])))
        written.add(info["folder"])
    for d in out.iterdir():   # suites whose runs are all gone
        if d.is_dir() and not d.is_symlink() and (d / MARK).exists() and d.name not in written:
            shutil.rmtree(guard(d))

    # one page per dataset, every system's runs on it
    shutil.rmtree(guard(out / "datasets"), ignore_errors=True)
    by_dataset = {}
    for run_id, s in sums.items():
        by_dataset.setdefault(s["dataset"]["name"], []).append(run_id)
    cards = []
    for name, ids in by_dataset.items():
        sha = sums[ids[-1]]["dataset"]["sha256"]
        same = [i for i in ids if sums[i]["dataset"]["sha256"] == sha][-PAIRS_MAX:]   # shortcut: only the newest PAIRS_MAX runs of the newest file are paired; `nasute compare A B` does any two
        paired = {}
        for i, a in enumerate(same):
            for b in same[i + 1:]:
                paired[f"{a} {b}"] = paired_brief(N.compare(cfg, a, b), set(keeps[a]) & set(keeps[b]))
        systems = [infos[k] for k in suites if infos[k]["dataset"] == name]
        mis = N.mislabels(cfg, [N.read_run(cfg, i)[1] for i in same])
        runs = [slims[i] for i in ids]
        emit(out / "datasets" / f"{slug(name)}.html", f"{name} · Nasute", {
            "page": "dataset", "name": name, "systems": systems, "runs": runs, "grid": {i: grids[i] for i in ids}, "questions": texts.get(name, {}),
            "paired": paired, "mislabels": mis, "pass_at": cfg["pass_at"], "k": runs[-1]["k"]})
        cards.append({"name": name, "href": dataset_href(name, ""), "runs": len(ids), "latest": [slims[[i for i in ids if sums[i].get("target", "") == t["target"]][-1]] for t in systems]})
    runs = sorted(slims.values(), key=lambda r: r["run"], reverse=True)
    emit(out / "index.html", "Nasute", {"page": "overview", "judges": judge_lines(cfg, sums, run_folder), "datasets": cards, "runs": runs,
                                        "pass_at": cfg["pass_at"], "generated": N.datetime.now(N.timezone.utc).isoformat(timespec="seconds")})
    N.log("report_written", suites=len(suites), runs=len(sums), folder=str(out))
    return suites
