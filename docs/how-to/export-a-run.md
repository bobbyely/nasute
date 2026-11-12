[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Export a run

You use this guide when you want a run's scores and answers outside the report, for example to sort them in a spreadsheet, to chart something Nasute does not, or to keep a copy. Every run can be exported, and the files are plain text.

When Nasute writes the report, it puts three files beside each run page, in `report/<dataset>@<target>/runs/`:

- `<run>.csv` has one row for every attempt, with the run id, the question id, the repeat, the tags (joined with `;`), the difficulty, whether it was answerable, every score, the failure cause, any error, the timings, and then the question, the reference answer and the answer.
- `<run>.results.jsonl` is a copy of the saved results, one JSON object per attempt, with everything the run recorded, including the judge's claims.
- `<run>.summary.json` is a copy of the run's summary. It goes through the same hiding of secrets as the saved summary, so it holds header names but never header values or keys.

Each suite folder also has `runs.csv`, which has one row for every question in every run of the suite: the run, its date, profile, judge mode, target, models and dataset version, then the question id, tags, difficulty, the mean of each score over the repeats, and how many attempts and errors there were. That is the file to use for a chart of one question over time.

On the run page the links are in a line that reads "Download", and on the suite page there is "Download all runs (CSV)". They are ordinary links, so they work when the report is opened from disk.

## From the command line

The same CSV files can be written without building the report.

```bash
nasute runs export 20261029T0928
nasute runs export 20261029T0928 --csv run.csv
nasute runs export --suite example@mine --csv all-runs.csv
```

The first command prints the per-attempt CSV for one run (a run id, or the start of one). The second writes it to a file, and the third writes the suite CSV.

## Opening the files in a spreadsheet

The files are UTF-8 with a header row. If an answer or question starts with `=`, `+`, `-` or `@`, Nasute puts a single apostrophe in front of it, because a spreadsheet would otherwise run it as a formula. Remove the apostrophe if you need the exact text.

---

← [Previous](read-a-run-page.md) · [Next](run-overnight.md) →
