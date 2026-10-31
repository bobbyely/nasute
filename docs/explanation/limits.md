[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](../reference/README.md) · [Explanation](README.md)

# Explanation: limits

This page lists where Nasute falls short, and it is worth reading before you show a number to anyone else. Some limits come from the method (a judge can be wrong, small samples are noisy) and some from how it is set up, and each entry says what to do about it.

## The test can be too easy: the ceiling effect

In the full run `20261029T121042Z` of the case-study deployment described in [How Nasute works](../how-nasute-works.md), Answer correctness, Faithfulness and Answer relevancy were all exactly 1.00 on 27 questions. A system cannot score above 1.00, so this test cannot tell the system from a better one and cannot show a gain, and a high score from an easy test tells you little. If every score is at the top, write harder questions.

Two things follow from all-1.00 scores.

- **A range that looks like certainty.** The normal formula needs spread in the scores, and with none, Nasute uses a Wilson interval that counts questions (about 0.87 to 1.00 for 27 questions at 1.00). That is cautious on purpose, but it is a stand-in and not a measured range, and runs saved before this rule show 1.00 to 1.00.
- **No power estimate.** The power line needs some spread in the scores to work from, so with none, the report says it cannot estimate how many questions are needed instead of printing a number.

## The judge

These limits concern the model that marks the answers.

- **The judge marks its own homework.** In the case study the judge is the same 7-billion-parameter model that writes the answers. A model tends to be kind to text like its own and can miss its own mistakes, so for an independent view you should point `[judge]` at a different or larger model.
- **A small judge slips.** It can invent claims that the answer never made (seen on refusals), and it often marks a wrong but on-topic answer "not relevant". Answer relevancy was in range only 72% of the time in the judge-check, so read it as rough (see [the judge-check](the-judge-check.md)).
- **The judge-check is small.** It uses 47 answers about 7 questions, all of them Wikipedia-style facts.
- **Quick-mode correctness does not see what is missing.** Only claims mode counts reference facts that the answer left out, and in both modes a true extra detail that the reference lacks counts against Answer correctness.

## The numbers

These limits concern how much a score can tell you.

- **Small samples give wide ranges.** Under 5 shared questions there is no verdict, and a power line that says hundreds of questions are needed means that your dataset cannot see a change of `detect`, so you should ask more repeats or write more questions.
- **The ranges are a little narrow for small runs.** Nasute uses the normal value 1.96 rather than a t-table, so with fewer than about 30 questions the intervals are slightly too narrow (see [the statistics](statistics.md#where-nasute-differs-from-the-paper)).
- **Hit rate@k is strict.** It counts only the articles that the dataset lists, and in the full run 4 of 27 questions missed because the system found a related article instead, even though the answers were right.
- **A failure cause is a hint.** The cause `judge?` means "take a look", not "the judge is wrong".

## The setup

These limits come from how the case-study deployment and Nasute itself are set up.

- **The extracts are re-fetched.** The case-study service does not send the passages it gave its model, so its target fetches the opening of each source article again and shows that to the judge. That is close to what the model read but not identical, so Faithfulness is approximate there, whereas a target that sends its real extracts has no such gap.
- **Speed can be flattered by a prompt cache.** See [independence](independence.md).
- **CI checks the harness, not live answer quality.** GitHub has no language model, so `tests/nasute_test.py` runs on made-up data, and real scores come only from running Nasute against a real system.
- **One Wikipedia-style dataset.** In the case study, 27 factual questions and 5 unanswerable ones make a smoke test rather than a full picture, and only a few are `hard`.
- **Not built:** token cost, power use, cold and warm detection, and a cron job.

---

← [Previous](independence.md)
