[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Tag questions and set difficulty

Tags and difficulty labels let you see where a system is weak, for example "it does well on science but poorly on history", or "it handles easy questions but fails the hard ones". You add them to the questions in your dataset, and every later run breaks its scores down by them.

1. Add `"tags": ["geography", "capitals"]` to a question. A tag can be any text, so use the same spelling every time.
2. Add `"difficulty": "easy"`, `"medium"` or `"hard"`, because anything else is reported as an error. An older file may put one of these words in `tags` instead, and Nasute reads that too.
3. Save the change as a new dataset version rather than editing the old one, as described in [write and version a dataset](write-a-dataset.md).

Each run then holds the mean of every score per tag and per difficulty, and the run page shows them in the topic breakdown under Details. Tags group the scores in the report: the topic is the first tag, and the run page's question list can be filtered by it and its distribution charts grouped by it, or by each tag.

## Check your difficulty labels

Nasute also measures difficulty itself, so that you can tell when a label is wrong. Across every run of the same dataset file, it takes the share of attempts in which Answer correctness reached `pass_at` (default 0.75). Once a question has `min_attempts` attempts (default 5), the dataset page flags it, under Details, if it is labelled easy but passed less than `mislabel_easy_below` of the time (0.5), or if it is labelled hard but passed more than `mislabel_hard_above` of the time (0.9). A flag means "take another look at the label", not "the label is wrong".

---

← [Previous](import-a-csv.md) · [Next](use-profiles.md) →
