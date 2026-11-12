[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](README.md) · [Explanation](../explanation/README.md)

# Reference: file formats

This page describes the contents of every file Nasute reads or writes, for readers who want to build on the files, such as a script that reads `summary.json`. Every file is JSON or JSON Lines (one JSON object per line), except the settings, which are TOML and are described in [settings](settings.md).

## Dataset file: `datasets/<name>/v<major>.<minor>.<patch>.jsonl`

A dataset file is a list of questions. Its first line is the header and every other line is one question.

```json
{"dataset": "my-questions", "target": "mine", "about": "what it covers"}
{"id": "capital-france", "question": "What is the capital of France?", "reference": "Paris", "sources": ["France"], "tags": ["geography"], "difficulty": "easy"}
{"id": "zorblax", "question": "In what year was the Treaty of Zorblax signed?", "reference": "", "tags": ["unanswerable"], "difficulty": "medium", "answerable": false}
```

Header:

| Field | Meaning |
| --- | --- |
| `dataset` | The dataset's name. Required, non-empty text. |
| `target` | The name of the `[targets.<name>]` table these questions are for. Required. The target `judge` marks a judge set. |
| `about` | Free text. Optional. |

Question:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Text, unique in the file. Not empty. |
| `question` | yes | The text sent to the target. Not empty. |
| `reference` | yes | The correct answer, short. Empty when `answerable` is `false`; otherwise it must not be empty. |
| `sources` | no | List of article titles that hold the answer, exactly as the target reports them. Compared ignoring case. Without it the retrieval scores are not measured. |
| `tags` | no | List of text. Scores are broken down by tag. |
| `difficulty` | no | `easy`, `medium` or `hard`. Older files may put one of these in `tags` instead; Nasute reads that too. Otherwise "unknown". |
| `answerable` | no | `false` for a question the system cannot answer. Then `reference` and `sources` must be empty, and the score is `abstention`. |

`nasute dataset check` reports every problem it finds, with its line number.

### Judge set

A judge set is a dataset used to test the judge instead of a system, and it has the same kind of header with `"target": "judge"`. Each item is an answer written by hand, with these fields:

| Field | Meaning |
| --- | --- |
| `id`, `question`, `reference` | As above. |
| `kind` | A label for the kind of fault: `right`, `wrong`, `refusal` and so on. Free text. |
| `extracts` | List of source texts the answer is checked against. |
| `answer` | The answer to judge. Written by hand, with a known fault or none. |
| `expect` | `{ metric: [low, high] }`. The range each score should fall in. Leave a metric out to skip it. |

All of `id`, `kind`, `question`, `reference`, `extracts`, `answer`, `expect` are required.

## CSV for `dataset import`

The import command reads questions from a spreadsheet export, and this section lists the columns it accepts.

Header row with `id`, `question`, `reference` (required) and optionally `sources`, `tags`, `difficulty`, `answerable`. `sources` and `tags` hold several values separated by `;`. `answerable` is `false`, `no` or `0` for an unanswerable question; anything else or empty means answerable. A byte-order mark from a spreadsheet export is accepted.

## `runs/<time>/results.jsonl`

This file holds the raw record of a run, with one line per attempt (so a question asked 3 times gives 3 lines), in dataset order.

| Field | Meaning |
| --- | --- |
| `id`, `repeat`, `seed` | The question, which repeat (1, 2, 3, ...), and the seed sent (equal to the repeat number). |
| `tags`, `difficulty`, `answerable`, `question`, `reference` | Copied from the dataset. |
| `expected` | The question's `sources`. |
| `answer`, `sources`, `extracts` | What the target returned. |
| `links` | Optional. The address of each source, in the same order as `sources`, or null where there is none. Older results have no `links`, and their sources show as plain text. |
| `first_text_s`, `total_s` | Seconds to first text (only some targets know it; else null) and in total. |
| `error` | The system's error text, or null. A system error counts against the system. |
| `scores` | One value per metric in [scores](scores.md); null where not measured. |
| `reasons` | A sentence per score showing the count behind it. |
| `judge_detail` | The judge's claims and verdicts. Shape depends on the judge mode. |
| `judge_error` | The judge's failure text, or null. Never counted against the system. |
| `judge_s` | Seconds the judging took. |
| `unreachable` | True if the system or judge could not be connected to. |

`judge_detail` in quick mode: `mode`, `claims` (each with `claim`, `supported`, `vs_reference`, `why`), `relevancy`, `relevancy_why`. In claims mode: `mode`, `answer_claims`, `reference_claims`, `precision`, `recall`, and four lists of verdicts: `answer_vs_extracts`, `answer_vs_reference`, `reference_vs_extracts`, `reference_vs_answer` (each item has `supported` and `why`). For an unanswerable question: `mode`, `verdict` (`declined` or `made_something_up`), `why`.

## `runs/<time>/summary.json`

This file holds the scores and everything needed to interpret them, such as the settings, the models and the counts, and the report is built from it.

| Field | Meaning |
| --- | --- |
| `run` | The run id. |
| `commit` | The code that made the run: a short git commit when run from a checkout, else the installed version (such as `v0.1.0`), else "unknown". |
| `target`, `target_kind` | Which target, and its kind. |
| `answering_model`, `judge_model` | Model names, as listed by the `/v1` addresses. "unknown" if not asked or not answered. |
| `aborted` | Null, or why the run stopped early. |
| `questions`, `attempts`, `total_s` | Distinct questions, attempts, wall-clock seconds. |
| `dataset` | `{name, version, sha256}`. The version is text such as `"1.2.0"`. Runs from before versions had three parts store a whole number (`2`), which is read as `2.0.0`. |
| `settings` | The settings used, with each `headers` table cut down to its names, anything (a value, list or table) under a name like key, token, secret, password, auth or credential hidden, and any URL's `user:password@` and query values hidden. Folder paths are saved as absolute paths. |
| `profile`, `judge_mode`, `judge_cache`, `temperature`, `repeats`, `pass_at` | The run's main settings. |
| `judge_prompts` | The judge prompts the run's mode used: `sha256` (the first 12 hex digits of each prompt's SHA-256, by name) and `custom` (the names that came from a file in `[judge.prompts]`). Runs from before 0.2.0 have none and used the built-in prompts. |
| `metrics` | Per score: `mean`, `std`, `se`, `ci` (95% interval), `n` (questions), `attempts`. Strict: a system error counts as 0. |
| `metrics_answered` | The same without the attempts where the system errored. No `error_rate`. |
| `power` | Per score: `needed` (questions to see a `detect` change) and `basis` (`repeats` or `worst case`). |
| `tags`, `difficulty` | Mean of each score per tag and per difficulty. |
| `counts`, `counts_line` | `asked`, `system_errors`, `judge_errors`, `scored`, and the plain sentence. |
| `judge_error_rate`, `incomplete` | Judge errors / answers judged; true if above `max_judge_errors`. |
| `consistency` | Null without repeats. Else `questions`, `pass_all`, `left_out`, `flaky`. |
| `causes` | `counts` per cause and a `questions` list with each cause and reason. |
| `failures` | Each system or judge error with its question id. |
| `judge_reliability` | The newest complete judge-check for this judge model, mode and judge prompts (`run`, `items`, `set_size`, `aborted`, `metrics`). If there is no complete one, the newest stopped check, with `aborted` set to why it stopped. Null if there is none. |
| `time_to_first_text_s` | Mean time to first text, if the target reports it. |

## `runs/judge-<time>/summary.json`

A judge-check saves its own summary in a folder beside the runs, with the fields below.

`run`, `dataset`, `judge_model`, `judge_mode`, `judge_prompts` (as in a run's summary), `items` (judged), `set_size`, `aborted`, `failed` (judge errors), `total_s`, `metrics` (per score `accuracy`, `kappa`, `n`) and `wrong` (each out-of-range mark with `id`, `kind`, `metric`, `expected`, `got`). Its `results.jsonl` has one line per item: `id`, `kind`, `scores`, `reasons`, `judge_detail`, `judge_error`, `judge_s`.

## `runs/index.json`

This small file holds the labels you gave to runs and the baseline of each suite, as in the example below.

```json
{"labels": {"20261029T103215Z": "first look"}, "baselines": {"fake-qa@mine": "20261029T103215Z"}}
```


## Exports

The report writes these beside each run page and, for every run of a suite, in `report/<dataset>@<target>/runs.csv` (linked from the dataset page), and `nasute runs export` writes the same CSV text. Every file is UTF-8 with a header row, with lists such as tags joined by `;`. A text that starts with `=`, `+`, `-` or `@` gets an apostrophe in front, so a spreadsheet does not run it as a formula.

| File | One row for | Columns |
| --- | --- | --- |
| `runs/<run>.csv` | each attempt | `run`, `id`, `repeat`, `tags`, `difficulty`, `answerable`, every score (`hit`, `recall`, `mrr`, `faithfulness`, `correctness`, `relevancy`, `context_recall`, `abstention`, `error_rate`), `cause`, `error`, `judge_error`, `first_text_s`, `total_s`, `judge_s`, `question`, `reference`, `answer` |
| `runs.csv` (in the suite folder) | each question in each run | `run`, `date`, `profile`, `judge_mode`, `target`, `answering_model`, `judge_model`, `dataset_version`, `id`, `tags`, `difficulty`, every score as a mean over the repeats, `attempts`, `errors` |
| `runs/<run>.results.jsonl` | each attempt | A copy of the run's results file. |
| `runs/<run>.summary.json` | the run | A copy of the run's summary, with settings hidden as in the saved summary. |

An empty score cell means the score was not measured for that attempt.

---

← [Previous](scores.md) · [Next](data-layout.md) →
