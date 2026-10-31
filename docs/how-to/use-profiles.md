[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Use profiles

A profile is a named table of settings that Nasute merges over your base settings when you pass `--profile NAME`. Profiles let you keep a quick check and a careful run side by side without editing the file each time, and there is no special code behind them.

Two profiles come with the starter file and with `nasute.example.toml`.

| Profile | What it sets | Use it |
| --- | --- | --- |
| `smoke` | 3 questions, 1 repeat, quick judge, prompt cache on | For a quick look after a change, to see whether you broke anything. |
| `deep` | all questions, 3 repeats, claims judge, cache off, a pause of 5 seconds after each call, and a fresh judge-check first if `judge_check = true` | For a careful run, usually overnight. |

In the starter file `deep` has `judge_check = false`, so you switch it on once you have a judge set (see [check the judge](judge-check.md)).

## Make your own

To define another profile, add a table to `nasute.toml`. This example asks 10 questions twice with the claims judge.

```toml
[profiles.medium]
limit = 10
repeats = 2
[profiles.medium.judge]
mode = "claims"
```

You then run it with `nasute run --profile medium`. A few rules decide how profiles behave.

- Any setting can go in a profile, including sub-tables such as `[profiles.medium.judge]`, and tables merge key by key, so the rest of `[judge]` stays as it was.
- Options on the command line (`--limit`, `--repeats`, `--mode`) beat the profile, and an unknown profile name stops the run.
- Each run records its profile, judge mode and repeats. `compare` warns when two runs differ in any of them, and it gives no verdict when both runs name a profile and the profiles differ, so compare a `smoke` run with a `smoke` run.

The order in which all settings are applied is in [settings](../reference/settings.md#order-of-precedence).

---

← [Previous](tag-questions.md) · [Next](compare-runs.md) →

---

← [Previous](tag-questions.md) · [Next](compare-runs.md) →
