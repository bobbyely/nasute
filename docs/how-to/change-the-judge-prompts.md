[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](README.md) · [Reference](../reference/README.md) · [Explanation](../explanation/README.md)

# Change the judge prompts

The judge is sent a fixed prompt for each kind of marking. You can replace any of them with your own wording. This guide shows when that is worth it, how to do it, and how to check a changed prompt before you trust its scores.

## When to do it

Change a prompt when the judge keeps slipping in the same way and the cause is the wording. For example: your answers are in another language, your judge model reads instructions in a fussy way, or you want to try fencing the answer off from the instructions. Do not change a prompt to make a score look better. A changed prompt is a different marker, so its scores are not like for like with the old ones.

You can change the words, not the shape of the reply. The JSON shape the judge must fill, the checks on its reply and the counting that turns verdicts into scores stay in the code.

## 1. Start from the real text

```bash
nasute prompts export prompts
```

This writes the six built-in prompts into the folder `prompts`: `quick.txt`, `split.txt`, `check.txt`, `knowledge.txt`, `knowledge_abstain.txt` and `abstain.txt`. It writes the set your settings pick: the fenced prompts, or the 0.1.0 ones if `[judge] fence = false`. It never overwrites a file. Which prompt is used when is in [judge prompts](../reference/judge-prompts.md).

## 2. Edit the ones you want

Edit only the prompts you mean to change. Keep every placeholder, such as `{question}` and `{answer}`, and add none: Nasute fills these in for each answer. If your text needs a real brace, for example to show a JSON example, write it doubled: `{{` for `{` and `}}` for `}`.

## 3. Name them in the settings

Add a `[judge.prompts]` table to `nasute.toml`, with one line per changed prompt. Paths start from the settings file's folder.

```toml
[judge.prompts]
quick = "prompts/quick.txt"
```

Prompts you leave out keep the built-in text. Nasute checks each file when it loads the settings. With `fence = true` (the default), Nasute takes the markers `<<<ANSWER` and `ANSWER>>>` out of every answer before it fills your prompt too, so you can fence the answer with them in your own wording and an answer cannot close the fence early. A missing placeholder, an unknown one or a single brace stops it with an error that names the file.

## 4. Check the changed prompt

Run the judge-check with the same mode and the new prompt:

```bash
nasute judge-check --mode quick
```

Compare its accuracy and kappa with a check made on the built-in prompts. Trust the new prompt's scores only if it marks the known faults at least as well. A run's judge reliability only uses a check made with the same prompts, so an old check does not vouch for a new prompt. See [check the judge](judge-check.md).

## What the report shows

Each run records a short fingerprint of every prompt its mode used, and which were custom. The run page's details say, for example, "custom judge prompts: quick", and so does `nasute runs show`. When two runs used different prompts, `nasute compare` and the report add a note, and the marked scores show "not comparable", the same as for two different judge models. Retrieval scores and error rate are still compared.

To go back, remove the line from `[judge.prompts]`.

---

← [Previous](judge-check.md) · [Next](../reference/README.md) →
