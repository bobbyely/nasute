[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Read a run page

You use this guide when a score looks wrong and you want to see why. Every number in Nasute traces back to the claims behind it, and the run page is where you follow that trail.

1. Open `report/index.html`, click a suite's run count, and then click "Every question of this run" (which opens the latest run) or pick an older run from the table of runs. You can also open `report/<dataset>@<target>/runs/<run>.html` directly.
2. Read the counting line at the top of the page first, such as `32 asked · 32 scored · 0 system errors · 0 judge errors`, because it tells you what was left out of the scores.
3. The table "Every question" has one row per question, with its number (`#`, its place in the dataset file), the question and its id, its scores and, for a weak one, a cause. You can filter by failed or got worse, by cause, topic or text, and you can sort by any column. The filters and the sort apply to all the questions first, and the table then shows them 50 to a page, with Previous and Next buttons above and below.
4. Click a row to open the question on its own view (see below), which shows the question, the reference answer, the answer, the sources the system found, and the sources you expected. When the system gives an address for a source, its name is a link that opens the page in a new tab. A link is only followed if it starts with `http://`, `https://` or a single `/`, so an address of any other kind stays plain text.
5. Under "Claims in the answer" each claim has two marks: the first says whether the extracts (what the system read) back it, and the second says whether it matches the reference. The judge's few words of reason sit beside each mark, and "Facts in the reference" shows the same thing the other way round (claims mode only).
6. "Scores, and how each was counted" shows the sentence behind each score, such as `Faithfulness 0.80 = claims backed by the extracts / claims in the answer = 8 / 10`.

![A run page with one question opened](../images/report-run.png)

*A run page from a demo report, with one question opened to show its claims and count sentences.*

## The charts on the run page

The run page starts with two charts, drawn with one dot for each question, so you can see which questions sit behind a score before you read any of them. Hover over a dot, or move between dots with the arrow keys, to see the question and its scores. Click a dot, or press Enter, to open that question. On a phone, tap a dot once to see its tooltip and a second time to open it.

The scatter puts Faithfulness (how much of the answer the extracts back up) on the left-to-right axis and Answer correctness (how well it matches the reference) on the other, and a line at 0.5 splits it into four corners. The top right, "grounded and right", is where you want questions to be. The bottom right, "grounded but wrong", holds answers that the extracts support but that do not match the reference, which points at the retrieval step finding the wrong page, or at a reference the system cannot be expected to match. The top left, "right but not backed", holds correct answers that the extracts do not support, so the system may have answered from memory. The bottom left, "neither", is the worst. Each corner label shows how many dots are in it, and a score of exactly 0.5 counts as the high side. Scores cluster at 0, 0.33, 0.5 and 1, so the dots are nudged slightly apart; the tooltip always shows the exact scores. Switch between "per question" (the mean over its repeats) and "per attempt" to see the spread between repeats. A question with no Faithfulness score is left out, and a note says how many and why; an unanswerable question has none.

You can colour the dots by difficulty, by origin tag (the commonest tag after the first one), by topic (the first tag), or by failure cause, and the legend turns a group on or off. Only three groups get a colour of their own, and any more are folded into a grey "other", so the colours stay easy to tell apart; each group also has its own shape.

The box plots show one score at a time (Answer correctness, Faithfulness, Answer relevancy, Hit rate or MRR) for each group, with the groups left to right, weakest first (or easy to hard for difficulty). They are Tukey box plots. The box is the interquartile range (IQR), from the first quartile (Q1) to the third (Q3), so it holds the middle half of the questions. The line inside it is the median and the ring is the mean. The whiskers reach the furthest question within 1.5 × IQR of the box, and any question beyond them is an outlier. Every question is also drawn as a dot, and under each box are its count (n) and mean (on a narrow screen with many groups, only the name; the rest is in the hover). Hovering a box lists these numbers and names the outliers. A group with fewer than four questions shows only its dots, because quartiles of so few questions mean little.

Both charts have a hidden table for screen readers, which lists each group with its count and its medians and means.

## One question on its own

Clicking a row or a dot shows just that question, across the whole page, and the address becomes `...<run>.html#q-<id>`, so you can send the link to someone else. The page shows a breadcrumb (the overview, the suite, the run, and "Question 12"), the reference answer, the answer for each repeat with its sources, the claims and the count sentence behind every score, and the timings. "Previous question" and "Next question" follow the order the table was showing, including its filters and sort, so you can step through just the failed ones. The browser's Back button returns to the table on the page that holds the question, scrolled to where you were, and the table keeps its filters and sort.

## Marking a change on the charts over time

Give a run a label when you start it, such as `nasute run --label "prompt change"`, or later with `nasute runs label`. On the suite page the charts over time mark every labelled run with a small triangle, and hovering over that run shows its label, so you can see where a change happened.

## What to look for

Some patterns come up often, and each points to a different kind of problem.

- **A score is low but the claims look right.** The judge or the reference may be wrong, and the cause column shows `judge?`, which means "take a look" rather than "the judge is wrong".
- **The answer lists claims it never made.** The judge invented them, which has been seen on refusals, so it is a judge fault.
- **Hit rate@k is 0 but the answer is right.** The system found a related article instead of the one the dataset lists, so you need to decide whether the dataset should list both.
- **A system error or judge error line appears.** A system error counts as 0 against the system, whereas a judge error leaves the answer out. See [how errors count](../explanation/how-errors-count.md).

The causes are `retrieval` (the right article was not found), `generation` (it was found but the answer is still wrong), `judge?` (the marks disagree) and `system` (an error or timeout).

---

← [Previous](baselines-and-labels.md) · [Next](export-a-run.md) →
