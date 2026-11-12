[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Write and version a dataset

A dataset is the list of questions that Nasute asks, and writing a good one is the most important thing you do. This guide shows how to write the first version, how to change it later without breaking old results, and how to keep private questions out of version control.

A dataset is a folder `datasets/<name>/` that holds one file for each version, named like `v1.0.0.jsonl`, `v1.1.0.jsonl` and `v2.0.0.jsonl`. In each file the first line names the dataset and its target, and every other line is one question. The fields are described one by one in [file formats](../reference/file-formats.md).

## Write the first version

Start with a header line and a few questions, as in this example for a dataset called `trivia`.

```json
{"dataset": "trivia", "target": "mine", "about": "what it covers"}
{"id": "capital-france", "question": "What is the capital of France?", "reference": "Paris", "sources": ["France"], "tags": ["geography"], "difficulty": "easy"}
{"id": "zorblax", "question": "In what year was the Treaty of Zorblax signed?", "reference": "", "tags": ["unanswerable"], "difficulty": "medium", "answerable": false}
```

1. Keep each `reference` short, as the fact itself rather than an essay.
2. Check every question by hand: does the answer really exist in your system's library, and, if you list `sources`, is that article really there and does it hold the answer?
3. For a question with no answer, set `"answerable": false` and leave `reference` empty, and check that the library really has nothing by searching for the made-up names.
4. Run `nasute dataset check trivia`, which lists every problem with its line number.

## Change it by writing the next version

A version file is never edited, because each run records the file's fingerprint and you want old runs to stay tied to the questions they used. To change a dataset you copy the file and edit the copy.

```bash
cp datasets/trivia/v1.0.0.jsonl datasets/trivia/v1.1.0.jsonl
```

Choose the new version number by what you changed. Raise the first number (the major) when a question was removed, or a question's text, reference answer or `answerable` changed, because old scores are then about different questions. Raise the second (the minor) when you only added questions. Raise the third (the patch) when you only changed tags, difficulty or sources. A file named `v2.jsonl`, from before versions had three parts, is read as `2.0.0`, and versions compare as numbers, so `1.10.0` comes after `1.9.0`. When you import a CSV, Nasute picks the number for you by comparing with the newest version.

After editing the copy, check it. `nasute run` uses the newest version unless you pass `--version`, which takes `2`, `2.1` or `2.1.0` (a short one means the newest version that starts that way). When two runs used different versions, `compare` warns you and does not compare question by question.

## Keep private questions out of the repo

If some questions are about your own documents, put them in a folder outside the repository and add that folder to `datasets`:

```toml
datasets = ["datasets", "/path/to/private/datasets"]
```

## How many questions you need

A small dataset gives wide ranges. The "power" line on a run page says how many questions it would take to see a 0.05 change, and [the statistics](../explanation/statistics.md#power-how-many-questions-do-i-need) explain how that number is worked out.

---

← [Previous](add-a-target.md) · [Next](import-a-csv.md) →
