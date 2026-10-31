[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Import questions from a CSV

This guide is for the case where you would rather write your questions in a spreadsheet than in JSON Lines. You save the sheet as a CSV file, and Nasute turns it into the next version of a dataset and checks it for you.

## The CSV

The file needs a header row followed by one question per row, using the columns below.

| Column | Needed | Notes |
| --- | --- | --- |
| `id` | yes | Must be unique. |
| `question` | yes | |
| `reference` | yes | May be empty only when `answerable` is false. |
| `sources` | no | Several values are separated by `;`. |
| `tags` | no | Several values are separated by `;`. |
| `difficulty` | no | `easy`, `medium` or `hard`. |
| `answerable` | no | `false`, `no` or `0` means no answer exists, and anything else means one does. |

A byte-order mark from a spreadsheet export is accepted.

## Import it

Run the import command with the name you want for the dataset and the target it is for.

```bash
nasute dataset import questions.csv --name my-questions --target mine
```

1. The file becomes the next version of `my-questions`, which is `v1.0.0.jsonl` if the dataset is new, and Nasute never overwrites a version. For an existing dataset it compares your CSV with the newest version and raises the major number if a question was removed or its text, reference or `answerable` changed, the minor number if you only added questions, and the patch number if only tags, difficulty or sources changed. It prints which part it raised and why, such as "minor: 5 questions added". If nothing changed it writes nothing.
2. You need `--target` for a new dataset when your settings do not have exactly one target. For an existing dataset the target comes from the earlier version.
3. Nasute checks the questions before it writes anything. If it finds problems, such as an empty field or a repeated id, it prints them with line numbers, returns 1 and writes no version, so you fix the CSV and import again.

Afterwards, `nasute dataset list` shows the versions and question counts.

---

← [Previous](write-a-dataset.md) · [Next](tag-questions.md) →

---

← [Previous](write-a-dataset.md) · [Next](tag-questions.md) →
