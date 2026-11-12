[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](README.md) · [Explanation](../explanation/README.md)

# Reference: commands

This page lists every Nasute command and option, for readers who already know what they want to do and need the exact syntax. The list matches the argument parser in `src/nasute/__init__.py`, and a test parses every complete `nasute ...` command in the guides against it (lines with placeholders such as `[FOLDER]` are skipped).

Install Nasute with `pipx install nasute` (or `pip install nasute` in a virtual environment) to get the `nasute` command. `python3 -m nasute` does the same.

```text
nasute [--config FILE] [--log text|json] COMMAND ...
```

`--config FILE` goes before the command. Without it, Nasute reads `./nasute.toml`, and if there is none it runs on defaults (see [settings](settings.md)).

`--log` also goes before the command and sets how `run` and `judge-check` report their progress. `text` is short lines for a person, such as `[3/24] gold-79 ... right (2.1 s)`, with WARNING or ERROR in front of a failure (in colour at a terminal, unless `NO_COLOR` is set); a run ends with a summary of its measured scores and their 95% ranges, its system errors, its tokens and cost when known, and a link to its report page (under the `report_url` setting when it is set, else a `file://` address). `json` is one JSON object per line, for a program that reads the log: each has `time`, `level`, `app`, `event` and the event's details, and a run ends with a `run_done` event carrying the same summary. Without `--log`, the environment variable `NASUTE_LOG` decides, and without that Nasute writes text at a terminal and JSON when the output goes to a file or a pipe. Either way the log never contains question or answer text: ids, counts, outcomes and scores only. Commands return exit code 0 on success, and where a command can return 1, that is noted below.

## init

`init` creates a starter folder so that you can begin without writing settings from scratch.

```text
nasute init [FOLDER] [--demo]
```

It writes `nasute.toml` and `datasets/example/v1.jsonl` into FOLDER, which defaults to the current folder. With `--demo` the settings point at `nasute demo-server` (the system, its sources and the judge), so you can try a run without editing anything. It never overwrites anything: if either file already exists it writes nothing, lists the files in the way, and returns 1.

## prompts export

`prompts export` writes the six built-in judge prompts as text files, so that you can start a custom prompt from the real text.

```text
nasute prompts export FOLDER
```

It writes `quick.txt`, `split.txt`, `check.txt`, `knowledge.txt`, `knowledge_abstain.txt` and `abstain.txt` into FOLDER, creating it if needed. It needs no settings. It never overwrites anything: if any of the files already exists it writes nothing, lists the files in the way, and returns 1. Name the files you change in [`[judge.prompts]`](settings.md#judgeprompts). See [change the judge prompts](../how-to/change-the-judge-prompts.md).

## run

`run` is the command that does the actual testing, and it asks every question of a dataset, judges the answers, scores them, saves the run and rewrites the report.

```text
nasute run [--profile NAME] [--dataset NAME] [--target NAME] [--version V]
           [--limit N] [--repeats N] [--mode quick|claims] [--label TEXT]
```

| Option | Meaning |
| --- | --- |
| `--profile NAME` | Merge the settings table `[profiles.NAME]` over the base settings. An unknown name stops the run. |
| `--dataset NAME` | The dataset to ask. Without it, Nasute uses the `dataset` setting, and if that is empty, the one dataset whose header names the chosen target. If there is not exactly one, Nasute stops and says so. |
| `--target NAME` | Ask the dataset's questions of this target instead of the one its header names, which makes a separate suite (`dataset@target`). Without it, the target is the one in the dataset's header. |
| `--version V` | A dataset version such as `2`, `2.1` or `2.1.0`. The default is the newest. |
| `--label TEXT` | Names the run as it starts, for example `--label "prompt change"`. It is the same label `runs label` sets, and the dataset page marks labelled runs on the charts over time, so you can see where a change happened. |
| `--limit N` | Ask only the first N questions, where `0` means all. This overrides the profile and the `limit` setting. |
| `--repeats N` | The number of times each question is asked. This overrides the profile, and `0` is ignored. |
| `--mode quick\|claims` | The judge mode. This overrides `[judge] mode` and the profile. |

When your settings file has one target and one dataset, the first run needs no options at all.

## judge-check

`judge-check` measures how reliable the judge is by running it on a set of answers with known faults.

```text
nasute judge-check [--mode quick|claims] [--limit N]
```

It reports how often the judge's marks fall where they should. The set is the `judge_set` setting, or, if that is empty, the one dataset whose header says `"target": "judge"`, and the results are saved under `runs/judge-<UTC time>/`. With `--limit N` only the first N items are checked. The check records which judge prompts it used, and a run's judge reliability only counts a check made with the same prompts. See [check the judge](../how-to/judge-check.md).

## compare

`compare` tells you whether a change moved a score.

```text
nasute compare [RUN_A RUN_B] [--suite SUITE]
```

With two run ids, it compares them, treating A as the older run. With none, it compares the newest run (of SUITE, if you give one) against its reference run, which is the suite's baseline if the profiles fit and otherwise the previous compatible run. You must give exactly two ids or none, because a single id is ignored, and a run id can be shortened to its start only in `runs ...` commands, not here.

Two runs can be compared when they used the same dataset file, whatever their targets. Runs that name different profiles, or that used different dataset files, print "not comparable" and no verdicts. Runs marked by a different judge model or with different judge prompts get a note, such as `Different judge prompts (quick): custom quick against custom none. Marked scores are not comparable.`, and their marked scores (faithfulness, correctness, relevancy, context recall, abstention) show "not comparable"; retrieval scores and error rate are still compared. See [compare two models](../how-to/compare-runs.md).

## report

`report` rewrites the report folder from the saved runs, which `run` already does for you, so you need it only after changing labels or baselines.

```text
nasute report
```

## serve

`serve` shows the report folder over HTTP, for browsers that refuse to open local files.

```text
nasute serve [--port PORT] [--host HOST]
```

The defaults are port 8765 and host 127.0.0.1, which means this machine only. On 127.0.0.1 it also answers only requests addressed to `localhost` or `127.0.0.1`, so a web page using another name can't read your report through your browser. Report pages also open straight from disk, so you need `serve` only if your browser blocks local files.

## dataset

The `dataset` commands check, import and list the question files.

```text
nasute dataset check NAME [--version V]
nasute dataset import FILE --name NAME [--target TARGET]
nasute dataset list
```

- `check` lists every problem in a dataset file with its line number, and returns 1 if there are any. The default version is the newest. `V` is a version such as `2`, `2.1` or `2.1.0`, and a short one means the newest version that starts that way.
- `import` turns a CSV into the next version of NAME. The columns, the `;` lists and the checks are described in [import questions from a CSV](../how-to/import-a-csv.md), and the dataset format is in [write and version a dataset](../how-to/write-a-dataset.md). You need `--target` for a new dataset when your settings do not have exactly one target, whereas for an existing dataset it is taken from the earlier version. It works out the new version number itself by comparing with the newest version, prints which part it raised and why, and never overwrites a version. It checks the questions first, and if it finds problems it prints them, returns 1 and writes nothing.
- `list` shows each dataset, its target, and the question count of each version.

Dataset and target names may use only letters, digits, `_`, `.` and `-`, must start with a letter or digit, and must not contain `..`.

## runs

The `runs` commands list your saved runs and manage their labels and baselines.

```text
nasute runs [--suite SUITE]
nasute runs show RUN
nasute runs label RUN TEXT
nasute runs baseline RUN
nasute runs export [RUN | --suite SUITE] [--csv FILE]
nasute runs delete RUN [--yes]
```

| Command | What it does |
| --- | --- |
| `runs` | Lists runs grouped by suite, showing the date, profile, judge mode, counts, correctness with its interval, marks (`BASELINE`, `STOPPED EARLY`, `INCOMPLETE`) and label. `--suite` goes before any action word. |
| `runs show RUN` | Shows one run's scores with their meanings, why answers failed, and the worst questions. |
| `runs label RUN TEXT` | Sets a label, and empty text (`""`) removes it. Rewrites the report. |
| `runs baseline RUN` | Makes RUN the baseline of its suite, and rewrites the report. A run that was stopped early cannot be a baseline. |
| `runs export RUN` | Writes the run as CSV, one row for each attempt, to the screen or to `--csv FILE`. With `--suite SUITE` instead of a run it writes one row for each question in each run of the suite. The columns are in [file formats](file-formats.md#exports). |
| `runs delete RUN [--yes]` | Deletes a run folder after asking, and the baseline of a suite needs `--yes`. Rewrites the report, so the run's page and its copies are gone from it too. |

RUN is a run id (such as `20261029T090937Z`) or the start of one, as long as only one run starts that way.

## Related

[Settings](settings.md) lists every setting, and [data layout](data-layout.md) shows where files go.

---

← [Previous](README.md) · [Next](settings.md) →
