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
| `workers` | `1` |
| `max_judge_errors` | `0.1` |

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

## `[targets.<name>]`

Each system under test is described by a table named by you, and the table's `kind` decides which code talks to the system.

The name follows the [naming rule](commands.md#dataset), and a table with no `kind` is an error when it is used.

Settings for every kind:

| Setting | Meaning |
| --- | --- |
| `kind` | `"http"`, or `"module:function"` for your own Python function ([add a target](../how-to/add-a-target.md#a-python-function)). |
| `label` | Optional. The name the report shows for this system instead of the table name, such as `"Support bot"` (a display name only; runs and folders keep the table name). |
| `model_url` | Optional. A `/v1` address that names the model that writes the answers. Nasute asks it for the model name and records the name in each run. It is never sent questions. |

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

## `[profiles.<name>]`

A profile lets you keep several named bundles of settings in one file. It is a table holding any of the settings above, including sub-tables such as `[profiles.deep.judge]`. See [use profiles](../how-to/use-profiles.md).

---

← [Previous](commands.md) · [Next](scores.md) →
