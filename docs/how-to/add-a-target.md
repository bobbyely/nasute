[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Add a target

A target is the system you want to test, and you add one when you want Nasute to ask questions of something new. Most systems need no code at all, because the `http` kind can talk to anything that answers in JSON, but a system that is not behind HTTP needs one small Python function.

A target is a `[targets.<name>]` table in `nasute.toml`, with a name that you choose, and the first line of a dataset says which target the dataset is for.

## An HTTP endpoint

You describe the endpoint in settings, and Nasute builds the requests from your description. The example below is for an OpenAI-compatible chat endpoint.

```toml
[targets.mine]
kind = "http"
url = "https://api.example.com/v1/chat/completions"
headers = { Authorization = "env:MY_API_KEY" }
request = { model = "my-model", messages = [{ role = "user", content = "{question}" }] }
answer = "$.choices[0].message.content"
```

1. Set `url` and, if you need it, `method`, which is `POST` by default and can also be `GET`. For `GET` you put `{question}` in the url.
2. Keep any key in an environment variable and refer to it as `"env:NAME"`. Set it in your shell before you run, for example `export MY_API_KEY="Bearer sk-..."`, and Nasute reads it when it makes the call. Runs save header names only, never values.
3. Write `request` as the JSON body. Nasute replaces `{question}` in every string of it.
4. Use `answer` to say where the answer is in the reply. You can also set `sources`, which points at the titles of the pages the system used, and `extracts`, which points at the text it read. The retrieval scores (Hit rate@k, Recall@k and MRR) are not measured for a question that lists no expected sources, but if a question does list them and the target returns none, they count as misses (0). Without `extracts`, Faithfulness is not measured. If the system also gives an address for each page, set `links` to the path of those addresses, in the same order as `sources`, and the run page turns each source name into a link (only `http://`, `https://` and addresses starting with `/` are followed). There must be one address for every source: if the counts differ, no links are used, so a link never lands on the wrong source. You can also give the system a friendly name in the report with `label = "My system"`.
5. Optionally set `model_url`, a `/v1` address that names the model, so that each run records which model answered.

A path is `$.a.b` for a field, `$.a[0].b` for an item, or `$.a[*].b` for every item, and nothing more elaborate is supported. Every setting is listed in [settings](../reference/settings.md#kind--http).

## A Python function

If your system is not behind HTTP, you can write one function that Nasute calls for each question. You do not edit Nasute itself.

1. Create a Python file next to your `nasute.toml`, such as `my_target.py`, containing an `ask(question, settings, timeout)` function that returns a dict:

   ```python
   def ask(question, settings, timeout):
       text = my_system(question)                 # your code
       return {"answer": text, "sources": [], "extracts": [], "first_text_s": None, "total_s": 1.0, "error": None}
   ```

2. Make sure the function never raises an exception, and put any problem in `error` instead. Add `"unreachable": True` if it could not connect at all, so that Nasute waits and retries, and add `"extracts_failed": True` if it could not get the text the judge needs, in which case Faithfulness is not measured and the failure is not held against the system. Nasute keeps only these keys, plus `links`, `tokens_in`, `tokens_out` and `cost`; anything else in the dict is dropped, so a target cannot change the question, reference or expected sources it is judged against.
3. Use the `temperature` and `seed` values in `settings` if your system can take them.
4. Add a `[targets.<name>]` table with `kind = "my_target:ask"` (the module, a colon, the function), and a dataset whose header says `"target": "<name>"`. Nasute imports the module from the folder of `nasute.toml`, or from anywhere Python can already import it.

Settings are trusted: a `module:function` kind runs whatever code it names.

`src/nasute/targets/http.py` is a worked example of the same shape.

## Check it

A one-question run is the quickest way to confirm that your paths find the answer.

```bash
nasute dataset check my-questions
nasute run --limit 1
```

If the answer is missing, the run page names the system error.

---

← [Previous](README.md) · [Next](write-a-dataset.md) →
