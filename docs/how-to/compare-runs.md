[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Compare two models on the same questions

This guide is for the moment when you have two candidate systems, perhaps two models, and want to know whether model B is better than model A on the same questions. The method is to ask one dataset of both targets and then compare the two runs by id.

1. Add a target for each model, as described in [add a target](add-a-target.md), and call them `model-a` and `model-b`.
2. Write the dataset once, with `"target": "model-a"` in its header.
3. Run the dataset against each target:

   ```bash
   nasute run --dataset my-questions --target model-a
   nasute run --dataset my-questions --target model-b
   ```

   The `--target` option asks the dataset's questions of another target. Each target forms its own suite, `my-questions@model-a` and `my-questions@model-b`, because a suite is one dataset asked of one target.
4. Find the two run ids with `nasute runs`, and compare them by id with the older run first:

   ```bash
   nasute compare RUN_A RUN_B
   ```

Two runs can be compared when they used the same dataset file, meaning the same SHA-256 fingerprint, whatever their targets. `compare` pairs the questions of the two runs and prints, for each score, both means, the change, its 95% CI (range) and a verdict of real gain, real drop or within noise. It then lists the questions that got worse or better, and when the targets differ it adds a note saying "same questions, different targets".

A baseline, and `nasute compare` with no ids, stay inside one suite. In the report you can compare across targets too: open the dataset's page, tick the two runs in its list of runs, and press Compare. You get the headline scores side by side, the same paired test as `nasute compare` (for up to the 30 newest runs of the dataset file), and a question-by-question grid of outcomes, by default only where the runs differ. You can tick more than two runs; the paired test is for two.

On the dashboard you can also tick runs on different datasets. They asked different questions, so the report shows only their headline scores, cost and speed side by side, with a note that this is not a like-for-like test.

Nasute prints "not comparable" and gives no verdicts when the dataset file differs, when a run stopped early, or when both runs name different profiles. For judged scores the judge model must also be the same, because scores from different judges are not comparable, so use the same judge and the same profile for both runs. With fewer than 5 shared questions there is no verdict either, and each score shows "too few questions".

## Run several targets in one command

Instead of one `run` per target, name them all. On the command line, give `--target` more than once:

```bash
nasute run --dataset my-questions --target model-a --target model-b
```

Or keep the list in the settings, usually in a profile, and run that profile:

```toml
[profiles.shootout]
run_targets = ["model-a", "model-b"]
max_cost = 1.0           # US$ per target's run, where the API reports cost
```

Nasute runs each target in turn on the same questions, each as its own run, exactly as above. A target that fails (a bad name, a crash) is reported, and the others still run. At the end it prints one summary that ranks the targets by the main score, with its 95% range, the cost and the seconds per answer. With exactly two finished runs it also prints the paired compare. The spending cap, `max_cost`, applies to each target's run on its own, so an expensive first target never cuts the second one short.

## Before and after a change

To compare the same system before and after a change, run it twice and use `nasute compare` with no ids, which compares the newest run with the baseline. See [baselines and labels](baselines-and-labels.md).

---

← [Previous](use-profiles.md) · [Next](baselines-and-labels.md) →
