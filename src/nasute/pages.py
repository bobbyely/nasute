"""The report: a folder of static pages that open straight from disk (file://) or from any web server.

What it does: turns the saved runs into index.html (every suite), <suite>/index.html (charts and the latest scores),
<suite>/runs/<run>.html (every question of one run) and <suite>/compare/<a>-<b>.html (what changed between two runs).
How it runs: nasute calls write() after every run and for `nasute report`. Nothing runs in the background.
Reads: the runs folder (summary.json, results.jsonl, index.json). Writes: the report folder, and only these things:
the pages, assets/ (copied from this folder's assets/) and, in each suite folder (marked by a .nasute-suite file),
runs/ and compare/, which are rebuilt every time, and runs.csv. Beside each run page go its downloads: <run>.csv,
<run>.results.jsonl and <run>.summary.json (the same CSV code as `nasute runs export`). A suite folder with no runs left is removed, but only if it carries
that marker. A leftover index.json from the old report is removed. Nothing is written through a symlink or outside the
report folder. Give the report its own folder.
shortcut: a suite folder made before the .nasute-suite marker existed is never removed by itself; delete it by hand once.
Each page holds its data as JSON in one <script type="application/json"> block (a "<" is written \\u003c, so text from a
dataset or an answer can never end the block) and assets/report.js draws it. All text goes in with textContent.
shortcut: every page embeds all its data, about 15 KB per answer in claims mode (a 32-question, 3-repeat deep run is about
1.5 MB). Past a few MB a page gets slow, and write() logs a warning at 2 MB; the fix then is the run's data in a .json beside the page and `serve`.
"""
import hashlib
import json
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
# Chart.js and its boxplot plugin (vendored, see README) are loaded only by the suite page, which draws the per-question charts.
CHART_SCRIPTS = '<script src="{up}assets/chart.umd.min.js"></script>\n<script src="{up}assets/chartjs-chart-boxplot.umd.min.js"></script>\n'
BIG = 2_000_000   # bytes: a page over this gets a warning in the log


MARK = ".nasute-suite"


def slug(suite):
    """The suite's folder name: the id itself when it is plain (always, for ids made from allowed names). Otherwise a cleaned
    copy plus a short hash of the id, so two different ids never share a folder."""
    plain = re.sub(r"[^\w.@-]", "_", suite)
    return suite if plain == suite and re.match(r"\w", suite) and ".." not in suite else plain.lstrip(".") + "~" + hashlib.sha1(suite.encode()).hexdigest()[:8]   # "~" is not allowed in a name, so this never equals a real id


def embed(data):
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def slim(s, meta, suite):
    """What the overview and the charts need from a run's summary."""
    return {"run": s["run"], "profile": s.get("profile", ""), "judge_mode": s.get("judge_mode"), "repeats": s.get("repeats"), "counts_line": s.get("counts_line", ""),
            "aborted": s.get("aborted"), "questions": s.get("questions"), "incomplete": s.get("incomplete"), "dataset": {k: s["dataset"][k] for k in ("name", "version")}, "total_s": s.get("total_s"),
            "metrics": {m: {"mean": v.get("mean"), "ci": v.get("ci")} for m, v in s["metrics"].items()}, "label": meta["labels"].get(s["run"], ""),
            "baseline": meta["baselines"].get(suite) == s["run"], "answering_model": s.get("answering_model"), "judge_model": s.get("judge_model"), "k": s["settings"].get("k"), "usage": s.get("usage")}


def judge_lines(cfg, sums, run_folder):
    """For the line under the overview table: each judge model and mode seen in runs, with its latest judge check. Names, dates and scores only."""
    judges = {}
    for run_id, s in sums.items():
        if s.get("judge_model"):
            j = judges.setdefault((s["judge_model"], s.get("judge_mode") or "quick"), {"model": s["judge_model"], "mode": s.get("judge_mode") or "quick", "runs": 0})
            j.update(runs=j["runs"] + 1, last_run=run_id, folder=run_folder.get(run_id))
    return [{**j, "check": N.latest_judge_check(cfg, j["model"], j["mode"], full=True)} for j in judges.values()]


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
        """The newest judge-check for this run's judge model and mode, looked up now (not when the run was made), so an old run shows a later check too."""
        jc = N.latest_judge_check(cfg, s.get("judge_model"), s.get("judge_mode"), full=True)
        return {"judge_check": jc, "judge_checked_since": bool(jc) and jc["run"] != (s.get("judge_reliability") or {}).get("run")}
    suites, run_folder = {}, {}
    for run_id, s in sums.items():
        suites.setdefault(N.suite_of(s), []).append(run_id)
    overview = []
    for key, ids in suites.items():
        first = sums[ids[0]]
        info = {"id": key, "folder": slug(key), "dataset": first["dataset"]["name"], "target": first.get("target", ""), "target_label": target_label(first.get("target", ""))}
        base = guard(out / info["folder"])
        for sub in ("runs", "compare"):
            shutil.rmtree(guard(base / sub), ignore_errors=True)
        base.mkdir(exist_ok=True)
        guard(base / MARK).write_text("made by nasute pages.py; removed when the suite has no runs left\n")
        runs = [slim(sums[i], meta, key) for i in ids]
        latest = ids[-1]
        ref = N.reference_run(cfg, sums, latest)
        c = N.compare(cfg, ref, latest) if ref else None
        href = f"compare/{ref}-{latest}.html" if c else None
        sha = sums[latest]["dataset"]["sha256"]
        same_file, pairs = [], []
        for run_id in ids:
            run_folder[run_id] = info["folder"]
            s, rows = N.read_run(cfg, run_id)
            pairs.append((s, rows))
            export(guard(base / "runs"), run_id, s, rows)
            if s["dataset"]["sha256"] == sha:
                same_file.append(rows)
            r = N.reference_run(cfg, sums, run_id)
            vs = N.compare(cfg, r, run_id) if r else None
            emit(base / "runs" / f"{run_id}.html", f"Run {run_id} · {key} · Nasute", {
                "page": "run", "suite": info, "summary": {**{k: v for k, v in s.items() if k != "settings"}, "k": s["settings"].get("k")}, "rows": rows, "label": meta["labels"].get(run_id, ""),
                "baseline": meta["baselines"].get(key) == run_id, "vs": r if vs and not vs["warning"] else None, "worse": sorted({w["id"] for w in vs["worse"]}) if vs else [],
                "compare_href": href if run_id == latest else None, **marker_check(s)})
            if run_id == latest:
                latest_summary = {**{k: v for k, v in s.items() if k != "settings"}, "k": s["settings"].get("k")}
                latest_rows = rows
        if c:
            ra = {r["id"]: r for r in reversed(N.read_run(cfg, ref)[1])}   # first repeat of each question
            rb = {r["id"]: r for r in reversed(latest_rows)}
            keep = lambda r: r and {k: r[k] for k in ("answer", "sources", "scores", "reasons", "error")}
            changed = sorted({w["id"] for w in c["worse"] + c["better"]})
            emit(base / href, f"{ref} to {latest} · {key} · Nasute", {
                "page": "compare", "suite": info, "compare": c, "labels": {ref: meta["labels"].get(ref, ""), latest: meta["labels"].get(latest, "")},
                "items": [{"id": i, "question": rb[i]["question"], "reference": rb[i]["reference"], "a": keep(ra.get(i)), "b": keep(rb.get(i))} for i in changed if i in rb]})
        with guard(base / "runs.csv").open("w", newline="", encoding="utf-8") as f:
            N.suite_csv(pairs, f)
        emit(base / "index.html", f"{key} · Nasute", {
            "page": "suite", "suite": info, "runs": runs, "latest": latest_summary, "compare": c, "compare_href": href, "reference": ref,
            "mislabels": N.mislabels(cfg, same_file), "pass_at": cfg["pass_at"], **marker_check(sums[latest])})
        overview.append({**info, "runs": runs})
    for d in out.iterdir():   # suites whose runs are all gone
        if d.is_dir() and not d.is_symlink() and (d / MARK).exists() and d.name not in {o["folder"] for o in overview}:
            shutil.rmtree(guard(d))
    emit(out / "index.html", "Nasute", {"page": "overview", "judges": judge_lines(cfg, sums, run_folder), "suites": overview, "generated": N.datetime.now(N.timezone.utc).isoformat(timespec="seconds")})
    N.log("report_written", suites=len(suites), runs=len(sums), folder=str(out))
    return suites
