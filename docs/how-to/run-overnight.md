[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Run a deep test overnight on a shared machine

A careful run asks every question several times with the slower judge, which can keep a processor busy for hours. If the machine also does other work, that heat and load slow everything else down, so this guide shows the settings that spare it and how to start the run.

```toml
pause = 5          # seconds to wait after every call
max_temp = 80      # also wait while the CPU is hotter than this (Linux only)
concurrency = 1    # one question at a time
```

1. Estimate the time as questions x repeats x (answer time + judge time). Measured with a 7-billion-parameter model on an older laptop, a quick judge takes about 20 to 37 seconds per answer and a claims judge takes about 82 seconds, so a `deep` run of 32 questions takes about 4 to 5 hours.
2. Choose a quiet time and look at the temperature first, with `cat /sys/class/thermal/thermal_zone*/type` and `.../temp`, which reports thousandths of a degree. Start when it is under 80 degrees C.
3. Start the run with `nasute run --profile deep`. With the judge-check switched on it runs a fresh one first, so that the run records how reliable the judge is. In the starter file this is switched off (`judge_check = false`), so you switch it on once you have a judge set (see [check the judge](judge-check.md)), and if the judge-check stops because the judge cannot be reached, the run does not start.
4. You do not need to watch it. Results are saved as each attempt finishes (in `results.partial.jsonl`), so a crash loses nothing that was already done.
5. In the morning, `nasute runs` and the report show the finished run.

`max_temp` only waits between calls, and one call can keep the processor busy for tens of seconds, so the temperature can still rise above the limit during a call. Watch it the first time you run this. Raise `concurrency` only for an endpoint that takes several requests at once, such as a cloud service.

---

← [Previous](export-a-run.md) · [Next](use-a-cloud-judge.md) →
