[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](../reference/README.md) · [Explanation](README.md)

# Explanation: the judge-check

This page explains how Nasute tests its own judge and how to read the result. It is for anyone who wonders how much to trust the marks, and it is worth reading before you rely on Answer relevancy or compare scores from two different judges.

The judge is a language model, so it can be wrong, and before you trust the scores you want to know how often. The judge-check measures that by taking answers whose faults you know, asking the judge to mark them, and seeing how often its marks land where they should. Two numbers come out for each score: Accuracy and Cohen's kappa.

## What is checked

A judge set is a dataset of answers written by hand, each with a known fault or none. The one that comes with Nasute is `judge-demo` v1, which has 20 items. For each of 3 questions about a made-up garden handbook (`src/nasute/datasets/demo/handbook.md`) there are six answers: one that is right, one that is wrong (it contradicts the reference), one that is off-topic, a refusal, a right answer plus an invented fact, and a half-right answer with one true claim and one false. Two more items are tricky: a paraphrase that is right, and a confident hedge around a wrong answer. Twenty items is enough to see the check work; to trust a judge, write a bigger set about your own material in the same shape.

Each item says which range each score should fall in, such as `"correctness": [0.75, 1]` for a right answer, and the extracts are the handbook sections the answer should rest on.

## The two numbers

**Accuracy** is the share of the judge's marks that landed in the expected range, so it is the marks inside the range divided by the marks checked. It is easy to read, but a judge that always says "good" would score well on a set that is mostly good.

**Cohen's kappa** measures agreement beyond chance, where 1 is perfect and 0 is no better than guessing. Each mark and the middle of each expected range is put in a bucket: below 0.25 is 0, below 0.75 is 0.5, and otherwise 1. A mark the judge failed to give is its own category, which counts as wrong in Accuracy and takes part in kappa as a category that never matches. Kappa is (agreement − agreement expected by chance) / (1 − agreement expected by chance), so it corrects for the chance agreement that Accuracy ignores. If chance agreement is already 1, because every mark and every expectation fall in the same bucket by construction, kappa is undefined and is shown empty.

As a rough guide, a kappa of 0.8 and up is strong, 0.6 to 0.8 is good, 0.4 to 0.6 is middling, and anything lower is weak.

## What it said in the case study

The judge-check `judge-20261029T114345Z` used Qwen2.5-7B in quick mode on all 47 items, took 27 minutes, and had no judge failures.

| Score | Accuracy | Cohen's kappa | Items |
| --- | --- | --- | --- |
| Faithfulness | 100% | 1.00 | 33 |
| Answer correctness | 96% | 0.74 | 47 |
| Answer relevancy | 72% | 0.51 | 47 |

There were two misses on Answer correctness: an off-topic answer scored 1, because the judge listed claims that the answer never made, taken from the extracts, and a right answer with an invented fact scored 0.33 where 0.5 or more was expected. All 13 misses on Answer relevancy were wrong, half-right or hedged answers that the judge marked "no" or "partly" even though they address the question, which shows that a small judge blurs "on topic" with "true".

## What that means

You can trust Answer correctness to tell a right answer from a wrong or empty one. You can trust Faithfulness to tell whether the answer is grounded in the extracts, but it is not a truth test, so a claim that the extracts support scores as backed even if it is false, and an answer with no claims is not measured. You should not lean on Answer relevancy, which is better read as rough, and you should not act on small changes in it.

## What the check cannot tell you

The check has limits that you should keep in mind.

- It tests the judge on 47 hand-made answers about 7 questions, so it does not prove that the judge is right on your questions.
- The set covers Wikipedia-style facts, so for another subject you should write a judge set for it, as described in [check the judge](../how-to/judge-check.md).
- In the case study the judge and the system were the same model, and the check does not measure the extra kindness a model shows to its own text, so use a different judge if you can.
- If you change the judge or the prompts, run the check again. Each run records the newest check for its judge model and mode, and the run page shows it under "Judge reliability".

---

← [Previous](how-errors-count.md) · [Next](independence.md) →
