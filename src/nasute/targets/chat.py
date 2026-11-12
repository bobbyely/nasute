"""Target: a model behind an OpenAI-compatible chat API (OpenAI, OpenRouter, Ollama, llama.cpp, vLLM and the like), with no JSON paths to write.

What it does: posts the question as the user message to <url>/chat/completions and reads the answer, tokens and cost from the reply.
It is the http target with the paths filled in, so the http target's header handling, redirect safety and usage checks all apply.
How it runs: imported by nasute, never on its own. Chosen with kind = "chat" in a [targets.<name>] table.
Reads: the API's reply, and environment variables named in headers. Writes: nothing.
Settings, under [targets.<name>]: url (the base address, ending /v1), model, headers (a value "env:NAME" is read from the environment),
system (an optional system prompt), temperature (else the run's), timeout.
It returns no sources or extracts, so the retrieval scores and faithfulness are not measured: use judge mode knowledge or quick.
"""
from . import http


def ask(question, cfg, timeout):
    """-> the http target's reply: {answer, sources (empty), links, extracts (empty), first_text_s, total_s, error, tokens_in, tokens_out, cost}."""
    messages = ([{"role": "system", "content": cfg["system"]}] if cfg.get("system") else []) + [{"role": "user", "content": "{question}"}]
    body = {"model": cfg.get("model", ""), "messages": messages}
    for k in ("temperature", "seed"):   # the harness sets both; seed is the repeat number, so repeats can differ
        if cfg.get(k) is not None:
            body[k] = cfg[k]
    # shortcut: the http target fills {question} into every string, so a system prompt that says "{question}" gets the question too; fine until someone needs that text
    return http.ask(question, {"url": cfg.get("url", "").rstrip("/") + "/chat/completions", "headers": cfg.get("headers", {}), "request": body,
                               "answer": "$.choices[0].message.content", "tokens_in": "$.usage.prompt_tokens", "tokens_out": "$.usage.completion_tokens",
                               "cost": "$.usage.cost", **({"timeout": cfg["timeout"]} if "timeout" in cfg else {})}, timeout)
