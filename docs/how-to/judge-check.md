[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Check the judge, and add judge items

The judge is a language model, so it can be wrong, and `judge-check` measures how often by testing it on answers whose faults you already know. This guide shows how to run the check and how to add your own test items to it. The reasoning behind it is in [the judge-check](../explanation/the-judge-check.md).

## Run it

The command needs a judge set to work from.

```bash
nasute judge-check [--mode quick|claims] [--limit N]
```

The judge set is the dataset named by the `judge_set` setting, or, if that is empty, the one dataset whose header says `"target": "judge"`. The check saves its results in `runs/judge-<time>/`. Every normal run then records the newest complete check for its judge and mode (or, if none is complete, the newest stopped one, marked as stopped with `aborted`), and the suite page shows it under "Judge reliability". The `deep` profile can run a fresh check first when `judge_check = true`, but in the starter file it is `false`, so you switch it on once you have a judge set.

The command prints, for each score, its Accuracy (the share of the judge's marks that landed in the expected range) and its Cohen's kappa (agreement beyond chance), and it lists the marks that were wrong.

## Add an item

A judge set is a dataset with `"target": "judge"` in its header, in which each item is an answer you wrote by hand together with the range each score should fall in. As with any dataset, a version file is never edited, so you copy the newest version to the next number and add lines there.

```json
{"id": "canberra-wrong", "kind": "wrong", "question": "What is the capital city of Australia?", "reference": "Canberra", "extracts": ["Canberra is the capital city of Australia."], "answer": "The capital of Australia is Sydney.", "expect": {"correctness": [0, 0.25], "faithfulness": [0, 0.25], "relevancy": [0.5, 1]}}
```

1. Copy the newest version to the next number.
2. Append your item, which needs all of `id`, `kind`, `question`, `reference`, `extracts`, `answer` and `expect`.
3. Leave a score out of `expect` when it should not be judged. A refusal has no claims, for example, so you leave out Faithfulness.
4. Write a "right" answer as one claim that the reference covers, because an extra true detail that the reference lacks counts against Answer correctness.
5. Set `judge_set` to the dataset name and run `nasute judge-check`.

The most useful items to add are the ones where you have seen the judge slip, such as a hedge around a wrong answer, a paraphrase that is right, or a refusal.

---

← [Previous](use-a-cloud-judge.md) · [Next](../reference/README.md) →

---

← [Previous](use-a-cloud-judge.md) · [Next](../reference/README.md) →
