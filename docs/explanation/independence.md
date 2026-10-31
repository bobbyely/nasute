[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](../reference/README.md) · [Explanation](README.md)

# Explanation: independence

This page explains why Nasute takes care that questions do not influence each other, what it does about it, and where it cannot fully succeed. It matters most when you compare timings or run repeats, and when you want to be sure that a score reflects the system rather than the order of the questions.

If question 2 is answered better because question 1 warmed something up, then a score is measuring the order of the questions and not the system. Nasute guards against that in three ways.

## What Nasute does about it

- **Every judge call stands alone.** Each call is one message and never includes an earlier one, so the model learns nothing between requests.
- **The prompt cache is off by setting.** With `[judge] cache = false`, which the `deep` profile uses, Nasute sends `"cache_prompt": false`, so llama.cpp does not reuse earlier prompts, while other OpenAI-compatible servers ignore the extra field. Setting `true` is faster and fine for a quick look, and each run records which one it used. With the cache off the timings are honest: in one measurement the same prompt took 35 seconds cold and 3 seconds cached.
- **Repeats really sample.** Each repeat sends its own `seed` (its number: 1, 2, 3, saved in `results.jsonl`) and the run's `temperature` to the judge, and to the target if it can use them. At `temperature = 0` the judge gives the same verdict every time, so repeats then show only the system's own variation, and a warning in the log says so when `repeats` is above 1.

## What it cannot do

Nasute cannot control what happens inside the system under test. In the case-study deployment described in [How Nasute works](../how-nasute-works.md), the question-answering service keeps nothing between requests, so each question builds its prompt from scratch with no history. Its own calls to the language model do use llama.cpp's default prompt cache, however, which Nasute cannot switch off without changing that service. A later question may therefore start faster because an earlier one warmed the cache. The answers do not change, only the speed, so the time to first text is not a clean cold measure, and you should compare speed only between runs that started cold.

That service also cannot be given a temperature or a seed, because it fixes the temperature at 0.2. For it, repeats show how much search, generation and the judge vary by themselves.

The statistics treat repeats of one question as related rather than independent, which is explained in [the statistics](statistics.md#repeats-and-clustering).

---

← [Previous](the-judge-check.md) · [Next](limits.md) →
