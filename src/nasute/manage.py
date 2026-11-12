"""Looking after Nasute's files: `init`, `dataset check|import|list`, `runs ...` and `serve`.

How it runs: imported by nasute, which hands it the settings; each function is one command and returns the exit code
(None or 0 is success). Reads: the settings, datasets, runs, starter/. Writes: only what the command is for: a starter
folder, the next dataset version, runs/index.json, or (delete) a run folder.
"""
import csv
import functools
import ipaddress
import http.server
import json
import os
import shutil
import urllib.parse
from pathlib import Path

import nasute as N

HERE = Path(__file__).resolve().parent
DIFFICULTIES = ("easy", "medium", "hard")


def say(text=""):
    print(text)   # command output for a person at a terminal, not logging


# ---- init ---------------------------------------------------------------------------------------

# `init --demo`: the starter settings pointed at `nasute demo-server`, so the demo is three commands with no editing.
DEMO = {'url = "http://127.0.0.1:8000/ask"': 'url = "http://127.0.0.1:8700/ask"', '# sources = "$.sources[*].title"': 'sources = "$.sources[*].title"  ',
        '# extracts = "$.sources[*].text"': 'extracts = "$.sources[*].text"  ', 'url = "http://127.0.0.1:8080/v1"': 'url = "http://127.0.0.1:8700/v1"'}


def init(folder, demo=False):
    """Copy starter/ into `folder`: nasute.toml and datasets/example/v1.jsonl. Never overwrites. demo: settings for `nasute demo-server`."""
    folder = Path(folder)
    files = {folder / "nasute.toml": HERE / "starter" / "nasute.toml", folder / "datasets" / "example" / "v1.jsonl": HERE / "starter" / "example.jsonl"}
    taken = [str(t) for t in files if t.exists()]
    if taken:
        say("Nothing written: these files already exist: " + ", ".join(taken))
        return 1
    for target, source in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        say(f"wrote {target}")
    if demo:
        text = (folder / "nasute.toml").read_text()
        for a, b in DEMO.items():
            assert a in text, f"starter nasute.toml no longer has {a!r}"   # the starter changed: change DEMO with it
            text = text.replace(a, b, 1)
        (folder / "nasute.toml").write_text(text)
        say(f"\nSettings point at the demo server. Start it in another terminal (nasute demo-server), then from {folder}:\n  nasute run --profile smoke")
        return
    say(f"\nNext: edit the [targets.mine] table in {folder / 'nasute.toml'}, then from that folder:\n"
        "  nasute dataset check example\n  nasute run --profile smoke\n"
        "  nasute report      (then open report/index.html)")


# ---- datasets -----------------------------------------------------------------------------------

def problems(path):
    """Everything wrong with a dataset file: [(line number, what)]. A good file gives []."""
    out, seen, first, questions, target = [], {}, True, 0, None
    for n, text in enumerate(Path(path).read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            item = json.loads(text)
        except ValueError as e:
            out.append((n, f"not valid JSON ({e})"))
            first = False
            continue
        if first:   # the first line of text is the header
            first = False
            target = item.get("target") if isinstance(item, dict) and isinstance(item.get("target"), str) else None
            if not isinstance(item, dict) or "question" in item:
                out.append((n, "the first line must be the header ({\"dataset\": ..., \"target\": ...}), not a question"))
            else:
                out += [(n, f"header: {k!r} must be non-empty text") for k in ("dataset", "target") if not isinstance(item.get(k), str) or not item[k]]
                out += [(n, f"header: {k!r} {item[k]!r} is not a plain name (letters, digits, _ . - only)") for k in ("dataset", "target")
                        if isinstance(item.get(k), str) and item[k] and not (N.NAME.fullmatch(item[k]) and ".." not in item[k])]
            continue
        questions += 1
        out += [(n, m) for m in question_problems(item, target)]
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            if item["id"] in seen:
                out.append((n, f"repeated id {item['id']!r} (first on line {seen[item['id']]})"))
            seen.setdefault(item["id"], n)
    if not first and not questions:
        out.append((1, "no questions after the header"))
    return out or ([(1, "the file is empty")] if first else [])


def question_problems(q, target):
    if not isinstance(q, dict):
        return ["not an object"]
    need = N.REQUIRED.get(target, N.REQUIRED_DEFAULT)
    out = [f"missing field(s): {', '.join(sorted(need - q.keys()))}"] * bool(need - q.keys())
    if target in N.REQUIRED:   # a judge set has its own shape; the rest is checked when it is used
        return out
    text = lambda k: [f"{k!r} must be text"] * (k in q and not isinstance(q[k], str))
    lists = lambda k: [f"{k!r} must be a list of text"] * (k in q and not (isinstance(q[k], list) and all(isinstance(x, str) for x in q[k])))
    out += text("id") + text("question") + text("reference") + lists("sources") + lists("tags")
    out += [f"'id' must not be empty"] * (q.get("id") == "") + [f"'question' must not be empty"] * (q.get("question") == "")
    if "difficulty" in q and q["difficulty"] not in DIFFICULTIES:
        out.append(f"'difficulty' must be one of {', '.join(DIFFICULTIES)}, not {q['difficulty']!r}")
    if "answerable" in q and not isinstance(q["answerable"], bool):
        out.append("'answerable' must be true or false")
    elif q.get("answerable") is False:
        out += ["answerable is false, so 'reference' should be empty"] * bool(q.get("reference")) + ["answerable is false, so 'sources' should be empty"] * bool(q.get("sources"))
    elif q.get("reference") == "":
        out.append("no 'reference' answer: give one, or set answerable to false")
    return out


def dataset_check(cfg, name, version=None):
    path, version = N.find_dataset(cfg, name, version)
    found = problems(path)
    for n, what in found:
        say(f"{path.name} line {n}: {what}")
    say(f"{name} v{N.vtext(version)}: " + (f"{len(found)} problem{'s' * (len(found) != 1)}" if found else f"ok, {len(path.read_text().splitlines()) - 1} questions"))
    return 1 if found else 0


def dataset_targets(cfg):
    """{dataset name: the target its newest version's header names ("?" if unreadable)}. Folders with odd names are skipped."""
    names = sorted({d.name for root in map(N.folder, cfg["datasets"]) if root.exists() for d in root.iterdir() if d.is_dir() and N.NAME.fullmatch(d.name) and ".." not in d.name})
    out = {}
    for name in names:
        found = N.versions_of(cfg, name)
        if found:
            try:
                out[name] = json.loads(found[max(found)].read_text().splitlines()[0]).get("target", "?")
            except (ValueError, IndexError, AttributeError):
                out[name] = "?"
    return out


def only_dataset(cfg, target):
    """The one dataset made for `target` ("judge" for the judge set), when the settings do not name one. Else a clear stop."""
    found = [n for n, t in dataset_targets(cfg).items() if t == target] if target else []
    if len(found) != 1:
        what = "the judge set (judge_set)" if target == "judge" else f"a dataset (--dataset, or dataset in the settings) for target {target!r}" if target else "a dataset (--dataset, or dataset in the settings)"
        raise SystemExit(f"which dataset? Name {what}: " + (f"{len(found)} datasets are made for it" + (f" ({', '.join(found)})" if found else "") if target else "no single target to go by"))
    return found[0]


def dataset_list(cfg):
    for name, target in dataset_targets(cfg).items():
        found = N.versions_of(cfg, name)
        counts = ", ".join(f"v{N.vtext(v)} ({sum(bool(x.strip()) for x in found[v].read_text().splitlines()) - 1} questions)" for v in sorted(found))
        say(f"{name}  target {target}  {counts}")


def bump(old, new):
    """Which part of the version a new set of questions earns, by comparing it with the newest version. -> (part, why).
    major: a question was removed, or one's question, reference or answerable changed. minor: questions were only added. patch: only other fields changed (tags, difficulty, sources)."""
    a, b = {q["id"]: q for q in old}, {q["id"]: q for q in new}
    removed = a.keys() - b.keys()
    changed = [i for i in a.keys() & b.keys() if any(a[i].get(k, d) != b[i].get(k, d) for k, d in (("question", ""), ("reference", ""), ("answerable", True)))]
    added = b.keys() - a.keys()
    if removed or changed:
        return "major", ", ".join(x for x in (f"{len(removed)} questions removed" if removed else "", f"{len(changed)} questions changed" if changed else "") if x)
    if added:
        return "minor", f"{len(added)} questions added"
    norm = lambda q: {**q, "answerable": q.get("answerable", True), "tags": q.get("tags", []), "sources": q.get("sources", [])}   # an explicit default is not a change
    if {i: norm(q) for i, q in a.items()} != {i: norm(q) for i, q in b.items()}:
        return "patch", "only tags, difficulty or sources changed"
    raise SystemExit("nothing changed since the newest version; no new version written")


def bump_version(v, part):
    major, minor, patch = v or (0, 0, 0)
    return {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[part]


def dataset_import(cfg, file, name, target=None):
    """A CSV (columns id, question, reference; optional sources, tags, difficulty, answerable; lists split on ;) becomes the next version."""
    N.check_name(name, "dataset name")
    if target:
        N.check_name(target, "target name")
    with open(file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"id", "question", "reference"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{file}: missing column(s): {', '.join(sorted(missing))}")
        rows = list(reader)
    found = N.versions_of(cfg, name)
    before = json.loads(found[max(found)].read_text().splitlines()[0]) if found else {}
    target = target or before.get("target") or (next(iter(cfg["targets"])) if len(cfg["targets"]) == 1 else None)
    if not target:
        raise SystemExit("which target is this dataset for? Give --target NAME")
    items = []
    for row in rows:
        row = {k: (v or "").strip() for k, v in row.items() if k}
        q = {"id": row["id"], "question": row["question"], "reference": row["reference"],
             "sources": [x.strip() for x in row.get("sources", "").split(";") if x.strip()], "tags": [x.strip() for x in row.get("tags", "").split(";") if x.strip()]}
        if row.get("difficulty"):
            q["difficulty"] = row["difficulty"].lower()
        if row.get("answerable", "").lower() in ("false", "no", "0"):
            q["answerable"] = False
        items.append(q)
    root = found[max(found)].parent if found else N.folder(cfg["datasets"][0]) / name
    root.mkdir(parents=True, exist_ok=True)
    header = {"dataset": name, "target": target, "about": before.get("about") or f"Imported from {Path(file).name}."}
    newest = max(found, default=None)
    part, why = bump(N.load_dataset(found[newest], newest)[1], items) if newest else ("major", "first version")
    v = bump_version(newest, part)
    # checked as a temporary file first: a version that fails the check is never written, so fixing the CSV and importing again just works
    tmp = root / f".import-{os.getpid()}.tmp"
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in [header] + items), encoding="utf-8")
    try:
        bad = problems(tmp)
        if bad:
            for n, what in bad:
                say(f"line {n}: {what}")
            say(f"{len(bad)} problem(s). Nothing was written: fix the CSV and import again.")
            return 1
        while True:   # a hard link fails if the name is taken, so two imports at once never overwrite each other's version
            out = root / f"v{N.vtext(v)}.jsonl"
            try:
                os.link(tmp, out)
                break
            except FileExistsError:
                v = bump_version(v, part)
    finally:
        tmp.unlink(missing_ok=True)
    say(f"{part}: {why}")
    say(f"wrote {out} ({len(items)} questions)")
    return 0


# ---- runs ---------------------------------------------------------------------------------------

def when(run_id):
    return f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}"


def resolve(cfg, text):
    """A run id, or the start of one if only one run starts that way."""
    sums = N.summaries(cfg)
    hits = [i for i in sums if i == text] or [i for i in sums if i.startswith(text)]
    if len(hits) != 1:
        raise SystemExit(f"{'no run' if not hits else 'several runs'} match {text!r}; `runs` lists them")
    return hits[0], sums


def correctness(s):
    c = s["metrics"].get("correctness", {})
    return "correctness –" if c.get("mean") is None else f"correctness {c['mean']:.2f}" + (f" ({max(0, c['ci'][0]):.2f}–{min(1, c['ci'][1]):.2f})" if c.get("ci") else "")


def runs_list(cfg, suite=None):
    sums, meta = N.summaries(cfg), N.run_meta(cfg)
    by = {}
    for i, s in sums.items():
        by.setdefault(N.suite_of(s), []).append(i)
    for key in sorted(by):
        if suite and suite != key:
            continue
        s0 = sums[by[key][0]]
        say(f"{s0['dataset']['name']} × {s0.get('target', '?')}   (suite {key})")
        for i in reversed(by[key]):
            s = sums[i]
            marks = [m for m, on in (("BASELINE", meta["baselines"].get(key) == i), ("STOPPED EARLY", s.get("aborted")), ("INCOMPLETE", s.get("incomplete"))) if on]
            say(f"  {i}  {s.get('profile') or 'no profile'}, {s.get('judge_mode', '?')} judge  {s.get('counts_line', '')}  {correctness(s)}"
                + "".join(f"  [{m}]" for m in marks) + (f"  \"{meta['labels'][i]}\"" if i in meta["labels"] else ""))
    if not sums:
        say("No runs yet.")


def runs_show(cfg, text):
    run_id, sums = resolve(cfg, text)
    s, rows = N.read_run(cfg, run_id)
    meta = N.run_meta(cfg)
    say(f"{run_id}  ({when(run_id)} UTC)  suite {s['dataset']['name']} × {s.get('target', '?')}"
        + (f"  \"{meta['labels'][run_id]}\"" if run_id in meta["labels"] else "") + ("  [BASELINE]" if meta["baselines"].get(N.suite_of(s)) == run_id else ""))
    say(f"{s.get('profile') or 'no profile'}, {s['judge_mode']} judge ({s.get('judge_model')}), {s['repeats']} repeat(s), questions {s['dataset']['name']} v{N.vtext(s['dataset']['version'])}")
    say(s["counts_line"] + (f"\nSTOPPED EARLY: {s['aborted']}" if s.get("aborted") else "") + ("\nINCOMPLETE: too many judge errors" if s.get("incomplete") else ""))
    say("\n".join(N.describe(s)))
    if any(s["causes"]["counts"].values()):
        say("\nWhy answers failed: " + ", ".join(f"{k} {v}" for k, v in s["causes"]["counts"].items() if v))
    worst = sorted(N.question_means(rows, "correctness").items(), key=lambda x: x[1])
    worst = [(i, v) for i, v in worst if v < s["pass_at"]][:5]
    if worst:
        say("\nWorst questions:")
        for i, v in worst:
            why = next((r["error"] or r["reasons"].get("correctness", "") for r in rows if r["id"] == i), "")
            say(f"  {i}  correctness {v:.2f}  {N.clip(why, 160)}")


def runs_export(cfg, text, suite, file):
    """`runs export RUN` or `runs export --suite SUITE`: the same CSV the report writes, to FILE or to the screen."""
    if bool(text) == bool(suite):
        raise SystemExit("give a run (or the start of its id), or --suite SUITE, not both")
    if suite:
        pairs = [N.read_run(cfg, i) for i, s in N.summaries(cfg).items() if N.suite_of(s) == suite]
        if not pairs:
            raise SystemExit(f"no runs for suite {suite!r}; `runs` lists them")
        write = lambda out: N.suite_csv(pairs, out)
    else:
        run_id, _ = resolve(cfg, text)
        s, rows = N.read_run(cfg, run_id)
        write = lambda out: N.run_csv(s, rows, out)
    if file:
        with open(file, "w", newline="", encoding="utf-8") as out:
            write(out)
        say(f"written to {file}")
    else:
        import sys
        write(sys.stdout)


def runs_label(cfg, text, label):
    run_id, _ = resolve(cfg, text)
    N.set_label(cfg, run_id, label)
    say(f"{run_id}: " + (f"labelled \"{label}\"" if label else "label removed"))


def runs_baseline(cfg, text):
    run_id, sums = resolve(cfg, text)
    if sums[run_id].get("aborted"):
        raise SystemExit(f"{run_id} was stopped early; a baseline needs a whole run")
    meta = N.run_meta(cfg)
    meta["baselines"][N.suite_of(sums[run_id])] = run_id
    N.save_meta(cfg, meta)
    say(f"{run_id} is now the baseline of {N.suite_of(sums[run_id])}. Compare and the report measure against it.")


def runs_delete(cfg, text, yes=False):
    run_id, sums = resolve(cfg, text)
    meta = N.run_meta(cfg)
    suite = N.suite_of(sums[run_id])
    if meta["baselines"].get(suite) == run_id and not yes:
        raise SystemExit(f"{run_id} is the baseline of {suite}. Delete it anyway with --yes.")
    if not yes and input(f"Delete run {run_id} ({sums[run_id].get('counts_line', '')})? [y/N] ").strip().lower() != "y":
        say("Kept.")
        return 1
    shutil.rmtree(N.folder(cfg["runs"]) / run_id)
    meta["labels"].pop(run_id, None)
    if meta["baselines"].get(suite) == run_id:
        del meta["baselines"][suite]
    N.save_meta(cfg, meta)
    say(f"deleted {run_id}")


# ---- serve --------------------------------------------------------------------------------------

def loopback(name):
    """localhost, or an address on this machine only (127.x.x.x, ::1, and 127.x.x.x written as IPv6)."""
    if name == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(name.strip("[]"))
    except ValueError:
        return False
    return ip.is_loopback or bool(getattr(ip, "ipv4_mapped", None) and ip.ipv4_mapped.is_loopback)



class ReportHandler(http.server.SimpleHTTPRequestHandler):
    """Static files from the report folder. Bound to this machine only, it also refuses requests addressed to any other name:
    a web page whose own name points at 127.0.0.1 (DNS rebinding) would otherwise read the report from the browser."""
    def send_head(self):
        if loopback(self.server.server_address[0]):
            name = urllib.parse.urlsplit("//" + (self.headers.get("Host") or "")).hostname or ""
            if not loopback(name):
                self.send_error(421, "this report is served to localhost only")
                return None
        return super().send_head()

    def log_message(self, *args):
        pass


def make_server(cfg, host, port):
    """The report folder over http, for the one case file:// cannot do. Nothing else is exposed."""
    out = N.folder(cfg["report"])
    out.mkdir(parents=True, exist_ok=True)
    return http.server.ThreadingHTTPServer((host, port), functools.partial(ReportHandler, directory=str(out)))


def serve(cfg, host, port):
    server = make_server(cfg, host, port)
    say(f"Report at http://{host}:{server.server_address[1]}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
