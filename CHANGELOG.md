# Changelog

## 0.2.0 (unreleased)

- Judge mode `knowledge`, for plain chat models that cite no sources: is the reference's key fact in the answer, and is
  anything false? Extra true detail is fine. Right scores 1, right with an error 0.5, wrong 0. Questions about made-up
  things get their own prompt: declined scores 1, declined with a false claim 0.5, made something up 0.
- Tokens and cost: the `http` target reads `tokens_in`, `tokens_out` and `cost` from the reply. Each answer records them,
  a run totals them, the judge's own use is totalled too, and the report shows them.
- `examples/`: settings for an OpenAI-compatible API and for Ollama.
- `SECURITY.md`, `CONTRIBUTING.md` and `llms.txt`.
- Fixed: doc pages showed their footer two or three times; a few messages still said `python3 nasute.py`.

## 0.1.0

First release as its own package. Named targets (`http`, or any `module:function`), suites, profiles,
claim-level judging counted in code, clustered error bars and paired compare (Miller 2024), judge-check,
a static report, dataset versions, and a demo dataset about a made-up garden handbook.
