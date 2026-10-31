[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](../reference/README.md) · [Explanation](README.md)

# Explanation: the statistics

This page explains how sure Nasute's numbers are and how it decides whether a change is real, and it is written for readers who want to understand the error bars rather than just read them. The method follows Evan Miller, "Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations" (2024), [arXiv 2411.00640](https://arxiv.org/abs/2411.00640), and each part below says what is used, first in words and then in formulas.

**The short version.** A score from 30 questions is one draw from the many questions you could have asked, so another 30 would give a slightly different average. The 95% interval says how far the average could plausibly move. When two runs differ, Nasute compares them question by question and says "real gain", "real drop" or "within noise", and because repeating a question tells you nothing new about other questions, repeats are counted with care.

## The standard error

Suppose a run scores 40 questions and the average Answer correctness (how well the answer matches the reference answer) is 0.70. If the 40 scores spread widely, with some at 0 and some at 1, the average is shaky, whereas if they all sit near 0.70 it is firm. The standard error (SE) puts a number on that. With one score per question it is:

```text
SE = sqrt( variance of the scores / n )
```

Here `n` is the number of scores, and the variance uses `n - 1` in its divisor. The 95% interval is then:

```text
mean ± 1.96 × SE
```

Every score runs from 0 to 1, so the range is cut off at 0 and 1. With only a handful of questions it would otherwise spill past them.

The true score, which is the one you would get from every question you could ever ask, is probably inside this range. "Probably" has a precise meaning: if you repeated the whole exercise many times, about 95 of the 100 intervals would contain it.

### Repeats and clustering

If you ask the same question three times you have three scores, but they are not independent, because they belong to the same question and tend to resemble each other. Counting them as separate would make the interval too narrow, so Miller's fix adds a term for how much the repeats of one question move together:

```text
SE² = variance / n  +  (1 / n²) × Σ over questions of Σ over pairs of repeats (s_i − mean)(s_j − mean)
```

The sum runs over every pair of two different repeats of the same question. With one score per question there are no pairs and the extra term is zero, and if the repeats of a question agree with each other the term is positive and the interval widens. That is the honest answer, since three copies of one question are not three questions.

### Yes/no scores

Hit rate@k (a right source was among the top k found), Abstention accuracy (says it doesn't know when there's no answer) and Error rate (share of attempts where the system failed) are either 0 or 1 for each attempt. For these Nasute uses the Wilson interval, which stays between 0 and 1 and works even with a single answer. With repeats, the number of trials is divided by the same inflation that the clustering term causes, which is the variance with the extra term divided by the variance without it, never below 1. When every attempt agrees there is no variance to inflate, and the trials counted are the questions rather than the attempts, so 2 questions asked 3 times that all pass give the same range as 2 questions asked once.

Two real examples from the full run of the case-study deployment described in [How Nasute works](../how-nasute-works.md) (run `20261029T121042Z`, 32 questions) show how this looks in practice.

- Abstention accuracy was 5 of 5, and its Wilson range is 0.57 to 1.00, because five questions cannot rule out a true rate near 0.6.
- Answer correctness was 1.00 on all 27 answerable questions. Because every score was exactly 1, the normal formula has no spread to work with and would give a range of zero width, which looks like certainty and is not. So when the scores have no spread, or only one attempt was scored, Nasute uses a Wilson interval on the mean with the number of questions as the trials. For 27 questions at 1.00 that gives about 0.87 to 1.00. The rule is deliberately cautious, since it ignores how many repeats there were. That run was made before the rule existed, so its saved summary still shows 1.00 to 1.00. An all-1.00 score still means "at the top of what this test can show", as described in [limits](limits.md).

## Comparing two runs: paired, per question

To find out whether a change helped, Nasute compares two runs on the same questions. For each shared question it takes the score in each run (the average over repeats) and works out the difference:

```text
d = score in B − score in A     for each shared question
mean difference ± 1.96 × sqrt( variance of d / number of questions )
```

The verdict then follows from where that interval falls.

- If the interval is entirely above 0, the change is a **real gain**.
- If it is entirely below 0, the change is a **real drop**.
- If it includes 0, the change is **within noise**.
- With fewer than 5 shared questions there is **too few questions** and no verdict.

For Error rate, lower is better, so a rise counts as a "real drop". Pairing is stronger than comparing two separate averages, because questions that are hard in run A are mostly hard in run B too, and that shared difficulty cancels out in the differences and leaves only the change.

Nasute gives no verdict, and shows "not comparable", whenever a comparison would mislead. That happens when both runs name a profile and the profiles differ, when either run was stopped early, when the dataset file differs (in which case there is no per-question comparison at all), and, for judged scores, when the judge model differs. Two runs of different targets can be compared as long as they used the same dataset file, and Nasute adds a note that the targets differ.

## Power: how many questions do I need?

Sometimes a run says "within noise" because nothing changed, and sometimes it says so because there are too few questions to see the change. The power line is a planning estimate for the second case. It answers this question: roughly how many questions would I need to have an 80% chance of noticing a difference of `detect` (default 0.05) between two runs, with 5% false alarms, under the assumptions below? It is not an explanation of a result you already have.

```text
n = (1.96 + 0.84)² × variance of the paired differences / detect²
```

In `compare`, the variance is the one observed in the differences. A single run's summary has no differences yet, so Nasute estimates it in one of two ways.

- **With repeats**, it takes the average, over questions, of 2 × (variance between the repeats of that question) / (number of repeats), which assumes that a change moves every question about the same amount.
- **Without repeats**, it takes twice the variance of the scores. This is a rule of thumb that assumes the two runs have similar variance and that their per-question scores do not move in opposite directions (non-negative covariance). If they do, it overstates the need, and if the runs differ more than assumed, it understates it.

If the scores have no spread (every question scored the same), there is nothing to estimate from, and Nasute says it cannot estimate instead of giving a number. If the line says 280 and you have 32 questions, then a 0.05 change is out of reach for this dataset, so you should add questions or accept that you can only see bigger changes.

## Consistency

For questions that were asked more than once, Nasute reports the spread (the highest minus the lowest Answer correctness) and Pass^k (the share of questions answered well on every repeat), where "well" means that Answer correctness reached `pass_at` (default 0.75) on every repeat. A question with a missing repeat is left out of Pass^k and counted separately, rather than counted as a pass, and questions with a spread of at least `worse_by` are listed as flaky.

## Where Nasute differs from the paper

A few choices differ from Miller's paper, or are simplifications of it.

- Like the paper (its equation 3), Nasute uses the normal value 1.96 and not a t-table. This is a shared approximation, and with very few questions (under about 30) the intervals cover the true score less often than 95% of the time.
- Wilson with repeats uses the inflation shortcut described above, not a full clustered Wilson interval.
- Intervals on averages are not clamped to 0 and 1, so a small sample can show an interval such as 0.01 to 1.32, in which case you should read the part past 1 as "could be anything near the top". The `runs` list clamps it for display.
- The paper's other ideas, resampling and next-token probabilities, are not used.

## Related

- The formulas for each score are in [scores](../reference/scores.md).
- The settings used here (`repeats`, `temperature`, `pass_at`, `detect` and `worse_by`) are in [settings](../reference/settings.md).
- Real numbers from a real run are in [How Nasute works](../how-nasute-works.md).

---

← [Previous](README.md) · [Next](why-the-judge-says-yes-or-no.md) →
