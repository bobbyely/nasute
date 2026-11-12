[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](README.md) · [Explanation](../explanation/README.md)

# Reference: data layout

This page shows what Nasute reads and writes, and where each file lives, which is useful when you want to back up your results, share a dataset or find a particular run. Folders named in the settings are relative to the settings file's folder.

```text
nasute.toml                    your settings
datasets/<name>/v1.jsonl       questions. v2.jsonl is the next version, never an edit of v1
runs/                          the `runs` setting
  index.json                   labels and baselines
  <UTC time>/                  one run, e.g. 20261029T090937Z
    results.partial.jsonl      only while the run is going: each attempt, added as it finishes
    results.jsonl              every question and repeat, in dataset order
    summary.json               scores, intervals, settings, models, counts
  judge-<UTC time>/            one judge-check
    results.jsonl
    summary.json
report/                        the `report` setting; written by `nasute report`
  index.html                   every suite
  assets/                      report.js, report.css, uPlot, Chart.js and its boxplot plugin (shared by pages)
  <dataset>@<target>/          one suite
    .nasute-suite              marker: this folder is ours
    index.html                 charts over runs, latest scores, compare, breakdowns
    runs.csv                   every question of every run
    runs/<run>.html            one run: charts of its questions, the questions table, one view per question (#q-<id>)
    runs/<run>.csv             the run's attempts (also .results.jsonl and .summary.json)
    compare/<a>-<b>.html       what changed between two runs
```

## Rules

The layout follows a handful of rules, and knowing them explains why Nasute behaves as it does when you delete, move or rerun things.

- **A dataset file is never edited.** A change is the next version. Each run records the file's SHA-256, so a run can always be tied to the exact questions.
- **`results.partial.jsonl` is a crash safety net.** If a run is killed you keep every attempt that finished. A finished run replaces it with `results.jsonl`.
- **`judge-*` folders are not runs.** `runs`, `compare` and the report ignore them as runs. A run's summary quotes the newest complete judge-check for its judge model and mode. If none is complete, it quotes the newest stopped one, marked `aborted`.
- **A suite id is `dataset@target`.** `@` is not allowed in names, so two different pairs never share an id. The same string names the suite's report folder.
- **Labels and baselines live in `runs/index.json` only.** `runs label` and `runs baseline` never touch a run folder. The file is written to a temporary file and moved into place; two commands changing it at the same moment can lose one change.
- **The report folder is rebuilt from `runs/`.** It is safe to delete. Give it a folder of its own: Nasute rewrites it, removes a suite folder when the suite has no runs left (only if the folder holds the `.nasute-suite` marker), and refuses to write through a symlink or outside it.
- **Private data stays out of the repo.** Put questions about private documents in a folder outside it, listed in `datasets`.

## Report pages

The report is a set of static pages, which means you can copy the folder anywhere and open it without a server. Each page holds its data as JSON inside the page, and `assets/report.js` draws it, so pages open from disk with no server, and text from datasets, answers and the judge is only ever inserted as text, never as HTML. A run page holds all its data: about 13 KB per answer in claims mode, so a 32-question, 3-repeat deep run is around 1 MB. The log warns past 2 MB.

The charts use uPlot 1.6.32 (MIT licence), vendored in `src/nasute/assets/` with its licence file. `uPlot.iife.min.js` SHA-256 `19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f`, `uPlot.min.css` SHA-256 `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04`. If the script fails to load, the charts become plain tables. The question charts on the run page use Chart.js 4.5.1 (MIT licence, `chart.umd.min.js`, SHA-256 `48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a`) and its boxplot plugin @sgratzl/chartjs-chart-boxplot 4.4.5 (MIT licence, `chartjs-chart-boxplot.umd.min.js`, SHA-256 `467600cc59a7f7c53afed1acdc683c1ef9b7b76ba9f5d3a4c81b560852cb6b23`), both vendored in `assets/` with their licence files and loaded only by run pages. The plugin asks for Chart.js 4.1.1 or newer.

File contents are in [file formats](file-formats.md).

---

← [Previous](file-formats.md) · [Next](judge-prompts.md) →
