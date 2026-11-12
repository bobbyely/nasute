# Changelog

## 0.1.0 (unreleased)

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
