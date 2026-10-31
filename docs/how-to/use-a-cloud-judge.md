[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Use a cloud judge

A hosted model is usually stronger than a small local one, and because it is a different model from the system under test, it avoids the problem of a judge marking its own homework. This guide shows how to point Nasute at one.

1. Find an OpenAI-compatible address that ends in `/v1`, and the name of the model you want to use.
2. Put the key in an environment variable that holds the whole header value, for example `export JUDGE_API_KEY="Bearer sk-..."`.
3. Edit the `[judge]` table:

   ```toml
   [judge]
   url = "https://api.example.com/v1"
   model = "the-model-name"
   headers = { Authorization = "env:JUDGE_API_KEY" }
   ```

4. A hosted model takes several requests at once, so you can set `workers = 4` to run four questions together.
5. Run `nasute judge-check` before you trust the scores, because it tells you how reliable this judge is (see [the judge-check](judge-check.md)).

A few things are worth knowing before you switch.

- Runs record the judge model and the header names, but never the key.
- Scores from different judges are not comparable, so changing the judge starts a new line of results.
- Nasute does not need an outside AI to keep working, because the judge is just a setting that you can point back at a local model.
- A claims-mode run makes five requests per answer, so keep an eye on the cost.

---

← [Previous](run-overnight.md) · [Next](judge-check.md) →

---

← [Previous](run-overnight.md) · [Next](judge-check.md) →
