# Contributing

Thank you for helping. Small, focused changes are easiest to review.

## Before you start

- For anything bigger than a fix, open an issue first and say what you want to change and why.
- Read [AGENTS.md](AGENTS.md). It is written for coding agents, but it is also the shortest list of the rules this code keeps: standard library only, the judge never gives a score, secrets never reach a run or a report, and the report stays static.

## Making a change

1. Fork the repo and make a branch. To try your change as the `nasute` command, install it editable in a virtual environment: `python3 -m venv .venv && .venv/bin/pip install -e .` (then `.venv/bin/nasute`).
2. Make the change. Every file starts with a short header saying what it does; comments say why, not what.
3. Changed a score, a setting, a prompt or a file format? Update the matching page in `docs/reference/` in the same change.
4. Run the checks. They need no network, no model and no install:

   ```bash
   python3 tests/nasute_test.py
   ```

5. Add a line to `CHANGELOG.md` under the unreleased version.
6. Open a pull request saying what you changed, why, and how you tried it.

## Datasets

Never add private questions or real documents. Example datasets must be made up, like the garden handbook in `src/nasute/datasets/demo/`. A dataset file is never edited: a change is a new version.

## Writing

Plain English, short sentences. Explain a term the first time you use it.
