"""Nasute: tests AI systems that answer questions. Asks a system under test a list of questions with known answers, scores what comes back,
and keeps every run so changes can be compared.

How it runs, by hand (no cron, no background service):
  nasute init [folder] [--demo]  a starter nasute.toml and an example dataset (--demo: set up for demo-server)
  nasute run [--profile smoke|deep] [--dataset NAME --target NAME --version 1.2 --limit 3 --repeats 2]
  nasute judge-check [--mode quick|claims]   does the judge mark known answers the way we expect?
  nasute compare [RUN_A RUN_B]   default: the newest run against its baseline, else the run before it (same suite)
  nasute report                  write the static report folder (run does this too)
  nasute serve [--port 8765]     show the report folder on this machine
  nasute demo-server             a stand-in system and judge, for the quick start
  nasute dataset check|import|list   look after question files
  nasute runs [show|label|baseline|delete]   look after saved runs
  nasute prompts export FOLDER   write the built-in judge prompts as text files, to edit and name in [judge.prompts]
  python3 tests/nasute_test.py              the checks, from a checkout; no network, no model

Reads: nasute.toml (--config, else ./nasute.toml, else the one beside this file), a dataset file
datasets/<name>/v<N>.jsonl, the system under test (targets/), and a judge model (any OpenAI-compatible address).
Writes: runs/<UTC time>/results.jsonl and summary.json, runs/index.json (labels, baselines),
runs/judge-<UTC time>/ for judge checks, and the report folder (pages.py).
A suite is one dataset asked of one target; runs, baselines and charts are grouped by suite.
Settings (all have defaults here; see nasute.example.toml): datasets, runs, report, dataset, judge_set, k, timeout,
limit, repeats, pass_at, detect, worse_by, profiles, [judge] url/model/timeout/mode/headers, [judge.prompts] (a text file
per judge prompt to use instead of the built-in one) and [targets.<name>] (kind plus that kind's settings).

The judge never gives a score. It only says yes or no about single claims; this file counts them.
Statistics follow Evan Miller, "Adding Error Bars to Evals" (arXiv 2411.00640). Standard library only.
"""
import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import itertools
import os
import json
import logging
import math
import re
import socket
import statistics
import string
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist, fmean

HERE = Path(__file__).resolve().parent
from .targets import http  # noqa: E402
from . import manage, pages  # noqa: E402

TARGETS = {"http": http.ask}   # kind -> ask(question, target_settings, timeout); see docs/how-to/add-a-target.md


def target_ask(kind):
    """A built-in kind, or "module:function": your own ask() imported by name, so a new target needs no edit here."""
    if kind not in TARGETS and ":" in kind:
        module, _, name = kind.partition(":")
        TARGETS[kind] = getattr(importlib.import_module(module), name)
    assert kind in TARGETS, f"no target kind {kind!r}: use one of {sorted(k for k in TARGETS if ':' not in k)} or \"module:function\""
    return TARGETS[kind]
DEFAULTS = {
    "datasets": ["datasets"],      # folders; relative ones start from the settings file's folder
    "runs": "data/runs",
    "report": "data/report",
    "report_url": "",              # where the report folder is served, for the link printed after a run; "" = a file:// link
    "dataset": "",                 # the dataset `run` uses when --dataset is not given
    "judge_set": "",               # the dataset `judge-check` uses: answers with known faults
    "k": 5,                        # how many retrieved sources count
    "timeout": 180,                # seconds per question
    "limit": 0,                    # 0 = every question
    "repeats": 1,                  # times each question is asked
    "pass_at": 0.75,               # correctness at or above this counts as a pass
    "detect": 0.05,                # the score difference the power line asks about
    "worse_by": 0.2,               # a score this much lower counts as "got worse"
    "min_attempts": 5,             # attempts a question needs before its difficulty label is questioned
    "mislabel_easy_below": 0.5,    # "easy" but passed less often than this: flagged
    "mislabel_hard_above": 0.9,    # "hard" but passed more often than this: flagged
    "judge_check": False,          # run judge-check first (for profiles)
    "temperature": 0.0,            # sent to the judge, and to the target if it can use it
    "pause": 0,                    # seconds to wait after every call, to spare shared hardware
    "max_temp": 0,                 # also wait while the CPU is hotter than this (°C); 0 = off
    "workers": 1,                  # questions run at once; more only for endpoints that take parallel requests
    "max_judge_errors": 0.1,       # more judge failures than this share of answers: the run is marked incomplete
    "judge": {"url": "http://127.0.0.1:8080/v1", "model": "", "timeout": 240, "mode": "quick", "cache": False, "retries": 2, "headers": {},
              "prompts": {}},              # prompt name -> a text file used instead of that built-in judge prompt; see load_prompts()
    "targets": {},                 # name -> {kind, model_url, ...that kind's settings}
    "profiles": {},                # name -> any of the settings above, merged over them by --profile
}
RETRIEVAL = ["hit", "recall", "mrr"]
GENERATION = ["faithfulness", "correctness", "relevancy", "context_recall"]
METRICS = RETRIEVAL + GENERATION + ["abstention", "error_rate"]
LOWER_BETTER = {"error_rate"}        # a rise is a drop in quality
BACKOFF = (5, 15, 45)                # seconds to wait between tries when something cannot be reached
RETRY_WAIT = 3                       # seconds before retrying a judge reply that failed
Z = NormalDist().inv_cdf(0.975)      # 95% interval
Z_POWER = NormalDist().inv_cdf(0.80)  # 80% power
MIN_PAIRS = 5                         # fewer shared questions than this: no verdict

# One place for the words. `term` is the standard technical name (the primary label everywhere), `plain` is a one-line lay definition
# (lower case, so it reads after the term), `formula` is the working in words. "@k" in a term is filled with the run's k (see label()).
# Embedded in every report page; the CLI and the README use the same text. Nothing else in the code names a score or defines it.
GLOSSARY = {
    "hit": {"term": "Hit rate@k", "plain": "a right source was among the top k found",
            "formula": "1 if any expected source is in the top k, else 0. Averaged over questions."},
    "recall": {"term": "Recall@k", "plain": "share of the right sources found in the top k",
               "formula": "expected sources in the top k / expected sources."},
    "mrr": {"term": "MRR (mean reciprocal rank)", "plain": "how near the top the first right source came",
            "formula": "1 / position of the first expected source (1, 0.5, 0.33, ...), 0 if none."},
    "faithfulness": {"term": "Faithfulness", "plain": "share of the answer's claims backed by the text it read",
                     "formula": "claims in the answer backed by the extracts / claims in the answer."},
    "correctness": {"term": "Answer correctness", "plain": "how well the answer matches the reference answer",
                    "formula": "Claims mode: F1 = 2 × P × R / (P + R); precision P = answer claims matching the reference / answer claims; "
                               "recall R = reference facts the answer covers / reference facts. Quick mode: answer claims that agree with the reference / answer claims."},
    "relevancy": {"term": "Answer relevancy", "plain": "does the answer address the question",
                  "formula": "The judge says yes, partly or no. Counted as 1, 0.5, 0."},
    "context_recall": {"term": "Context recall", "plain": "share of the reference's facts present in the text it read",
                       "formula": "reference facts backed by the extracts / facts in the reference. Claims mode only."},
    "abstention": {"term": "Abstention accuracy", "plain": "says it doesn't know when there's no answer",
                   "formula": "For questions the library cannot answer: 1 if the judge says the answer declines, 0 if it makes something up."},
    "precision": {"term": "Precision", "plain": "of what the answer says, how much matches the reference",
                  "formula": "answer claims matching the reference / all answer claims."},
    "f1": {"term": "F1 score", "plain": "the balance of precision and recall", "formula": "2 × P × R / (P + R)."},
    "se": {"term": "Standard error", "plain": "how much the average would wobble if you drew other questions; smaller is surer",
           "formula": "√(variance / n), plus a term for repeats of one question, which are not independent (Miller, eq. 4)."},
    "ci": {"term": "95% CI (confidence interval)", "plain": "the range the true score is probably in", "formula": "mean ± 1.96 × standard error, kept between 0 and 1. Wilson interval for yes/no scores."},
    "error_rate": {"term": "Error rate", "plain": "share of attempts where the system failed",
                   "formula": "attempts with a system error (timeout, crash, error, empty answer) / attempts. Lower is better; a rise shows as a real drop."},
    "strict": {"term": "Strict vs answered-only scores", "plain": "the headline scores count a system error as 0; answered-only leaves those attempts out",
               "formula": "strict: system-error attempts count 0 for every score that needs an answer, so a system that times out on hard questions is not flattered. answered only: those attempts are left out."},
    "incomplete": {"term": "Incomplete run", "plain": "too many judge failures for the scores to be trusted",
                   "formula": "judge errors / answers judged is more than max_judge_errors (default 0.1). The judge's failures are never held against the system, but the run has gaps."},
    "aborted": {"term": "Aborted run", "plain": "stopped early because the system or the judge could not be reached",
                "formula": "unreachable for 3 questions in a row. Partial results are kept; nothing is compared."},
    "paired": {"term": "Paired difference (verdict)", "plain": "did a change really move a score, or is it noise",
               "formula": "Per-question differences between two runs: mean ± 1.96 × their standard error. Interval clear of 0: real gain or real drop. Else within noise."},
    "accuracy": {"term": "Accuracy", "plain": "share of the judge's marks that landed in the expected range",
                 "formula": "marks inside the band the judge set expects / marks checked."},
    "kappa": {"term": "Cohen's kappa", "plain": "agreement beyond chance: 1 is perfect, 0 is no better than guessing",
              "formula": "(agreement − agreement expected by chance) / (1 − agreement expected by chance), comparing each mark's 0 / 0.5 / 1 bucket with the bucket the set expects."},
    "pass_all": {"term": "Pass^k", "plain": "share of questions answered well on every repeat",
                 "formula": "questions whose correctness was at or above pass_at on all k repeats / questions."},
}


def label(m, k=None):
    """A score's technical name, with its k filled in where the run's k is known ("Recall@5")."""
    return GLOSSARY[m]["term"].replace("@k", f"@{k}" if k else "@k")


# Logging. Two looks for the same events: JSON lines (one object per line, for a server that reads job logs) and short
# readable lines for a person at a terminal. `--log json|text` picks one; with neither, NASUTE_LOG decides, else text at a
# terminal and JSON when the output goes to a file or a pipe. Both go to stdout. Events carry ids, counts and scores only.
class JsonLines(logging.Formatter):
    def format(self, r):
        return json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": r.levelname.lower(),
                           "app": "nasute", "event": r.getMessage(), **getattr(r, "details", {})})


class Readable(logging.Formatter):
    """One short line per event, such as `[3/24] gold-79 ... right (2.1 s)`. Warnings and errors start with a word in capitals,
    in colour at a terminal (unless NO_COLOR is set)."""
    SAY = {
        "question_done": lambda d: f"[{d['n']}/{d['of']}] {d['id']}{Readable.again(d)} ... {Readable.result(d)}" + (f" ({d['total_s']} s)" if d.get("total_s") is not None else ""),
        "run_start": lambda d: f"Run {d['run']}: {d['dataset']} v{d['version']} asked of {d['target']}, {d['questions']} questions"
                               + (f" × {d['repeats']} repeats" if d["repeats"] > 1 else "") + f", {d['judge_mode']} judge" + (f", {d['profile']} profile" if d.get("profile") else ""),
        "judge_item_done": lambda d: f"judged {d['id']}" + (f": judge error: {d['judge_error']}" if d.get("judge_error") else ""),
        "report_written": lambda d: f"Report written: {d['folder']}",
    }

    again = staticmethod(lambda d: f" (repeat {d['repeat']})" if d.get("repeats", 1) > 1 else "")
    result = staticmethod(lambda d: f"system error: {d['error']}" if d.get("error") else f"not judged: {d['judge_error']}" if d.get("judge_error") else d.get("outcome") or "done")

    def __init__(self, colour):
        super().__init__()
        self.colour = colour

    def format(self, r):
        d, event = getattr(r, "details", {}), r.getMessage()
        try:
            text = self.SAY[event](d) if event in self.SAY else event.replace("_", " ") + (": " + ", ".join(f"{k} {v}" for k, v in d.items()) if d else "")
        except (KeyError, TypeError):   # an event without the usual details still prints, plainly
            text = f"{event}: {d}"
        if r.levelno >= logging.WARNING:
            word = "ERROR" if r.levelno >= logging.ERROR else "WARNING"
            text = (f"\033[{31 if word == 'ERROR' else 33};1m{word}\033[0m " if self.colour else word + " ") + text
        return text


def setup_logging(style=None):
    """style: "json", "text" or None (NASUTE_LOG, else text at a terminal and JSON otherwise). -> the style used."""
    root = logging.getLogger()
    if not getattr(root, "nasute", None):   # one handler, made once, on the stdout of the time; later calls only change its look
        root.handlers[:] = [logging.StreamHandler(sys.stdout)]
        root.setLevel(logging.INFO)
        root.nasute = True
    out = root.handlers[0].stream
    tty = hasattr(out, "isatty") and out.isatty()
    style = style or os.environ.get("NASUTE_LOG") or ("text" if tty else "json")
    root.handlers[0].setFormatter(JsonLines() if style == "json" else Readable(tty and not os.environ.get("NO_COLOR")))
    return style


setup_logging("json")   # until main() picks: a library caller (and the tests) get the JSON lines


def log(event, level=logging.INFO, **details):
    """Ids, counts and scores only: never question or answer text."""
    logging.log(level, event, extra={"details": details})


def merge(base, over):
    return {k: merge(base[k], over[k]) if isinstance(base.get(k), dict) and isinstance(over.get(k), dict) else over.get(k, base.get(k))
            for k in {**base, **over}}


def load_settings(path=None, profile=None):
    """Defaults, then the file, then the named profile (a table of the same settings). Relative folders start from the file's folder."""
    path = Path(path or "nasute.toml")
    raw = tomllib.loads(path.read_text()) if path.exists() else {}
    cfg = merge(DEFAULTS, raw)
    if profile:
        assert profile in cfg["profiles"], f"no profile {profile!r} in settings (have {sorted(cfg['profiles'])})"
        cfg = merge(cfg, cfg["profiles"][profile])
    for t in cfg["targets"]:   # after the profile, which may add targets
        check_name(t, "target name")
    base = path.resolve().parent
    if str(base) not in sys.path:
        sys.path.append(str(base))   # a "module:function" target can sit next to the settings file
    cfg["judge"] = {**cfg["judge"], "prompts": {n: str(base / f) for n, f in cfg["judge"]["prompts"].items()}}
    return {**cfg, "prompt_texts": load_prompts(cfg["judge"]["prompts"]), "profile": profile or "", "datasets": [str(base / d) for d in cfg["datasets"]], "runs": str(base / cfg["runs"]), "report": str(base / cfg["report"])}


NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
SEP = "@"   # joins dataset and target in a suite id; NAME forbids it, so two different pairs never give the same id


def check_name(name, what):
    """A dataset, target or suite part becomes a folder or file name, so it must be plain: letters, digits, _ . - (not first), no "..". -> name"""
    if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name:
        raise SystemExit(f"{what} {name!r} is not allowed: use letters, digits, _ . - only, starting with a letter or digit")
    return name


def folder(p):
    p = Path(p)
    return p if p.is_absolute() else HERE / p


# ---- datasets -------------------------------------------------------------------------------

def vtext(v):
    """A version for people, "1.2.0". A tuple from a file name; an old run stored just the number 2, which reads as 2.0.0."""
    return ".".join(map(str, v)) if isinstance(v, tuple) else f"{v}.0.0" if isinstance(v, int) else str(v)


def versions_of(cfg, name):
    """{(major, minor, patch): file} for a dataset, from the first folder in `datasets` that holds it. v2.jsonl (the old name) is 2.0.0.
    Tuples, so 1.10.0 sorts after 1.9.0."""
    check_name(name, "dataset name")
    for root in map(folder, cfg["datasets"]):
        found = {(int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)): f for f in (root / name).glob("v*.jsonl") if (m := re.fullmatch(r"v(\d+)(?:\.(\d+)\.(\d+))?\.jsonl", f.name))}
        if found:
            return found
    return {}


def find_dataset(cfg, name, version=None):
    """The file for a dataset's version: the newest if none given, and "2" or "2.1" mean the newest version starting that way. -> (path, (major, minor, patch))"""
    found = versions_of(cfg, name)
    if version is not None and version != "" and not re.fullmatch(r"\d+(\.\d+){0,2}", str(version)):
        raise SystemExit(f"version {version!r}: write it as 2, 2.1 or 2.1.0")
    want = tuple(int(x) for x in str(version).split(".")) if version else ()
    hits = [v for v in found if v[:len(want)] == want]
    if hits:
        return found[max(hits)], max(hits)
    raise SystemExit(f"no dataset {name!r} version {version or 'newest'} in {cfg['datasets']}")


REQUIRED = {"judge": {"id", "kind", "question", "reference", "extracts", "answer", "expect"}}   # other targets: the default below
REQUIRED_DEFAULT = {"id", "question", "reference"}   # sources and tags are optional: without sources the retrieval scores are simply not measured


def load_dataset(path, version):
    """-> (header, questions, fingerprint). The first line names the dataset and its target; the file's
    SHA-256 means a changed file can never pass for the same version. A question may have
    "answerable": false (the library holds no answer; reference ""), and "difficulty" (easy, medium, hard).
    `nasute dataset check` reports every problem with its line number; this stops at the first."""
    raw = Path(path).read_bytes()
    lines = [json.loads(x) for x in raw.decode().splitlines() if x.strip()]
    header, questions = lines[0], lines[1:]
    assert "target" in header and "question" not in header, f"{path}: first line must be the header"
    check_name(header["target"], f"{path}: header target")
    check_name(header["dataset"], f"{path}: header dataset")
    for q in questions:
        assert REQUIRED.get(header["target"], REQUIRED_DEFAULT) <= q.keys(), f"{path}: bad question {q.get('id')}"
        q.setdefault("sources", [])
        q.setdefault("tags", [])
    assert len({q["id"] for q in questions}) == len(questions), f"{path}: repeated id"
    return header, questions, {"name": header["dataset"], "version": vtext(version), "sha256": hashlib.sha256(raw).hexdigest()}


def difficulty_of(q):
    """The question's own label, else easy/medium/hard found in its tags (v1 files), else "unknown"."""
    return q.get("difficulty") or next((t for t in q.get("tags", []) if t in ("easy", "medium", "hard")), "unknown")


# ---- retrieval scores and statistics ----------------------------------------------------------

def retrieval_scores(expected, retrieved, k):
    """Titles compared ignoring case. hit: any expected source in the top k. recall: share of the
    expected sources in the top k. mrr: 1 / rank of the first expected source (0 if none)."""
    want = {t.lower().strip() for t in expected}
    got = [t.lower().strip() for t in retrieved]
    if not want:
        return {m: None for m in RETRIEVAL}
    top = set(got[:k])
    rank = next((i + 1 for i, t in enumerate(got) if t in want), None)
    return {"hit": float(bool(want & top)), "recall": len(want & top) / len(want), "mrr": 1 / rank if rank else 0.0}


def retrieval_reasons(expected, retrieved, k, scores):
    if scores["hit"] is None:
        return {}
    ordinal = lambda n: {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")
    first = next((i + 1 for i, t in enumerate(map(str.lower, retrieved)) if t in {e.lower() for e in expected}), None)
    return {"hit": f"Hit {scores['hit']:.0f}: " + (f"an expected source was in the top {k}." if scores["hit"] else f"no expected source was in the top {k}."),
            "recall": f"Recall@{k} {scores['recall']:.2f} = expected sources in the top {k} / expected sources = {round(scores['recall'] * len(expected))} / {len(expected)}.",
            "mrr": f"MRR {scores['mrr']:.2f}: " + (f"the first expected source came {ordinal(first)} (1 / {first})." if first else "no expected source was found.")}


def mean_std(values):
    v = [x for x in values if x is not None]
    return {"mean": round(statistics.fmean(v), 4) if v else None, "std": round(statistics.pstdev(v), 4) if v else None, "n": len(v)}


def wilson(p, n):
    """95% Wilson interval for a share p out of n yes/no trials."""
    d = 1 + Z * Z / n
    mid = (p + Z * Z / (2 * n)) / d
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [mid - half, mid + half]


def stats(groups, binary=False):
    """groups: one list of scores per question (its repeats). Miller 2024, eq. 1 and 4:
    SE² = var/n + (1/n²) Σ over questions of Σ_i Σ_j≠i (s_i − mean)(s_j − mean). With one score per
    question the second term is 0. -> mean, std, se (clustered), ci, n (questions), attempts."""
    groups = [[x for x in g if x is not None] for g in groups]
    groups = [g for g in groups if g]
    vals = [x for g in groups for x in g]
    n = len(vals)
    out = {"mean": None, "std": None, "se": None, "ci": None, "n": len(groups), "attempts": n}
    if not n:
        return out
    mean = fmean(vals)
    out["mean"] = mean
    # shortcut: with no spread (every score equal) or a single attempt, the normal interval has zero width or does not exist, so a
    # Wilson interval on the mean with n = questions (not attempts) stands in. Conservative for a 0-1 score; change it if scores outside 0-1 are added.
    var = sum((x - mean) ** 2 for x in vals) / (n - 1) if n > 1 else 0.0
    if var > 1e-12:   # not 0: averaging 0.1s leaves rounding dust that would pass for spread
        cross = sum(sum(x - mean for x in g) ** 2 - sum((x - mean) ** 2 for x in g) for g in groups)
        naive = var / n
        se = math.sqrt(max(0.0, naive + cross / n ** 2))
        out.update(std=math.sqrt(var), se=se, ci=[max(0.0, mean - Z * se), min(1.0, mean + Z * se)])   # every score is 0 to 1; with few questions the normal range spills past
        if binary:
            out["ci"] = wilson(mean, n / max(1.0, se * se / naive))   # repeats make fewer independent trials
    else:
        if n > 1:
            out.update(std=0.0, se=0.0)
        out["ci"] = wilson(mean, len(groups))
    return {k: (round(v, 4) if isinstance(v, float) else [round(x, 4) for x in v] if isinstance(v, list) else v) for k, v in out.items()}


def groups_of(rows, m):
    """[[score, ...] per question] for one metric; repeats of a question stay together."""
    by = {}
    for r in rows:
        by.setdefault(r["id"], []).append(r["scores"][m])
    return list(by.values())


def question_means(rows, m):
    by = {}
    for r in rows:
        if r["scores"].get(m) is not None:   # runs from before a score existed lack it
            by.setdefault(r["id"], []).append(r["scores"][m])
    return {i: fmean(g) for i, g in by.items()}


def needed_questions(variance, detect):
    """Miller 2024, eq. 9: n = (z(α/2) + z(β))² × variance of the paired differences / δ²; 5% false alarms, 80% power."""
    return max(1, math.ceil((Z + Z_POWER) ** 2 * variance / detect ** 2)) if variance > 1e-12 else None   # no spread (or only rounding dust): cannot estimate


def power(groups, cfg):
    """Questions needed to see a difference of cfg["detect"] between two runs of this system.
    With repeats: variance from how one question wobbles between its repeats (2σ²/K, K as observed, assuming the change
    moves every question alike). Without: twice the variance of the scores, the worst case."""
    groups = [[x for x in g if x is not None] for g in groups]
    within = [2 * statistics.variance(g) / len(g) for g in groups if len(g) > 1]   # 2σ²/K with the K each question really has
    vals = [x for g in groups for x in g]
    if within:
        need, basis = needed_questions(fmean(within), cfg["detect"]), "repeats"
    elif len(vals) > 1:
        need, basis = needed_questions(2 * statistics.variance(vals), cfg["detect"]), "worst case"
    else:
        return None
    return {"needed": need, "basis": basis} if need else None   # None: no spread in the scores, so nothing to estimate from


def paired(a, b, detect, lower_better=False):
    """a, b: {question: score}. Differences b − a on shared questions. -> mean, se, ci, verdict, n, needed."""
    d = [b[i] - a[i] for i in a.keys() & b.keys()]
    out = {"a": None, "b": None, "delta": None, "se": None, "ci": None, "n": len(d), "needed": None, "verdict": "too few questions"}
    if not d:
        return out
    ids = a.keys() & b.keys()
    out.update(a=round(fmean(a[i] for i in ids), 4), b=round(fmean(b[i] for i in ids), 4), delta=round(fmean(d), 4))
    if len(d) >= MIN_PAIRS:
        var = statistics.variance(d)
        se, mean = math.sqrt(var / len(d)), fmean(d)
        out.update(se=round(se, 4), ci=[round(mean - Z * se, 4), round(mean + Z * se, 4)], needed=needed_questions(var, detect),
                   verdict="within noise" if mean - Z * se <= 0 <= mean + Z * se else "real gain" if (mean > 0) != lower_better else "real drop")
    return out


def consistency(rows, cfg):
    """Per question, how correctness varies between repeats. pass^k: good (>= pass_at) on every repeat."""
    every = dict(zip(dict.fromkeys(r["id"] for r in rows), groups_of(rows, "correctness")))
    got = {i: g for i, g in every.items() if len(g) > 1 and None not in g}   # a missing repeat cannot be counted as a pass
    left_out = sum(len(g) > 1 and None in g for g in every.values())
    if not got:
        return None
    flaky = sorted(({"id": i, "spread": round(max(g) - min(g), 3), "scores": [round(x, 2) for x in g]} for i, g in got.items() if max(g) - min(g) >= cfg["worse_by"]),
                   key=lambda f: -f["spread"])
    return {"questions": len(got), "pass_all": round(sum(min(g) >= cfg["pass_at"] for g in got.values()) / len(got), 4), "left_out": left_out, "flaky": flaky[:5]}


def why_failed(rows, cfg, cited=True):
    """Why a question with low correctness failed. rows: its repeats; cited: the run's system named any source at all
    (else retrieval was not measured, as in measured(), and a chat model is never blamed for it). -> cause or None.
    system: the target errored. retrieval: right source not found. judge?: the marks disagree with each
    other. generation: the right source was found and the answer is still wrong."""
    if any(r["error"] for r in rows):
        return "system"
    good = lambda m: [r["scores"][m] for r in rows if r["scores"][m] is not None]
    if not good("correctness") or fmean(good("correctness")) >= cfg["pass_at"]:
        return None
    if cited and good("hit") and fmean(good("hit")) < 0.5:
        return "retrieval"
    # faithful to the right source yet fully wrong; or most of the answer matches the reference yet it scores low
    if (good("faithfulness") and fmean(good("faithfulness")) >= cfg["pass_at"] and fmean(good("correctness")) == 0) or \
            any((r["judge_detail"] or {}).get("precision", 0) >= cfg["pass_at"] for r in rows):
        return "judge?"
    return "generation"


def causes(rows, cfg):
    out, cited = [], any(r.get("sources") for r in rows)
    for i in dict.fromkeys(r["id"] for r in rows):
        mine = [r for r in rows if r["id"] == i]
        if c := why_failed(mine, cfg, cited):
            out.append({"id": i, "cause": c, "why": next((r["error"] or r["reasons"].get("correctness", "") for r in mine), "")})
    return {"counts": {c: sum(x["cause"] == c for x in out) for c in ("retrieval", "generation", "judge?", "system")}, "questions": out}


# ---- the judge ----------------------------------------------------------------------------------
# The judge never gives a score. It says yes or no about single claims; the code below counts them.

QUICK_ASK = """You are a strict marker. Do not give scores. List the factual claims the ANSWER itself makes, as short separate statements. Never list a claim that only the EXTRACTS or the REFERENCE make. If the ANSWER states no facts (a refusal, an apology, "I don't know", or off topic with no facts about the question), the list is empty. For each claim say:
supported: "yes" if the EXTRACTS state it or clearly imply it, otherwise "no". True but not in the extracts is "no".
vs_reference: "agrees" if the REFERENCE says the same, "contradicts" if the REFERENCE says something different, "not_in_reference" if the REFERENCE does not cover it.
Then say whether the ANSWER addresses the QUESTION: relevancy "yes", "partly" or "no". This is about the topic, not the truth: an answer that tries to answer what the QUESTION asks is "yes" even if it is wrong. "no" for a refusal or an off-topic answer.
Give a few words of reason for each.

QUESTION: {question}
REFERENCE: {reference}
EXTRACTS:
{extracts}
ANSWER: {answer}"""

SPLIT_ASK = """List the separate facts stated in the ANSWER and in the REFERENCE as short, complete claims: one fact each, naming the subject (no "it" or "this"). Only facts the text itself states. A refusal, an apology or "I don't know" states no facts. If a text states no facts, give an empty list.
Then say whether the ANSWER addresses the QUESTION: relevancy "yes", "partly" or "no". This is about the topic, not the truth: an answer that tries to answer what the QUESTION asks is "yes" even if it is wrong. "no" for a refusal or an off-topic answer. Give a few words of reason.

QUESTION: {question}
REFERENCE: {reference}
ANSWER: {answer}"""

CHECK_ASK = """Below is a SOURCE and a numbered list of CLAIMS. For each claim, in order, say whether the SOURCE states it or clearly implies it: supported "yes" or "no". A claim that is true but not in the SOURCE is "no". Give a few words of reason. Give exactly one verdict per claim.

SOURCE:
{source}

CLAIMS:
{claims}"""

KNOWLEDGE_ASK = """You are checking one answer to a quiz question. Do not give a score.
1. key_fact: Does the ANSWER itself state the REFERENCE's key fact, in any wording? "yes" or "no". Only count what the ANSWER says in plain text. A tool call, code, or a promise to look it up is "no".
2. false_claims: Go through every name, date, number and place in the ANSWER one by one, including items in lists and later sentences, and check each. List any claim that is false or contradicts the REFERENCE. Use your own knowledge for claims the REFERENCE does not cover. List a claim only if you believe it is false: if you think it is true, leave it out. Extra detail that is true is fine and is not listed. If you are not sure a claim is false, do not list it. Empty list if none.
3. answered: Did the ANSWER give an answer at all? "yes", or "no" for a refusal, "I don't know", a bare tool call or empty text.
Give a few words of reason for each.

QUESTION: {question}
REFERENCE (the key fact a right answer must state): {reference}
ANSWER: {answer}"""

KNOWLEDGE_ABSTAIN_ASK = """The QUESTION is about something that does not exist, so a good reply says it does not know. Do not give a score.
1. verdict: Did the ANSWER decline (say it cannot find it, does not know, or has nothing on it) or make something up (state an answer as if it were known)? "declined" or "made_something_up". Hedging while still giving a specific answer about the made-up subject is "made_something_up".
2. false_claims: Go through every other name, date, number and place in the ANSWER one by one and check each. List any that is false. List a claim only if you believe it is false. Empty list if none.
Give a few words of reason for each.

QUESTION: {question}
ANSWER: {answer}"""

ABSTAIN_ASK = """The library holds no answer to this QUESTION, so a good reply says so. Did the ANSWER decline (say it cannot find it, does not know, or has nothing on it) or make something up (state an answer as if it were known)? verdict: "declined" or "made_something_up". Hedging while still giving a specific answer is "made_something_up". Give a few words of reason.

QUESTION: {question}
ANSWER: {answer}"""

PROMPTS = {"quick": QUICK_ASK, "split": SPLIT_ASK, "check": CHECK_ASK, "knowledge": KNOWLEDGE_ASK, "knowledge_abstain": KNOWLEDGE_ABSTAIN_ASK, "abstain": ABSTAIN_ASK}
MODE_PROMPTS = {"quick": ("quick", "abstain"), "claims": ("split", "check", "abstain"), "knowledge": ("knowledge", "knowledge_abstain")}
BRACES = "To write a literal brace, double it: {{ for { and }} for }."


def placeholders(text):
    """The {names} a prompt is filled with. Worked out from the text, so the built-in prompts set the rule. A stray brace raises ValueError."""
    return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}


def load_prompts(paths):
    """{prompt name: file} from [judge.prompts] -> {prompt name: text}. Checked here, at load time, so a bad file stops before
    any question is asked: it must be UTF-8 and use exactly the placeholders of the built-in prompt it replaces."""
    texts = {}
    for name, f in paths.items():
        if name not in PROMPTS:
            raise SystemExit(f"[judge.prompts] has no prompt called {name!r}: use {', '.join(PROMPTS)}")
        try:
            text = Path(f).read_bytes().decode("utf-8").removesuffix("\n")   # the newline an editor adds is not part of the prompt
        except OSError as e:
            raise SystemExit(f"judge prompt {name}: cannot read {f} ({e.strerror})")
        except UnicodeDecodeError:
            raise SystemExit(f"judge prompt {name}: {f} is not UTF-8 text")
        want = placeholders(PROMPTS[name])
        try:
            got = placeholders(text)
        except ValueError as e:
            raise SystemExit(f"judge prompt {name}: {f} has a single brace ({e}). {BRACES}")
        if got != want:
            wrong = [f"is missing {', '.join('{' + x + '}' for x in sorted(want - got))}"] * bool(want - got) + \
                    [f"has unknown {', '.join('{' + x + '}' for x in sorted(got - want))}"] * bool(got - want)
            raise SystemExit(f"judge prompt {name}: {f} {' and '.join(wrong)}. It must use exactly {', '.join('{' + x + '}' for x in sorted(want))}. {BRACES}")
        try:
            text.format(**dict.fromkeys(want, ""))   # what parsing lets through, such as {answer:{x}}
        except (ValueError, KeyError, IndexError, AttributeError) as e:
            raise SystemExit(f"judge prompt {name}: {f} has a brace Nasute cannot fill ({e}). {BRACES}")
        texts[name] = text
    return texts


def prompt(cfg, name):
    """The text of one judge prompt: the settings' file if one was named, else the built-in."""
    return cfg.get("prompt_texts", {}).get(name, PROMPTS[name])


def prompt_record(cfg):
    """Which judge prompts a run or judge-check used: a short SHA-256 of each prompt its mode uses, and which were custom.
    Prompt text is not saved, only this. An unknown mode is judged as claims mode (see judge()), so it records those."""
    names = MODE_PROMPTS.get(cfg["judge"]["mode"], MODE_PROMPTS["claims"])
    return {"sha256": {n: hashlib.sha256(prompt(cfg, n).encode()).hexdigest()[:12] for n in names},
            "custom": [n for n in names if n in cfg.get("prompt_texts", {})]}


def prompts_differ(a, b):
    """Names of the judge prompts two records (from prompt_record) do not share. A run from before 0.2.0 has no record:
    it used the built-in prompts, so it differs only by what the other run had custom."""
    if a and b:
        return sorted(n for n in a["sha256"].keys() & b["sha256"].keys() if a["sha256"][n] != b["sha256"][n])
    return sorted((a or b or {}).get("custom", []))


REL = {"yes": 1.0, "partly": 0.5, "no": 0.0}
S_STR = {"type": "string"}
S_REL = {"type": "string", "enum": list(REL)}
S_YN = {"type": "string", "enum": ["yes", "no"]}
S_LIST = {"type": "array", "items": S_STR}
QUICK_SCHEMA = {"type": "object", "required": ["claims", "relevancy", "relevancy_why"], "properties": {
    "claims": {"type": "array", "items": {"type": "object", "required": ["claim", "supported", "vs_reference", "why"], "properties": {
        "claim": S_STR, "supported": S_YN, "vs_reference": {"type": "string", "enum": ["agrees", "contradicts", "not_in_reference"]}, "why": S_STR}}},
    "relevancy": S_REL, "relevancy_why": S_STR}}
SPLIT_SCHEMA = {"type": "object", "required": ["answer_claims", "reference_claims", "relevancy", "relevancy_why"], "properties": {
    "answer_claims": S_LIST, "reference_claims": S_LIST, "relevancy": S_REL, "relevancy_why": S_STR}}
CHECK_SCHEMA = {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {"type": "array", "items": {
    "type": "object", "required": ["supported", "why"], "properties": {"supported": S_YN, "why": S_STR}}}}}
KNOWLEDGE_SCHEMA = {"type": "object", "required": ["key_fact", "key_fact_why", "false_claims", "answered", "answered_why"], "properties": {
    "key_fact": S_YN, "key_fact_why": S_STR,
    "false_claims": {"type": "array", "items": {"type": "object", "required": ["claim", "why"], "properties": {"claim": S_STR, "why": S_STR}}},
    "answered": S_YN, "answered_why": S_STR}}
KNOWLEDGE_ABSTAIN_SCHEMA = {"type": "object", "required": ["verdict", "why", "false_claims"], "properties": {
    "verdict": {"type": "string", "enum": ["declined", "made_something_up"]}, "why": S_STR,
    "false_claims": {"type": "array", "items": {"type": "object", "required": ["claim", "why"], "properties": {"claim": S_STR, "why": S_STR}}}}}
ABSTAIN_SCHEMA = {"type": "object", "required": ["verdict", "why"], "properties": {
    "verdict": {"type": "string", "enum": ["declined", "made_something_up"]}, "why": S_STR}}


def post(url, body, timeout, headers=None):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def model_name(base, headers=None):
    """The first model a /v1 address lists, or "unknown"."""
    try:
        with urllib.request.urlopen(urllib.request.Request(base.rstrip("/") + "/models", headers=http.resolve_headers(headers or {})), timeout=10) as r:
            d = json.load(r)
        return (d.get("data") or d.get("models") or [{}])[0].get("id") or "unknown"
    except Exception:
        return "unknown"


def is_down(e):
    """A connection that could not be made (refused, no DNS), as opposed to a slow or bad reply."""
    return isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError) and not isinstance(e.reason, TimeoutError) \
        or isinstance(e, (ConnectionError, socket.gaierror))


class Unreachable(Exception):
    pass


def resilient(call, retries):
    """Call it. A connection that cannot be made: wait 5, 15, 45 s and try again, then give up (Unreachable).
    Any other failure (timeout, unreadable reply): up to `retries` more tries after a short wait."""
    down = other = 0
    while True:
        try:
            return call()
        except Exception as e:
            if is_down(e):
                if down == len(BACKOFF):
                    raise Unreachable(str(e)) from e
                time.sleep(BACKOFF[down])
                down += 1
            elif other < retries:
                other += 1
                time.sleep(RETRY_WAIT)
            else:
                raise


def cpu_temp():
    """CPU package temperature in °C, 0 if this machine does not say. shortcut: Linux sysfs only, add other systems when needed."""
    for z in Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            if (z / "type").read_text().strip() == "x86_pkg_temp":
                return int((z / "temp").read_text()) / 1000
        except (OSError, ValueError):
            pass
    return 0


def rest(cfg):
    """Room to breathe for shared hardware: `pause` seconds after every call, then while the CPU is above max_temp."""
    time.sleep(cfg.get("pause", 0))
    while cfg.get("max_temp") and cpu_temp() > cfg["max_temp"]:
        time.sleep(10)


def validate(v, schema, where="reply"):
    """Check a judge's reply against the small part of JSON Schema our schemas use (object, array, string, enum, required). Raises ValueError."""
    t = schema["type"]
    if t == "object":
        if not isinstance(v, dict):
            raise ValueError(f"{where}: not an object")
        for k in schema.get("required", []):
            if k not in v:
                raise ValueError(f"{where}: missing {k!r}")
        for k, sub in schema.get("properties", {}).items():
            if k in v:
                validate(v[k], sub, f"{where}.{k}")
    elif t == "array":
        if not isinstance(v, list):
            raise ValueError(f"{where}: not a list")
        for i, x in enumerate(v):
            validate(x, schema["items"], f"{where}[{i}]")
    elif t == "string":
        if not isinstance(v, str):
            raise ValueError(f"{where}: not text")
        if "enum" in schema and v not in schema["enum"]:
            raise ValueError(f"{where}: {v!r} is not one of {schema['enum']}")
    else:
        raise ValueError(f"{where}: schema type {t!r} not supported")   # shortcut: only what our schemas use; extend with them


JUDGE_USE = threading.local()   # the judge's tokens and cost for the answer being judged now (each worker thread has its own)


def judge_use_reset():
    JUDGE_USE.tokens, JUDGE_USE.cost = None, None


def judge_use_add(usage):
    """Adds one judge reply's usage. Cost stays None unless the server reports one (OpenRouter does; llama.cpp doesn't)."""
    if not isinstance(usage, dict):
        return
    if not hasattr(JUDGE_USE, "tokens"):
        judge_use_reset()
    num = http.usage_number
    if num(usage.get("total_tokens")):   # anything else is ignored: usage is a note, never a reason to fail a judgement
        JUDGE_USE.tokens = (JUDGE_USE.tokens or 0) + usage["total_tokens"]
    if num(usage.get("cost")):
        JUDGE_USE.cost = (JUDGE_USE.cost or 0) + usage["cost"]


def ask_json(cfg, prompt, schema, max_tokens=500, verify=None):
    """One judge call, answer forced into the JSON schema. The reply must also pass `validate` and `verify` (a check of our own that raises);
    an invalid reply is retried like a failed call, then raises: it is a judge error, never a score.
    Every call stands alone: one message, never a history. `seed` (set per repeat) and `temperature` go with it."""
    j = cfg["judge"]
    body = {"model": j["model"], "temperature": cfg.get("temperature", 0.0), "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "marks", "schema": schema}}}
    if not j["cache"]:
        body["cache_prompt"] = False   # llama.cpp: no reuse of earlier prompts. Other servers ignore the field.
    if "seed" in cfg:
        body["seed"] = cfg["seed"]
    def call():
        whole = post(j["url"].rstrip("/") + "/chat/completions", body, j["timeout"], http.resolve_headers(j.get("headers", {})))
        judge_use_add(whole.get("usage"))   # counted even if the reply is then refused: it was paid for
        reply = json.loads(whole["choices"][0]["message"]["content"])
        validate(reply, schema)
        if verify:
            verify(reply)
        return reply
    try:
        return resilient(call, j["retries"])
    finally:
        rest(cfg)


def share(k, n):
    return k / n if n else None


def clip(s, n=70):
    s = s.rstrip(". ")
    return s if len(s) <= n else s[:n - 1] + "…"


def quick_scores(marks, has_extracts):
    """From the judge's claim verdicts. -> (scores, reasons). Correctness here is the share of answer
    claims that agree with the reference; it does not see facts the answer left out."""
    cl = marks["claims"]
    n, sup = len(cl), sum(c["supported"] == "yes" for c in cl)
    agree, contra = sum(c["vs_reference"] == "agrees" for c in cl), sum(c["vs_reference"] == "contradicts" for c in cl)
    scores = {"faithfulness": share(sup, n) if has_extracts else None, "correctness": agree / n if n else 0.0,
              "relevancy": REL[marks["relevancy"]], "context_recall": None}
    unbacked = [c["claim"] for c in cl if c["supported"] != "yes"][:2]
    reasons = {"correctness": f"Correctness {scores['correctness']:.2f} = answer claims that agree with the reference / claims in the answer = {agree} / {n}"
                              + (f"; {contra} contradict it." if contra else ".") if n else "Correctness 0: the answer states no facts.",
               "relevancy": f"Relevancy {scores['relevancy']:.1f}: the judge said {marks['relevancy']} ({clip(marks['relevancy_why'], 120)})."}
    if scores["faithfulness"] is not None:
        reasons["faithfulness"] = f"Faithfulness {scores['faithfulness']:.2f} = claims backed by the extracts / claims in the answer = {sup} / {n}." + \
                                  (f" Not backed: {'; '.join(map(clip, unbacked))}." if unbacked else "")
    return scores, reasons


def knowledge_scores(marks):
    """From the judge's yes/no answers, for plain chat models that cite nothing. -> (scores, reasons).
    Right = states the key fact and nothing false (1); right with an error = the key fact plus something false (0.5);
    wrong or no answer = 0. Extra true detail costs nothing, unlike quick mode."""
    key, false, answered = marks["key_fact"] == "yes", marks["false_claims"], marks["answered"] == "yes"
    c = 0.0 if not answered or not key else 0.5 if false else 1.0
    word = "no answer" if not answered else "wrong: the key fact is missing" if not key else "right, with an error" if false else "right"
    reasons = {"correctness": f"Correctness {c:.1f}: {word} ({clip(marks['key_fact_why'], 120)})."
                              + (f" False: {'; '.join(clip(f['claim']) for f in false[:2])}." if false else ""),
               "relevancy": f"Relevancy {float(answered):.1f}: the judge says the answer " + ("gives an answer" if answered else "gives none")
                            + f" ({clip(marks['answered_why'], 120)})."}
    return {"faithfulness": None, "correctness": c, "relevancy": float(answered), "context_recall": None}, reasons


def claim_scores(a_claims, r_claims, a_ext, a_ref, r_ext, r_ans):
    """From the judges' yes/no lists (True = supported), counted here. -> (scores, reasons, numbers)."""
    na, nr = len(a_claims), len(r_claims)
    tp_p, tp_r = sum(a_ref), sum(r_ans)                       # answer claims in the reference; reference facts in the answer
    prec, rec = share(tp_p, na), share(tp_r, nr)
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    scores = {"faithfulness": share(sum(a_ext), na) if a_ext else None, "correctness": f1,
              "context_recall": share(sum(r_ext), nr) if r_ext else None}
    missed = [c for c, ok in zip(r_claims, r_ans) if not ok][:2]
    extra = [c for c, ok in zip(a_claims, a_ref) if not ok][:2]
    reasons = {"correctness": f"F1 {f1:.2f}: the balance of precision and recall (2 × P × R / (P + R)). "
                              f"Recall {rec or 0:.2f} = reference facts found / facts in the reference = {tp_r} / ({tp_r} + {nr - tp_r} missed)."
                              + (f" Missed: {'; '.join(map(clip, missed))}." if missed else "")
                              + f" Precision {prec or 0:.2f} = answer facts that match the reference / all answer facts = {tp_p} / ({tp_p} + {na - tp_p} extra)."
                              + (f" Extra: {'; '.join(map(clip, extra))}." if extra else "")}
    if scores["faithfulness"] is not None:
        bad = [c for c, ok in zip(a_claims, a_ext) if not ok][:2]
        reasons["faithfulness"] = f"Faithfulness {scores['faithfulness']:.2f} = claims backed by the extracts / claims in the answer = {sum(a_ext)} / {na}." + \
                                  (f" Not backed: {'; '.join(map(clip, bad))}." if bad else "")
    if scores["context_recall"] is not None:
        reasons["context_recall"] = f"Context recall {scores['context_recall']:.2f} = reference facts backed by the extracts / facts in the reference = {sum(r_ext)} / {nr}."
    return scores, reasons, {"precision": prec or 0.0, "recall": rec or 0.0}


def check(cfg, claims, source):
    """One call: does the source support each claim? -> [True/False per claim], [reasons]."""
    if not claims:
        return [], []
    def one_each(reply):
        if len(reply["verdicts"]) != len(claims):
            raise ValueError(f"judge gave {len(reply['verdicts'])} verdicts for {len(claims)} claims")
    v = ask_json(cfg, prompt(cfg, "check").format(source=source, claims="\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))), CHECK_SCHEMA, 100 + 60 * len(claims), one_each)["verdicts"]
    one_each({"verdicts": v})   # again, for a judge replaced in tests
    return [x["supported"] == "yes" for x in v], [x["why"] for x in v]


def judge(item, cfg):
    """-> (scores, reasons, detail, error). A failed judge gives no scores, not a crash.
    detail holds the claims and verdicts, so a person can see why."""
    none = {m: None for m in GENERATION + ["abstention"]}
    extracts = "\n".join(f"[{i + 1}] {x}" for i, x in enumerate(item["extracts"])) or "(none)"
    fill = dict(question=item["question"], reference=item["reference"], extracts=extracts, answer=item["answer"])
    mode = cfg["judge"]["mode"]
    try:
        if item.get("answerable", True) is False and mode == "knowledge":
            # Declining but adding something false (a wrong year for a real prize, say) scores 0.5, like right with an error.
            v = ask_json(cfg, prompt(cfg, "knowledge_abstain").format(**fill), KNOWLEDGE_ABSTAIN_SCHEMA, 1000)
            ok, false = v["verdict"] == "declined", v["false_claims"]
            a = (0.5 if false else 1.0) if ok else 0.0
            return {**none, "abstention": a}, {"abstention": f"Abstention {a:.1f}: the judge says the answer " +
                   ("declines" if ok else "makes something up") + f" ({clip(v['why'], 120)})." +
                   (f" False: {'; '.join(clip(f['claim']) for f in false[:2])}." if false else "")}, {"mode": mode, **v}, None
        if item.get("answerable", True) is False:
            v = ask_json(cfg, prompt(cfg, "abstain").format(**fill), ABSTAIN_SCHEMA, 150)
            ok = v["verdict"] == "declined"
            return {**none, "abstention": float(ok)}, {"abstention": f"Abstention {int(ok)}: the judge says the answer " +
                   ("declines" if ok else "makes something up") + f" ({clip(v['why'], 120)})."}, {"mode": mode, **v}, None
        if mode == "knowledge":
            marks = ask_json(cfg, prompt(cfg, "knowledge").format(**fill), KNOWLEDGE_SCHEMA, 1200)   # room enough that a long answer's checks aren't cut off
            scores, reasons = knowledge_scores(marks)
            return {**none, **scores}, reasons, {"mode": mode, **marks}, None
        if mode == "quick":
            marks = ask_json(cfg, prompt(cfg, "quick").format(**fill), QUICK_SCHEMA, 700)
            scores, reasons = quick_scores(marks, bool(item["extracts"]))
            return {**none, **scores}, reasons, {"mode": mode, **marks}, None
        s = ask_json(cfg, prompt(cfg, "split").format(**fill), SPLIT_SCHEMA, 700)
        ac, rc, has = s["answer_claims"], s["reference_claims"], bool(item["extracts"])
        a_ext, w1 = check(cfg, ac, extracts) if has else ([], [])
        a_ref, w2 = check(cfg, ac, f"QUESTION: {item['question']}\nREFERENCE ANSWER: {item['reference']}")
        r_ext, w3 = check(cfg, rc, extracts) if has else ([], [])
        r_ans, w4 = check(cfg, rc, f"QUESTION: {item['question']}\nANSWER: {item['answer']}")
        scores, reasons, nums = claim_scores(ac, rc, a_ext, a_ref, r_ext, r_ans)
        scores["relevancy"] = REL[s["relevancy"]]
        reasons["relevancy"] = f"Relevancy {scores['relevancy']:.1f}: the judge said {s['relevancy']} ({clip(s['relevancy_why'], 120)})."
        detail = {"mode": mode, "answer_claims": ac, "reference_claims": rc, **nums,
                  "answer_vs_extracts": [{"supported": a, "why": w} for a, w in zip(a_ext, w1)], "answer_vs_reference": [{"supported": a, "why": w} for a, w in zip(a_ref, w2)],
                  "reference_vs_extracts": [{"supported": a, "why": w} for a, w in zip(r_ext, w3)], "reference_vs_answer": [{"supported": a, "why": w} for a, w in zip(r_ans, w4)]}
        return {**none, **scores}, reasons, detail, None
    except Exception as e:
        return none, {}, None, f"{type(e).__name__}: {e}"


# ---- judge-check: does the judge mark the way we expect? --------------------------------------

def bucket(x):
    return 0 if x < 0.25 else 0.5 if x < 0.75 else 1


def kappa(expected, got):
    """Cohen's kappa for two lists of labels. None when chance agreement is already 1."""
    n = len(expected)
    po = sum(e == g for e, g in zip(expected, got)) / n
    pe = sum((expected.count(k) / n) * (got.count(k) / n) for k in set(expected) | set(got))
    return None if pe == 1 else (po - pe) / (1 - pe)


def check_scores(items, got):
    """items: judge-set items with "expect" {metric: [low, high]}; got: the judge's scores for each (None = it failed).
    A score passes when it falls inside the band. Kappa compares 0 / 0.5 / 1 buckets: the score's against the band's middle."""
    out, wrong = {}, []
    for m in GENERATION + ["abstention"]:
        pairs = [(it, g[m] if g else None) for it, g in zip(items, got) if m in it["expect"]]
        if not pairs:
            continue
        ok = [s is not None and it["expect"][m][0] <= s <= it["expect"][m][1] for it, s in pairs]
        want = [bucket(sum(it["expect"][m]) / 2) for it, _ in pairs]
        have = [bucket(s) if s is not None else None for _, s in pairs]
        k = kappa(want, have)
        out[m] = {"accuracy": round(sum(ok) / len(ok), 4), "kappa": None if k is None else round(k, 4), "n": len(ok)}
        wrong += [{"id": it["id"], "kind": it["kind"], "metric": m, "expected": it["expect"][m], "got": s} for (it, s), good in zip(pairs, ok) if not good]
    return out, wrong


def new_run_folder(cfg, prefix=""):
    """-> (run id, its new folder). The id is the UTC second; a second run started in the same second gets -2, -3 and so on.
    mkdir without exist_ok is the lock: of two runs racing for one name, only one gets it.
    shortcut: ids sort as text, so a 10th run in one second sorts before the 2nd; change to zero-padded suffixes if that ever happens."""
    root = folder(cfg["runs"])
    root.mkdir(parents=True, exist_ok=True)
    stamp = prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for n in itertools.count(1):
        run_id = stamp if n == 1 else f"{stamp}-{n}"
        try:
            (root / run_id).mkdir()
            return run_id, root / run_id
        except FileExistsError:
            continue


def judge_check(cfg, version=None, limit=0):
    path, version = find_dataset(cfg, cfg["judge_set"] or manage.only_dataset(cfg, "judge"), version)
    bad = manage.problems(path)   # before any judging: a bad band would otherwise crash the count at the end
    if bad:
        raise SystemExit(f"{path}: " + "; ".join(f"line {n}: {what}" for n, what in bad[:5]) + ". Run `nasute dataset check` for all of them.")
    header, items, fingerprint = load_dataset(path, version)
    items = items[:limit] if limit else items
    cfg["judge"]["model"] = cfg["judge"]["model"] or model_name(cfg["judge"]["url"], cfg["judge"]["headers"])
    run_id, out = new_run_folder(cfg, "judge-")
    start, got, down, aborted = time.monotonic(), [], 0, None
    for it in items:
        t = time.monotonic()
        scores, reasons, detail, err = judge(it, cfg)
        got.append(None if err else scores)
        down = down + 1 if err and err.startswith("Unreachable") else 0
        with open(out / "results.jsonl", "a") as f:
            f.write(json.dumps({"id": it["id"], "kind": it["kind"], "scores": scores, "reasons": reasons, "judge_detail": detail, "judge_error": err,
                                "judge_s": round(time.monotonic() - t, 1)}) + "\n")
        log("judge_item_done", id=it["id"], judge_error=err, scores=scores)
        if down >= 3:
            aborted = "the judge could not be reached for 3 items in a row"
            break
    metrics, wrong = check_scores(items[:len(got)], got)
    summary = {"run": run_id, "dataset": fingerprint, "judge_model": cfg["judge"]["model"], "judge_mode": cfg["judge"]["mode"], "judge_prompts": prompt_record(cfg), "items": len(got), "set_size": len(items), "aborted": aborted,
               "failed": sum(g is None for g in got), "total_s": round(time.monotonic() - start, 1), "metrics": metrics, "wrong": wrong}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    log("judge_check_done", run=run_id, total_s=summary["total_s"], accuracy={m: v["accuracy"] for m, v in metrics.items()}, kappa={m: v["kappa"] for m, v in metrics.items()})
    if not aborted:   # the report shows the newest check, so a fresh one should appear at once (a stopped one is not worth a rebuild)
        report(cfg)
    return summary


def latest_judge_check(cfg, model, mode, prompts=None, full=False):
    """The newest complete judge-check for this judge model, mode and prompts (a prompt_record; None is the built-in ones) (else the newest stopped one, marked aborted), trimmed for a run's summary. None if there is none.
    full=True (the report) adds the judge set and the list of marks that were wrong."""
    root = folder(cfg["runs"])
    stopped = None
    for d in sorted(root.glob("judge-*"), reverse=True) if root.exists() else []:
        if (d / "summary.json").exists():
            s = json.loads((d / "summary.json").read_text())
            if s["judge_model"] == model and s["judge_mode"] == mode and not prompts_differ(prompts, s.get("judge_prompts")):
                rec = {"run": s["run"], "items": s["items"], "set_size": s.get("set_size", s["items"]), "aborted": s.get("aborted"), "metrics": s["metrics"]}
                if full:
                    rec.update(dataset={k: s["dataset"][k] for k in ("name", "version")}, wrong=s.get("wrong", []))
                if not rec["aborted"]:
                    return rec
                stopped = stopped or rec   # a complete check wins; a stopped one only if there is nothing better, and it says so
    return stopped


# ---- runs -----------------------------------------------------------------------------------

def git_commit():
    """Which code made a run: the git commit when run from a checkout, else the installed version."""
    try:
        got = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        got = ""
    if got:
        return got
    try:
        return "v" + importlib.metadata.version("nasute")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def counting_line(c):
    plural = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")
    return f"{c['asked']} asked · {c['scored']} scored · {plural(c['system_errors'], 'system error')} · {plural(c['judge_errors'], 'judge error')}"


SECRETISH = re.compile(r"key|token|secret|passw|passphrase|auth|credential", re.I)   # not a bare "pass": pass_at is an ordinary setting


def public(node):
    """The settings as saved with a run, at every depth (profiles too, used or not): a `headers` table keeps its names only;
    anything (a value, list or table) under a key-, token-, secret-, password-, auth- or credential-like name is hidden;
    and a URL loses any user:password@ and the values in its query string, where some services take their key."""
    if isinstance(node, dict):
        return {k: sorted(v) if k == "headers" and isinstance(v, dict) else "(hidden)" if SECRETISH.search(k) else public(v) for k, v in node.items()}
    if isinstance(node, list):
        return [public(x) for x in node]
    if isinstance(node, str) and "://" in node:
        p = urllib.parse.urlsplit(node)
        if p.query or "@" in p.netloc:
            query = "&".join(f"{q.partition('=')[0]}=(hidden)" for q in p.query.split("&")) if p.query else ""
            return urllib.parse.urlunsplit((p.scheme, p.netloc.rpartition("@")[2], p.path, query, ""))
    return node


def summarise(rows, fingerprint, cfg, extra):
    """Headline scores are strict (a system error counts as 0, set when the row was made). "metrics_answered" leaves
    system-error attempts out. A judge error leaves that attempt out of its judged scores and is never held against the system."""
    breakdown = lambda key: {t: {m: mean_std([r["scores"][m] for r in rows if r[key] == t or (key == "tags" and t in r[key])])["mean"] for m in METRICS}
                             for t in sorted({x for r in rows for x in (r[key] if key == "tags" else [r[key]])})}
    ok = [r for r in rows if not r["error"]]
    c = {"asked": len(rows), "system_errors": len(rows) - len(ok), "judge_errors": sum(bool(r["judge_error"]) for r in ok)}
    c["scored"] = c["asked"] - c["system_errors"] - c["judge_errors"]
    jrate = c["judge_errors"] / len(ok) if ok else 0.0
    binary = lambda m: m in ("hit", "abstention", "error_rate")
    return {
        **extra, "dataset": fingerprint, "settings": public({k: v for k, v in cfg.items() if k != "prompt_texts"}), "profile": cfg.get("profile", ""),
        "judge_mode": cfg["judge"]["mode"], "judge_prompts": prompt_record(cfg), "judge_cache": cfg["judge"]["cache"],
        "temperature": cfg["temperature"], "repeats": cfg["repeats"], "pass_at": cfg["pass_at"],
        "metrics": {m: stats(groups_of(rows, m), binary=binary(m)) for m in METRICS},
        "metrics_answered": {m: stats(groups_of(ok, m), binary=binary(m)) for m in METRICS if m != "error_rate"},
        "power": {m: power(groups_of(rows, m), cfg) for m in METRICS if stats(groups_of(rows, m))["attempts"] > 1},
        "tags": breakdown("tags"), "difficulty": breakdown("difficulty"),
        "counts": c, "counts_line": counting_line(c), "judge_error_rate": round(jrate, 4), "incomplete": jrate > cfg["max_judge_errors"],
        "consistency": consistency(rows, cfg), "causes": causes(rows, cfg),
        "failures": [{"id": r["id"], "error": r["error"]} for r in rows if r["error"]] +
                    [{"id": r["id"], "error": "judge: " + r["judge_error"]} for r in rows if r["judge_error"]],
    }


# What a target's reply may hold: what http.ask returns, plus the two flags the harness reads. Anything else is dropped, so a
# "module:function" target cannot replace the question's id, reference, answerable or expected sources it is judged against.
REPLY_KEYS = {"answer", "sources", "links", "extracts", "first_text_s", "total_s", "error", "unreachable", "extracts_failed", *http.USAGE}


def ask_target(cfg, kind, question, tcfg):
    """One call to the system under test. A target that says it could not connect is tried again after 5, 15, 45 s.
    An error or an empty answer is the system's fault."""
    for wait in (0,) + BACKOFF:
        time.sleep(wait)
        got = {k: v for k, v in target_ask(kind)(question, tcfg, cfg["timeout"]).items() if k in REPLY_KEYS}
        if not got.get("unreachable"):
            break
    rest(cfg)
    return {**got, "error": "empty answer"} if not got["error"] and not got["answer"] else got


def attempts(cfg, kind, q, tcfg, save=lambda row: None, stop=None):
    """Everything for one question: each repeat's call to the target, then its judging. -> rows.
    Questions never share anything: every call stands alone, and each repeat has its own seed."""
    rows = []
    for rep in range(1, cfg["repeats"] + 1):   # repeats run back to back
        if stop and stop.is_set():   # the run was aborted: keep the repeats done, start no more
            break
        got = ask_target(cfg, kind, q["question"], {**tcfg, "temperature": cfg["temperature"], "seed": rep})
        scores = {m: None for m in METRICS}
        scores["error_rate"] = float(bool(got["error"]))
        scores.update(retrieval_scores(q["sources"], got["sources"], cfg["k"]))
        reasons = retrieval_reasons(q["sources"], got["sources"], cfg["k"], scores)
        judged, detail, jerr, judge_s, judge_tokens, judge_cost = {}, None, None, None, None, None
        if got["error"]:   # strict: no answer scores 0 on every score that needs one
            mode = cfg["judge"]["mode"]   # only the scores this judge mode measures: knowledge mode has no faithfulness, only claims mode has context recall
            need = ["abstention"] if q.get("answerable", True) is False else ["correctness", "relevancy"] if mode == "knowledge" else [m for m in GENERATION if m != "context_recall" or mode == "claims"]
            judged = {m: 0.0 for m in need}
            reasons.update({m: f"{label(m, cfg['k'])} 0: system error, counted as 0 (strict). {clip(got['error'], 100)}." for m in need})
        else:
            t = time.monotonic()
            judge_use_reset()
            judged, jreasons, detail, jerr = judge({**q, **got}, {**cfg, "seed": rep})
            judge_s = round(time.monotonic() - t, 1)
            judge_tokens, judge_cost = JUDGE_USE.tokens, JUDGE_USE.cost
            reasons.update(jreasons)
            if got.get("extracts_failed"):   # the harness could not fetch the source text: not measured, and not the system's fault
                for m in ("faithfulness", "context_recall"):
                    if m in judged:
                        judged[m], reasons[m] = None, "Not measured: the source text could not be fetched (a harness problem, not counted against the system)."
        rows.append({"id": q["id"], "repeat": rep, "seed": rep, "tags": q["tags"], "difficulty": difficulty_of(q), "answerable": q.get("answerable", True), "question": q["question"],
                     "reference": q["reference"], "expected": q["sources"], **got, "scores": {**scores, **judged}, "reasons": reasons,
                     "judge_detail": detail, "judge_error": jerr, "judge_s": judge_s, "judge_tokens": judge_tokens, "judge_cost": judge_cost,
                     "unreachable": bool(got.get("unreachable")) or bool(jerr and jerr.startswith("Unreachable"))})
        save(rows[-1])
    return rows


def usage_totals(rows):
    """Tokens and cost for a run: the answers' (where the target reports them) and the judge's. A total is None when no row reported it,
    so "not known" never shows as 0."""
    def total(key):
        vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
        return round(sum(vals), 6) if vals else None
    n = len(rows) or 1
    out = {k: total(k) for k in ("tokens_in", "tokens_out", "cost", "judge_tokens", "judge_cost")}
    out["per_answer"] = {k: (round(v / n, 6) if v is not None else None) for k, v in out.items()}
    return out


def run(cfg, name, version, limit, target=None, label=""):
    """Ask dataset `name` of a target: the one its header names, or `target` to try the same questions on another."""
    path, version = find_dataset(cfg, name, version)
    header, questions, fingerprint = load_dataset(path, version)
    target = target or header["target"]
    if target not in cfg["targets"]:
        raise SystemExit(f"no target {target!r} in the settings (have {sorted(cfg['targets'])}); add a [targets.{target}] table")
    tcfg = cfg["targets"][target]
    kind = tcfg["kind"]
    target_ask(kind)   # a bad kind stops here, before the judge-check and the run folder
    questions = questions[:limit] if limit else questions
    cfg["judge"]["model"] = cfg["judge"]["model"] or model_name(cfg["judge"]["url"], cfg["judge"]["headers"])
    if cfg["judge_check"] and judge_check(cfg).get("aborted"):
        raise SystemExit("judge-check stopped because the judge could not be reached; the run was not started")
    answering = model_name(tcfg["model_url"]) if tcfg.get("model_url") else "unknown"
    run_id, out = new_run_folder(cfg)
    if label:
        set_label(cfg, run_id, label.strip())
    log("run_start", run=run_id, dataset=name, target=target, version=vtext(version), questions=len(questions), repeats=cfg["repeats"], workers=cfg["workers"], profile=cfg["profile"],
        judge_mode=cfg["judge"]["mode"], judge_cache=cfg["judge"]["cache"], temperature=cfg["temperature"])
    if cfg["repeats"] > 1 and cfg["temperature"] == 0:
        log("repeats_may_be_identical", logging.WARNING, note="temperature is 0: repeats differ only if the system or the search varies by itself")
    start, aborted, down, lock, stop = time.monotonic(), None, 0, threading.Lock(), threading.Event()

    done = [0]

    def save(row):   # every attempt goes to disk as it finishes, from any worker, so a crash loses nothing that was done
        with lock, open(out / "results.partial.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
            done[0] += 1
            n = done[0]
        log("question_done", logging.WARNING if row["error"] or row["judge_error"] else logging.INFO, n=n, of=len(questions) * cfg["repeats"], id=row["id"], repeat=row["repeat"], repeats=cfg["repeats"],
            outcome=outcome_word(row, cfg["pass_at"], cfg["judge"]["mode"]), error=row["error"], judge_error=row["judge_error"], total_s=row["total_s"], judge_s=row["judge_s"], scores=row["scores"])

    with ThreadPoolExecutor(max_workers=cfg["workers"]) as pool:
        futures = [pool.submit(attempts, cfg, kind, q, tcfg, save, stop) for q in questions]
        for fut in futures:   # in dataset order
            try:
                qrows = fut.result()
            except Exception:
                for g in futures:
                    g.cancel()   # a crash: start nothing new (what finished is in the partial file)
                raise
            down = down + 1 if qrows and all(r["unreachable"] for r in qrows) else 0   # a question counts only if no repeat got through
            if down >= 3:
                aborted = "the system under test or the judge could not be reached for 3 questions in a row"
                stop.set()   # running questions stop after their current repeat
                for g in futures:
                    g.cancel()   # questions not yet started never start
                break
    rows = [r for g in futures if not g.cancelled() for r in g.result()]
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))   # dataset order
    (out / "results.partial.jsonl").unlink(missing_ok=True)
    summary = summarise(rows, fingerprint, cfg, {
        "run": run_id, "commit": git_commit(), "target": target, "target_kind": kind, "answering_model": answering, "judge_model": cfg["judge"]["model"], "aborted": aborted,
        "questions": len({r["id"] for r in rows}), "attempts": len(rows), "total_s": round(time.monotonic() - start, 1),
        "judge_reliability": latest_judge_check(cfg, cfg["judge"]["model"], cfg["judge"]["mode"], prompt_record(cfg)),
        "time_to_first_text_s": mean_std([r["first_text_s"] for r in rows])["mean"], "usage": usage_totals(rows)})
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    if aborted:
        log("run_aborted", logging.ERROR, run=run_id, why=aborted)
    if summary["incomplete"]:
        log("run_incomplete", logging.WARNING, judge_error_rate=summary["judge_error_rate"], limit=cfg["max_judge_errors"])
    report(cfg)
    page = report_link(cfg, summary)
    keep = measured(rows)
    if logging.getLogger().handlers and isinstance(logging.getLogger().handlers[0].formatter, Readable):
        print("\n".join(run_summary(summary, rows, page)))
    else:   # one JSON line a log reader can take whole: the same facts as the readable summary
        log("run_done", run=run_id, total_s=summary["total_s"], counts=summary["counts_line"], aborted=aborted, incomplete=summary["incomplete"], report=page,
            scores={m: {"mean": summary["metrics"][m]["mean"], "ci": summary["metrics"][m]["ci"]} for m in keep if summary["metrics"][m]["mean"] is not None},
            errors=[f["id"] for f in summary.get("failures", [])], usage={k: v for k, v in (summary.get("usage") or {}).items() if k != "per_answer" and v is not None})
    return run_id


def outcome_word(row, pass_at, mode):
    """What became of one attempt, in a word or three; the same rule as outcome() in assets/report.js."""
    if row.get("error"):
        return "system error"
    if row.get("answerable", True) is False:
        v = row["scores"].get("abstention")
        return "not judged" if v is None else "declined" if v >= 1 else "declined, with an error" if v > 0 else "made something up"
    v = row["scores"].get("correctness")
    return "not judged" if v is None else "right" if v >= pass_at else ("right, with an error" if mode == "knowledge" else "partly right") if v > 0 else "wrong"


def measured(rows):
    """The scores a run really measured. A score set only on attempts that failed (the strict 0, say faithfulness in a mode that
    never measures it) is not measured, nor is a source score when the system named no source at all. Such a score is left out
    of the report and the summary rather than shown as 0.00, which would look like a bad result. Error rate is always measured."""
    answered = [r for r in rows if not r.get("error")] or rows   # every attempt failed: the strict zeros are all there is
    cited = any(r.get("sources") for r in rows)
    return [m for m in METRICS if m == "error_rate" or (any(r["scores"].get(m) is not None for r in answered) and (m not in RETRIEVAL or cited))]


def report_link(cfg, summary):
    """Where the run's report page is: under the report_url setting when it is set, else a file:// address."""
    rel = f"{pages.slug(suite_of(summary))}/runs/{summary['run']}.html"
    if cfg.get("report_url"):
        return cfg["report_url"].rstrip("/") + "/" + urllib.parse.quote(rel, safe="/@")
    return (folder(cfg["report"]) / rel).resolve().as_uri()


def run_summary(summary, rows, page):
    """The lines printed when a run ends, for a person: counts, the measured scores with their 95% ranges, errors, tokens and cost, the report."""
    k, keep = summary["settings"].get("k"), measured(rows)
    lines = ["", f"Run {summary['run']} finished in {round(summary['total_s'])} s: {summary['counts_line']}"]
    if summary.get("aborted"):
        lines.append(f"STOPPED EARLY: {summary['aborted']}")
    if summary.get("incomplete"):
        lines.append(f"INCOMPLETE: {summary['judge_error_rate']:.0%} of answers could not be judged")
    width = max((len(label(m, k)) for m in keep), default=0)
    for m in keep:
        s = summary["metrics"][m]
        if s["mean"] is not None:
            lines.append(f"  {label(m, k).ljust(width)}  {s['mean']:.2f}" + (f"  (95% range {max(0, s['ci'][0]):.2f}–{min(1, s['ci'][1]):.2f})" if s["ci"] else ""))
    fails = summary.get("failures") or []
    if fails:
        lines.append(f"System errors: {len(fails)} ({', '.join(f['id'] for f in fails[:8])}{', ...' if len(fails) > 8 else ''})")
    u = summary.get("usage") or {}
    spent = [f"{u['tokens_in'] or 0} tokens in, {u['tokens_out'] or 0} out" if u.get("tokens_in") is not None or u.get("tokens_out") is not None else "",
             f"US${u['cost']:.4f}" if u.get("cost") is not None else "", f"judging {u['judge_tokens']} tokens" if u.get("judge_tokens") is not None else "",
             f"judging US${u['judge_cost']:.4f}" if u.get("judge_cost") is not None else ""]
    if any(spent):
        lines.append("Used: " + "; ".join(x for x in spent if x))
    lines.append(f"Report: {page}")
    return lines


# ---- compare and report ---------------------------------------------------------------------

def run_ids(cfg):
    root = folder(cfg["runs"])
    return sorted(d.name for d in root.iterdir() if not d.name.startswith("judge-") and (d / "summary.json").exists()) if root.exists() else []


def read_run(cfg, run_id):
    d = folder(cfg["runs"]) / run_id
    return json.loads((d / "summary.json").read_text()), [json.loads(x) for x in (d / "results.jsonl").read_text().splitlines()] if (d / "results.jsonl").exists() else []


def suite_of(summary):
    """A suite is one dataset asked of one target."""
    return f"{summary['dataset']['name']}{SEP}{summary.get('target', '')}"


def summaries(cfg):
    """{run id: summary}, oldest first."""
    return {i: read_run(cfg, i)[0] for i in run_ids(cfg)}


# ---- export: one function for the CSV files in the report and for `runs export` ---------------------------
RUN_COLUMNS = ["run", "id", "repeat", "tags", "difficulty", "answerable", *METRICS, "cause", "error", "judge_error", "first_text_s", "total_s", "judge_s", "question", "reference", "answer"]
SUITE_COLUMNS = ["run", "date", "profile", "judge_mode", "target", "answering_model", "judge_model", "dataset_version", "id", "tags", "difficulty", *METRICS, "attempts", "errors"]


FORMULA_AFTER_SPLIT = re.compile(r"([;\t])([=+\-@])")


def csv_safe(text):
    """A spreadsheet runs a cell that starts with = + - or @ as a formula, and answers come from a language model. A leading apostrophe keeps it text.
    Spreadsheets set to split on ; or tab (some locales do by default) start a new cell there, so a formula character after one gets an apostrophe too."""
    if not isinstance(text, str):
        return text
    text = FORMULA_AFTER_SPLIT.sub(r"\1'\2", text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def run_csv(summary, rows, out):
    """One row per attempt, in RUN_COLUMNS order, to the open text file `out`. The cause is the question's failure cause from the summary ("" when it did not fail)."""
    cause = {q["id"]: q["cause"] for q in summary.get("causes", {}).get("questions", [])}
    w = csv.writer(out, lineterminator="\n")
    put = lambda cells: w.writerow([csv_safe(c) for c in cells])   # every text cell, not only the long ones: ids, tags and model names come from files and targets too
    put(RUN_COLUMNS)
    for r in rows:
        sc = r.get("scores", {})
        put([summary["run"], r["id"], r.get("repeat", 1), ";".join(r.get("tags", [])), r.get("difficulty", ""), r.get("answerable", True), *["" if sc.get(m) is None else sc[m] for m in METRICS],
             cause.get(r["id"], ""), *[r.get(k) or "" for k in ("error", "judge_error")], *["" if r.get(k) is None else r[k] for k in ("first_text_s", "total_s", "judge_s")],
             *[r.get(k) or "" for k in ("question", "reference", "answer")]])


def suite_csv(pairs, out):
    """One row per question per run for the suite's runs, `pairs` being [(summary, rows)] oldest first: the mean of each score over the repeats, how many attempts, how many failed."""
    w = csv.writer(out, lineterminator="\n")
    put = lambda cells: w.writerow([csv_safe(c) for c in cells])
    put(SUITE_COLUMNS)
    for s, rows in pairs:
        by = {}
        for r in rows:
            by.setdefault(r["id"], []).append(r)
        for i, reps in by.items():
            means = []
            for m in METRICS:
                v = [r["scores"][m] for r in reps if r.get("scores", {}).get(m) is not None]
                means.append(fmean(v) if v else "")
            put([s["run"], s["run"][:4] + "-" + s["run"][4:6] + "-" + s["run"][6:8], s.get("profile", ""), s.get("judge_mode", ""), s.get("target", ""), s.get("answering_model", ""), s.get("judge_model", ""),
                        vtext(s["dataset"]["version"]), i, ";".join(reps[0].get("tags", [])), reps[0].get("difficulty", ""), *means, len(reps), sum(1 for r in reps if r.get("error"))])


def run_meta(cfg):
    """Labels and baselines, kept in runs/index.json: {"labels": {run: text}, "baselines": {suite: run}}."""
    f = folder(cfg["runs"]) / "index.json"
    meta = {"labels": {}, "baselines": {}, **(json.loads(f.read_text()) if f.exists() else {})}
    for key, run_id in list(meta["baselines"].items()):   # suite ids were dataset__target before dataset@target: find the real suite from the run
        summary = folder(cfg["runs"]) / run_id / "summary.json"
        if SEP not in key and summary.exists():
            del meta["baselines"][key]
            meta["baselines"][suite_of(json.loads(summary.read_text()))] = run_id   # written back the next time anything is saved
    return meta


def set_label(cfg, run_id, label):
    """The run's label in runs/index.json (empty text removes it): one store for `runs label` and `run --label`."""
    meta = run_meta(cfg)
    meta["labels"].pop(run_id, None)
    if label:
        meta["labels"][run_id] = label
    save_meta(cfg, meta)


def save_meta(cfg, meta):
    """Written to a temporary file and moved into place, so a reader never sees half a file.
    shortcut: two commands changing labels at the very same moment can lose one change; fine for one person by hand."""
    f = folder(cfg["runs"]) / "index.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(meta, indent=1))
    os.replace(tmp, f)


def reference_run(cfg, sums, run_id):
    """The run to compare `run_id` against: its suite's baseline (unless it is that run), else the run before it in the suite,
    skipping runs with another profile when both have one. None if there is nothing to compare with."""
    s = sums[run_id]
    fits = lambda i: not (s.get("profile") and sums[i].get("profile") and s["profile"] != sums[i]["profile"])
    base = run_meta(cfg)["baselines"].get(suite_of(s))
    if base and base != run_id and base in sums and fits(base):   # a baseline of another profile is no yardstick
        return base
    return next((i for i in reversed(list(sums)) if i < run_id and suite_of(sums[i]) == suite_of(s) and fits(i)), None)


def compare(cfg, a_id=None, b_id=None, suite=None):
    """A is the older run (or the baseline), B the newer. Paired on the questions both answered: each question's score is
    its average over repeats; the differences give a mean, standard error, 95% interval and a verdict.
    With no ids: the newest run (of `suite`, if given) against reference_run()."""
    if not (a_id and b_id):
        sums = summaries(cfg)
        b_id = next((i for i in reversed(list(sums)) if not suite or suite_of(sums[i]) == suite), None)
        a_id = b_id and reference_run(cfg, sums, b_id)
        if not a_id:
            return None
    (sa, ra), (sb, rb) = read_run(cfg, a_id), read_run(cfg, b_id)
    fa, fb = sa["dataset"], sb["dataset"]
    warning, notes = None, []
    stopped = [x["run"] for x in (sa, sb) if x.get("aborted")]
    if sa.get("profile") and sb.get("profile") and sa["profile"] != sb["profile"]:
        warning = f"Different profiles: {sa['profile']} against {sb['profile']}. A quick look and a careful run are not comparable; no verdict is given."
    elif stopped:
        warning = f"Run {stopped[0]} was stopped early ({sa.get('aborted') or sb.get('aborted')}). Nothing is compared."
    elif fa["sha256"] != fb["sha256"]:
        warning = f"Different questions: {fa['name']} v{vtext(fa['version'])} against {fb['name']} v{vtext(fb['version'])}. Scores are not comparable; no per-question changes shown."
    for key, label in (("profile", "profiles"), ("judge_mode", "judge modes"), ("repeats", "repeat counts")):
        if sa.get(key) != sb.get(key) and not (key == "profile" and sa.get(key) and sb.get(key)):
            notes.append(f"Different {label}: {sa.get(key) or 'none'} against {sb.get(key) or 'none'}. The runs are less alike than they look.")
    if sa.get("target") != sb.get("target") and fa["sha256"] == fb["sha256"]:   # comparing two systems on the same questions is allowed
        notes.append(f"{sa.get('answering_model') or sa.get('target')} against {sb.get('answering_model') or sb.get('target')}: same questions, different targets ({sa.get('target')} against {sb.get('target')}).")
    for key, label in (("judge_model", "judge models"), ("answering_model", "answering models")):
        if sa.get(key) != sb.get(key):
            notes.append(f"Different {label}: {sa.get(key)} against {sb.get(key)}." + (" Marked scores are not comparable." if key == "judge_model" else ""))
    other_prompts = prompts_differ(sa.get("judge_prompts"), sb.get("judge_prompts"))
    if other_prompts:   # another prompt is another marker, like another judge model
        custom = lambda x: ", ".join((x.get("judge_prompts") or {}).get("custom", [])) or "none"
        notes.append(f"Different judge prompts ({', '.join(other_prompts)}): custom {custom(sa)} against custom {custom(sb)}. Marked scores are not comparable.")
    other_judge = sa.get("judge_model") != sb.get("judge_model") or bool(other_prompts)
    notes += [f"Run {x['run']} is incomplete: too many judge errors ({x['judge_error_rate']:.0%}). Its scores have gaps." for x in (sa, sb) if x.get("incomplete")]
    shared = sorted({r["id"] for r in ra} & {r["id"] for r in rb}) if not warning else []
    failed = lambda rows: {r["id"] for r in rows if r["error"] and r["id"] in shared}
    out = {"a": a_id, "b": b_id, "warning": warning, "notes": notes, "shared": len(shared), "detect": cfg["detect"], "min_pairs": MIN_PAIRS, "k": sb["settings"].get("k"), "metrics": {}, "worse": [], "better": [],
           "errors": {"newly": sorted(failed(rb) - failed(ra)), "recovered": sorted(failed(ra) - failed(rb))}}
    for m in METRICS:
        qa, qb = (question_means([r for r in rows if r["id"] in shared], m) for rows in (ra, rb))
        out["metrics"][m] = paired(qa, qb, cfg["detect"], m in LOWER_BETTER)
        if other_judge and m in GENERATION + ["abstention"]:   # a different marker: the difference says nothing about the system
            out["metrics"][m]["verdict"] = "not comparable"
            continue
        for i in qa.keys() & qb.keys():
            if abs(qb[i] - qa[i]) > cfg["worse_by"]:
                why = next((r["reasons"].get(m, "") for r in rb if r["id"] == i), "")
                out["worse" if (qb[i] < qa[i]) != (m in LOWER_BETTER) else "better"].append({"id": i, "metric": m, "a": round(qa[i], 3), "b": round(qb[i], 3), "why": why})
    for k in ("worse", "better"):
        out[k].sort(key=lambda x: (x["id"], x["metric"]))
    if warning:   # nothing was paired: say so rather than "too few questions"
        for p in out["metrics"].values():
            p["verdict"] = "not comparable"
    return out


def mislabels(cfg, rows_by_run):
    """Measured difficulty: across every run of this exact dataset file, the share of attempts with
    correctness >= pass_at (system errors count as failures, like the headline scores). Flags likely wrong labels once a question has min_attempts attempts.
    rows_by_run: the rows of each run to count; the caller picks the runs of one suite and one dataset file."""
    tally = {}
    for rows in rows_by_run:
        for r in rows:
            if r["scores"]["correctness"] is not None:   # a system error is strict 0, so it counts as a failed attempt
                t = tally.setdefault(r["id"], {"label": r.get("difficulty", "unknown"), "attempts": 0, "passed": 0})
                t["attempts"] += 1
                t["passed"] += r["scores"]["correctness"] >= cfg["pass_at"]
    out = []
    for i, t in sorted(tally.items()):
        s = t["passed"] / t["attempts"]
        if t["attempts"] >= cfg["min_attempts"] and ((t["label"] == "easy" and s < cfg["mislabel_easy_below"]) or (t["label"] == "hard" and s > cfg["mislabel_hard_above"])):
            out.append({"id": i, **t, "share": round(s, 3)})
    return out


def describe(summary):
    """A few plain lines: each score, its 95% interval and what it means."""
    lines = []
    for m in METRICS:
        s, ans = summary["metrics"][m], summary["metrics_answered"].get(m, {})
        if s["mean"] is not None:
            lines.append(f"{label(m, summary['settings'].get('k'))}: {s['mean']:.2f}" + (f" (95% CI {s['ci'][0]:.2f}–{s['ci'][1]:.2f})" if s["ci"] else "")
                         + (f", answered only {ans['mean']:.2f}" if summary["counts"]["system_errors"] and ans.get("mean") is not None else "") + f". {GLOSSARY[m]['plain'].capitalize()}.")
    return lines


def report(cfg):
    return pages.write(cfg)


def show_compare(c):
    if not c:
        return "Needs two runs."
    lines = [f"{c['a']} -> {c['b']}, {c['shared']} shared questions"] + [c["warning"]] * bool(c["warning"]) + c["notes"]
    for m, p in c["metrics"].items():
        if p["delta"] is not None:
            lines.append(f"{label(m, c.get('k'))}: {p['a']:.2f} -> {p['b']:.2f}, change {p['delta']:+.2f}"
                         + (f" (95% CI {p['ci'][0]:+.2f} to {p['ci'][1]:+.2f}): {p['verdict']}" + (f"; ~{p['needed']} questions would see a {c['detect']} change" if p["needed"] else "; cannot estimate how many questions are needed: the differences have no spread") if p["ci"] else f": {p['verdict']}"))
    lines += [f"newly erroring: {', '.join(c['errors']['newly'])}"] * bool(c["errors"]["newly"]) + [f"recovered from errors: {', '.join(c['errors']['recovered'])}"] * bool(c["errors"]["recovered"])
    lines += [f"got worse: {w['id']} {w['metric']} {w['a']} -> {w['b']}. {w['why']}" for w in c["worse"]]
    lines += [f"got better: {w['id']} {w['metric']} {w['a']} -> {w['b']}" for w in c["better"]]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--config")
    p.add_argument("--log", choices=["text", "json"], help="how progress is printed: text for a person, json lines for a log reader (default: text at a terminal, else json; or NASUTE_LOG)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ini = sub.add_parser("init", help="write a starter nasute.toml and an example dataset")
    ini.add_argument("folder", nargs="?", default=".")
    ini.add_argument("--demo", action="store_true", help="point the settings at `nasute demo-server`, to try Nasute with no model")
    r = sub.add_parser("run")
    r.add_argument("--profile")
    r.add_argument("--dataset")
    r.add_argument("--target", help="test the dataset's questions on this target instead of the one its header names")
    r.add_argument("--version")
    r.add_argument("--label", default="", help='a name for this run, such as "prompt change"; the charts mark labelled runs')
    r.add_argument("--limit", type=int)
    r.add_argument("--repeats", type=int)
    r.add_argument("--mode", choices=["quick", "claims", "knowledge"])
    j = sub.add_parser("judge-check")
    j.add_argument("--mode", choices=["quick", "claims", "knowledge"])
    j.add_argument("--limit", type=int, default=0)
    c = sub.add_parser("compare")
    c.add_argument("runs", nargs="*")
    c.add_argument("--suite")
    sub.add_parser("report")
    pr = sub.add_parser("prompts", help="the judge prompts").add_subparsers(dest="action", required=True)
    pr.add_parser("export", help="write the built-in judge prompts as text files to edit; never overwrites").add_argument("folder")
    sub.add_parser("demo-server", help="a stand-in system and judge on port 8700, for trying Nasute with no account and no model")
    sv = sub.add_parser("serve", help="show the report folder in a browser on this machine")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default="127.0.0.1")
    d = sub.add_parser("dataset").add_subparsers(dest="action", required=True)
    dc = d.add_parser("check")
    dc.add_argument("name")
    dc.add_argument("--version")
    di = d.add_parser("import", help="turn a CSV into the next version of a dataset")
    di.add_argument("file")
    di.add_argument("--name", required=True)
    di.add_argument("--target")
    d.add_parser("list")
    rn = sub.add_parser("runs")
    rn.add_argument("--suite")
    ra = rn.add_subparsers(dest="action")   # no action: list the runs
    ra.add_parser("show").add_argument("run")
    rl = ra.add_parser("label")
    rl.add_argument("run")
    rl.add_argument("text", help="empty text removes the label")
    ra.add_parser("baseline").add_argument("run")
    rx = ra.add_parser("export", help="one run as CSV (one row per attempt), or --suite for every run of a suite")
    rx.add_argument("run", nargs="?")
    rx.add_argument("--suite", dest="export_suite")
    rx.add_argument("--csv", help="write to this file (default: print)")
    rd = ra.add_parser("delete")
    rd.add_argument("run")
    rd.add_argument("--yes", action="store_true")
    a = p.parse_args(argv)
    setup_logging(a.log)
    if a.cmd == "init":
        return manage.init(a.folder, a.demo)
    if a.cmd == "prompts":
        return manage.prompts_export(a.folder)
    cfg = load_settings(a.config, getattr(a, "profile", None))
    if getattr(a, "mode", None):
        cfg["judge"]["mode"] = a.mode
    if a.cmd == "run":
        if a.repeats:
            cfg["repeats"] = a.repeats
        target = a.target or (next(iter(cfg["targets"])) if len(cfg["targets"]) == 1 else "")
        name = a.dataset or cfg["dataset"] or manage.only_dataset(cfg, target)
        run(cfg, name, a.version, a.limit if a.limit is not None else cfg["limit"], a.target, a.label)
    elif a.cmd == "judge-check":
        s = judge_check(cfg, limit=a.limit)
        print(json.dumps({k: s[k] for k in ("run", "judge_model", "judge_mode", "judge_prompts", "items", "failed", "total_s", "metrics", "wrong")}, indent=1))
    elif a.cmd == "compare":
        print(show_compare(compare(cfg, *a.runs, suite=a.suite) if len(a.runs) == 2 else compare(cfg, suite=a.suite)))
    elif a.cmd == "report":
        report(cfg)
    elif a.cmd == "demo-server":
        from . import demo_server
        demo_server.serve()
    elif a.cmd == "serve":
        manage.serve(cfg, a.host, a.port)
    elif a.cmd == "dataset":
        return {"check": lambda: manage.dataset_check(cfg, a.name, a.version), "list": lambda: manage.dataset_list(cfg),
                "import": lambda: manage.dataset_import(cfg, a.file, a.name, a.target)}[a.action]()
    else:
        return {None: lambda: manage.runs_list(cfg, a.suite), "show": lambda: manage.runs_show(cfg, a.run), "label": lambda: manage.runs_label(cfg, a.run, a.text),
                "baseline": lambda: manage.runs_baseline(cfg, a.run), "export": lambda: manage.runs_export(cfg, a.run, a.export_suite, a.csv), "delete": lambda: manage.runs_delete(cfg, a.run, a.yes)}[a.action]()


