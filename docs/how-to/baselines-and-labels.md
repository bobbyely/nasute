[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Baselines and labels

A baseline is the run of a suite that you measure against, and a label is a short name on a run, such as "before the new prompt". This guide shows how to set both, so that `compare` and the report show changes against a run you chose rather than against whatever came last.

```bash
nasute runs                                   # list runs; find the id
nasute runs baseline 20261029T121042Z         # make it the baseline of its suite
nasute runs label 20261029T121042Z "first full run"
nasute run --label "prompt change"            # label a run as it starts
nasute runs label 20261029T121042Z ""         # remove the label
```

A few rules apply.

- You can shorten a run id to its start as long as only one run starts that way.
- Each suite has one baseline. `compare` and the report measure against it when its profile fits the new run's (or when either has none), and otherwise, or when there is no baseline, they use the previous run of the suite that fits.
- A run that stopped early cannot be a baseline, and deleting a baseline needs `--yes`, as in `nasute runs delete RUN --yes`.
- Labels and baselines live only in `runs/index.json`, so no run folder is touched. After `label`, `baseline` or `delete`, run `nasute report` so that the report shows the change.

The suite page marks the baseline and shows each score's change against it.

---

← [Previous](compare-runs.md) · [Next](read-a-run-page.md) →
