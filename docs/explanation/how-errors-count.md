[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](../reference/README.md) · [Explanation](README.md)

# Explanation: how errors count

This page explains what Nasute does when something goes wrong during a run, and why it keeps three kinds of failure apart. You need it when a run shows errors and you want to know how much they affect the scores, or whether the system or the judge is to blame.

Three things can go wrong in a run, and they are kept apart on purpose, because a flaky judge must never make the system look bad and a system that times out on hard questions must never hide.

| Kind | Examples | What happens |
| --- | --- | --- |
| **System error** (the system's fault) | A timeout, a crash, an HTTP error, a reply with no answer at the path, or an empty answer | The attempt counts as **0** for every score that needs an answer: Answer correctness, Faithfulness, Answer relevancy, and Abstention accuracy for unanswerable questions. Hit rate@k, Recall@k and MRR come from what was found, so they are 0 when nothing came back. The attempt is also counted in Error rate. |
| **Judge error** (the harness's fault) | An unreadable reply, a timeout, a reply that breaks the required shape, or a verdict count that does not match the claims | Nasute retries (`[judge] retries`, default 2, with a short wait), and if it still fails, that answer is left out of its judged scores. **It is never counted against the system.** |
| **Connection error** (nothing answers) | Connection refused, or no DNS | Nasute retries after 5, 15 and 45 seconds. If it still cannot connect to the system, that is a system error, and if it cannot connect to the judge, that is a judge error. |

## Strict and answered-only scores

The headline scores are **strict**, which means that a system error counts as a 0. A system that answers 10 questions perfectly and times out on 10 others therefore gets about 0.5 rather than 1.0, so a system that fails on hard questions cannot flatter itself.

Next to each score, the summary and the page also show an **answered only** value, which leaves the errored attempts out. You should read the two together, because a big gap between them says that the answers are good but the system often fails to give one. Error rate (the share of attempts where the system failed) is scored like any other score, so `compare` can show a rise in system errors as a real drop.

## Incomplete runs

A run is marked **incomplete** when more than `max_judge_errors` (default 0.1) of its answers could not be judged. The page shows a banner, the log warns, and `compare` notes it. The scores are still computed from what was judged, but they have gaps, and the gaps may not be random. Judge errors are never a penalty for the system, but they are a reason to trust the run less.

## Aborted runs

If the system or the judge cannot be reached for **3 questions in a row** (a question counts only if none of its repeats got through), the run stops. Nothing new starts, questions in flight stop after their current repeat, and everything that finished is kept. The summary records `aborted` and the reason. `compare` refuses to compare an aborted run, and an aborted run cannot be a baseline. A `judge-check` stops in the same way, and a `deep` run that begins with a judge-check does not start if that check stopped.

## One case that is not an error

Sometimes a target cannot fetch the source text that the judge needs, which a target reports with the `extracts_failed` flag. In that case Faithfulness and Context recall for that attempt are "not measured", and because the problem belongs to the harness, it is not held against the system.

## The counting line

Every summary, the end of a run, and the report page carry one line that counts per attempt, so a question asked 3 times is 3 attempts:

```text
27 asked · 25 scored · 1 system error · 1 judge error
```

The intervals are worked out from the attempts that were actually scored. `compare` pairs the questions that were scored in both runs, and it lists those that newly errored or recovered.

---

← [Previous](why-the-judge-says-yes-or-no.md) · [Next](the-judge-check.md) →
