# Nasute

A self-hosted eval harness for RAG (retrieval-augmented generation: a system that looks things up and then writes an answer) and for language models. It asks a system questions with known answers, has a second AI mark the answers claim by claim, counts, and keeps every run. It tells you whether a change made things better, worse or no different, with a 95% range on every number. Named after the nasute, the soldier termite that guards the colony.

Plain Python 3.11 or newer, standard library only. Any system you can ask a question over HTTP is a target, and anything else takes one Python function.

## Quick start

```bash
pipx install nasute                   # or: pip install nasute
nasute init mytest && cd mytest        # a starter folder: nasute.toml and an example dataset
# edit [targets.mine] and [judge] in nasute.toml, then:
nasute run --profile smoke             # a quick look; the report is written to report/index.html
```

The full walk-through, which runs with no account and no model, is the [Quick start](docs/tutorial.md).

## Documentation

All of it is in [docs/](docs/README.md): a [Quick start](docs/tutorial.md), [How Nasute works](docs/how-nasute-works.md), [how-to guides](docs/how-to/README.md), a [reference](docs/reference/README.md) and [explanations](docs/explanation/README.md).

## This repo

| Path | What |
| --- | --- |
| `src/nasute/__init__.py` | The tool: settings, datasets, statistics, judge, runs, compare, command line. |
| `src/nasute/manage.py`, `pages.py` | `dataset` and `runs` commands; the static report. |
| `src/nasute/demo_server.py` | `nasute demo-server`: a stand-in system and judge for the quick start. |
| `src/nasute/targets/` | The built-in kind of target, `http`. Your own is a `module:function` in the settings. |
| `src/nasute/datasets/` | `demo`: ten questions about a made-up garden handbook (`demo/handbook.md`). `judge-demo`: answers with known faults, to test the judge. |
| `src/nasute/assets/` | The report page script and style, and three vendored libraries (MIT, each with its licence file): uPlot 1.6.32, Chart.js 4.5.1 and @sgratzl/chartjs-chart-boxplot 4.4.5. Versions and SHA-256 are in [data layout](docs/reference/data-layout.md). |
| `src/nasute/starter/` | What `nasute init` copies out. |
| `nasute.example.toml` | Every setting, explained. |
| `tests/nasute_test.py` | Checks, with made-up data: `python3 tests/nasute_test.py`. No network, no model, no install. |

## Licence

MIT (see `LICENSE`). The vendored chart libraries keep their own MIT licences, in `src/nasute/assets/`.
