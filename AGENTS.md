# AGENTS.md — Nasute

Start here. This file is for any coding agent working in this repo.

Nasute asks a system under test questions with known answers, marks the answers, keeps each run, compares runs, and writes a static report. Any HTTP endpoint is a target (`http`); anything else is one function named in the settings (`kind = "module:function"`). The manual is `docs/` (start at `docs/README.md`); `README.md` is the short version. **Docs agents: the exact facts are in `docs/reference/`.** The pages are checked against the code by `tests/nasute_test.py`.

Plain Python 3.11+, standard library only. No runtime dependencies: keep it so.

## Where things are

| Path | What |
| --- | --- |
| `src/nasute/__init__.py` | Everything generic: settings and profiles, datasets, statistics, judge, judge-check, run, suites, compare, command line (`main`). |
| `src/nasute/manage.py` | `init`, `dataset check/import/list`, `runs ...`, `serve`. |
| `src/nasute/pages.py` | Writes the static report folder. |
| `src/nasute/demo_server.py` | `nasute demo-server`: a stand-in system and judge for the quick start. |
| `src/nasute/assets/` | `report.js`, `report.css` (all pages) and the vendored uPlot, Chart.js and Chart.js boxplot plugin, each with its licence. |
| `src/nasute/starter/` | What `nasute init` copies out. |
| `src/nasute/targets/http.py` | The generic target: any JSON endpoint, paths `$.a[0].b`. |
| `src/nasute/datasets/<name>/v<N>.jsonl` | Questions. Header line first. `demo` is ten questions about a made-up handbook (`demo/handbook.md`); `judge-demo` is answers with known faults, to test the judge. Both are used by the tests. |
| `nasute.example.toml` | Every setting explained. |
| `examples/` | Settings for an OpenAI-compatible API and for Ollama. The test checks each uses only real settings. |
| `llms.txt` | An index of the docs for language models. Added a page to `docs/`? Add it here too. |
| `docs/` | The manual, Diátaxis style: quick start, how it works, how-to, reference, explanation. |
| `tests/nasute_test.py` | Checks. Fake data, no network, no model, no install. Also checks `docs/`: links, commands, scores, prompts, settings. |

## Rules

- **Nothing about any one deployment.** No real hostnames, addresses, private questions or people's names in code, docs or datasets. Examples use made-up systems.
- **A dataset file is never edited.** A change is a new `v<N+1>.jsonl`.
- **Private questions never go in the repo.** Users keep them in their own datasets folder.
- **Never log question or answer text.** Ids, counts and scores only.
- **The judge never gives a score.** It says yes or no about single claims; `src/nasute/__init__.py` counts them and writes the count sentence that explains each score. Keep it so. Every judge prompt is in `docs/reference/judge-prompts.md` in full; a test fails if they drift apart.
- **One glossary.** Names and meanings of scores live in `GLOSSARY` in `src/nasute/__init__.py`, are embedded in every report page, which reads them. Do not copy them into the page script.
- **Statistics follow Miller 2024** (arXiv 2411.00640): clustered standard errors for repeats, paired differences for compare. Changed a formula? Change `docs/explanation/statistics.md`, `docs/reference/scores.md` and the test that works it out by hand.
- **A new target kind is one function**, named in the settings as `kind = "module:function"` (`target_ask()` imports it); most systems need none, the `http` kind does it from settings. No plugin machinery. Built-in kinds are in `TARGETS`.
- **A suite is dataset × target.** Runs, baselines, compare, charts and measured difficulty are grouped by it. 
- **Secrets never reach a run, a report or an error.** Header values may be `env:NAME`; `public()` in `src/nasute/__init__.py` keeps header names only, at every depth, and hides key/token/secret/password settings; `resolve_headers()` names the header, never its value, when one is bad. Keep it so for any new setting that could hold a key.
- **Names become paths, so they are checked.** Dataset, target and suite parts go through `check_name()` (letters, digits, `_ . -`); a suite id is `dataset@target` and `@` is not allowed in a name. The report refuses symlinks and anything outside its folder.
- **The report is static and self-contained.** Page data is JSON in the page (`<` written `\u003c`); `src/nasute/assets/report.js` inserts text with `textContent` only, no `innerHTML`, no inline handlers. A test fails otherwise. Changed `pages.py` or `report.js`? Open the pages in a browser (file://) at phone width, light and dark.
- **The report goes dashboard (`index.html`), dataset (`datasets/<name>.html`), run (`<suite>/runs/<run>.html`).** A suite's old `index.html` is a redirect page with no script. A score not measured (`measured()` in `src/nasute/__init__.py`) is masked to null in page data, never shown as 0.00 or in the warning colour; a chart with nothing in it is left out.
- **Logging: `log()` only.** `--log text|json` (else `NASUTE_LOG`, else text at a terminal, JSON otherwise) picks the formatter (`Readable` or `JsonLines`); a server reads the JSON lines, so a new event keeps ids, counts and scores in its details.
- **uPlot, Chart.js and its boxplot plugin are vendored, not edited.** uPlot draws the over-time charts on every page that has them; Chart.js 4.5.1 (`chart.umd.min.js`) and @sgratzl/chartjs-chart-boxplot 4.4.5 (`chartjs-chart-boxplot.umd.min.js`) draw the per-question charts and load on the run page only. Versions and SHA-256 are in `docs/reference/data-layout.md`; to update, replace the files from the npm tarballs (`npm pack`), keep the licence files, and change both. The plugin needs Chart.js 4.1.1 or newer. Never take them from a CDN at page view.
- **Dataset versions are `major.minor.patch`.** `v2.jsonl` (old) is `2.0.0`; versions sort as number tuples (`manage.bump` picks the part on import). Run summaries store the version as text; an old whole number is shown as `N.0.0`.
- **Exports share one function.** `run_csv()` and `suite_csv()` in `src/nasute/__init__.py` write the report's CSV files and `runs export`; the copied summary goes through `public()`; text cells that start with `= + - @`, or have one after a `;` or tab, get an apostrophe (`csv_safe`).
- **A source is a link only if it is http(s) or starts with a single `/`** (`safeUrl` in `report.js`, tested with node); `links` from a target must line up one to one with `sources`.
- **Do not call the live model in tests.** `tests/nasute_test.py` must pass with no network.
- A new setting goes in `DEFAULTS` and `nasute.example.toml`; the test fails if one is missing. A profile is just a table of settings: no code per profile.
- `--profile smoke` is the small live run; `deep` takes hours.
- Changed the score definitions, file formats or report? Update the page in `docs/reference/` (scores, file-formats, data-layout) in the same change; scores and prompts are checked by a test, the rest is on you.

## Check

```bash
python3 tests/nasute_test.py
```

## Release

Bump `version` in `pyproject.toml`, add a `CHANGELOG.md` entry, tag `v<version>` and push the tag. GitHub builds it and publishes to PyPI (trusted publishing, no stored password).
