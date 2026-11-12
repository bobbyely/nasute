[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](README.md) · [Explanation](../explanation/README.md)

# Reference: settings

This page is for looking up a setting: its default, how settings combine, and what each kind of target accepts. Nasute reads its settings from a TOML file called `nasute.toml`, and every setting has a default in the code, so the file is optional.

**What each setting does is explained in the comments of [`nasute.example.toml`](../../nasute.example.toml), which is the single source of truth, so this page does not repeat those explanations.** It adds what the example file does not hold: the defaults at a glance, the order in which settings are applied, and the settings of each target kind.

## Where the file is found

Nasute reads `--config FILE` if given, else `./nasute.toml` in the current folder.

Relative folders in the file (`datasets`, `runs`, `report`) start from the file's own folder, not from the folder where you run Nasute.

## Order of precedence

The same setting can come from several places, and the more specific place wins. From lowest to highest priority:


1. The defaults in the code.
2. The settings file.
3. The profile named by `--profile`, merged over the above. Tables merge key by key (a profile that sets `[profiles.deep.judge] mode = "claims"` leaves the rest of `[judge]` alone).
4. Command line options (`--limit`, `--repeats`, `--mode`).

## Top-level settings and defaults

These settings sit at the top of the file, outside any table, and the table below gives the default of each.

| Setting | Default |
| --- | --- |
| `datasets` | `["datasets"]` |
| `runs` | `"data/runs"` |
| `report` | `"data/report"` |
| `report_url` | `""` (the link printed after a run is a `file://` address; set it to where the report folder is served, and the link starts with it) |
| `dataset` | `""` |
| `judge_set` | `""` |
| `k` | `5` |
| `timeout` | `180` |
| `limit` | `0` |
| `repeats` | `1` |
| `pass_at` | `0.75` |
| `detect` | `0.05` |
| `worse_by` | `0.2` |
| `min_attempts` | `5` |
| `mislabel_easy_below` | `0.5` |
| `mislabel_hard_above` | `0.9` |
| `judge_check` | `false` |
| `temperature` | `0.0` |
| `pause` | `0` |
| `max_temp` | `0` |
| `concurrency` | `1` (questions asked at once; a target's own `concurrency` wins. 0.1.0 called it `workers`, which still works) |
| `max_cost` | `0` (no cap; else US$ a run may spend on answers plus judging) |
| `run_targets` | `[]` (the dataset's own target; else the targets to run in turn and rank) |
| `max_judge_errors` | `0.1` |

**`concurrency`.** How many questions are asked at once. Keep 1 for a local model that does one request at a time. A target can set its own, for example `concurrency = 8` for a cloud API. Results are saved in dataset order whatever order they finish in, each repeat keeps its seed (its number), and progress lines are numbered as attempts finish. The run stops after 3 questions in a row could not reach the system or the judge: "in a row" means 3 questions next to each other in the dataset, checked in that order. With more than one at once, the questions already being asked when that happens finish first.

**`max_cost`.** A spending cap in US dollars for one run, counting the answers' cost and the judge's, as their replies report them. Once the run has spent more, no new question or repeat starts. The ones being asked finish and are kept, so a run can go a little over. The run is then marked stopped early (`aborted` in its summary, with the reason), which the end summary and the run page show. When a reply reports no cost (a local model, say), a warning says so once and only reported cost counts. With several targets, each run has its own cap. See [run several targets](../how-to/compare-runs.md#run-several-targets-in-one-command).

**`run_targets`.** A list of target names, such as `["model-a", "model-b"]`, usually in a profile. `run` asks each the same questions in turn, each as its own run, then prints one summary ranking them. `--target`, given once or more, overrides it.

## `[judge]`

The `[judge]` table configures the model that marks the answers. It is kept separate from the targets so that you can change the judge without touching the system you measure.

| Setting | Default |
| --- | --- |
| `url` | `"http://127.0.0.1:8080/v1"` |
| `model` | `""` (the first model the address lists) |
| `timeout` | `240` |
| `mode` | `"quick"` (or `"claims"`, or `"knowledge"` for plain chat models) |
| `cache` | `false` |
| `retries` | `2` |
| `headers` | `{}` |
| `concurrency` | `1` (judge requests at once; a hosted judge can take more) |
| `fence` | `true` (the built-in prompts fence the answer off; `false` is the 0.1.0 prompts) |
| `prompts` | `{}` (every judge prompt is the built-in one) |

**`fence`.** An answer is text from the system under test, so it can hold lines that look like the judge's trusted fields, such as `REFERENCE: ...`. With `fence = true` the built-in `quick`, `abstain`, `knowledge` and `knowledge_abstain` prompts put the answer first, between a `<<<ANSWER` line and an `ANSWER>>>` line, and the question, reference and extracts after it. Before any answer goes into any prompt, built-in or custom, Nasute takes both markers out of it, so an answer cannot close the fence early. `split` and `check` (claims mode) are the same either way; only the markers are taken out. With `fence = false` every built-in prompt is the 0.1.0 text and answers go in unchanged: use it to compare with runs from 0.1.0. Runs record the setting, and a run with the other setting has its judged scores marked "not comparable". The prompts and the numbers behind them: [judge prompts](judge-prompts.md).

### `[judge.prompts]`

Each key names one judge prompt, and its value is a path to a UTF-8 text file that is sent instead of that built-in prompt. A relative path starts from the settings file's folder. Prompts you do not name keep the built-in text, which is in [judge prompts](judge-prompts.md).

| Key | Replaces | Placeholders it must use |
| --- | --- | --- |
| `quick` | quick mode | `{question}`, `{reference}`, `{extracts}`, `{answer}` |
| `split` | claims mode, step 1 | `{question}`, `{reference}`, `{answer}` |
| `check` | claims mode, steps 2 to 5 | `{source}`, `{claims}` |
| `knowledge` | knowledge mode | `{question}`, `{reference}`, `{answer}` |
| `knowledge_abstain` | knowledge mode, unanswerable questions | `{question}`, `{answer}` |
| `abstain` | quick and claims mode, unanswerable questions | `{question}`, `{answer}` |

```toml
[judge.prompts]
quick = "prompts/quick.txt"
```

The files are checked when the settings load, before any question is asked. A file that cannot be read, is not UTF-8, misses a placeholder or has one the built-in prompt does not use stops Nasute with an error naming the file. To write a literal brace, double it: `{{` and `}}`. One newline at the end of the file is dropped. Only the path is saved with a run, not the text; the run records a short SHA-256 fingerprint of each prompt instead. See [change the judge prompts](../how-to/change-the-judge-prompts.md).

## `[targets.<name>]`

Each system under test is described by a table named by you, and the table's `kind` decides which code talks to the system.

The name follows the [naming rule](commands.md#dataset), and a table with no `kind` is an error when it is used.

Settings for every kind:

| Setting | Meaning |
| --- | --- |
| `kind` | `"http"`, `"chat"`, or `"module:function"` for your own Python function ([add a target](../how-to/add-a-target.md#a-python-function)). |
| `label` | Optional. The name the report shows for this system instead of the table name, such as `"Support bot"` (a display name only; runs and folders keep the table name). |
| `model_url` | Optional. A `/v1` address that names the model that writes the answers. Nasute asks it for the model name and records the name in each run. It is never sent questions. |
| `concurrency` | Optional. Questions asked of this target at once, instead of the top-level `concurrency`. |
| `temperature` | Optional. Sent to this target instead of the top-level `temperature` (the judge keeps the top-level one). |

### `kind = "http"`

This is the general-purpose kind, for any HTTP endpoint that answers in JSON, and its code is `src/nasute/targets/http.py`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `url` | `""` | Where to send the question. For GET, `{question}` in the url is replaced by the question, fully URL-encoded (`/` too). |
| `method` | `"POST"` | `POST` or `GET`. GET sends no body. |
| `headers` | `{}` | `{ Name = "value" }`. A value `"env:VARNAME"` is read from that environment variable at call time; trailing line breaks are removed. Only header names are ever saved with a run. |
| `request` | `{ question = "{question}" }` | The JSON body. In every string, at any depth, `{question}` is replaced by the question. Numbers and booleans are sent as written. |
| `answer` | `"$.answer"` | Path to the answer in the reply. Required. Must lead to text or a number. |
| `sources` | `""` | Optional path to the titles of the pages the system used. Empty: nothing is found, so a question that lists expected sources scores 0 on the retrieval scores. A question that lists none is not measured. |
| `links` | `""` | Optional path to the address of each source, in the same order as `sources`. One for every source, or no links are used. The report follows only `http://`, `https://` and addresses starting with `/`. |
| `extracts` | `""` | Optional path to the texts the system read. Empty: faithfulness is not measured. |
| `timeout` | the global `timeout` | Seconds for one question. |

The paths use a small subset of JSONPath, which supports `$.a.b` for a field, `$.a[0].b` for an item, and `$.a[*].b` for every item (items without `b` are skipped), but no filters, no `..` and no slices. A path that selects a list, such as `$.sources`, gives the items of that list, and items that are not text are saved as JSON text. A path that finds nothing is an error for `answer`, but for `sources` and `extracts` it simply gives an empty list.

The http target does not send `temperature` or `seed`, so if your endpoint takes a temperature, put it in `request` yourself.

### `kind = "chat"`

For a model behind an OpenAI-compatible chat API (a hosted service, Ollama, llama.cpp's server, vLLM), with no paths to write. Its code is `src/nasute/targets/chat.py`, which hands the request to the http target, so the same header and redirect rules apply.

| Setting | Default | Meaning |
| --- | --- | --- |
| `url` | `""` | The base address, ending `/v1`. Nasute posts to `<url>/chat/completions`. |
| `model` | `""` | The model to ask. Also recorded as the run's answering model. |
| `headers` | `{}` | As for http: `"env:VARNAME"` values are read from the environment, and only header names are saved. |
| `system` | none | Optional system prompt, sent before the question. |
| `temperature` | the top-level `temperature` | Sent with every question, with `seed` (the repeat number). |
| `timeout` | the global `timeout` | Seconds for one question. |

The question is the user message. The answer is read from `choices[0].message.content`, and `usage.prompt_tokens`, `usage.completion_tokens` and `usage.cost` are recorded when the reply has them. A chat target returns no sources or extracts, so use judge mode `knowledge` or `quick`.

```toml
[targets.mine]
kind = "chat"
url = "http://127.0.0.1:11434/v1"
model = "llama3.2"
```

## `[profiles.<name>]`

A profile lets you keep several named bundles of settings in one file. It is a table holding any of the settings above, including sub-tables such as `[profiles.deep.judge]`. See [use profiles](../how-to/use-profiles.md).

---

← [Previous](commands.md) · [Next](scores.md) →
