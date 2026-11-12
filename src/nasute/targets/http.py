"""Target: any HTTP endpoint that takes a question and answers in JSON (a chat API, a RAG service, a small script of your own).

What it does: sends one question as a request you describe, and picks the answer, and optionally the sources and
extracts, out of the JSON reply with a small path.
How it runs: imported by nasute, never on its own. Chosen with kind = "http" in a [targets.<name>] table.
Reads: the endpoint's reply, and environment variables named in headers. Writes: nothing.
Settings, under [targets.<name>]: url, method (POST), headers, request, answer, sources, links, extracts, timeout.
  headers   {name = "value"}; a value "env:NAME" is read from the environment variable NAME at call time, so a secret
            never sits in the settings. Runs and reports record the header names only.
  request   the JSON body, as a table. Every string in it has "{question}" replaced by the question (the JSON
            encoding takes care of quotes and newlines). Not sent for GET; there, put {question} in url instead.
  answer, sources, links, extracts   paths into the reply: $.a.b, $.a[0].b, $.a[*].b. That subset only: no filters, no
            "..", no slices. answer is required and must be text; sources and extracts are optional lists of text.
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# tokens_in, tokens_out, cost: optional paths to the reply's usage figures (OpenAI-style: $.usage.prompt_tokens, $.usage.completion_tokens;
# OpenRouter adds $.usage.cost in US dollars). Recorded with each answer, never needed.
DEFAULTS = {"url": "", "method": "POST", "headers": {}, "request": {"question": "{question}"}, "answer": "$.answer", "sources": "", "links": "", "extracts": "",
            "tokens_in": "", "tokens_out": "", "cost": ""}
USAGE = ("tokens_in", "tokens_out", "cost")
STEP = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+|\*)\]")


def json_path(doc, path):
    """Every value `path` finds in `doc`, as a list (empty if the path leads nowhere). Raises ValueError for a path outside the subset."""
    if not path.startswith("$"):
        raise ValueError(f"path {path!r} must start with $")
    steps, pos = [], 1
    while pos < len(path):
        m = STEP.match(path, pos)
        if not m:
            raise ValueError(f"path {path!r}: cannot read it from position {pos} (only .name, [0] and [*] are allowed)")
        steps.append(m.group(1) if m.group(1) is not None else m.group(2))
        pos = m.end()
    found = [doc]
    for step in steps:
        nxt = []
        for node in found:
            if step == "*" and isinstance(node, list):
                nxt += node
            elif step.isdigit() and isinstance(node, list) and int(step) < len(node):
                nxt.append(node[int(step)])
            elif isinstance(node, dict) and step in node:
                nxt.append(node[step])
        found = nxt
    return found


def fill(node, question):
    """The request template with {question} put into every string."""
    if isinstance(node, str):
        return node.replace("{question}", question)
    if isinstance(node, list):
        return [fill(x, question) for x in node]
    if isinstance(node, dict):
        return {k: fill(v, question) for k, v in node.items()}
    return node


def resolve_headers(headers):
    """{name: value} with "env:NAME" values read from the environment (trailing newlines removed: a key pasted from a file often has one).
    Raises ValueError naming the header, and never quoting its value: a bad header must not leak its secret into an error."""
    out = {}
    for k, v in headers.items():
        if isinstance(v, str) and v.startswith("env:"):
            if v[4:] not in os.environ:
                raise ValueError(f"header {k}: environment variable {v[4:]} is not set")
            v = os.environ[v[4:]].rstrip("\r\n")
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", k):
            raise ValueError(f"header {k!r}: the name is not a valid header name")
        bad = not isinstance(v, str) or bool(re.search(r"[\x00-\x08\x0a-\x1f\x7f]", v)) or any(ord(c) > 255 for c in v)   # http.client sends latin-1
        if bad:
            raise ValueError(f"header {k}: the value is not allowed (it must be text with no line breaks or control characters)")
        out[k] = v
    return out


def texts(found):
    return [x if isinstance(x, str) else json.dumps(x) for x in found if x is not None]


def paired_links(reply, spath, lpath, sources):
    """The address of each source, in the order of `sources`, or [] when they cannot be paired for certain (no link beats a link on the wrong source).
    Two paths into the same array of objects ($.s[*].title and $.s[*].url) are read from each object, so a source with no address gets None.
    Two paths that each select a whole list ($.titles and $.urls) are paired by position, only when both lists are the same length."""
    sp, srest, lp, lrest = spath.rpartition("[*]")[0], spath.rpartition("[*]")[2], lpath.rpartition("[*]")[0], lpath.rpartition("[*]")[2]
    swild, lwild = "[*]" in spath, "[*]" in lpath
    srest, lrest = srest if swild else "", lrest if lwild else ""   # text after the last [*]; none when the path has no wildcard
    if swild and lwild and sp == lp and srest and lrest:   # a field of each object in the same array
        titles, links = [], []
        for el in json_path(reply, sp + "[*]"):
            t, u = json_path(el, "$" + srest), json_path(el, "$" + lrest)
            if len(t) > 1 or len(u) > 1:
                return []
            if t and t[0] is not None:
                titles.append(t[0])
                links.append(u[0] if u and isinstance(u[0], str) and u[0].strip() else None)
        return links if texts(titles) == sources else []
    if not srest and not lrest:   # whole lists
        flat = lambda p: [x for f in json_path(reply, p) for x in (f if isinstance(f, list) else [f])]
        got, raw = flat(lpath), flat(spath)   # compare with the titles before nulls are dropped, so a missing title cannot shift the links
        if len(got) != len(raw) or texts(raw) != sources:
            return []
        return [x if isinstance(x, str) and x.strip() else None for t, x in zip(raw, got) if t is not None]
    return []


class SameHostHeaders(urllib.request.HTTPRedirectHandler):
    """urllib follows a redirect with the same headers. To another host, or from https to http, only harmless ones go: the rest may carry an API key."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        old, to = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new is not None and (to.scheme.lower(), to.netloc.lower()) != (old.scheme.lower(), old.netloc.lower()):
            for name in list(new.headers):
                if name.lower() not in ("user-agent", "accept"):
                    del new.headers[name]
            new.unredirected_hdrs.clear()
        return new


# Process-wide, so the judge's requests (nasute.post) and any urlopen in a module target get it too: Nasute is a command, not a library.
urllib.request.install_opener(urllib.request.build_opener(SameHostHeaders))


def usage_number(v):
    """A token count or cost worth keeping: a finite number of 0 or more. NaN or Infinity would also make the report's page data invalid JSON."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return v >= 0 if isinstance(v, int) else math.isfinite(v) and v >= 0   # isfinite() overflows on a huge int


def ask(question, cfg, timeout):
    """-> {answer, sources, links, extracts, first_text_s, total_s, error}. Never raises."""
    cfg = {**DEFAULTS, **cfg}
    out = {"answer": "", "sources": [], "links": [], "extracts": [], "first_text_s": None, "total_s": None, "error": None, **{k: None for k in USAGE}}
    start = time.monotonic()
    try:
        method = cfg["method"].upper()
        body = None if method == "GET" else json.dumps(fill(cfg["request"], question)).encode()
        req = urllib.request.Request(cfg["url"].replace("{question}", urllib.parse.quote(question, safe="")), body,
                                     {"Content-Type": "application/json", **resolve_headers(cfg["headers"])}, method=method)
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", timeout)) as r:
            reply = json.load(r)
        found = json_path(reply, cfg["answer"])
        if not found or not isinstance(found[0], (str, int, float)) or isinstance(found[0], bool):
            out["error"] = f"no text at {cfg['answer']} in the reply"
        else:
            out["answer"] = str(found[0]).strip()
        for key in ("sources", "extracts"):
            if cfg[key]:   # a path that selects a list ($.sources) gives its items, like [*]
                out[key] = texts([x for f in json_path(reply, cfg[key]) for x in (f if isinstance(f, list) else [f])])
        if cfg["links"] and cfg["sources"]:
            out["links"] = paired_links(reply, cfg["sources"], cfg["links"], out["sources"])
        for key in USAGE:   # a number of 0 or more, or None when the reply doesn't say (json.load accepts NaN and Infinity)
            got = json_path(reply, cfg[key]) if cfg[key] else []
            out[key] = got[0] if got and usage_number(got[0]) else None
    except urllib.error.HTTPError as e:   # first: an HTTPError is also a URLError
        out["error"] = f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        # a connection that could not be made (not a slow or bad reply): the harness waits and tries again
        out["unreachable"] = isinstance(e, urllib.error.URLError) and not isinstance(e.reason, TimeoutError)
    out["total_s"] = round(time.monotonic() - start, 2)
    return out
