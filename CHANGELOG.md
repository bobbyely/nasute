# Changelog

## 0.2.0 (unreleased)

- Judge prompts can be changed from the settings: `[judge.prompts]` names a text file per prompt (`quick`, `split`,
  `check`, `knowledge`, `knowledge_abstain`, `abstain`). Each file is checked when the settings load: readable UTF-8,
  and exactly the placeholders of the built-in prompt it replaces (a literal brace is `{{` or `}}`). The reply shapes,
  checks and counting do not change.
- Runs and judge-checks record a short SHA-256 fingerprint of each judge prompt they used, and which were custom
  (`judge_prompts` in the summary). `compare` and the report say when two runs used different prompts and mark their
  judged scores "not comparable", as for different judge models. A run's judge reliability only counts a check made
  with the same prompts. The run page and `runs show` say "custom judge prompts: ...".
- `nasute prompts export FOLDER` writes the six built-in prompts as text files to start from. It never overwrites.
- A spending cap: `max_cost` (US$, answers plus judging; at the top level or in a profile; `--max-cost`). Past it, no new
  question or repeat starts; the ones being asked finish and are kept. The run is marked stopped early with the reason,
  in the log, the end summary and the run page. Cost that a reply does not report cannot count: a warning says so once.
- Several targets in one command: `run_targets = ["a", "b"]` (usually in a profile) or `--target` given more than
  once. Each target runs in turn as its own run, with its own spending cap; one that fails does not stop the others.
  A summary ranks them by the main score with its range, cost and seconds per answer, and two get the paired compare.
  A run that could not reach the system or judge counts as failed (exit 1); one stopped by the spending cap is ranked,
  marked partial.
- A `chat` target kind for OpenAI-compatible chat APIs: `url`, `model`, optional `headers`, `system` and `temperature`.
  It reuses the http target, so its header, redirect and usage checks apply. The examples use it.
- `concurrency` (was `workers`, which still works): questions asked at once, also per target, with `--concurrency` to
  override. `[judge] concurrency` limits judge requests at once (default 1, so a local judge is never flooded; with
  `workers` above 1 in 0.1.0 the judge got as many). A target's own `temperature` now wins over the top-level one.
- Fixed: two runs (or judge-checks) started in the same second no longer crash the second one. Run folders are made
  exclusively, and a clash gets a suffix such as `20261112T005857Z-2`.
- Fixed: a `module:function` target's reply can no longer overwrite the question's fields (`id`, `reference`,
  `answerable`, expected sources). Only the reply keys `http` returns, plus `unreachable` and `extracts_failed`, are kept.
- Fixed: `runs delete`, `runs label` and `runs baseline` rewrite the report, so a deleted run's page and its copied
  results are no longer left for `serve` to show.
- Fixed: a judge set's `answer`, `extracts`, `kind` and `expect` are type-checked by `dataset check`, and `judge-check`
  stops before judging a set with a bad field instead of failing at the end.
- Fixed: "Why questions failed" no longer gives retrieval as the cause when the system cited no sources at all (hit
  rate not measured), as with plain chat models.
- The README is shorter: what Nasute is, a Features list (with the judge modes in a table), and a four-step quick start.
  Running from a clone moved to CONTRIBUTING.md. Nasute is described as a tool for any AI system that answers
  questions, not only RAG; the PyPI summary says so from this release.

## 0.1.0 (12 November 2026)

The first release. Named targets (`http`, or any `module:function`), suites, profiles, claim-level judging counted in code,
clustered error bars and paired compare (Miller 2024), judge-check, dataset versions, and a demo dataset about a made-up
garden handbook. Also:

- The report: dashboard, dataset, run. The front page shows each dataset with its systems ranked by their latest
  main score, cost and seconds per answer, and a table of recent runs to tick and compare (runs on different datasets:
  headline scores only, with a note that the questions differ). A new page per dataset lists every run on it; tick any
  to compare them question by question, with the paired test for two. The run page holds the numbers: the answer and
  headline scores first, then every question with its outcome (right, partly right, wrong, declined, made something up,
  system error), then the charts.
- The run page opens with "At a glance": a stacked bar of outcomes for each difficulty (right, right with an error, wrong,
  system error; declined, made something up), in colour-blind-safe colours; tap a block to list those questions. On a
  phone the question list stops at 10 with "Show all". The charts gain one "Group by" picker (difficulty, each tag, topic,
  cause) for score by group (a strip of dots when scores take three values or fewer, else a box), seconds, tokens out and
  cost per answer, and a scatter of score against seconds.
- A score with nothing to show is left out of the report and the run summary instead of showing as 0.00: source scores
  when the system names no sources, and scores set only on failed attempts. Charts with nothing in them are left out.
- Logging: short readable lines at a terminal (`[3/24] gold-79 ... right (2.1 s)`, failures marked WARNING), JSON lines
  otherwise; `--log text|json` and `NASUTE_LOG` choose. A run ends with a summary: measured scores with their 95% ranges,
  system errors, tokens and cost, and a link to its report page (`report_url` setting, else `file://`).
- `nasute init --demo`: settings for `nasute demo-server`, so the demo is three commands.
- Judge mode `knowledge`, for plain chat models that cite no sources: is the reference's key fact in the answer, and is
  anything false? Extra true detail is fine. Right scores 1, right with an error 0.5, wrong 0. Questions about made-up
  things get their own prompt: declined scores 1, declined with a false claim 0.5, made something up 0.
- Tokens and cost: the `http` target reads `tokens_in`, `tokens_out` and `cost` from the reply. Each answer records them,
  a run totals them, the judge's own use is totalled too, and the report shows them.
- `examples/`: settings for an OpenAI-compatible API and for Ollama.
- `SECURITY.md`, `CONTRIBUTING.md` and `llms.txt`.
- Security, from an audit before release: token counts and costs must be finite numbers of 0 or more (a NaN from a system
  under test blanked the report); saved settings hide anything under a key-, auth- or credential-like name at any depth, and
  keys in URLs; CSV cells get an apostrophe before a formula character after `;` or a tab too; `serve` on 127.0.0.1 answers
  only localhost names; a redirect to another host drops the configured headers; the demo server refuses a missing or huge
  request; the PyPI publish step is pinned to a commit; a test checks the vendored scripts' SHA-256.
