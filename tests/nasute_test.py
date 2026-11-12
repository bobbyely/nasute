#!/usr/bin/env python3
"""Checks for nasute, with made-up data: no network, no model, nothing written outside a temp folder.

How it runs: by hand and in CI (.github/workflows/checks.yml): python3 tests/nasute_test.py, from a checkout (no install needed).
Reads: src/nasute, nasute.example.toml, docs/, the demo datasets. Writes: a temp folder, deleted after.
"""
import json
import re
import shutil
import tempfile
import time
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # the checkout: docs/, nasute.example.toml
sys.path.insert(0, str(ROOT / "src"))   # test this checkout's code, not an installed copy
import nasute  # noqa: E402
from nasute import manage, pages  # noqa: E402

PKG = Path(nasute.__file__).parent   # the package: assets/, datasets/, pages.py
close = lambda a, b: abs(a - b) < 1e-9


def fake_run(cfg, run_id, dataset, scores, profile="", questions=None, **extra):
    """Write a run folder as run() would, from {question id: {metric: score}}. questions: {id: question text}."""
    rows = [{"id": i, "repeat": 1, "tags": ["t"], "difficulty": "easy", "error": s.get("error"), "judge_error": None, "first_text_s": 1.0, "total_s": 2.0, "judge_s": 3.0, "reasons": {m: f"{m} explained" for m in s if m != "error"},
             "judge_detail": None, "question": (questions or {}).get(i, f"Question {i}?"), "reference": "ref", "answer": f"Answer to {i}", "sources": [], "extracts": [], "expected": [], "answerable": True,
             "scores": {m: s.get(m) for m in nasute.METRICS}} for i, s in scores.items()]
    d = Path(cfg["runs"]) / run_id
    d.mkdir(parents=True)
    (d / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (d / "summary.json").write_text(json.dumps(nasute.summarise(rows, dataset, {**nasute.DEFAULTS, "profile": profile}, {"run": run_id, **extra})))


def row(i, **scores):
    return {"id": i, "error": scores.pop("error", None), "reasons": {}, "judge_detail": scores.pop("detail", None),
            "scores": {m: scores.get(m) for m in nasute.METRICS}}


def statistics_checks():
    # clustered standard error, worked by hand: scores [[1,0],[1,1],[0,0]]; mean .5, variance .3, n 6,
    # SE_CLT² = .3/6 = .05; cross terms (deviations of ±.5): -.5 + .5 + .5 = .5, divided by n² = 36
    s = nasute.stats([[1, 0], [1, 1], [0, 0]])
    assert close(s["mean"], 0.5) and abs(s["se"] - (0.05 + 0.5 / 36) ** 0.5) < 1e-4 and s["n"] == 3 and s["attempts"] == 6, s
    one = nasute.stats([[1], [0], [1], [1]])   # one score per question: the plain standard error, variance = n/(n-1) p(1-p)
    assert abs(one["se"] - ((0.75 * 0.25 * 4 / 3) / 4) ** 0.5) < 1e-4, one
    assert nasute.stats([[None]])["mean"] is None and nasute.stats([[1]])["se"] is None
    # Wilson interval: 5 of 10 is 0.2366 to 0.7634; 0 of 10 is 0 to 0.2775
    lo, hi = nasute.wilson(0.5, 10)
    assert abs(lo - 0.2366) < 1e-4 and abs(hi - 0.7634) < 1e-4, (lo, hi)
    lo, hi = nasute.wilson(0.0, 10)
    assert abs(lo) < 1e-9 and abs(hi - 0.2775) < 1e-4, (lo, hi)
    assert nasute.stats([[1], [0]] * 5, binary=True)["ci"] == [round(x, 4) for x in nasute.wilson(0.5, 10)]

    # questions needed = (1.96 + 0.8416)² × variance / difference²; the paper's own example (variance 1/9, difference .03) gives 969
    assert nasute.needed_questions(1 / 9, 0.03) == 969 and nasute.needed_questions(0.09, 0.05) == 283
    p = nasute.power([[1, 0], [0, 0], [1, 1]], {"repeats": 2, "detect": 0.05})   # within-question variances .5, 0, 0: mean 1/6; times 2, over K = 2
    assert p["basis"] == "repeats" and p["needed"] == nasute.needed_questions(1 / 6, 0.05)
    assert nasute.power([[1], [0], [1], [1]], {"repeats": 1, "detect": 0.05})["basis"] == "worst case"

    # paired: every question rose by about .3: a real gain; the other way round, a real drop
    a = {f"q{i}": 0.5 for i in range(6)}
    up = {f"q{i}": 0.5 + d for i, d in enumerate([.3, .2, .4, .3, .25, .35])}   # mean .3, variance .005
    r = nasute.paired(a, up, 0.05)
    assert r["verdict"] == "real gain" and close(r["delta"], 0.3) and abs(r["se"] - (0.005 / 6) ** 0.5) < 1e-4 and r["n"] == 6, r
    assert nasute.paired(up, a, 0.05)["verdict"] == "real drop"
    noisy = {f"q{i}": 0.5 + d for i, d in enumerate([.1, -.1, .1, -.1, 0, 0])}
    assert nasute.paired(a, noisy, 0.05)["verdict"] == "within noise"
    assert nasute.paired({"q1": 1}, {"q1": 0}, 0.05)["verdict"] == "too few questions"

    # pass^k: x passes both repeats, y only one (spread .8); z was asked once, so it says nothing about consistency
    cfg = {**nasute.DEFAULTS}
    rows = [row("x", correctness=0.9), row("x", correctness=0.8), row("y", correctness=1.0), row("y", correctness=0.2), row("z", correctness=0.1)]
    c = nasute.consistency(rows, cfg)
    assert c["questions"] == 2 and close(c["pass_all"], 0.5) and [f["id"] for f in c["flaky"]] == ["y"] and close(c["flaky"][0]["spread"], 0.8), c
    assert nasute.consistency([row("z", correctness=0.1)], cfg) is None

    # measured difficulty: "e" is easy but 1 of 5 passed, "h" is hard but 5 of 5, "few" has too few attempts, "ok" is fine
    def attempts(i, label, passes):
        return [{"id": i, "difficulty": label, "scores": {"correctness": 1.0 if p else 0.1}} for p in passes]
    runs = [attempts("e", "easy", [1, 0, 0, 0, 0]) + attempts("h", "hard", [1] * 5) + attempts("few", "easy", [0] * 4) + attempts("ok", "easy", [1] * 5)]
    assert [m["id"] for m in nasute.mislabels(cfg, runs)] == ["e", "h"]
    split = [attempts("e", "easy", [1, 0, 0]), attempts("e", "easy", [0, 0])]   # attempts add up across runs
    assert [m["id"] for m in nasute.mislabels(cfg, split)] == ["e"]


def judge_checks():
    # claim maths: 4 answer claims, 3 in the reference; 4 reference facts, 3 in the answer: P .75, R .75, F1 .75
    s, why, nums = nasute.claim_scores(list("abcd"), list("wxyz"), [1, 1, 1, 0], [1, 1, 1, 0], [1, 1, 1, 1], [1, 1, 1, 0])
    assert close(s["correctness"], 0.75) and close(s["faithfulness"], 0.75) and close(s["context_recall"], 1.0) and nums == {"precision": 0.75, "recall": 0.75}, s
    assert "Recall 0.75" in why["correctness"] and "3 / (3 + 1 missed)" in why["correctness"] and "Missed: z" in why["correctness"] and "Extra: d" in why["correctness"]
    assert "8 / 10" in nasute.claim_scores(list("a" * 10), ["w"], [1] * 8 + [0] * 2, [1] * 10, [1], [1])[1]["faithfulness"]
    s, _, _ = nasute.claim_scores([], ["w"], [], [], [1], [0])   # a refusal says nothing, so nothing is right
    assert s["correctness"] == 0 and s["faithfulness"] is None
    # quick mode: 5 claims, 4 backed, 3 agree, 1 contradicts
    marks = {"claims": [{"claim": str(i), "supported": "yes" if i < 4 else "no", "vs_reference": v, "why": ""} for i, v in
                        enumerate(["agrees"] * 3 + ["contradicts", "not_in_reference"])], "relevancy": "partly", "relevancy_why": "half"}
    s, why = nasute.quick_scores(marks, True)
    assert close(s["faithfulness"], 0.8) and close(s["correctness"], 0.6) and s["relevancy"] == 0.5, s
    assert "4 / 5" in why["faithfulness"] and "3 / 5; 1 contradict" in why["correctness"]
    assert nasute.quick_scores({"claims": [], "relevancy": "no", "relevancy_why": ""}, True)[0]["correctness"] == 0

    # the judge with its model call replaced: abstention is counted from a verdict, and nothing else is scored
    real = nasute.ask_json
    yes, no = {"supported": "yes", "why": ""}, {"supported": "no", "why": ""}
    try:
        nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: {"verdict": "declined", "why": "says it has nothing"}
        s, why, detail, err = nasute.judge({"question": "q", "reference": "", "answer": "I can't find that.", "extracts": [], "answerable": False}, {"judge": {"mode": "quick"}})
        assert s["abstention"] == 1.0 and s["correctness"] is None and s["relevancy"] is None and err is None and "declines" in why["abstention"], (s, why)
        nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: {"verdict": "made_something_up", "why": "gives a year"}
        assert nasute.judge({"question": "q", "reference": "", "answer": "1850.", "extracts": [], "answerable": False}, {"judge": {"mode": "claims"}})[0]["abstention"] == 0.0
        # claims mode: one split, then four checks (answer vs extracts, answer vs reference, reference vs extracts, reference vs answer)
        replies = iter([{"answer_claims": ["a1", "a2"], "reference_claims": ["r1"], "relevancy": "yes", "relevancy_why": "ok"},
                        {"verdicts": [yes, no]}, {"verdicts": [yes, no]}, {"verdicts": [yes]}, {"verdicts": [yes]}])
        nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: next(replies)
        s, why, detail, err = nasute.judge({"question": "q", "reference": "r", "answer": "a", "extracts": ["e"]}, {"judge": {"mode": "claims"}})
        assert err is None and close(s["correctness"], 2 * 0.5 * 1 / 1.5) and s["faithfulness"] == 0.5 and s["relevancy"] == 1.0 and detail["answer_claims"] == ["a1", "a2"], (s, err)
        # knowledge mode: right, right with an error, wrong, no answer; extra true detail costs nothing
        def kmarks(key, false, answered="yes"):
            return {"key_fact": key, "key_fact_why": "k", "false_claims": [{"claim": c, "why": "w"} for c in false], "answered": answered, "answered_why": "a"}
        item = {"question": "What is the capital of Australia?", "reference": "Canberra", "answer": "Canberra, a planned city chosen in 1908.", "extracts": []}
        for marks, want, rel in [(kmarks("yes", []), 1.0, 1.0), (kmarks("yes", ["It is in Victoria"]), 0.5, 1.0),
                                 (kmarks("no", []), 0.0, 1.0), (kmarks("no", [], "no"), 0.0, 0.0)]:
            nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None, m=marks: m
            s, why, detail, err = nasute.judge(item, {"judge": {"mode": "knowledge"}})
            assert err is None and s["correctness"] == want and s["relevancy"] == rel and s["faithfulness"] is None and detail["mode"] == "knowledge", (marks, s)
        assert "Victoria" in nasute.knowledge_scores(kmarks("yes", ["It is in Victoria"]))[1]["correctness"]
        # knowledge mode, made-up names: declined 1, declined with a false side claim 0.5, made up 0
        made_up = {"question": "Which novel by Harriet Pellingworth won the 1962 Miles Franklin Award?", "reference": "", "answer": "a", "extracts": [], "answerable": False}
        for v, want in [({"verdict": "declined", "why": "w", "false_claims": []}, 1.0),
                        ({"verdict": "declined", "why": "w", "false_claims": [{"claim": "The 1962 winner was The Tree of Man", "why": "w"}]}, 0.5),
                        ({"verdict": "made_something_up", "why": "w", "false_claims": []}, 0.0)]:
            nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None, v=v: v
            s, why, detail, err = nasute.judge(made_up, {"judge": {"mode": "knowledge"}})
            assert err is None and s["abstention"] == want and detail["mode"] == "knowledge", (v, s)
        nasute.ask_json = lambda *a, **k: {"verdicts": []}   # a judge that miscounts is an error, not a guess
        # the judge's usage: added up per answer; cost stays None when the server never reports one
        nasute.judge_use_reset()
        nasute.judge_use_add({"total_tokens": 120, "cost": 0.0001})
        nasute.judge_use_add({"total_tokens": 30})
        nasute.judge_use_add(None)
        assert nasute.JUDGE_USE.tokens == 150 and close(nasute.JUDGE_USE.cost, 0.0001)
        nasute.judge_use_reset()
        nasute.judge_use_add({"total_tokens": 10})
        assert nasute.JUDGE_USE.tokens == 10 and nasute.JUDGE_USE.cost is None
        nasute.judge_use_reset()
        nasute.judge_use_add({"total_tokens": "lots", "cost": "x"})   # odd values: ignored, no failure
        nasute.judge_use_add({})
        assert nasute.JUDGE_USE.tokens is None and nasute.JUDGE_USE.cost is None   # never reported: not known, not 0
        # a run's totals: None when nothing reported a figure, so "not known" never shows as 0
        u = nasute.usage_totals([{"tokens_in": 10, "tokens_out": 5, "cost": 0.001, "judge_tokens": 100, "judge_cost": None},
                                 {"tokens_in": 30, "tokens_out": 15, "cost": None, "judge_tokens": 50, "judge_cost": None}])
        assert u["tokens_in"] == 40 and u["tokens_out"] == 20 and close(u["cost"], 0.001) and u["judge_tokens"] == 150 and u["judge_cost"] is None
        assert u["per_answer"]["tokens_in"] == 20 and u["per_answer"]["judge_cost"] is None
        assert nasute.usage_totals([])["cost"] is None
        assert nasute.judge({"question": "q", "reference": "r", "answer": "a", "extracts": ["e"]}, {"judge": {"mode": "claims"}})[3] is not None
    finally:
        nasute.ask_json = real
    # an unreachable judge is recorded, not raised
    bad = {"judge": {"url": "http://127.0.0.1:9/v1", "model": "m", "timeout": 2, "mode": "quick"}}
    scores, _, _, err = nasute.judge({"question": "q", "reference": "r", "answer": "a", "extracts": ["e"]}, bad)
    assert err and all(v is None for v in scores.values()), (scores, err)

    # judge-check scoring: correctness bands [.75,1] twice and [0,.25] twice; the judge gave .9, .5, .1, 0.
    # Accuracy 3 / 4. Buckets wanted 1,1,0,0; got 1,.5,0,0. Agreement .75; chance .5 × .25 + .5 × .5 = .375; kappa .375 / .625 = .6
    items = [{"id": str(i), "kind": "k", "expect": {"correctness": b}} for i, b in enumerate([[.75, 1], [.75, 1], [0, .25], [0, .25]])]
    out, wrong = nasute.check_scores(items, [{"correctness": x} for x in (.9, .5, .1, 0)])
    assert out["correctness"]["accuracy"] == 0.75 and abs(out["correctness"]["kappa"] - 0.6) < 1e-4 and [w["id"] for w in wrong] == ["1"], (out, wrong)
    assert nasute.check_scores(items, [None] * 4)[0]["correctness"]["accuracy"] == 0   # a judge that failed is wrong
    assert nasute.kappa([1, 1], [1, 1]) is None


def reason_checks():
    cfg = {**nasute.DEFAULTS}
    hit0 = row("a", correctness=0.0, hit=0.0, faithfulness=0.0)
    assert nasute.why_failed([hit0], cfg) == "retrieval"
    assert nasute.why_failed([row("a", correctness=0.0, hit=1.0, faithfulness=0.2)], cfg) == "generation"
    assert nasute.why_failed([row("a", correctness=0.0, hit=1.0, faithfulness=1.0)], cfg) == "judge?"
    assert nasute.why_failed([row("a", correctness=0.4, hit=1.0, faithfulness=0.5, detail={"precision": 1.0})], cfg) == "judge?"
    assert nasute.why_failed([row("a", correctness=0.9, hit=0.0)], cfg) is None
    assert nasute.why_failed([row("a", error="timeout")], cfg) == "system"
    c = nasute.causes([hit0, row("b", error="x"), {**row("c", correctness=1.0, hit=1.0), "sources": ["Fees"]}], cfg)
    assert c["counts"] == {"retrieval": 1, "generation": 0, "judge?": 0, "system": 1} and [q["id"] for q in c["questions"]] == ["a", "b"], c
    # a chat model that cites nothing: hit rate is not measured, so a wrong answer is never put down to retrieval
    c = nasute.causes([hit0, row("c", correctness=1.0, hit=0.0)], cfg)
    assert c["counts"]["retrieval"] == 0 and c["counts"]["generation"] == 1, c
    # the retrieval sentences name the standard terms
    s = nasute.retrieval_scores(["Iron"], ["Gold", "Iron"], 5)
    r = nasute.retrieval_reasons(["Iron"], ["Gold", "Iron"], 5, s)
    assert "2nd (1 / 2)" in r["mrr"] and r["hit"].startswith("Hit 1") and "1 / 1" in r["recall"], r


def judge_prompt_checks():
    """[judge.prompts]: a custom prompt is used, checked at load time, fingerprinted, flagged by compare; prompts export."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        conf = tmp / "n.toml"
        conf.write_text('runs = "runs"\nreport = "report"\n[judge.prompts]\nabstain = "p/abstain.txt"\n')
        (tmp / "p").mkdir()
        bad = lambda text: ((tmp / "p" / "abstain.txt").write_text(text), cli(conf, "report"))[1]
        for text, want in [("Q {question} {answer} {reference}", "has unknown {reference}"), ("Q {question} only", "is missing {answer}"),
                           ('Reply like {"verdict": "declined"}. {question} {answer}', "{{"), ("Stray } {question} {answer}", "{{")]:
            code, out = bad(text)
            assert code != 0 and want in out and "abstain.txt" in out, (text, out)
        (tmp / "p" / "abstain.txt").write_bytes(b"\xff\xfe {question} {answer}")
        assert "not UTF-8" in cli(conf, "report")[1]
        other = tmp / "other.toml"
        other.write_text('[judge.prompts]\nquick = "gone.txt"\n')
        assert "cannot read" in cli(other, "report")[1] and "gone.txt" in cli(other, "report")[1]
        other.write_text('[judge.prompts]\nquik = "p/abstain.txt"\n')
        assert "no prompt called 'quik'" in cli(other, "report")[1]
        # literal braces work, and the custom text is what the judge is sent
        (tmp / "p" / "abstain.txt").write_text('Reply like {{"verdict": "declined"}}.\nQ: {question}\nA: {answer}\n')
        cfg = nasute.load_settings(conf)
        sent = []
        real = nasute.ask_json
        try:
            nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: sent.append(prompt) or {"verdict": "declined", "why": "w"}
            nasute.judge({"question": "q?", "reference": "", "answer": "no idea", "extracts": [], "answerable": False}, cfg)
        finally:
            nasute.ask_json = real
        assert sent == ['Reply like {"verdict": "declined"}.\nQ: q?\nA: no idea'], sent
        # the fingerprint: custom differs from built-in, and the text is never saved
        mine, built = nasute.prompt_record(cfg), nasute.prompt_record(nasute.DEFAULTS)
        assert mine["custom"] == ["abstain"] and built["custom"] == [] and mine["sha256"]["abstain"] != built["sha256"]["abstain"] and mine["sha256"]["quick"] == built["sha256"]["quick"]
        assert nasute.prompts_differ(mine, built) == ["abstain"] and nasute.prompts_differ(built, None) == [] and nasute.prompts_differ(None, mine) == ["abstain"]
        d = {"name": "x", "version": 1, "sha256": "aaa"}
        fake_run(cfg, "20260101T000000Z", d, {"q1": {"hit": 1, "correctness": 1.0}, "q2": {"hit": 1, "correctness": 0.5}})
        rows = json.loads((Path(cfg["runs"]) / "20260101T000000Z" / "summary.json").read_text())
        assert rows["judge_prompts"]["custom"] == [] and "prompt_texts" not in rows["settings"]
        s = nasute.summarise([], d, cfg, {"run": "r"})
        assert s["judge_prompts"] == mine and "prompt_texts" not in s["settings"] and "declined" not in json.dumps(s), s["judge_prompts"]
        (Path(cfg["runs"]) / "20260102T000000Z").mkdir()
        old = Path(cfg["runs"]) / "20260101T000000Z"
        (Path(cfg["runs"]) / "20260102T000000Z" / "results.jsonl").write_text((old / "results.jsonl").read_text())
        (Path(cfg["runs"]) / "20260102T000000Z" / "summary.json").write_text(json.dumps({**json.loads((old / "summary.json").read_text()), "run": "20260102T000000Z", "judge_prompts": mine}))
        c = nasute.compare(cfg, "20260101T000000Z", "20260102T000000Z")
        assert any("Different judge prompts (abstain)" in n for n in c["notes"]) and c["metrics"]["correctness"]["verdict"] == "not comparable" and c["metrics"]["hit"]["verdict"] != "not comparable", c
        nasute.report(cfg)
        page = (Path(cfg["report"]) / "x@" / "runs" / "20260102T000000Z.html").read_text()
        assert "Different judge prompts" in page and '"custom": ["abstain"]' in page
        # a judge-check counts only for the prompts it was run with
        jc = Path(cfg["runs"]) / "judge-20260101T000000Z"
        jc.mkdir()
        (jc / "summary.json").write_text(json.dumps({"run": jc.name, "judge_model": "m", "judge_mode": "quick", "judge_prompts": built, "items": 1, "metrics": {}}))
        assert nasute.latest_judge_check(cfg, "m", "quick", built) and nasute.latest_judge_check(cfg, "m", "quick") and not nasute.latest_judge_check(cfg, "m", "quick", mine)
        # export: all six, unedited files load as the built-in text, and it never overwrites
        code, out = cli(tmp / "none.toml", "prompts", "export", str(tmp / "out"))
        assert code == 0 and sorted(f.stem for f in (tmp / "out").iterdir()) == sorted(nasute.PROMPTS), out
        assert nasute.load_prompts({n: str(tmp / "out" / f"{n}.txt") for n in nasute.PROMPTS}) == nasute.PROMPTS
        (tmp / "out" / "check.txt").write_text("mine")
        code, out = cli(tmp / "none.toml", "prompts", "export", str(tmp / "out"))
        assert code == 1 and "already exist" in out and (tmp / "out" / "check.txt").read_text() == "mine"


def release_020_checks():
    """0.2.0 fixes: two runs in one second, a target reply that tries to change the question, judge set types."""
    import datetime as dt
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report")}
        real = nasute.datetime
        class Frozen(dt.datetime):   # every call is in the same second
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(2026, 1, 1, tzinfo=tz)
        try:
            nasute.datetime = Frozen
            ids = [nasute.new_run_folder(cfg)[0] for _ in range(3)] + [nasute.new_run_folder(cfg, "judge-")[0]]
        finally:
            nasute.datetime = real
        assert ids == ["20260101T000000Z", "20260101T000000Z-2", "20260101T000000Z-3", "judge-20260101T000000Z"], ids
        d = {"name": "x", "version": 1, "sha256": "aaa"}
        for i, x in zip(ids[:3], (0.2, 0.5, 0.9)):
            (Path(cfg["runs"]) / i).rmdir()
            fake_run(cfg, i, d, {"q1": {"correctness": x}, "q2": {"correctness": x}})
        assert nasute.run_ids(cfg) == ids[:3] and nasute.compare(cfg)["a"] == ids[1]
        assert manage.resolve(cfg, ids[0])[0] == ids[0] and manage.resolve(cfg, "20260101T000000Z-3")[0] == ids[2]
        nasute.report(cfg)
        assert all((tmp / "report" / "x@" / "runs" / f"{i}.html").exists() for i in ids[:3])
        assert "Z(-\\d+)?$" in (PKG / "assets" / "report.js").read_text()   # dates on the page read the suffixed ids too
        # a "module:function" target can add only reply fields, never change the question it is judged against
        nasute.TARGETS["sly"] = lambda q, t, timeout: {"answer": "yes", "error": None, "reference": "yes", "id": "other", "answerable": False, "expected": [], "sources": ["A"], "tokens_in": 3}
        got = nasute.ask_target({**cfg, "pause": 0, "max_temp": 0}, "sly", "q?", {})
        assert got == {"answer": "yes", "error": None, "sources": ["A"], "tokens_in": 3}, got
        real_judge = nasute.judge
        try:
            nasute.judge = lambda item, cfg: (item.update(seen=dict(item)) or {}, {}, None, None)
            q = {"id": "q1", "question": "q?", "reference": "no", "sources": ["B"], "tags": [], "answerable": True}
            r = nasute.attempts({**cfg, "pause": 0, "max_temp": 0}, "sly", q, {})[0]
        finally:
            nasute.judge = real_judge
            del nasute.TARGETS["sly"]
        assert (r["id"], r["reference"], r["answerable"], r["expected"]) == ("q1", "no", True, ["B"]), r
        # a judge set's fields are type-checked, and judge-check stops before judging a bad one
        jd = tmp / "datasets" / "jj"
        jd.mkdir(parents=True)
        good = {"id": "a", "kind": "right", "question": "q", "reference": "r", "extracts": ["e"], "answer": "r", "expect": {"correctness": [0.75, 1]}}
        (jd / "v1.jsonl").write_text("".join(json.dumps(x) + "\n" for x in [{"dataset": "jj", "target": "judge"}, good,
                                     {**good, "id": "b", "answer": 5, "extracts": "e", "expect": {"correctness": [1, 0.5], "speed": [0, 1]}}, {**good, "id": "c", "expect": [0, 1]}]))
        bad = [what for _, what in manage.problems(jd / "v1.jsonl")]
        assert bad == ["'answer' must be text", "'extracts' must be a list of text", "'expect' has no score called 'speed'", "'expect' correctness: must be [low, high], two numbers from 0 to 1, low first", "'expect' must be a table of scores, such as {\"correctness\": [0.75, 1]}"], bad
        conf = tmp / "n.toml"
        conf.write_text('judge_set = "jj"\n[judge]\nurl = "http://127.0.0.1:9/v1"\n')
        code, out = cli(conf, "judge-check")
        assert code != 0 and "line 3" in out, out
        assert not any(p.name.startswith("judge-") and p.name != "judge-20260101T000000Z" for p in (tmp / "runs").iterdir())


def features_020_checks():
    """0.2.0 features: the spending cap, concurrency (questions and judge), several targets in one run, the chat target."""
    import logging
    import os
    import threading
    real = {k: getattr(nasute, k) for k in ("ask_json", "post", "BACKOFF")}
    real_target = nasute.TARGETS.get("fake")
    events, ranked = [], []
    class Catch(logging.Handler):
        def emit(self, record):
            events.append(record.getMessage())
            if record.getMessage() == "targets_done":
                ranked[:] = record.details["ranked"]
    catch = Catch()
    logging.getLogger().addHandler(catch)

    def judge_says(cfg, prompt, schema, max_tokens=500, verify=None):
        nasute.judge_use_add({"total_tokens": 10, "cost": 0.001})   # as ask_json does with a reply's usage
        return {"claims": [{"claim": "c", "supported": "yes", "vs_reference": "agrees", "why": ""}], "relevancy": "yes", "relevancy_why": ""}

    def make_cfg(tmp, name, **over):
        return nasute.merge(nasute.DEFAULTS, {"runs": str(tmp / name / "runs"), "report": str(tmp / name / "report"), "profile": "", "limit": 6,
                                              "judge": {"model": "m"}, "targets": {"demo": {"kind": "fake"}}, **over})

    def run_with(target, cfg):
        nasute.TARGETS["fake"] = target
        nasute.run(cfg, "demo", 1, cfg["limit"])
        d = Path(cfg["runs"]) / nasute.run_ids(cfg)[-1]
        return json.loads((d / "summary.json").read_text()), [json.loads(x) for x in (d / "results.jsonl").read_text().splitlines()]

    def paid(q, t, timeout, wait=0.0):
        time.sleep(wait)
        return {"answer": "an answer", "sources": [], "extracts": [], "first_text_s": 0.1, "total_s": 0.1, "error": None, "cost": 0.01}

    nasute.ask_json, nasute.BACKOFF = judge_says, (0, 0, 0)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # the cap: 0.011 per attempt, cap 0.025, so the third attempt passes it and nothing new starts
            s, rows = run_with(paid, make_cfg(tmp, "cap", max_cost=0.025))
            assert len(rows) == 3 and "spending cap" in s["aborted"] and close(s["usage"]["cost"], 0.03) and close(s["usage"]["judge_cost"], 0.003), (len(rows), s["aborted"], s["usage"])
            assert "spending_cap_reached" in events and nasute.compare(make_cfg(tmp, "cap")) is None
            page = next((tmp / "cap" / "report").rglob("runs/*.html")).read_text()
            assert "spending cap was reached" in page
            # cost not reported: one warning, and the cap cannot stop the run
            events.clear()
            s, rows = run_with(lambda q, t, to: {**paid(q, t, to), "cost": None}, make_cfg(tmp, "nocost", max_cost=0.01, limit=3))   # only the judge's 0.003 counts
            assert len(rows) == 3 and not s["aborted"] and events.count("cost_unknown") == 1, (events, s["aborted"])
            # no cap set: no warning
            events.clear()
            run_with(lambda q, t, to: {**paid(q, t, to), "cost": None}, make_cfg(tmp, "nocap", limit=2))
            assert "cost_unknown" not in events
            # concurrency: the same rows, seeds and totals as one at a time, in dataset order, and faster
            got, took = {}, {}
            for n in (1, 4):
                t = time.monotonic()
                s, rows = run_with(lambda q, tc, to: paid(q, tc, to, 0.1), make_cfg(tmp, f"c{n}", limit=8, repeats=2, concurrency=n))
                took[n] = time.monotonic() - t
                got[n] = ([(r["id"], r["repeat"], r["seed"], r["scores"]) for r in rows], s["usage"]["judge_tokens"], s["usage"]["cost"], s["metrics"]["correctness"]["mean"])
            assert got[1] == got[4] and got[1][1] == 160, got[1][1:]
            assert took[4] < took[1] * 0.6, took
            # a target's own concurrency wins over the top-level one
            t = time.monotonic()
            run_with(lambda q, tc, to: paid(q, tc, to, 0.1), make_cfg(tmp, "own", limit=8, targets={"demo": {"kind": "fake", "concurrency": 8}}))
            assert time.monotonic() - t < took[1] * 0.5
            # the judge's own limit: questions side by side, but one judge request at a time unless [judge] concurrency says more
            nasute.ask_json = real["ask_json"]
            live, peak, lock = [0], [0], threading.Lock()
            marks = json.dumps({"claims": [], "relevancy": "yes", "relevancy_why": ""})
            def judge_post(url, body, timeout, headers=None):
                with lock:
                    live[0] += 1
                    peak[0] = max(peak[0], live[0])
                time.sleep(0.05)
                with lock:
                    live[0] -= 1
                return {"choices": [{"message": {"content": marks}}]}
            nasute.post = judge_post
            for jn, want in ((1, lambda p: p == 1), (4, lambda p: p > 1)):
                peak[0] = 0
                run_with(paid, make_cfg(tmp, f"j{jn}", limit=8, concurrency=4, judge={"model": "m", "concurrency": jn}))
                assert want(peak[0]), (jn, peak[0])
            nasute.ask_json, nasute.post = judge_says, real["post"]

            # several targets in one command: each its own run, ranked; a failing target does not stop the others
            nasute.TARGETS["fake"] = paid
            conf = tmp / "many.toml"
            conf.write_text(f'datasets = ["{(PKG / "datasets").as_posix()}"]\nruns = "runs"\nreport = "report"\n[judge]\nmodel = "m"\n'
                            '[targets.a]\nkind = "fake"\n[targets.b]\nkind = "fake"\n[targets.broken]\nkind = "no_such_module_here:ask"\n'
                            '[profiles.both]\nrun_targets = ["a", "b"]\n')
            code, out = cli(conf, "--log", "text", "run", "--dataset", "demo", "--limit", "5", "--target", "a", "--target", "broken", "--target", "b")
            nasute.setup_logging("json")
            assert code == 1 and "2 target(s) ranked by Answer correctness" in out and "1. a  1.00" in out and "broken  failed: ModuleNotFoundError" in out and "5 shared questions" in out, out
            runs = nasute.summaries(nasute.load_settings(conf))
            assert sorted(s["target"] for s in runs.values()) == ["a", "b"]
            code, out = cli(conf, "--log", "text", "run", "--dataset", "demo", "--limit", "5", "--profile", "both", "--max-cost", "0.025")
            nasute.setup_logging("json")
            assert code == 0 and "2 target(s) ranked" in out and len(re.findall(r"^  \d\. [ab] .*PARTIAL, STOPPED EARLY: the spending cap", out, re.M)) == 2, out   # each target has its own cap
            # every target unreachable: each run stops early and counts as failed, so the command fails
            nasute.TARGETS["fake"] = lambda q, t, to: {"answer": "", "sources": [], "extracts": [], "first_text_s": None, "total_s": 0, "error": "URLError: refused", "unreachable": True}
            code, out = cli(conf, "--log", "text", "run", "--dataset", "demo", "--limit", "5", "--target", "a", "--target", "b")
            nasute.setup_logging("json")
            assert code == 1 and "0 target(s) ranked" in out and out.count("failed: stopped early: the system under test or the judge could not be reached") == 2, out
            # the JSON summary ranks by score too, not in command order
            nasute.TARGETS.update({"low": lambda q, t, to: paid(q, t, to), "high": lambda q, t, to: paid(q, t, to), "mid": lambda q, t, to: paid(q, t, to)})
            conf.write_text(conf.read_text() + '[targets.c2]\nkind = "low"\n[targets.c9]\nkind = "high"\n[targets.c5]\nkind = "mid"\n')
            score = {}
            def judge_by(cfg, prompt, schema, max_tokens=500, verify=None):   # correctness = share of claims that agree: 0.2, 0.9 or 0.5 per target
                agree = score["now"]
                return {"claims": [{"claim": str(i), "supported": "yes", "vs_reference": "agrees" if i < agree else "contradicts", "why": ""} for i in range(10)], "relevancy": "yes", "relevancy_why": ""}
            nasute.ask_json = judge_by
            real_run = nasute.run
            def run_scored(cfg, name, version, limit, target=None, label=""):
                score["now"] = {"c2": 2, "c9": 9, "c5": 5}[target]
                return real_run(cfg, name, version, limit, target, label)
            nasute.run = run_scored
            events.clear()
            try:
                code, out = cli(conf, "--log", "json", "run", "--dataset", "demo", "--limit", "5", "--target", "c2", "--target", "c9", "--target", "c5")
            finally:
                nasute.run = real_run
            assert code == 0 and ranked == ["c9", "c5", "c2"], (code, ranked)
    finally:
        nasute.ask_json, nasute.post, nasute.BACKOFF = real["ask_json"], real["post"], real["BACKOFF"]
        nasute.TARGETS["fake"] = real_target
        for k in ("low", "high", "mid"):
            nasute.TARGETS.pop(k, None)
        logging.getLogger().removeHandler(catch)
        nasute.setup_logging("json")

    # the chat target: question as the user message, system prompt, temperature and seed, model; usage read, bad usage dropped
    from nasute.targets import chat
    ep = FakeEndpoint()
    try:
        os.environ["NASUTE_TEST_KEY"] = "Bearer k"
        got = chat.ask("Capital of France?", {"url": ep.url + "/v1/", "model": "m1", "system": "Be brief.", "temperature": 0.3, "seed": 2,
                                               "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}, 5)
        sent = ep.seen[-1]
        assert got["answer"] == "Paris." and got["error"] is None and (got["tokens_in"], got["tokens_out"], got["cost"]) == (5, 2, 0.0003) and got["sources"] == [], got
        assert sent["path"] == "/v1/chat/completions" and sent["headers"]["Authorization"] == "Bearer k" and sent["body"] == {
            "model": "m1", "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Capital of France?"}], "temperature": 0.3, "seed": 2}, sent
        bad = chat.ask("q", {"url": ep.url + "/bad/v1", "model": "m"}, 5)
        assert bad["tokens_in"] is None and bad["cost"] is None and bad["tokens_out"] == 2 and ep.seen[-1]["body"]["messages"] == [{"role": "user", "content": "q"}], bad
        assert chat.ask("q", {"url": "http://127.0.0.1:9/v1", "model": "m"}, 5)["unreachable"]
        del os.environ["NASUTE_TEST_KEY"]
        missing = chat.ask("q", {"url": ep.url + "/v1", "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}, 5)
        assert "NASUTE_TEST_KEY is not set" in missing["error"], missing
        assert nasute.TARGETS["chat"] is chat.ask
    finally:
        ep.close()
    # the 0.1.0 name of concurrency still works
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "old.toml"
        f.write_text("workers = 3\n")
        cfg = nasute.load_settings(f)
        assert cfg["concurrency"] == 3 and "workers" not in cfg


def settings_checks():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "e.toml"
        f.write_text('limit = 9\n[judge]\nurl = "http://x/v1"\n[profiles.smoke]\nlimit = 3\n[profiles.smoke.judge]\nmode = "claims"\n')
        base, smoke = nasute.load_settings(f), nasute.load_settings(f, "smoke")
        assert base["limit"] == 9 and base["judge"]["mode"] == "quick" and base["profile"] == ""
        assert smoke["limit"] == 3 and smoke["judge"] == {**base["judge"], "mode": "claims"} and smoke["profile"] == "smoke" and smoke["repeats"] == 1
        try:
            nasute.load_settings(f, "nope")
            raise RuntimeError("an unknown profile should stop the run")
        except AssertionError:
            pass
    example = tomllib.loads((ROOT / "nasute.example.toml").read_text())
    smoke, deep = example["profiles"]["smoke"], example["profiles"]["deep"]
    assert smoke["limit"] == 3 and smoke["repeats"] == 1 and smoke["judge"]["mode"] == "quick" and not smoke.get("judge_check")
    assert deep["repeats"] == 3 and deep["judge"]["mode"] == "claims" and deep["judge_check"] and deep.get("limit", 0) == 0
    # the glossary: every entry has the same three parts (docs/reference/scores.md and judge-prompts.md are checked in docs_checks)
    assert {"hit", "correctness", "se", "ci", "paired", "pass_all"} <= nasute.GLOSSARY.keys() and all(set(g) == {"term", "plain", "formula"} for g in nasute.GLOSSARY.values())
    assert nasute.label("recall", 5) == "Recall@5" and nasute.label("recall") == "Recall@k" and nasute.label("faithfulness", 5) == "Faithfulness"
    code = (PKG / "assets" / "report.js").read_text() + (PKG / "pages.py").read_text()   # one source for names and definitions: the glossary
    assert not [g["term"] for g in nasute.GLOSSARY.values() if g["term"] in code and "@k" not in g["term"]], "a score name is hard-coded outside the glossary"


def review_checks():
    """Findings from a review: each one reproduced here with fake data."""
    import http.server
    import threading
    import time
    real = {k: getattr(nasute, k) for k in ("post", "ask_json", "BACKOFF", "RETRY_WAIT")}
    real_target, real_sleep = nasute.TARGETS.get("fake"), time.sleep
    cfg = {"judge": {"url": "http://x/v1", "model": "m", "timeout": 5, "cache": True, "retries": 1, "mode": "quick"}, "pause": 0}

    # 1 and 4: an invalid reply (bad enum, missing key, wrong count) is retried inside the call, then a judge error, never a 0
    try:
        nasute.time.sleep = lambda s: None
        replies = []
        nasute.post = lambda url, body, timeout, headers=None: {"choices": [{"message": {"content": json.dumps(replies.pop(0))}}]}
        bad = {"verdicts": [{"supported": "INVALID", "why": "x"}]}
        good = {"verdicts": [{"supported": "yes", "why": "x"}]}
        replies[:] = [bad, good]
        assert nasute.check(cfg, ["c"], "source") == ([True], ["x"]) and not replies   # retried, then fine
        replies[:] = [bad, bad]
        try:
            nasute.check(cfg, ["c"], "source")
            raise RuntimeError("an invalid reply must not pass")
        except ValueError as e:
            assert "INVALID" in str(e)
        replies[:] = [{"verdicts": [good["verdicts"][0]] * 2}, good]   # two verdicts for one claim: retried, not an assertion
        assert nasute.check(cfg, ["c"], "source")[0] == [True]
        replies[:] = [{"nothing": 1}, {"nothing": 1}]
        for schema in (nasute.CHECK_SCHEMA,):
            try:
                nasute.ask_json(cfg, "p", schema)
                raise RuntimeError("missing key must not pass")
            except ValueError as e:
                assert "missing" in str(e)
        replies[:] = [{"verdict": "maybe", "why": "x"}] * 2   # the whole judge: excluded (None), not scored 0
        scores, _, _, err = nasute.judge({"question": "q", "reference": "", "answer": "a", "extracts": [], "answerable": False}, cfg)
        assert err and all(v is None for v in scores.values()), (scores, err)
        for value, schema in (({"x": 1}, {"type": "array", "items": {"type": "string"}}), ([1], {"type": "array", "items": {"type": "string"}}), ("x", {"type": "object"})):
            try:
                nasute.validate(value, schema)
                raise RuntimeError("should be invalid")
            except ValueError:
                pass
    finally:
        nasute.time.sleep = real_sleep
        nasute.post = real["post"]

    # 2: claims are checked against the reference and the answer together with the question
    prompts = []
    replies = iter([{"answer_claims": ["a1"], "reference_claims": ["r1"], "relevancy": "yes", "relevancy_why": ""}] + [{"verdicts": [{"supported": "yes", "why": ""}]}] * 4)
    try:
        nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: prompts.append(prompt) or next(replies)
        nasute.judge({"question": "What is the capital?", "reference": "Canberra", "answer": "It is Canberra.", "extracts": ["e"]}, {"judge": {"mode": "claims"}})
    finally:
        nasute.ask_json = real["ask_json"]
    assert "QUESTION: What is the capital?\nREFERENCE ANSWER: Canberra" in prompts[2] and "QUESTION: What is the capital?\nANSWER: It is Canberra." in prompts[4], prompts

    # 3: compare notes a different judge, answering model or target, and gives no verdict on judged scores (retrieval scores still get one)
    with tempfile.TemporaryDirectory() as tmp:
        c = {**nasute.DEFAULTS, "runs": str(Path(tmp) / "runs"), "report": str(Path(tmp) / "report")}
        d = {"name": "x", "version": 1, "sha256": "a"}
        many = {f"q{i}": {"hit": 1.0, "correctness": 1.0 if i % 2 else 0.5} for i in range(6)}
        fake_run(c, "20260101T000000Z", d, many, judge_model="judge-a", answering_model="m1", target="demo")
        fake_run(c, "20260102T000000Z", d, {k: {"hit": 1.0, "correctness": 1.0} for k in many}, judge_model="judge-b", answering_model="m2", target="demo")
        r = nasute.compare(c)
        assert r["metrics"]["correctness"]["verdict"] == "not comparable" and r["metrics"]["hit"]["verdict"] != "not comparable", r["metrics"]["correctness"]
        assert any("judge models" in n for n in r["notes"]) and any("answering models" in n for n in r["notes"]) and not any("targets" in n for n in r["notes"]), r["notes"]
        assert not [w for w in r["better"] + r["worse"] if w["metric"] == "correctness"]

    # 5: a question with a missing repeat is left out of pass^k, not counted as a pass
    rows = [row("x", correctness=0.9), row("x", correctness=0.9), row("y", correctness=1.0), row("y", correctness=None)]
    c = nasute.consistency(rows, nasute.DEFAULTS)
    assert c["questions"] == 1 and c["left_out"] == 1 and close(c["pass_all"], 1.0), c

    # 6: power uses the repeats each question really has: variances 1/3 over 3 repeats and 0 over 2
    p = nasute.power([[1, 0, 1], [0, 0]], {"repeats": 99, "detect": 0.05})
    assert p["needed"] == nasute.needed_questions((2 / 3 / 3 + 0) / 2, 0.05), p

    # 16 and 17: system errors count as failed attempts for measured difficulty; one yes/no observation still gets a Wilson interval
    failed = [[{"id": "e", "difficulty": "easy", "error": "timeout", "scores": {"correctness": 0.0}} for _ in range(5)]]
    assert [m["id"] for m in nasute.mislabels({**nasute.DEFAULTS}, failed)] == ["e"]
    assert nasute.stats([[1.0]], binary=True)["ci"] == [round(x, 4) for x in nasute.wilson(1.0, 1)] and nasute.stats([[1.0]])["ci"] == nasute.stats([[1.0]], binary=True)["ci"]

    # 7, 8, 9, 10, 11, 12 with fake targets and judges
    def judge_says(cfg, prompt, schema, max_tokens=500, verify=None):
        return {"claims": [{"claim": "c", "supported": "yes", "vs_reference": "agrees", "why": ""}], "relevancy": "yes", "relevancy_why": ""}

    def make_cfg(tmp, name, **over):
        return nasute.merge(nasute.DEFAULTS, {"runs": str(tmp / name / "runs"), "report": str(tmp / name / "report"), "profile": "", "limit": 6, "judge": {"model": "m"}, "targets": {"demo": {"kind": "fake"}}, "judge_set": "judge-demo", **over})

    def good(q, tcfg, timeout):
        return {"answer": "an answer", "sources": ["Iron"], "extracts": ["e"], "first_text_s": 1.0, "total_s": 1.0, "error": None}

    def go(target, cfg):
        nasute.TARGETS["fake"], nasute.ask_json = target, judge_says
        try:
            nasute.run(cfg, "demo", 1, cfg["limit"])
        finally:
            nasute.TARGETS["fake"], nasute.ask_json = real_target, real["ask_json"]
        d = Path(cfg["runs"]) / nasute.run_ids(cfg)[-1]
        return json.loads((d / "summary.json").read_text()), [json.loads(x) for x in (d / "results.jsonl").read_text().splitlines()], d

    nasute.BACKOFF = (0, 0, 0)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # 7: a source that could not be fetched leaves faithfulness unmeasured; it is not a system error and not a 0
            s, rows, _ = go(lambda q, t, to: {**good(q, t, to), "extracts_failed": True}, make_cfg(tmp, "nofetch", limit=1))
            assert rows[0]["scores"]["faithfulness"] is None and rows[0]["scores"]["correctness"] == 1.0 and rows[0]["error"] is None and "Not measured" in rows[0]["reasons"]["faithfulness"], rows[0]["scores"]
            assert s["counts"]["system_errors"] == 0 and s["counts"]["judge_errors"] == 0
            # 10: unreachable on one repeat only does not count; every repeat unreachable does
            def one_repeat_down(q, t, to):
                return {**good(q, t, to), "answer": "", "error": "URLError: refused", "unreachable": True} if t["seed"] == 1 else good(q, t, to)
            s, rows, _ = go(one_repeat_down, make_cfg(tmp, "half", limit=5, repeats=2))
            assert s["aborted"] is None and len(rows) == 10, (s["aborted"], len(rows))
            # 9: a crash on the third question leaves the finished attempts in the partial file
            n = []
            def crash(q, t, to):
                n.append(1)
                if len(n) == 3:
                    raise RuntimeError("boom")
                return good(q, t, to)
            cfg = make_cfg(tmp, "crash", limit=5)
            try:
                go(crash, cfg)
                raise AssertionError("the crash should have stopped the run")
            except RuntimeError:
                part = next((Path(cfg["runs"])).glob("*/results.partial.jsonl"))
                assert [json.loads(x)["id"] for x in part.read_text().splitlines()][:2] == ["opening-time", "full-plot-fee"]
            # 11: on abort nothing new starts, and what finished is kept in dataset order with the summary agreeing
            def down(q, t, to):
                real_sleep(0.05)
                return {**good(q, t, to), "answer": "", "error": "URLError: refused", "unreachable": True}
            s, rows, d = go(down, make_cfg(tmp, "abort", limit=8, concurrency=2))
            assert s["aborted"] and 3 <= len(rows) < 8 and s["attempts"] == len(rows) and not (d / "results.partial.jsonl").exists(), (len(rows), s["attempts"])
            assert [r["id"] for r in rows] == [q["id"] for q in nasute.load_dataset(*nasute.find_dataset(nasute.DEFAULTS, "demo", 1)[:1], 1)[1][:len(rows)]]
            # 12: judge-check stops when the judge is unreachable, and a run that begins with one does not start
            def judge_down(cfg, prompt, schema, max_tokens=500, verify=None):
                raise nasute.Unreachable("refused")
            cfg = make_cfg(tmp, "jc", judge_check=True)
            nasute.ask_json = judge_down
            rebuilt, real_report = [], nasute.report
            nasute.report = lambda c: rebuilt.append(1)
            try:
                s = nasute.judge_check(cfg)
                assert s["aborted"] and s["failed"] == 3 and s["items"] == 3 and s["set_size"] > 3, s
                assert not rebuilt   # a stopped check does not rebuild the report
                assert nasute.latest_judge_check(cfg, "m", "quick")["aborted"]   # nothing better exists: attached, and marked
                real_sleep(1.1)   # run folders are named by the second
                nasute.ask_json = lambda *a, **k: {"claims": [], "relevancy": "yes", "relevancy_why": ""}
                assert not nasute.judge_check(cfg, limit=1)["aborted"] and rebuilt == [1]   # a finished check rebuilds the report, as a run does
                nasute.ask_json = judge_down
                real_sleep(1.1)
                try:
                    nasute.run(cfg, "demo", 1, 2)
                    raise AssertionError("the run should not start")
                except SystemExit as e:
                    assert "not started" in str(e)
                assert nasute.run_ids(cfg) == []
            finally:
                nasute.ask_json, nasute.report = real["ask_json"], real_report
    finally:
        nasute.BACKOFF = real["BACKOFF"]

    # A: a running question stops after its current repeat once the run is aborted
    stop = threading.Event()
    seen_calls = []
    def stopper(q, tcfg, timeout):
        seen_calls.append(1)
        stop.set()
        return {"answer": "a", "sources": [], "extracts": [], "first_text_s": 1.0, "total_s": 1.0, "error": None}
    try:
        nasute.TARGETS["fake"], nasute.ask_json = stopper, lambda *a, **k: {"claims": [], "relevancy": "yes", "relevancy_why": ""}
        got = nasute.attempts(nasute.merge(nasute.DEFAULTS, {"repeats": 3, "judge": {"model": "m"}}), "fake", {"id": "q", "question": "q", "reference": "r", "sources": [], "tags": []}, {}, lambda row: None, stop)
    finally:
        nasute.TARGETS["fake"], nasute.ask_json = real_target, real["ask_json"]
    assert len(got) == 1 and len(seen_calls) == 1, (len(got), seen_calls)

    # B: a judge-check record says how many items were judged; a complete check is preferred over a newer stopped one
    with tempfile.TemporaryDirectory() as tmp:
        c = {**nasute.DEFAULTS, "runs": tmp}
        def check_dir(name, **over):
            (Path(tmp) / name).mkdir()
            (Path(tmp) / name / "summary.json").write_text(json.dumps({"run": name, "judge_model": "m", "judge_mode": "quick", "items": 47, "set_size": 47, "aborted": None, "metrics": {}, **over}))
        assert nasute.latest_judge_check(c, "m", "quick") is None
        check_dir("judge-20260101T000000Z")
        check_dir("judge-20260102T000000Z", items=3, aborted="unreachable")
        assert nasute.latest_judge_check(c, "m", "quick")["run"] == "judge-20260101T000000Z"
        (Path(tmp) / "judge-20260101T000000Z" / "summary.json").unlink()
        r = nasute.latest_judge_check(c, "m", "quick")
        assert r["aborted"] and r["items"] == 3 and r["set_size"] == 47, r


def robustness_checks():
    import time
    import urllib.error
    real = {k: getattr(nasute, k) for k in ("post", "cpu_temp", "ask_json", "BACKOFF", "RETRY_WAIT")}
    real_target = nasute.TARGETS.get("fake")
    slept, real_sleep = [], time.sleep
    try:
        nasute.time.sleep = slept.append
        # pause comes from settings, after every call; max_temp waits while the CPU is too hot
        nasute.rest({"pause": 3})
        assert slept == [3], slept
        temps = iter([90, 85, 70])
        nasute.cpu_temp = lambda: next(temps)
        slept.clear()
        nasute.rest({"pause": 0, "max_temp": 80})
        assert slept == [0, 10, 10], slept

        # a judge call stands alone (one message), carries the seed and temperature, and switches the prompt cache off unless asked
        sent = []
        nasute.post = lambda url, body, timeout, headers=None: sent.append(body) or {"choices": [{"message": {"content": '{"verdict": "declined", "why": "x"}'}}]}
        cfg = {"judge": {"url": "http://x/v1", "model": "m", "timeout": 5, "cache": False, "retries": 0}, "temperature": 0.7, "seed": 2, "pause": 4}
        slept.clear()
        assert nasute.ask_json(cfg, "hello", nasute.ABSTAIN_SCHEMA)["verdict"] == "declined"
        b = sent[0]
        assert b["cache_prompt"] is False and b["seed"] == 2 and b["temperature"] == 0.7 and [m["role"] for m in b["messages"]] == ["user"] and slept == [4], (b, slept)
        nasute.ask_json({**cfg, "judge": {**cfg["judge"], "cache": True}}, "hello", nasute.ABSTAIN_SCHEMA)
        assert "cache_prompt" not in sent[1]

        # retries: two failures then a success; failures past the limit; a connection that cannot be made
        calls = []
        def flaky(n):
            def call():
                calls.append(1)
                if len(calls) <= n:
                    raise ValueError("unreadable")
                return "ok"
            return call
        slept.clear()
        assert nasute.resilient(flaky(2), 2) == "ok" and slept == [nasute.RETRY_WAIT] * 2
        calls.clear()
        try:
            nasute.resilient(flaky(5), 2)
            raise RuntimeError("should have given up")
        except ValueError:
            assert len(calls) == 3
        slept.clear()
        def refused():
            raise urllib.error.URLError(ConnectionRefusedError())
        try:
            nasute.resilient(refused, 2)
            raise RuntimeError("should have given up")
        except nasute.Unreachable:
            assert slept == [5, 15, 45], slept
        slept.clear()
        def timed_out():
            raise urllib.error.URLError(TimeoutError())   # slow, not unreachable: an ordinary retry
        try:
            nasute.resilient(timed_out, 1)
        except urllib.error.URLError:
            assert slept == [nasute.RETRY_WAIT], slept
        # a judge that fails for good is recorded and the answer is left out (None), never scored 0
        nasute.ask_json = lambda *a, **k: (_ for _ in ()).throw(ValueError("garbage"))
        scores, _, _, err = nasute.judge({"question": "q", "reference": "r", "answer": "a", "extracts": ["e"]}, {"judge": {"mode": "quick"}})
        assert err and all(v is None for v in scores.values()), (scores, err)
    finally:
        nasute.time.sleep = real_sleep
        for k, v in real.items():
            setattr(nasute, k, v)

    # strict and answered-only: two good answers (correctness 1, .5) and one timeout, which counts 0 when strict
    def full(i, **kw):
        r = row(i, **kw)
        return {**r, "repeat": 1, "tags": ["t"], "difficulty": "easy", "judge_error": kw.get("judge_error"), "first_text_s": 1.0, "error_rate": 0}
    cfg = {**nasute.DEFAULTS, "profile": ""}
    rows = [full("a", correctness=1.0, error_rate=0.0), full("b", correctness=0.5, error_rate=0.0), full("c", correctness=0.0, error_rate=1.0, error="timeout")]
    s = nasute.summarise(rows, {"name": "x", "version": 1, "sha256": "a"}, cfg, {})
    assert close(s["metrics"]["correctness"]["mean"], 0.5) and close(s["metrics_answered"]["correctness"]["mean"], 0.75) and abs(s["metrics"]["error_rate"]["mean"] - 1 / 3) < 1e-4
    assert s["counts_line"] == "3 asked · 2 scored · 1 system error · 0 judge errors" and not s["incomplete"], s["counts_line"]
    # a judge error leaves the attempt out of the judged scores and is not held against the system; over 10% marks the run incomplete
    ok = [full(i, correctness=1.0) for i in "abcdefghi"]
    one = nasute.summarise(ok + [full("j", judge_error="timeout")], {"name": "x", "version": 1, "sha256": "a"}, cfg, {})
    assert one["counts_line"] == "10 asked · 9 scored · 0 system errors · 1 judge error" and close(one["metrics"]["correctness"]["mean"], 1.0) and not one["incomplete"]
    two = nasute.summarise(ok + [full("j", judge_error="t"), full("k", judge_error="t")], {"name": "x", "version": 1, "sha256": "a"}, cfg, {})
    assert two["incomplete"] and abs(two["judge_error_rate"] - 2 / 11) < 1e-3
    # error rate: more errors is a drop, not a gain
    a, b = {f"q{i}": 0.0 for i in range(6)}, {f"q{i}": 1.0 if i < 3 else 0.0 for i in range(6)}
    assert nasute.paired(a, b, 0.05, lower_better=True)["verdict"] == "real drop" and nasute.paired(b, a, 0.05, lower_better=True)["verdict"] == "real gain"

    # whole runs with a fake target and judge: strict zero for a timeout, seeds, concurrency keeps order and saves time, abort after 3 unreachable
    seen = []

    def judge_says(cfg, prompt, schema, max_tokens=500):
        return {"claims": [{"claim": "c", "supported": "yes", "vs_reference": "agrees", "why": ""}], "relevancy": "yes", "relevancy_why": ""}

    def make_cfg(tmp, name, **over):
        return nasute.merge(nasute.DEFAULTS, {"runs": str(tmp / name / "runs"), "report": str(tmp / name / "report"), "profile": "", "limit": 6, "judge": {"model": "m"}, "targets": {"demo": {"kind": "fake"}}, "judge_set": "judge-demo", **over})

    def run_with(target, cfg):
        nasute.TARGETS["fake"], nasute.ask_json = target, judge_says
        try:
            nasute.run(cfg, "demo", 1, cfg["limit"])
        finally:
            nasute.TARGETS["fake"], nasute.ask_json = real_target, real["ask_json"]
        d = Path(cfg["runs"]) / nasute.run_ids(cfg)[-1]
        return json.loads((d / "summary.json").read_text()), [json.loads(x) for x in (d / "results.jsonl").read_text().splitlines()]

    def good(q, tcfg, timeout):
        seen.append((tcfg["seed"], tcfg["temperature"]))
        return {"answer": "an answer", "sources": ["Iron"], "extracts": ["e"], "first_text_s": 1.0, "total_s": 1.0, "error": None}

    nasute.BACKOFF = (0, 0, 0)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # repeats: each has its own seed, and the temperature goes to the target
            s, rows = run_with(good, make_cfg(tmp, "seeds", limit=2, repeats=2, temperature=0.5))
            assert seen == [(1, 0.5), (2, 0.5)] * 2 and [r["seed"] for r in rows] == [1, 2, 1, 2] and s["temperature"] == 0.5 and s["judge_cache"] is False, seen
            # a timeout on the second question: strict zero, an empty answer is a system error too
            count = []

            def sometimes(q, tcfg, timeout):
                count.append(1)
                got = good(q, tcfg, timeout)
                return {**got, "error": "TimeoutError: slow"} if len(count) == 2 else {**got, "answer": ""} if len(count) == 3 else got
            seen.clear()
            s, rows = run_with(sometimes, make_cfg(tmp, "strict", limit=3))
            assert [bool(r["error"]) for r in rows] == [False, True, True] and rows[2]["error"] == "empty answer", [r["error"] for r in rows]
            assert rows[1]["scores"]["correctness"] == 0.0 and rows[1]["scores"]["error_rate"] == 1.0 and rows[1]["scores"]["hit"] == 0.0 and "system error" in rows[1]["reasons"]["correctness"]
            assert s["counts_line"] == "3 asked · 1 scored · 2 system errors · 0 judge errors" and abs(s["metrics"]["correctness"]["mean"] - 1 / 3) < 1e-3 and close(s["metrics_answered"]["correctness"]["mean"], 1.0)
            assert s["causes"]["counts"]["system"] == 2
            # concurrency: same order in the file, and faster
            def slow_first(q, tcfg, timeout):
                real_sleep(0.5 if q.startswith("What time does") else 0.2)
                return good(q, tcfg, timeout)
            took = {}
            for w in (1, 3):
                t = time.monotonic()
                s, rows = run_with(slow_first, make_cfg(tmp, f"w{w}", limit=6, concurrency=w))
                took[w] = time.monotonic() - t
                assert [r["id"] for r in rows] == [q["id"] for q in nasute.load_dataset(*nasute.find_dataset(nasute.DEFAULTS, "demo", 1)[:1], 1)[1][:6]], w
            assert took[3] < took[1] * 0.7, took
            # unreachable on 3 questions in a row stops the run, keeps what it has, and nothing is compared
            def down(q, tcfg, timeout):
                return {"answer": "", "sources": [], "extracts": [], "first_text_s": None, "total_s": 0, "error": "URLError: refused", "unreachable": True}
            cfg = make_cfg(tmp, "down", limit=6)
            s, rows = run_with(down, cfg)
            assert s["aborted"] and len(rows) >= 3 and s["counts"]["system_errors"] == len(rows), (s["aborted"], len(rows))
            real_sleep(1.1)
            s2, _ = run_with(good, cfg)
            c = nasute.compare(cfg)
            assert "stopped early" in c["warning"] and c["shared"] == 0, c
            # newly erroring questions are listed in compare
            cfg = make_cfg(tmp, "newly")
            d1 = {"name": "x", "version": 1, "sha256": "aaa"}
            fake_run(cfg, "20260101T000000Z", d1, {"q1": {"correctness": 1.0}, "q2": {"correctness": 1.0, "error": "x"}})
            fake_run(cfg, "20260102T000000Z", d1, {"q1": {"correctness": 0.0, "error": "x"}, "q2": {"correctness": 1.0}})
            assert nasute.compare(cfg)["errors"] == {"newly": ["q1"], "recovered": ["q2"]}
    finally:
        nasute.BACKOFF = real["BACKOFF"]


class FakeEndpoint:
    """A local http server standing in for a system under test: routes by path, remembers what it was sent."""

    def __init__(self):
        import http.server
        import threading
        self.seen = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body, kind="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def handle_any(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                outer.seen.append({"method": self.command, "path": self.path, "body": body, "headers": dict(self.headers)})
                path = self.path.split("?")[0]
                if path.endswith("/v1/chat/completions"):   # the chat target: answer and usage; under /bad, usage figures that must be dropped
                    bad = path.startswith("/bad")
                    self.reply(200, {"choices": [{"message": {"content": "Paris."}}], "usage": {"prompt_tokens": -1 if bad else 5, "completion_tokens": 2, "cost": float("nan") if bad else 0.0003}})
                elif path == "/chat":
                    self.reply(200, {"choices": [{"message": {"content": " Paris. "}}]})
                elif path == "/rag":
                    self.reply(200, {"answer": "A", "sources": [{"title": "One"}, {"title": "Two"}, {"nottitle": 1}], "hits": [{"text": "t1"}, {"text": "t2"}]})
                elif path == "/boom":
                    self.reply(500, {"error": "boom"})
                elif path == "/empty":
                    self.reply(200, {"answer": ""})
                elif path == "/missing":
                    self.reply(200, {"nope": 1})
                elif path == "/lists":
                    self.reply(200, {"answer": "A", "sources": ["Paris", "France"], "hits": [1, {"a": 2}]})
                elif path == "/text":
                    self.reply(200, b"not json at all", "text/plain")
                else:
                    self.reply(404, {})
            do_GET = do_POST = handle_any

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def target_checks():
    """The generic http target against a fake local endpoint: reply shapes, errors, the request template, and env headers."""
    import os
    from nasute.targets import http
    # the path subset
    doc = {"a": {"b": "x"}, "l": [{"b": 1}, {"c": 2}, {"b": 3}], "s": ["p", "q"]}
    assert http.json_path(doc, "$.a.b") == ["x"] and http.json_path(doc, "$.l[0].b") == [1] and http.json_path(doc, "$.l[*].b") == [1, 3]
    assert http.json_path(doc, "$.s[*]") == ["p", "q"] and http.json_path(doc, "$.s[5]") == [] and http.json_path(doc, "$.a.zzz") == [] and http.json_path(doc, "$") == [doc]
    for bad in ("a.b", "$..a", "$.l[1:2]", "$.l[?(@.b)]", "$.a b"):
        try:
            http.json_path(doc, bad)
            raise AssertionError(f"{bad} should be refused")
        except ValueError:
            pass
    # the template: every string gets the question; quotes and newlines survive; other values are left alone
    q = 'He said "hi"\nand {left} alone'
    assert http.fill({"m": [{"role": "user", "content": "Q: {question}"}], "n": 3, "t": True}, q) == {"m": [{"role": "user", "content": "Q: " + q}], "n": 3, "t": True}

    ep = FakeEndpoint()
    try:
        base = {"url": ep.url + "/chat", "request": {"messages": [{"role": "user", "content": "{question}"}], "temperature": 0}, "answer": "$.choices[0].message.content"}
        got = http.ask(q, base, 5)
        assert got["answer"] == "Paris." and got["error"] is None and got["sources"] == [] and got["total_s"] is not None, got
        assert ep.seen[-1]["method"] == "POST" and ep.seen[-1]["body"] == {"messages": [{"role": "user", "content": q}], "temperature": 0}, ep.seen[-1]   # the server decoded exactly what we meant
        got = http.ask("q", {"url": ep.url + "/rag", "answer": "$.answer", "sources": "$.sources[*].title", "extracts": "$.hits[*].text"}, 5)
        assert (got["answer"], got["sources"], got["extracts"]) == ("A", ["One", "Two"], ["t1", "t2"]), got
        # a GET puts the question in the url, with no body
        got = http.ask("a b&c", {"url": ep.url + "/chat?q={question}", "method": "GET", "answer": "$.choices[0].message.content"}, 5)
        assert got["error"] is None and ep.seen[-1]["method"] == "GET" and ep.seen[-1]["path"] == "/chat?q=a%20b%26c" and ep.seen[-1]["body"] is None, ep.seen[-1]
        # errors: a 500, a path with nothing there, a bad path, a reply that is not JSON; none raise
        assert http.ask("q", {"url": ep.url + "/boom"}, 5)["error"].startswith("HTTP 500")
        got = http.ask("q", {"url": ep.url + "/missing", "answer": "$.answer"}, 5)
        assert "no text at $.answer" in got["error"] and not got.get("unreachable"), got
        assert "ValueError" in http.ask("q", {"url": ep.url + "/chat", "answer": "$..x"}, 5)["error"]
        assert http.ask("q", {"url": ep.url + "/text"}, 5)["error"] and http.ask("q", {"url": ep.url + "/gone"}, 5)["error"].startswith("HTTP 404")
        # an empty answer is the harness's to call an error, as for every target
        assert nasute.ask_target({**nasute.DEFAULTS, "pause": 0}, "http", "q", {"url": ep.url + "/empty"})["error"] == "empty answer"
        # connection refused: unreachable, so the harness waits and retries
        dead = http.ask("q", {"url": "http://127.0.0.1:9/x"}, 5)
        assert dead["unreachable"] and dead["error"], dead
        # headers: env: values come from the environment; a missing variable is an error that names it, not a crash
        os.environ["NASUTE_TEST_KEY"] = "Bearer s3cret"
        http.ask("q", {**base, "headers": {"Authorization": "env:NASUTE_TEST_KEY", "X-Plain": "plain"}}, 5)
        assert ep.seen[-1]["headers"]["Authorization"] == "Bearer s3cret" and ep.seen[-1]["headers"]["X-Plain"] == "plain"
        del os.environ["NASUTE_TEST_KEY"]
        got = http.ask("q", {**base, "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}, 5)
        assert "NASUTE_TEST_KEY is not set" in got["error"] and "s3cret" not in got["error"] and not got.get("unreachable"), got

        # a whole run through named targets: the dataset names "mine"; --target asks the same questions of "other"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "datasets" / "ex").mkdir(parents=True)
            (tmp / "datasets" / "ex" / "v1.jsonl").write_text('{"dataset": "ex", "target": "mine"}\n{"id": "a", "question": "What?", "reference": "Paris"}\n{"id": "b", "question": "Why?", "reference": "Because"}\n')
            os.environ["NASUTE_TEST_KEY"] = "Bearer s3cret"
            cfg = nasute.merge(nasute.DEFAULTS, {"runs": str(tmp / "runs"), "report": str(tmp / "report"), "profile": "", "judge": {"model": "m", "headers": {"Authorization": "env:NASUTE_TEST_KEY"}},
                                                 "datasets": [str(tmp / "datasets")], "targets": {
                "mine": {"kind": "http", "url": ep.url + "/chat", "answer": "$.choices[0].message.content", "headers": {"Authorization": "env:NASUTE_TEST_KEY", "X-Literal": "literal-secret"}},
                "other": {"kind": "http", "url": ep.url + "/rag", "answer": "$.answer", "sources": "$.sources[*].title"}}})
            real_ask = nasute.ask_json
            nasute.ask_json = lambda cfg, prompt, schema, max_tokens=500, verify=None: {"claims": [], "relevancy": "yes", "relevancy_why": ""}
            try:
                nasute.run(cfg, "ex", None, 0)
                time.sleep(1.1)   # run folders are named by the second
                nasute.run(cfg, "ex", None, 0, "other")
            finally:
                nasute.ask_json = real_ask
            sums = nasute.summaries(cfg)
            assert [(s["target"], s["target_kind"]) for s in sums.values()] == [("mine", "http"), ("other", "http")] and {nasute.suite_of(s) for s in sums.values()} == {"ex@mine", "ex@other"}
            assert list(sums.values())[1]["settings"]["targets"]["mine"]["headers"] == ["Authorization", "X-Literal"]   # names only
            for f in tmp.rglob("*"):   # the secret, and the literal header value, are in no file
                if f.is_file() and f.suffix in (".json", ".jsonl", ".html"):
                    assert "s3cret" not in f.read_text() and "literal-secret" not in f.read_text(), f
            try:
                nasute.run(cfg, "ex", None, 0, "nope")
                raise AssertionError("an unknown target should stop the run")
            except SystemExit as e:
                assert "no target 'nope'" in str(e)
            del os.environ["NASUTE_TEST_KEY"]
    finally:
        ep.close()


def settings_form_checks():
    """Named targets, and folders relative to the settings file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        new = tmp / "new" / "nasute.toml"
        new.parent.mkdir()
        new.write_text('runs = "r"\n[targets.a]\nkind = "http"\nurl = "http://x"\n[targets.b]\nkind = "mine:ask"\n')
        c = nasute.load_settings(new)
        assert c["targets"] == {"a": {"kind": "http", "url": "http://x"}, "b": {"kind": "mine:ask"}} and c["runs"] == str(tmp / "new" / "r") and c["datasets"] == [str(tmp / "new" / "datasets")]


def suite_checks():
    """Runs group by suite (dataset × target): compare pairs inside a suite, a baseline wins over the previous run, profiles are respected."""
    d = {"name": "ds", "version": 1, "sha256": "aaa"}
    two = lambda x: {"q1": {"correctness": x}, "q2": {"correctness": x}, "q3": {"correctness": x}, "q4": {"correctness": x}, "q5": {"correctness": x}}
    with tempfile.TemporaryDirectory() as tmp:
        cfg = {**nasute.DEFAULTS, "runs": str(Path(tmp) / "runs"), "report": str(Path(tmp) / "report")}
        for i, (t, x) in enumerate([("one", 0.2), ("two", 0.9), ("one", 0.6), ("two", 0.5)], 1):
            fake_run(cfg, f"2026010{i}T000000Z", d, two(x), target=t)
        c = nasute.compare(cfg)   # the newest run is a "two" run; it is paired with the earlier "two" run, not with the run just before it
        assert (c["a"], c["b"]) == ("20260102T000000Z", "20260104T000000Z") and not c["notes"], c
        c = nasute.compare(cfg, suite="ds@one")
        assert (c["a"], c["b"]) == ("20260101T000000Z", "20260103T000000Z"), c
        assert nasute.compare(cfg, suite="ds@none") is None
        # a baseline wins over the previous run, and the baseline run itself is compared with the one before it
        meta = nasute.run_meta(cfg)
        assert meta == {"labels": {}, "baselines": {}}
        nasute.save_meta(cfg, {"labels": {}, "baselines": {"ds@one": "20260101T000000Z"}})
        fake_run(cfg, "20260105T000000Z", d, two(0.7), target="one")
        assert nasute.compare(cfg, suite="ds@one")["a"] == "20260101T000000Z"
        sums = nasute.summaries(cfg)
        assert nasute.reference_run(cfg, sums, "20260101T000000Z") is None and nasute.reference_run(cfg, sums, "20260103T000000Z") == "20260101T000000Z"
    # profiles: two runs that both name a profile must match; a run without one pairs with anything
    with tempfile.TemporaryDirectory() as tmp:
        cfg = {**nasute.DEFAULTS, "runs": str(Path(tmp) / "runs")}
        for i, p in enumerate(["deep", "smoke", "", "smoke"], 1):
            fake_run(cfg, f"2026010{i}T000000Z", d, two(0.5), profile=p, target="t")
        sums = nasute.summaries(cfg)
        ref = lambda i: nasute.reference_run(cfg, sums, f"2026010{i}T000000Z")
        assert ref(2) is None   # smoke after deep: not the same kind of run
        assert ref(3) == "20260102T000000Z" and ref(4) == "20260103T000000Z"
        assert nasute.compare(cfg)["a"] == ref(4)


def cli(cfg_file, *args):
    """Run a nasute command as typed; -> (exit code, what it printed)."""
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = nasute.main(["--config", str(cfg_file), *args])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
            out.write(str(e.code) if not isinstance(e.code, int) else "")
    return code or 0, out.getvalue()


def manage_checks():
    """init, dataset check/import/list, and the run manager, as typed at a terminal."""
    import builtins
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # init writes a working starter and never overwrites
        code, out = cli(tmp / "none.toml", "init", str(tmp / "mine"))
        assert code == 0 and (tmp / "mine" / "nasute.toml").exists() and (tmp / "mine" / "datasets" / "example" / "v1.jsonl").exists(), out
        conf = tmp / "mine" / "nasute.toml"
        s = nasute.load_settings(conf)
        assert s["targets"]["mine"]["kind"] == "http" and s["dataset"] == "example" and s["profiles"]["smoke"]["limit"] == 3 and s["runs"] == str(tmp / "mine" / "runs")
        conf.write_text("# mine\n" + conf.read_text())
        code, out = cli(conf, "init", str(tmp / "mine"))
        assert code == 1 and "already exist" in out and conf.read_text().startswith("# mine\n")
        assert cli(conf, "dataset", "check", "example")[0] == 0 and "ok, 3 questions" in cli(conf, "dataset", "check", "example")[1]
        # the started example dataset header names the started target
        assert json.loads((tmp / "mine" / "datasets" / "example" / "v1.jsonl").read_text().splitlines()[0])["target"] in s["targets"]

        # dataset check: each kind of problem, with its line number
        ds = tmp / "mine" / "datasets" / "bad"
        ds.mkdir()
        good = '{"id": "g", "question": "Q?", "reference": "R"}'
        cases = {
            1: ('{"dataset": "bad", "target": "mine"}\n' + good + '\n{not json\n', "line 3: not valid JSON"),
            2: ('{"dataset": "bad"}\n' + good + "\n", "line 1: header: 'target' must be non-empty text"),
            3: (good + "\n", "line 1: the first line must be the header"),
            4: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?"}\n', "line 2: missing field(s): reference"),
            5: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?", "reference": "R", "sources": "One", "tags": [1]}\n', "line 2: 'sources' must be a list of text"),
            6: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?", "reference": "R", "difficulty": "tough"}\n', "line 2: 'difficulty' must be one of easy, medium, hard"),
            7: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?", "reference": "R", "answerable": "no"}\n', "line 2: 'answerable' must be true or false"),
            8: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?", "reference": "R", "answerable": false}\n', "line 2: answerable is false, so 'reference' should be empty"),
            9: ('{"dataset": "bad", "target": "mine"}\n{"id": "x", "question": "Q?", "reference": ""}\n', "line 2: no 'reference' answer"),
            10: ('{"dataset": "bad", "target": "mine"}\n' + good + "\n" + good + "\n", "line 3: repeated id 'g' (first on line 2)"),
            11: ('{"dataset": "bad", "target": "mine"}\n', "no questions after the header"),
            12: ("", "the file is empty"),
            13: ('{"dataset": "bad", "target": "mine"}\n{"id": "", "question": "", "reference": "R"}\n', "line 2: 'id' must not be empty"),
        }
        for v, (text, want) in cases.items():
            (ds / f"v{v}.jsonl").write_text(text)
            code, out = cli(conf, "dataset", "check", "bad", "--version", str(v))
            assert code == 1 and want in out, (v, out)
        assert "1 problem" in cli(conf, "dataset", "check", "bad", "--version", "10")[1]
        code, out = cli(conf, "dataset", "check", "nope")
        assert code != 0 and "no dataset 'nope'" in out

        # import: the next version, ; lists, answerable, and the old version untouched
        csv1 = tmp / "q.csv"
        csv1.write_text("id,question,reference,sources,tags,difficulty,answerable\na,What is A?,Alpha,One; Two,x;y,Easy,\nb,What is B?,,,,hard,false\nc,\"Quote, comma\",R,,,,TRUE\n")
        code, out = cli(conf, "dataset", "import", str(csv1), "--name", "fresh")
        v1 = tmp / "mine" / "datasets" / "fresh" / "v1.0.0.jsonl"
        assert code == 0 and v1.exists() and "3 questions" in out, out
        rows = [json.loads(x) for x in v1.read_text().splitlines()]
        assert rows[0]["target"] == "mine" and rows[1] == {"id": "a", "question": "What is A?", "reference": "Alpha", "sources": ["One", "Two"], "tags": ["x", "y"], "difficulty": "easy"}
        assert rows[2]["answerable"] is False and rows[2]["difficulty"] == "hard" and rows[3]["question"] == "Quote, comma" and "answerable" not in rows[3]
        before = v1.read_text()
        code, out = cli(conf, "dataset", "import", str(csv1), "--name", "fresh")
        assert code != 0 and "nothing changed" in out   # the same questions again are not a new version
        csv1.write_text(csv1.read_text() + "d,What is D?,Delta,,,,\n")
        code, out = cli(conf, "dataset", "import", str(csv1), "--name", "fresh")
        assert code == 0 and (v1.parent / "v1.1.0.jsonl").exists() and v1.read_text() == before and "minor: 1 questions added" in out, out
        # a CSV with a bad row is written and then reported; a missing column is refused before anything is written
        csv2 = tmp / "bad.csv"
        csv2.write_text("id,question,reference\nz,,R\n")
        code, out = cli(conf, "dataset", "import", str(csv2), "--name", "fresh")
        assert code == 1 and "line 2: 'question' must not be empty" in out and "Nothing was written" in out and not (v1.parent / "v2.0.0.jsonl").exists(), out
        # duplicate ids are caught before anything is written, so the fixed CSV imports straight after
        csv2.write_text("id,question,reference\na,What is A?,Alpha\na,Again?,Alpha\n")
        code, out = cli(conf, "dataset", "import", str(csv2), "--name", "fresh")
        assert code == 1 and "repeated" in out.lower() and not (v1.parent / "v2.0.0.jsonl").exists(), out
        csv2.write_text("id,question,reference\na,What is A?,Alpha\nb2,Other?,Beta\n")
        code, out = cli(conf, "dataset", "import", str(csv2), "--name", "fresh")
        assert code == 0 and (v1.parent / "v2.0.0.jsonl").exists() and not list(v1.parent.glob(".import-*")), out
        csv2.write_text("id,question\nz,Q\n")
        code, out = cli(conf, "dataset", "import", str(csv2), "--name", "fresh")
        assert code != 0 and "missing column(s): reference" in out and not (v1.parent / "v3.0.0.jsonl").exists()
        code, out = cli(conf, "dataset", "list")
        assert "fresh  target mine  v1.0.0 (3 questions), v1.1.0 (4 questions), v2.0.0 (2 questions)" in out and "example  target mine  v1.0.0 (3 questions)" in out, out

        # the run manager over fake runs in two suites
        cfg = nasute.load_settings(conf)
        d = {"name": "ds", "version": 1, "sha256": "aaa"}
        five = lambda x: {f"q{i}": {"correctness": x} for i in range(5)}
        fake_run(cfg, "20260101T000000Z", d, five(0.2), target="mine", profile="smoke")
        fake_run(cfg, "20260102T000000Z", d, {**five(0.8), "q0": {"correctness": 0.0, "hit": 0.0}}, target="mine", profile="smoke")
        fake_run(cfg, "20260103T000000Z", d, five(0.5), target="other", aborted="the system could not be reached")
        code, out = cli(conf, "runs")
        assert code == 0 and "ds × mine" in out and "ds × other" in out and "[STOPPED EARLY]" in out and out.index("20260102T000000Z") < out.index("20260101T000000Z"), out
        assert cli(conf, "runs", "label", "20260101", "before the fix")[0] == 0 and '"before the fix"' in cli(conf, "runs")[1]
        assert "label removed" in cli(conf, "runs", "label", "20260101", "")[1] and "before the fix" not in cli(conf, "runs")[1]
        code, out = cli(conf, "runs", "show", "20260102")
        assert "Answer correctness" in out and "Worst questions" in out and "q0" in out and "smoke" in out, out
        assert cli(conf, "runs", "show", "2026")[0] != 0 and "several runs" in cli(conf, "runs", "show", "2026")[1] and "no run" in cli(conf, "runs", "show", "x")[1]
        code, out = cli(conf, "runs", "baseline", "20260103")
        assert code != 0 and "stopped early" in out   # an aborted run cannot be a baseline
        assert cli(conf, "runs", "baseline", "20260101")[0] == 0 and nasute.run_meta(cfg)["baselines"] == {"ds@mine": "20260101T000000Z"}
        assert "[BASELINE]" in cli(conf, "runs", "--suite", "ds@mine")[1] and "ds × other" not in cli(conf, "runs", "--suite", "ds@mine")[1]
        assert nasute.compare(cfg, suite="ds@mine")["a"] == "20260101T000000Z"   # compare uses the baseline
        # delete: asks unless --yes; the baseline needs --yes
        code, out = cli(conf, "runs", "delete", "20260101")
        assert code != 0 and "is the baseline" in out and (Path(cfg["runs"]) / "20260101T000000Z").exists()
        real_input = builtins.input
        try:
            builtins.input = lambda prompt="": "n"
            assert cli(conf, "runs", "delete", "20260102")[0] == 1 and (Path(cfg["runs"]) / "20260102T000000Z").exists()
            builtins.input = lambda prompt="": "y"
            assert cli(conf, "runs", "delete", "20260102")[0] == 0 and not (Path(cfg["runs"]) / "20260102T000000Z").exists()
        finally:
            builtins.input = real_input
        cli(conf, "runs", "label", "20260101", "keep")
        page = Path(cfg["report"]) / "ds@mine" / "runs"
        assert (page / "20260101T000000Z.html").exists() and (page / "20260101T000000Z.results.jsonl").exists()
        assert cli(conf, "runs", "delete", "20260101", "--yes")[0] == 0 and nasute.run_meta(cfg) == {"labels": {}, "baselines": {}}
        assert not (Path(cfg["report"]) / "ds@mine").exists()   # the report is rebuilt: no page or copy of a deleted run is left to serve
        assert nasute.run_ids(cfg) == ["20260103T000000Z"]

    # serve: the report folder over http on 127.0.0.1 only
    import threading
    import urllib.request
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "index.html").write_text("<p>hi</p>")
        server = manage.make_server({"report": tmp}, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            assert server.server_address[0] == "127.0.0.1" and urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/").read() == b"<p>hi</p>"
        finally:
            server.shutdown()
            server.server_close()


def report_checks():
    """The static report: every page is written, its data survives hostile text, and its scripts parse."""
    import re
    import shutil
    import subprocess
    d = {"name": "ds", "version": 1, "sha256": "aaa"}
    evil = 'Q <b>bold</b> </script><script>alert(1)</script> <!-- & "quotes"'
    five = lambda x: {f"q{i}": {"correctness": x, "hit": 1.0} for i in range(5)}
    # the report shows the newest judge-check for each run's judge model and mode, looked up when the report is written (so an older run shows a later check too)
    page_data = lambda path: json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', path.read_text(), re.S).group(1))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report")}
        recorded = {"run": "judge-20260101T000000Z", "items": 47, "set_size": 47, "aborted": None, "metrics": {}}
        fake_run(cfg, "20260102T000000Z", d, five(0.5), target="t", judge_model="jm", judge_reliability=recorded)   # an older run, with the older check recorded
        fake_run(cfg, "20260103T000000Z", d, five(0.6), target="t", judge_model="jm")                              # a run that recorded none
        fake_run(cfg, "20260104T000000Z", d, five(0.6), target="u", judge_model="other")                           # another judge: no check
        def check_dir(name, **over):
            (tmp / "runs" / name).mkdir()
            (tmp / "runs" / name / "summary.json").write_text(json.dumps({"run": name, "dataset": {"name": "judge-set", "version": 2, "sha256": "x"}, "judge_model": "jm", "judge_mode": nasute.DEFAULTS["judge"]["mode"],
                                                                         "items": 47, "set_size": 47, "aborted": None, "metrics": {"correctness": {"accuracy": 0.96, "kappa": 0.74, "n": 47}},
                                                                         "wrong": [{"id": "x1", "kind": "invented", "metric": "correctness", "expected": [0, 0.25], "got": 1.0}], **over}))
        check_dir("judge-20260101T000000Z")
        check_dir("judge-20260105T000000Z")                                      # complete, the newest complete one
        check_dir("judge-20260106T000000Z", items=3, aborted="unreachable")      # newer but stopped: not preferred
        out = tmp / "report"
        nasute.report(cfg)
        suite_t, run2, other = page_data(out / "ds@t" / "runs" / "20260103T000000Z.html"), page_data(out / "ds@t" / "runs" / "20260102T000000Z.html"), page_data(out / "ds@u" / "runs" / "20260104T000000Z.html")
        assert suite_t["judge_check"]["run"] == "judge-20260105T000000Z" and suite_t["judge_checked_since"] and suite_t["judge_check"]["wrong"][0]["id"] == "x1" and suite_t["judge_check"]["dataset"]["name"] == "judge-set", suite_t["judge_check"]
        assert run2["judge_check"]["run"] == "judge-20260105T000000Z" and run2["judge_checked_since"]   # the older run's own record (the 1 Jan check) was superseded
        assert other["judge_check"] is None and not other["judge_checked_since"]
        shutil.rmtree(tmp / "runs" / "judge-20260105T000000Z")
        shutil.rmtree(tmp / "runs" / "judge-20260101T000000Z")
        nasute.report(cfg)
        assert page_data(out / "ds@t" / "runs" / "20260103T000000Z.html")["judge_check"]["aborted"] == "unreachable"   # only a stopped check is left: shown, and marked
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report")}
        fake_run(cfg, "20260101T000000Z", d, five(0.4), target="mine", questions={"q0": evil}, profile="smoke")
        fake_run(cfg, "20260102T000000Z", {**d, "version": 2, "sha256": "bbb"}, five(0.6), target="mine", questions={"q0": evil}, profile="smoke")
        fake_run(cfg, "20260103T000000Z", {**d, "version": 2, "sha256": "bbb"}, {**five(0.7), "q0": {"correctness": 0.1, "hit": 1.0}}, target="mine", questions={"q0": evil}, profile="smoke")
        fake_run(cfg, "20260104T000000Z", d, five(0.5), target="other")
        nasute.save_meta(cfg, {"labels": {"20260103T000000Z": evil}, "baselines": {"ds@mine": "20260102T000000Z"}})
        out = tmp / "report"
        out.mkdir()
        (out / "index.json").write_text("{}")   # the old report's file
        (out / "ds@mine").mkdir()
        (out / "ds@mine" / "runs").mkdir()
        (out / "ds@mine" / "runs" / "stale.html").write_text("old")
        suites = nasute.report(cfg)
        assert set(suites) == {"ds@mine", "ds@other"} and not (out / "index.json").exists() and not (out / "ds@mine" / "runs" / "stale.html").exists()
        pages = sorted(out.rglob("*.html"))
        names = {str(p.relative_to(out)) for p in pages}
        assert names == {"index.html", "datasets/ds.html", "ds@mine/index.html", "ds@other/index.html", "ds@mine/compare/20260102T000000Z-20260103T000000Z.html"} | \
            {f"ds@mine/runs/2026010{i}T000000Z.html" for i in (1, 2, 3)} | {"ds@other/runs/20260104T000000Z.html"}, names
        assets = {p.name for p in (out / "assets").iterdir()}
        assert {"report.js", "report.css", "uPlot.iife.min.js", "uPlot.min.css", "uPlot.LICENSE", "favicon.png", "apple-touch-icon.png"} <= assets
        for p in pages:
            text = p.read_text()
            if p.name == "index.html" and p.parent != out:   # an old suite address: a page with no script that sends the reader on to the dataset page
                assert re.findall(r"<script\b", text) == [] and 'content="0; url=../datasets/ds.html#system=' in text, text
                continue
            m = re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S)
            data = json.loads(m.group(1))   # the block ended where we wrote it, whatever the question said
            up = "../" * (len(p.relative_to(out).parts) - 1)
            charts = [f'<script src="{up}assets/chart.umd.min.js">', f'<script src="{up}assets/chartjs-chart-boxplot.umd.min.js">'] if data["page"] == "run" else []   # only run pages draw the question charts
            assert re.findall(r"<script\b[^>]*>", text) == ['<script id="data" type="application/json">', *charts, f'<script src="{up}assets/uPlot.iife.min.js">', f'<script src="{up}assets/report.js">'], p   # no other script in the page
            assert not re.search(r"\son[a-z]+\s*=", text), p   # no inline handlers
            assert "glossary" in data and data["page"] in ("overview", "dataset", "run", "compare")
            if data["page"] == "run" and "q0" in {r["id"] for r in data["rows"]}:
                assert next(r for r in data["rows"] if r["id"] == "q0")["question"] in (evil, "Question q0?")
        run3 = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', (out / "ds@mine" / "runs" / "20260103T000000Z.html").read_text(), re.S).group(1))
        assert run3["rows"][0]["question"] == evil and run3["label"] == evil and run3["vs"] == "20260102T000000Z" and run3["worse"] == ["q0"] and len(run3["rows"]) == 5
        dset = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', (out / "datasets" / "ds.html").read_text(), re.S).group(1))
        mine = [r for r in dset["runs"] if r["target"] == "mine"]
        assert [r["baseline"] for r in mine] == [False, True, False] and run3["compare"]["a"] == "20260102T000000Z" and run3["vs_baseline"]
        assert run3["compare_href"] == "../compare/20260102T000000Z-20260103T000000Z.html" and run3["dataset_href"] == "../../datasets/ds.html"
        cmp = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', (out / "ds@mine" / "compare" / "20260102T000000Z-20260103T000000Z.html").read_text(), re.S).group(1))
        assert [i["id"] for i in cmp["items"]] == ["q0"] and cmp["items"][0]["a"]["answer"] == "Answer to q0" and cmp["items"][0]["question"] == evil
        # the old run page disappears with its run
        shutil.rmtree(Path(cfg["runs"]) / "20260101T000000Z")
        nasute.report(cfg)
        assert not (out / "ds@mine" / "runs" / "20260101T000000Z.html").exists()
        # the pages' script, and the guard that no text goes in as HTML
        js = (out / "assets" / "report.js").read_text()
        assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js
        if shutil.which("node"):
            r = subprocess.run(["node", "--check", str(out / "assets" / "report.js")], capture_output=True, text=True)
            assert r.returncode == 0, "report.js does not parse:\n" + r.stderr


def review_round_checks():
    """Findings from the second review, each reproduced with fake data."""
    import os
    from nasute.targets import http
    d = {"name": "ds", "version": 1, "sha256": "aaa"}
    five = lambda x: {f"q{i}": {"correctness": x, "hit": 1.0} for i in range(5)}
    new_cfg = lambda tmp: {**nasute.DEFAULTS, "runs": str(Path(tmp) / "runs"), "report": str(Path(tmp) / "report")}

    # 1: secrets in settings are hidden at every depth, in profiles too (used or not)
    cfg = {**nasute.DEFAULTS, "profile": "", "targets": {"a": {"kind": "http", "headers": {"Authorization": "Bearer SECRET1"}, "api_key": "SECRET2"}},
           "profiles": {"x": {"targets": {"a": {"headers": {"X": "SECRET3"}}}, "judge": {"headers": {"Y": "SECRET4"}, "token": "SECRET5"}}},
           "judge": {**nasute.DEFAULTS["judge"], "headers": {"Z": "SECRET6"}}}
    saved = json.dumps(nasute.public(cfg))
    assert "SECRET" not in saved and nasute.public(cfg)["profiles"]["x"]["targets"]["a"]["headers"] == ["X"] and nasute.public(cfg)["targets"]["a"]["headers"] == ["Authorization"]
    assert nasute.public({"pass_at": 0.75, "k": 5})["pass_at"] == 0.75   # ordinary settings are not hidden

    # 2 and 11 and 12: a malformed header never reaches an error; a trailing newline on an env value is dropped; lists; the url
    ep = FakeEndpoint()
    try:
        os.environ["NASUTE_TEST_KEY"] = "Bearer SECRET\nX"
        for headers in ({"Authorization": "env:NASUTE_TEST_KEY"}, {"Authorization": "Bearer SECRET\nX"}, {"Authorization": "SECRET’"}, {"Bad Name": "SECRET"}):
            got = http.ask("q", {"url": ep.url + "/chat", "headers": headers}, 5)
            assert got["error"] and "SECRET" not in got["error"] and not got.get("unreachable"), got
        os.environ["NASUTE_TEST_KEY"] = "Bearer fine\n"
        http.ask("q", {"url": ep.url + "/chat", "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}, 5)
        assert ep.seen[-1]["headers"]["Authorization"] == "Bearer fine"
        os.environ["NASUTE_TEST_KEY"] = "Bearer SECRET\nX"
        bad_judge = {"judge": {"url": ep.url + "/v1", "model": "m", "timeout": 2, "mode": "quick", "retries": 0, "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}}
        scores, _, _, err = nasute.judge({"question": "q", "reference": "r", "answer": "a", "extracts": []}, bad_judge)
        assert err and "SECRET" not in err, err
        with tempfile.TemporaryDirectory() as tmp:   # and no secret in any file a run writes
            tmp = Path(tmp)
            (tmp / "datasets" / "ex").mkdir(parents=True)
            (tmp / "datasets" / "ex" / "v1.jsonl").write_text('{"dataset": "ex", "target": "mine"}\n{"id": "a", "question": "What?", "reference": "Paris"}\n')
            cfg = nasute.merge(nasute.DEFAULTS, {"runs": str(tmp / "runs"), "report": str(tmp / "report"), "profile": "", "datasets": [str(tmp / "datasets")], "judge": {"model": "m"},
                                                 "targets": {"mine": {"kind": "http", "url": ep.url + "/chat", "headers": {"Authorization": "env:NASUTE_TEST_KEY"}}},
                                                 "profiles": {"p": {"targets": {"mine": {"headers": {"Authorization": "SECRET-in-a-profile"}}}}}})
            nasute.run(cfg, "ex", None, 0)
            files = [f for f in tmp.rglob("*") if f.is_file() and f.suffix in (".json", ".jsonl", ".html")]
            assert files and all("SECRET" not in f.read_text() for f in files)
        assert nasute.TARGETS["http"] is http.ask
        assert nasute.target_ask("nasute.targets.http:ask") is http.ask   # a "module:function" kind is imported, no edit to TARGETS
        for bad in ("nope", "nasute.targets.http:nope"):
            try:
                nasute.target_ask(bad)
                raise AssertionError(f"kind {bad!r} should be refused")
            except (AssertionError, AttributeError) as e:
                assert "should be refused" not in str(e), e
        got = http.ask("q", {"url": ep.url + "/rag", "answer": "$.answer", "sources": "$.sources[*].title"}, 5)
        assert got["sources"] == ["One", "Two"]
        got = http.ask("q", {"url": ep.url + "/lists", "answer": "$.answer", "sources": "$.sources", "extracts": "$.hits"}, 5)
        assert (got["sources"], got["extracts"]) == (["Paris", "France"], ["1", '{"a": 2}']), got
        assert "no text at" in http.ask("q", {"url": ep.url + "/lists", "answer": "$.sources"}, 5)["error"]   # a list is not an answer
        http.ask("a/b?c", {"url": ep.url + "/chat/{question}", "method": "GET"}, 5)
        assert ep.seen[-1]["path"] == "/chat/a%2Fb%3Fc", ep.seen[-1]
    finally:
        os.environ.pop("NASUTE_TEST_KEY", None)
        ep.close()

    # 3, 5, 6: names are plain, so they stay inside their folders, suite ids cannot collide and folder names are unique
    for bad in ("../outside", "/abs/path", "a/b", "a@b", ".hidden", "a..b", "", "a b"):
        try:
            nasute.check_name(bad, "dataset name")
            raise AssertionError(f"{bad!r} should be refused")
        except SystemExit:
            pass
    assert all(nasute.check_name(x, "n") == x for x in ("demo", "judge-demo", "a.b_c", "mine2"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "mine").mkdir()
        conf = tmp / "mine" / "nasute.toml"
        conf.write_text('[targets.mine]\nkind = "http"\nurl = "http://x"\n')
        (tmp / "q.csv").write_text("id,question,reference\na,Q?,R\n")
        for bad in ("../outside", str(tmp / "abs")):
            code, out = cli(conf, "dataset", "import", str(tmp / "q.csv"), "--name", bad)
            assert code != 0 and "not allowed" in out and not (tmp / "outside").exists() and not (tmp / "abs").exists(), out
        assert "not allowed" in cli(conf, "dataset", "import", str(tmp / "q.csv"), "--name", "ok", "--target", "../t")[1]
        assert "not allowed" in cli(conf, "dataset", "check", "../x")[1]
        conf.write_text('[targets."a/b"]\nkind = "http"\n')
        assert cli(conf, "runs")[0] != 0 and "not allowed" in cli(conf, "runs")[1]
        # 9: two imports at once: the version number the first one took is not overwritten
        conf.write_text('[targets.mine]\nkind = "http"\nurl = "http://x"\n')
        cfg = nasute.load_settings(conf)
        ds = tmp / "mine" / "datasets" / "zz"
        ds.mkdir(parents=True)
        (ds / "v1.jsonl").write_text('{"dataset": "zz", "target": "mine"}\n{"id": "a", "question": "Q?", "reference": "old"}\n')
        (ds / "v2.0.0.jsonl").write_text("taken by the other import")
        real_versions = nasute.versions_of
        nasute.versions_of = lambda cfg, name: {(1, 0, 0): ds / "v1.jsonl"}   # what the first import saw before the other one wrote v2
        try:
            assert manage.dataset_import(cfg, str(tmp / "q.csv"), "zz") == 0
        finally:
            nasute.versions_of = real_versions
        assert (ds / "v2.0.0.jsonl").read_text() == "taken by the other import" and (ds / "v3.0.0.jsonl").exists()
    a, b = {"dataset": {"name": "a__b"}, "target": "c"}, {"dataset": {"name": "a"}, "target": "b__c"}
    assert nasute.suite_of(a) != nasute.suite_of(b) and pages.slug(nasute.suite_of(a)) != pages.slug(nasute.suite_of(b))
    assert pages.slug("ds@mine") == "ds@mine" and pages.slug("a b@c") != pages.slug("a_b@c") and pages.slug("../x@y").count("/") == 0 and not pages.slug("../x@y").startswith(".")

    # 4, 10, 14: the report writes nothing through a symlink or outside its folder, drops suites with no runs, and counts bytes
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = new_cfg(tmp)
        fake_run(cfg, "20260101T000000Z", d, five(0.5), target="one", questions={"q0": "é" * 400})
        fake_run(cfg, "20260102T000000Z", d, five(0.5), target="two")
        out, outside = tmp / "report", tmp / "outside"
        out.mkdir()
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        (out / "ds@one").symlink_to(outside, target_is_directory=True)
        try:
            nasute.report(cfg)
            raise AssertionError("a symlinked suite folder should stop the report")
        except SystemExit as e:
            assert "symlink" in str(e)
        assert sorted(p.name for p in outside.iterdir()) == ["keep.txt"]
        (out / "ds@one").unlink()
        (out / "ds@two").mkdir()
        (out / "ds@two" / "runs").symlink_to(outside, target_is_directory=True)   # only the inner folder is a link
        try:
            nasute.report(cfg)
            raise AssertionError("a symlinked runs folder should stop the report")
        except SystemExit:
            pass
        assert sorted(p.name for p in outside.iterdir()) == ["keep.txt"]
        (out / "ds@two" / "runs").unlink()
        nasute.report(cfg)
        assert (out / "ds@one" / "runs" / "20260101T000000Z.html").exists() and (out / "ds@one" / ".nasute-suite").exists()
        # 14: the warning counts bytes: this page has fewer characters than the limit and more bytes
        page = (out / "ds@one" / "runs" / "20260101T000000Z.html").read_text()
        real_big = pages.BIG
        pages.BIG = len(page) + 100
        try:
            assert len(page.encode()) > pages.BIG > len(page)
            seen, real_log = [], nasute.log
            nasute.log = lambda event, level=20, **d: seen.append((event, d))
            try:
                nasute.report(cfg)
            finally:
                nasute.log = real_log
            assert [d["page"] for e, d in seen if e == "page_large"] == ["ds@one/runs/20260101T000000Z.html"], seen
            assert [d["bytes"] for e, d in seen if e == "page_large"] == [len(page.encode())]   # bytes, not characters
        finally:
            pages.BIG = real_big
        # 10: a suite whose runs are all gone loses its pages; a folder Nasute did not make, and a symlink, stay
        (out / "mine").mkdir()
        (out / "mine" / "notes.txt").write_text("not ours")
        (out / "link").symlink_to(outside, target_is_directory=True)
        shutil.rmtree(Path(cfg["runs"]) / "20260101T000000Z")
        nasute.report(cfg)
        assert not (out / "ds@one").exists() and (out / "ds@two").exists() and (out / "mine" / "notes.txt").exists() and (out / "link").is_symlink() and (outside / "keep.txt").exists()

    # 7: an explicit compare across targets is allowed (same file); different profiles or files give no verdicts; a run with no profile pairs with any
    with tempfile.TemporaryDirectory() as tmp:
        cfg = new_cfg(tmp)
        fake_run(cfg, "20260101T000000Z", d, five(0.2), target="one", profile="smoke")
        fake_run(cfg, "20260102T000000Z", d, five(0.9), target="two", profile="smoke")
        fake_run(cfg, "20260103T000000Z", d, five(0.9), target="one", profile="deep")
        fake_run(cfg, "20260104T000000Z", d, five(0.9), target="one", profile="")
        c = nasute.compare(cfg, "20260101T000000Z", "20260102T000000Z")
        assert c["warning"] is None and c["metrics"]["correctness"]["verdict"] == "real gain" and any("different targets" in n for n in c["notes"]), c   # two systems, same questions
        fake_run(cfg, "20260110T000000Z", {**d, "sha256": "other"}, five(0.9), target="two", profile="smoke")
        c = nasute.compare(cfg, "20260101T000000Z", "20260110T000000Z")
        assert "Different questions" in c["warning"] and {p["verdict"] for p in c["metrics"].values()} == {"not comparable"}, c
        c = nasute.compare(cfg, "20260101T000000Z", "20260103T000000Z")
        assert "Different profiles" in c["warning"] and {p["verdict"] for p in c["metrics"].values()} == {"not comparable"}, c
        c = nasute.compare(cfg, "20260101T000000Z", "20260104T000000Z")
        assert c["warning"] is None and c["metrics"]["correctness"]["verdict"] == "real gain", c
        # 8: a baseline of another profile is not used; the previous run that fits is
        sums = nasute.summaries(cfg)
        nasute.save_meta(cfg, {"labels": {}, "baselines": {"ds@one": "20260103T000000Z"}})   # a deep baseline
        fake_run(cfg, "20260105T000000Z", d, five(0.3), target="one", profile="smoke")
        sums = nasute.summaries(cfg)
        assert nasute.reference_run(cfg, sums, "20260105T000000Z") == "20260104T000000Z"   # not the deep baseline; the unprofiled run fits
        fake_run(cfg, "20260106T000000Z", d, five(0.3), target="one", profile="deep")
        assert nasute.reference_run(cfg, nasute.summaries(cfg), "20260106T000000Z") == "20260103T000000Z"   # the deep baseline fits a deep run

    # second round. A: names are checked wherever they are read: a profile's targets, a dataset's header
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        conf = tmp / "n.toml"
        conf.write_text('[profiles.p.targets."a@b"]\nkind = "http"\n')
        nasute.load_settings(conf)   # fine unless the profile is chosen
        try:
            nasute.load_settings(conf, "p")
            raise AssertionError("a bad target name added by a profile should be refused")
        except SystemExit as e:
            assert "not allowed" in str(e)
        (tmp / "datasets" / "x").mkdir(parents=True)
        (tmp / "datasets" / "x" / "v1.jsonl").write_text('{"dataset": "a@b", "target": "c"}\n{"id": "q", "question": "Q?", "reference": "R"}\n')
        try:
            nasute.load_dataset(tmp / "datasets" / "x" / "v1.jsonl", 1)
            raise AssertionError("a bad dataset name in a header should be refused")
        except SystemExit as e:
            assert "header dataset" in str(e)
        conf.write_text('datasets = ["datasets"]\n')
        code, out = cli(conf, "dataset", "check", "x")
        assert code == 1 and "'dataset' 'a@b' is not a plain name" in out, out
    # B: a hashed folder name can never equal a real id
    hashed = pages.slug("ds@a+b")
    assert "~" in hashed and not nasute.NAME.fullmatch(hashed) and hashed != pages.slug("ds@a_b") and pages.slug("ds@a_b") == "ds@a_b"
    # F: a baseline saved under the old suite id (dataset__target) still works
    with tempfile.TemporaryDirectory() as tmp:
        cfg = new_cfg(tmp)
        for i in (1, 2, 3):
            fake_run(cfg, f"2026010{i}T000000Z", d, five(0.5), target="one")
        (Path(cfg["runs"]) / "index.json").write_text(json.dumps({"labels": {"20260102T000000Z": "kept"}, "baselines": {"ds__one": "20260101T000000Z"}}))
        assert nasute.run_meta(cfg) == {"labels": {"20260102T000000Z": "kept"}, "baselines": {"ds@one": "20260101T000000Z"}}
        assert nasute.reference_run(cfg, nasute.summaries(cfg), "20260103T000000Z") == "20260101T000000Z"
        nasute.save_meta(cfg, nasute.run_meta(cfg))
        assert "ds__one" not in (Path(cfg["runs"]) / "index.json").read_text()
    # E: a symlinked marker file, or asset file, cannot redirect a write
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = new_cfg(tmp)
        fake_run(cfg, "20260101T000000Z", d, five(0.5), target="one")
        (tmp / "outside.txt").write_text("keep")
        out = tmp / "report"
        (out / "ds@one").mkdir(parents=True)
        (out / "ds@one" / ".nasute-suite").symlink_to(tmp / "outside.txt")
        try:
            nasute.report(cfg)
            raise AssertionError("a symlinked marker should stop the report")
        except SystemExit:
            pass
        assert (tmp / "outside.txt").read_text() == "keep"
        (out / "ds@one" / ".nasute-suite").unlink()
        (out / "assets").mkdir(exist_ok=True)
        (out / "assets" / "report.css").unlink(missing_ok=True)
        (out / "assets" / "report.css").symlink_to(tmp / "outside.txt")
        try:
            nasute.report(cfg)
            raise AssertionError("a symlinked asset should stop the report")
        except SystemExit:
            pass
        assert (tmp / "outside.txt").read_text() == "keep"

    # 13: with no dataset named, the one dataset made for the target is used; the judge set likewise
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, target in (("mine-q", "mine"), ("other-q", "other"), ("mine-q2", "mine"), ("jset", "judge")):
            (tmp / "datasets" / name).mkdir(parents=True)
            (tmp / "datasets" / name / "v1.jsonl").write_text(json.dumps({"dataset": name, "target": target}) + "\n")
        cfg = {**nasute.DEFAULTS, "datasets": [str(tmp / "datasets")]}
        assert manage.only_dataset(cfg, "other") == "other-q" and manage.only_dataset(cfg, "judge") == "jset"
        for target in ("mine", "nope", ""):
            try:
                manage.only_dataset(cfg, target)
                raise AssertionError("two or no datasets: it must ask")
            except SystemExit as e:
                assert "which dataset?" in str(e) and (target != "mine" or "mine-q, mine-q2" in str(e)), str(e)
        # the datasets that come with Nasute: one for the demo target, one judge set
        s = nasute.DEFAULTS
        assert s["dataset"] == "" and manage.only_dataset(s, "judge") == "judge-demo" and manage.only_dataset(s, "demo") == "demo"


def interval_checks():
    for groups in ([[1], [0], [1]], [[0.0], [0.5], [1.0]], [[1, 1], [1, 0], [0.9, 1]]):   # few questions: the normal range would spill past 0 or 1
        lo, hi = nasute.stats(groups)["ci"]
        assert 0 <= lo <= hi <= 1, (groups, lo, hi)
    for v in (0.1, 0.2, 0.7):   # all equal but not 0 or 1: rounding must not hide the "no spread" case
        ci = nasute.stats([[v], [v], [v]])["ci"]
        assert ci[0] < v - 0.05 and ci[1] > v + 0.05, (v, ci)
    assert nasute.needed_questions(1e-17, 0.05) is None
    # no spread: a Wilson interval with n = questions, not a zero-width one
    s = nasute.stats([[1.0]] * 27)
    assert close(s["ci"][1], 1.0) and 0.86 < s["ci"][0] < 0.88, s
    # 2 questions x 3 repeats, all passing: the same as 2 independent questions, not as 6
    assert nasute.stats([[1, 1, 1], [1, 1, 1]], binary=True)["ci"] == nasute.stats([[1], [1]], binary=True)["ci"] == [round(x, 4) for x in nasute.wilson(1.0, 2)]
    # real spread still uses the normal interval
    s = nasute.stats([[0.0], [1.0], [0.5], [0.5]])
    assert abs(s["ci"][0] - (s["mean"] - nasute.Z * s["se"])) < 1e-3, s


def power_checks():
    cfg = {"detect": 0.05}
    assert nasute.power([[1.0]] * 27, cfg) is None and nasute.power([[1.0, 1.0]] * 5, cfg) is None   # no spread: cannot estimate
    assert nasute.power([[0.0], [1.0], [0.5]], cfg)["needed"] > 1 and nasute.power([[0.0, 1.0]] * 3, cfg)["basis"] == "repeats"


def http_usage_check():
    from nasute.targets import http
    reply = {"choices": [{"message": {"content": "Iron."}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3, "cost": 0.00002}}
    cfg = {"url": "http://x", "answer": "$.choices[0].message.content", "tokens_in": "$.usage.prompt_tokens",
           "tokens_out": "$.usage.completion_tokens", "cost": "$.usage.cost"}
    real = http.urllib.request.urlopen
    class Fake:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return json.dumps(self.body).encode()
    try:
        http.urllib.request.urlopen = lambda req, timeout=None: Fake(reply)
        got = http.ask("q", cfg, 5)
        assert got["answer"] == "Iron." and got["tokens_in"] == 12 and got["tokens_out"] == 3 and got["cost"] == 0.00002, got
        got = http.ask("q", {**cfg, "cost": "$.usage.nothing"}, 5)
        assert got["cost"] is None and got["error"] is None, got
        got = http.ask("q", {"url": "http://x", "answer": "$.choices[0].message.content"}, 5)
        assert got["tokens_in"] is None and got["cost"] is None, got
    finally:
        http.urllib.request.urlopen = real


def docs_checks():
    """The pages in docs/ agree with the code: every relative link lands, every command parses, scores, prompts and settings match."""
    import argparse
    import contextlib
    import io
    import re
    import shlex
    docs = ROOT / "docs"
    pages_md = sorted(docs.rglob("*.md"))
    text = {p: p.read_text() for p in pages_md}
    for p, body in text.items():
        for target in re.findall(r"\]\(([^)\s]+)\)", re.sub(r"```.*?```", "", body, flags=re.S)):
            if re.match(r"[a-z]+:", target):
                continue
            path = (p.parent / target.split("#")[0]).resolve()
            assert path.exists(), f"{p.relative_to(docs)}: broken link {target}"
        assert body.startswith("[Start here]") and "\n---\n\n" in body[-200:], f"{p.relative_to(docs)}: nav line or footer missing"
    # every `nasute ...` command in a code block parses; the parser is caught from main(), where it is built
    class Caught(Exception):
        pass
    real = argparse.ArgumentParser.parse_args
    def grab(self, args=None, namespace=None):
        raise Caught(self)
    argparse.ArgumentParser.parse_args = grab
    try:
        try:
            nasute.main([])
        except Caught as c:
            parser = c.args[0]
    finally:
        argparse.ArgumentParser.parse_args = real
    seen = 0
    for p, body in text.items():
        for block in re.findall(r"```(?:bash|text)?\n(.*?)```", body, flags=re.S):
            for line in block.splitlines():
                line = line.split("  #")[0].strip()
                if not line.startswith("nasute ") or re.search(r"\[|\||\.\.\.|<", line):   # synopses with placeholders are skipped
                    continue
                words = shlex.split(line)[1:]
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        real(parser, words)
                except SystemExit:
                    raise AssertionError(f"{p.relative_to(docs)}: this command does not parse: {line}")
                seen += 1
    assert seen > 10, seen
    # scores.md holds the glossary word for word
    scores = text[docs / "reference" / "scores.md"]
    for m, g in nasute.GLOSSARY.items():
        for part in (g["term"], g["plain"], g["formula"]):
            assert part in scores, f"scores.md is missing {m}: {part}"
    # judge-prompts.md holds the prompts word for word
    prompts = text[docs / "reference" / "judge-prompts.md"]
    for name in ("QUICK_ASK", "SPLIT_ASK", "CHECK_ASK", "KNOWLEDGE_ASK", "KNOWLEDGE_ABSTAIN_ASK", "ABSTAIN_ASK"):
        assert getattr(nasute, name).strip() in prompts, f"judge-prompts.md differs from {name}"
    # settings.md names every setting
    settings = text[docs / "reference" / "settings.md"]
    for key in [k for k, v in nasute.DEFAULTS.items() if not isinstance(v, dict)] + list(nasute.DEFAULTS["judge"]):
        assert f"`{key}`" in settings, f"settings.md does not mention {key}"


def version_checks():
    """Dataset versions are major.minor.patch: old file names still load, they sort as numbers, --version takes a prefix, and an import earns its bump."""
    with tempfile.TemporaryDirectory() as tmp:
        ds = Path(tmp) / "d"
        ds.mkdir()
        for n in ("v2.jsonl", "v1.9.0.jsonl", "v1.10.0.jsonl", "v1.10.1.jsonl", "notes.jsonl", "v1.x.jsonl"):
            (ds / n).write_text('{"dataset": "d", "target": "t"}\n')
        cfg = {**nasute.DEFAULTS, "datasets": [tmp]}
        found = nasute.versions_of(cfg, "d")
        assert sorted(found) == [(1, 9, 0), (1, 10, 0), (1, 10, 1), (2, 0, 0)], found   # v2.jsonl is 2.0.0; 1.10.0 is after 1.9.0; odd names are ignored
        find = lambda v=None: nasute.find_dataset(cfg, "d", v)[1]
        assert find() == (2, 0, 0) and find("2") == (2, 0, 0) and find("1") == (1, 10, 1) and find("1.9") == (1, 9, 0) and find("1.10.0") == (1, 10, 0) and find(2) == (2, 0, 0)
        for bad in ("3", "1.11", "x", "1.2.3.4"):
            try:
                find(bad)
            except SystemExit:
                continue
            raise AssertionError(bad)
        assert [nasute.vtext(v) for v in ((1, 2, 0), 2, "1.2.0")] == ["1.2.0", "2.0.0", "1.2.0"]   # an old run stored the plain number
        assert nasute.load_dataset(ds / "v2.jsonl", (2, 0, 0))[2]["version"] == "2.0.0"
    q = lambda i, **kw: {"id": i, "question": f"Q{i}?", "reference": "R", "tags": [], **kw}
    old = [q("a"), q("b", difficulty="easy")]
    cases = [("major", [q("a")]), ("major", [q("a"), q("b", reference="other")]), ("major", [q("a"), q("b", answerable=False)]), ("minor", old + [q("c")]), ("patch", [q("a"), q("b", difficulty="hard", tags=["x"])])]
    for part, new in cases:
        assert manage.bump(old, new)[0] == part, (part, new)
    assert manage.bump(old, [q("a"), q("b", difficulty="easy"), q("c")]) == ("minor", "1 questions added")
    try:   # an explicit default (answerable: true, empty lists) is not a change
        manage.bump([q("a", answerable=True, sources=[])], [{"id": "a", "question": "Qa?", "reference": "R"}])
        raise AssertionError("same questions should not make a version")
    except SystemExit as e:
        assert "nothing changed" in str(e)
    assert [manage.bump_version((1, 2, 3), p) for p in ("major", "minor", "patch")] == [(2, 0, 0), (1, 3, 0), (1, 2, 4)] and manage.bump_version(None, "major") == (1, 0, 0)


def chart_export_link_checks():
    """The suite page's question charts, the exports beside each run, and the source links."""
    import csv
    import io
    import re
    import shutil
    import subprocess
    from nasute.targets import http
    js = (PKG / "assets" / "report.js").read_text()
    page_data = lambda path: json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', path.read_text(), re.S).group(1))

    # the chart helpers, run with node on their own: quartiles and whiskers against a hand-worked example, the jitter, the link rule
    # 1..8 and 100: quartiles 3 and 7 (linear), box length 4, fences -3 and 13, so the whiskers end at 1 and 8 and 100 is an outlier
    if shutil.which("node"):
        block = js[js.index("// stats:start"):js.index("// stats:end")]
        qfn = js[js.index("// One entry per question"):js.index("function run() {")]   # `questions`, with the SCORES it reads
        script = js[js.index("const SCORES = "):js.index("\n", js.index("const SCORES = "))] + "\n" + qfn + block + """
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(m + ": " + JSON.stringify(a) + " != " + JSON.stringify(b)); };
const s = boxStats([100, 1, 2, 3, 4, 5, 6, 7, 8]);
eq([s.n, s.q1, s.median, s.q3, s.lo, s.hi, s.mean, s.out], [9, 3, 5, 7, 1, 8, 136 / 9, 1], "box");
eq(boxStats([0.5]).median, 0.5, "one value");
eq([pageRange(0, 1), pageRange(120, 3), pageRange(120, 9), pageRange(120, 0), pageRange(120, NaN), pageRange(50, 1), pageRange(51, 2), pageRange(7, -4, 5)].map(r => [r.page, r.pages, r.from, r.to]),
  [[1, 1, 0, 0], [3, 3, 100, 120], [3, 3, 100, 120], [1, 3, 0, 50], [1, 3, 0, 50], [1, 1, 0, 50], [2, 2, 50, 51], [1, 2, 0, 5]], "paging stays inside the list");
const qn = questions([{ id: "b", scores: { hit: 1 }, tags: [], difficulty: "easy" }, { id: "a", scores: { hit: 0 }, tags: [], difficulty: "easy" }, { id: "b", scores: { hit: 0 }, tags: [], difficulty: "easy" }], new Map());
eq(qn.map(q => [q.id, q.n, q.means.hit, q.reps.length]), [["b", 1, 0.5, 2], ["a", 2, 0, 1]], "numbers follow the file, repeats join their question");
const t = boxStats([0, 0, 0, 0, 0.005]);   // the plugin's own rule would have drawn the whisker through 0.005; ours (and so the chart) says 0 with one outlier
eq([t.hi, t.out, t.max], [0, 1, 0.005], "outlier next to a flat box");
eq(quantile([1, 2, 3, 4], 0.25), 1.75, "linear quartile");
for (const v of [0, 0.25, 0.5, 0.75, 1]) for (const id of ["a", "b", "q-9"]) {
  const x = nudge(v, id, "x"); if (x < 0 || x > 1 || !(v >= 0.5 ? x >= 0.5 : x <= 0.5)) throw new Error("nudge left its side: " + v + " -> " + x);
  eq(x, nudge(v, id, "x"), "same every time");
}
eq(nudge(0.7, "a", "x") === nudge(0.7, "b", "x"), false, "different ids spread");
// outcomes, as the run page and the compare grid word them: a system error on every attempt wins; a question with no answer is declined or not
eq([outcome(1, 0, 0, 1), outcome(0.5, 0, 0, 1, "knowledge"), outcome(0.5, 0, 0, 1, "quick"), outcome(0, 0, 0, 1), outcome(0, 0, 1, 1), outcome(0.5, 0, 1, 2), outcome(null, 0, 0, 1)].map(o => o.word),
  ["right", "right, with an error", "partly right", "wrong", "system error", "partly right", "not judged"], "outcomes");
eq([outcome(1, 1, 0, 1), outcome(0.5, 1, 0, 1), outcome(0, 1, 0, 1)].map(o => [o.word, o.cls]), [["declined", "good"], ["declined, with an error", "part"], ["made something up", "bad"]], "declined or not");
eq(outcome(0.8, 0, 0, 1, "quick", 0.9).word, "partly right", "pass_at is the line for right");
// at a glance: outcome counts per group come from the same outcome the list shows, made-up questions and system errors included
const og = (id, difficulty, rows) => rows.map(r => ({ id, repeat: 1, tags: [], difficulty, answer: "", question: "", ...r }));
const gq = questions([...og("a", "easy", [{ scores: { correctness: 1 } }]), ...og("b", "easy", [{ scores: { correctness: 0 } }]), ...og("c", "hard", [{ scores: { abstention: 0 }, answerable: false }]),
  ...og("d", "hard", [{ scores: { correctness: 0 }, error: "Timeout" }]), ...og("e", "hard", [{ scores: { abstention: 1 }, answerable: false }]), ...og("f", "hard", [{ scores: { correctness: 0.5 } }])], new Map(), new Set(), "knowledge");
eq(outcomeCounts(gq, q => [q.difficulty]), [["easy", { right: 1, wrong: 1 }], ["hard", { "made something up": 1, "system error": 1, declined: 1, "right, with an error": 1 }]], "outcomes per group");
eq(outcomeCounts(gq, () => ["all"])[0][1]["system error"], 1, "one bar when difficulty is unknown");
eq(outcomeCounts([{ out: { word: "right" } }], () => ["x", "y"]).map(g => g[0]), ["x", "y"], "a question in two groups counts in both");
// strip or box: a group of scores with three values or fewer is a strip; otherwise a box from four, else dots; seconds are never a strip
eq([distKind([0, 0.5, 1, 1, 1], true), distKind([1], true), distKind([0, 0.25, 0.5, 1], true), distKind([0, 0.25, 0.5, 0.75, 1], true), distKind([0.2, 0.4, 0.6], false), distKind([1, 1, 1, 1], false), distKind([1, 2], false)],
  ["strip", "strip", "box", "box", "dots", "box", "dots"], "strip or box");
// hide rules: the score chart needs two questions, the others a value, the scatter a question with both a score and seconds
eq(distCharts(gq, "correctness"), ["score"], "no timing: score only");
const tq = questions(og("a", "easy", [{ scores: { correctness: 1 }, total_s: 2, cost: null }, { scores: { correctness: 0 }, total_s: 4 }]), new Map());
eq([tq[0].per.seconds, tq[0].per.cost, tq[0].per.tokens], [3, null, null], "per-question means of what was measured");
eq(distCharts(tq, "correctness"), ["seconds", "speed"], "one question: no score chart; no cost or tokens: none of those");
eq(distCharts(tq, "abstention"), ["seconds"], "the scatter needs the score too");
eq(distCharts([], undefined), [], "nothing to draw");
eq([enough([], "c"), enough([{ metrics: { c: { mean: 1 } } }], "c"), enough([{ metrics: { c: { mean: 1 } } }, { metrics: { c: { mean: null } } }], "c"), enough([{ metrics: { c: { mean: 1 } } }, { metrics: { c: { mean: 0 } } }], "c")],
  [false, false, false, true], "over time needs two runs that measured the score");
// comparing: runs on two datasets are never like for like; two versions of one dataset are, by name, but not by file
const R = (name, sha) => ({ dataset: { name, sha256: sha } });
eq([likeForLike([R("a", 1), R("a", 1)]), likeForLike([R("a", 1), R("b", 2)]), likeForLike([R("a", 1), R("a", 2)]), likeForLike([R("a", 1), R("a", 2)], true)], [true, false, true, false], "like for like");
for (const [u, ok] of [["https://a.org/x", true], ["http://a.org", true], ["/wiki/content/b/p", true], ["javascript:alert(1)", false], ["data:text/html,x", false], ["//evil.org/x", false], ["/" + String.fromCharCode(92) + "evil.org", false],
  ["  https://a.org", false], ["HTTPS://A.ORG/x", true], ["ftp://a.org", false], ["", false], [null, false], [5, false], ["https://", false], ["vbscript:x", false]]) eq(safeUrl(u) !== null, ok, "safeUrl " + u);
"""
        r = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    d = {"name": "ds", "version": 1, "sha256": "aaa"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report"), "targets": {"t": {"kind": "http", "label": "The System", "headers": {"Authorization": "SECRETVALUE"}, "url": "http://secret.host/x"}}}
        scores = {"q0": {"correctness": 1.0, "faithfulness": 0.5, "hit": 1.0}, "q1": {"correctness": 0.0, "hit": 0.0}}
        fake_run(cfg, "20260101T000000Z", d, scores, target="t", judge_model="jm")
        fake_run(cfg, "20260102T000000Z", d, scores, target="t", judge_model="jm", answering_model="m")
        # a summary as an older version of the code might have saved it, with a header value in it: the copy must not carry it
        sp = Path(cfg["runs"]) / "20260102T000000Z" / "summary.json"
        s = json.loads(sp.read_text())
        s["settings"] = {"targets": {"t": {"headers": {"Authorization": "SECRETVALUE"}, "api_key": "SECRETKEY"}}}
        sp.write_text(json.dumps(s))
        nasute.report(cfg)
        out = tmp / "report" / "ds@t"
        # beside each run page: CSV (one row per attempt), results, summary
        for run in ("20260101T000000Z", "20260102T000000Z"):
            for suffix in (".csv", ".results.jsonl", ".summary.json"):
                assert (out / "runs" / (run + suffix)).exists(), (run, suffix)
        rows = list(csv.reader(io.StringIO((out / "runs" / "20260102T000000Z.csv").read_text())))
        assert rows[0] == nasute.RUN_COLUMNS and rows[0][:6] == ["run", "id", "repeat", "tags", "difficulty", "answerable"] and rows[0][-3:] == ["question", "reference", "answer"], rows[0]
        r0 = dict(zip(rows[0], rows[1]))
        assert (r0["run"], r0["id"], r0["repeat"], r0["tags"], r0["difficulty"], r0["answerable"], r0["correctness"], r0["faithfulness"], r0["context_recall"], r0["question"], r0["answer"]) == \
            ("20260102T000000Z", "q0", "1", "t", "easy", "True", "1.0", "0.5", "", "Question q0?", "Answer to q0") and len(rows) == 3, r0
        assert dict(zip(rows[0], rows[2]))["cause"] in ("retrieval", "generation", "judge?", "system", "")   # the cause column is filled from the summary
        text = (out / "runs" / "20260102T000000Z.summary.json").read_text()
        assert "SECRETVALUE" not in text and "SECRETKEY" not in text and json.loads(text)["settings"]["targets"]["t"]["headers"] == ["Authorization"], text
        assert "SECRET" not in "".join(f.read_text() for f in (tmp / "report").rglob("*") if f.is_file() and f.suffix in (".csv", ".json", ".jsonl", ".html")) and "secret.host" not in (tmp / "report" / "index.html").read_text()
        # ids, tags, difficulty and model names are text cells too
        rows_ = [json.loads(x) for x in (Path(cfg["runs"]) / "20260102T000000Z" / "results.jsonl").read_text().splitlines()]
        rows_[0].update(id="=HYPERLINK(1)", tags=["+cmd", "ok"], difficulty="@sum")
        summ = {**json.loads(sp.read_text()), "answering_model": "-model", "judge_model": "=judge", "target": "@t"}
        buf = io.StringIO()
        nasute.run_csv(summ, rows_, buf)
        r1 = dict(zip(nasute.RUN_COLUMNS, list(csv.reader(io.StringIO(buf.getvalue())))[1]))
        assert r1["id"] == "'=HYPERLINK(1)" and r1["tags"] == "'+cmd;ok" and r1["difficulty"] == "'@sum", r1
        buf = io.StringIO()
        nasute.suite_csv([(summ, rows_)], buf)
        r2 = dict(zip(nasute.SUITE_COLUMNS, list(csv.reader(io.StringIO(buf.getvalue())))[1]))
        assert (r2["id"], r2["tags"], r2["target"], r2["answering_model"], r2["judge_model"]) == ("'=HYPERLINK(1)", "'+cmd;ok", "'@t", "'-model", "'=judge"), r2
        # a spreadsheet formula in an answer is kept as text
        assert nasute.csv_safe("=1+1") == "'=1+1" and nasute.csv_safe("plain") == "plain" and nasute.csv_safe("-5 degrees") == "'-5 degrees"
        # the suite CSV: one row per question per run
        sc = list(csv.reader(io.StringIO((out / "runs.csv").read_text())))
        assert sc[0] == nasute.SUITE_COLUMNS and len(sc) == 1 + 2 * 2 and dict(zip(sc[0], sc[-1]))["id"] == "q1" and dict(zip(sc[0], sc[1]))["target"] == "t" and dict(zip(sc[0], sc[2]))["correctness"] == "0.0" and dict(zip(sc[0], sc[1]))["dataset_version"] == "1.0.0", sc[:3]
        # the CLI writes the same text
        conf = tmp / "nasute.toml"
        conf.write_text(f'runs = "{tmp / "runs"}"\nreport = "{tmp / "report"}"\n[targets.t]\nkind = "http"\nurl = "http://x"\n')
        code, printed = cli(conf, "runs", "export", "20260102")
        assert code == 0 and printed == (out / "runs" / "20260102T000000Z.csv").read_text().replace("\r\n", "\n"), printed[:200]
        code, _ = cli(conf, "runs", "export", "20260102", "--csv", str(tmp / "o.csv"))
        assert code == 0 and (tmp / "o.csv").read_text() == (out / "runs" / "20260102T000000Z.csv").read_text()
        code, printed = cli(conf, "runs", "export", "--suite", "ds@t")
        assert code == 0 and printed.splitlines()[0] == ",".join(nasute.SUITE_COLUMNS)
        assert cli(conf, "runs", "export")[0] != 0 and cli(conf, "runs", "export", "--suite", "nope@x")[0] != 0
        # the download links are in the page script, as plain relative <a download> links
        assert '`${S.run}.csv`' in js and '`${S.run}.results.jsonl`' in js and '`${S.run}.summary.json`' in js and 'runs.csv`' in js and js.count("download:") >= 4
        # the question charts: only on the run page
        run = page_data(out / "runs" / "20260102T000000Z.html")
        assert run["suite"]["target_label"] == "The System" and "causes" in run["summary"]
        assert (out / "runs" / "20260102T000000Z.html").read_text().count("chart.umd.min.js") == 1 and "chart.umd.min.js" not in (tmp / "report" / "index.html").read_text() and "chart.umd.min.js" not in (tmp / "report" / "datasets" / "ds.html").read_text()
        ov = page_data(tmp / "report" / "index.html")
        assert ov["runs"][0]["target_label"] == "The System" and "SECRET" not in json.dumps(ov) and "secret.host" not in json.dumps(ov) and "Authorization" not in json.dumps(ov)
        assert (PKG / "assets" / "chart.umd.min.js").exists() and (PKG / "assets" / "chartjs-chart-boxplot.umd.min.js").exists() and (tmp / "report" / "assets" / "chart.umd.min.js").exists()

    # source links: the http target reads them from a path, parallel to the sources
    class Reply:
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def __iter__(self):
            return iter(self.body.splitlines(True))
        def read(self):
            return self.body.encode()
    real = http.urllib.request.urlopen
    reply = {"a": "A", "s": [{"t": "One", "u": "https://x.org/1"}, {"t": "Two", "u": ""}, {"t": "Three", "u": "javascript:alert(1)"}]}
    http.urllib.request.urlopen = lambda req, timeout=0: Reply(json.dumps(reply))
    try:
        got = http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.s[*].t", "links": "$.s[*].u"}, 5)
        assert got["sources"] == ["One", "Two", "Three"] and got["links"] == ["https://x.org/1", None, "javascript:alert(1)"], got   # stored as given; the report decides what is safe to follow (tested above with node)
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.s[*].t"}, 5)["links"] == []
        # a title and an address are read from the same object: an address can never move to a neighbour, even when the counts happen to match
        reply["s"] = [{"t": "Alpha"}, {"u": "https://other.example/beta"}]
        got = http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.s[*].t", "links": "$.s[*].u"}, 5)
        assert got["sources"] == ["Alpha"] and got["links"] == [None], got
        reply["s"] = [{"t": "A", "u": "https://x.org/a"}, {"t": "B"}]
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.s[*].t", "links": "$.s[*].u"}, 5)["links"] == ["https://x.org/a", None]
        reply.update(titles=["A", "B"], urls=["https://x.org/a", "https://x.org/b"])   # two plain lists: paired by position when they are the same length
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.titles", "links": "$.urls"}, 5)["links"] == ["https://x.org/a", "https://x.org/b"]
        reply["urls"] = ["https://x.org/b"]
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.titles", "links": "$.urls"}, 5)["links"] == []
        reply.update(titles=[None, "Beta"], urls=["https://x.org/alpha"])   # a missing title must not let Beta take Alpha's address
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.titles", "links": "$.urls"}, 5)["links"] == []
        reply["urls"] = ["https://x.org/alpha", "https://x.org/beta"]
        assert http.ask("q", {"url": "http://x", "answer": "$.a", "sources": "$.titles", "links": "$.urls"}, 5)["links"] == ["https://x.org/beta"]
    finally:
        http.urllib.request.urlopen = real
    # an old result with no links still renders: the page reads them as optional
    assert "(links || [])[i]" in js and "r.links || []" in js


def label_checks():
    """`run --label` and `runs label` share one store, and the suite page's runs carry the label (the charts mark them)."""
    import re
    d = {"name": "ds", "version": 1, "sha256": "aaa"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report")}
        fake_run(cfg, "20260101T000000Z", d, {"q0": {"correctness": 1.0, "hit": 1.0}}, target="t")
        fake_run(cfg, "20260102T000000Z", d, {"q0": {"correctness": 0.5, "hit": 1.0}}, target="t")
        nasute.set_label(cfg, "20260102T000000Z", "prompt change")
        assert nasute.run_meta(cfg)["labels"] == {"20260102T000000Z": "prompt change"}
        nasute.report(cfg)
        data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', (tmp / "report" / "datasets" / "ds.html").read_text(), re.S).group(1))
        assert [r["label"] for r in data["runs"]] == ["", "prompt change"]
        nasute.set_label(cfg, "20260102T000000Z", "")
        assert nasute.run_meta(cfg)["labels"] == {}
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                nasute.main(["run", "--label", "x", "--help"])
            except SystemExit as e:
                assert e.code == 0
        assert "--label" in (ROOT / "docs" / "reference" / "commands.md").read_text()


def dashboard_checks():
    """The dashboard, the dataset page and the run page: scores with nothing to show are left out, the old suite address
    still leads somewhere, and runs on one dataset carry what the browser needs to compare them."""
    import re
    page_data = lambda path: json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', path.read_text(), re.S).group(1))
    # a system error in knowledge mode scores 0 only on what that mode measures: no faithfulness (it once showed as 0.00)
    real = nasute.TARGETS.get("fake")
    nasute.TARGETS["fake"] = lambda q, tcfg, timeout: {"answer": "", "sources": [], "extracts": [], "first_text_s": None, "total_s": 0, "error": "TimeoutError: slow"}
    try:
        cfg = nasute.merge(nasute.DEFAULTS, {"judge": {"mode": "knowledge"}})
        rows = nasute.attempts(cfg, "fake", {"id": "x", "question": "Q?", "reference": "r", "sources": ["S"], "answerable": True, "tags": [], "difficulty": "easy"}, {})
        assert rows[0]["scores"]["faithfulness"] is None and rows[0]["scores"]["correctness"] == 0.0 and rows[0]["scores"]["relevancy"] == 0.0, rows[0]["scores"]
    finally:
        nasute.TARGETS["fake"] = real
    # measured: strict zeros alone, or source scores from a system that names no source, are not measured; error rate always is
    r = lambda err=None, sources=(), **s: {"error": err, "sources": list(sources), "scores": {m: s.get(m) for m in nasute.METRICS}}
    assert nasute.measured([r(correctness=1.0, hit=0.0, error_rate=0.0), r("x", correctness=0.0, faithfulness=0.0, hit=0.0, error_rate=1.0)]) == ["correctness", "error_rate"]
    assert nasute.measured([r(sources=["A"], hit=0.0, correctness=1.0, error_rate=0.0)]) == ["hit", "correctness", "error_rate"]   # a real miss is a score
    assert nasute.measured([r("x", correctness=0.0, error_rate=1.0)]) == ["correctness", "error_rate"]   # every attempt failed: the zeros are all there is

    d1, d2 = {"name": "ds", "version": 1, "sha256": "aaa"}, {"name": "other", "version": 1, "sha256": "bbb"}
    five = lambda x, **more: {f"q{i}": {"correctness": x, "hit": 0.0, "error_rate": 0.0, **more} for i in range(5)}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report"), "targets": {"rag": {"label": "The RAG"}, "chat": {}}}
        fake_run(cfg, "20260101T000000Z", d1, five(0.5), target="rag", usage={"cost": 0.01, "per_answer": {"cost": 0.002}})
        fake_run(cfg, "20260102T000000Z", d1, five(0.7), target="rag")
        fake_run(cfg, "20260103T000000Z", d1, {**five(0.9), "q4": {"correctness": 0.0, "faithfulness": 0.0, "hit": 0.0, "error_rate": 1.0, "error": "TimeoutError"}}, target="chat")
        fake_run(cfg, "20260104T000000Z", d2, five(1.0), target="chat")
        nasute.report(cfg)
        out = tmp / "report"
        # the run page: hit (no sources named) and faithfulness (only on the failed attempt) are gone, from the scores and the rows
        run = page_data(out / "ds@chat" / "runs" / "20260103T000000Z.html")
        assert run["summary"]["measured"] == ["correctness", "error_rate"] and run["summary"]["metrics"]["hit"]["mean"] is None and run["summary"]["metrics"]["faithfulness"]["mean"] is None
        assert all(x["scores"]["hit"] is None and x["scores"]["faithfulness"] is None for x in run["rows"]) and run["summary"]["metrics"]["correctness"]["mean"] is not None
        assert json.loads((out / "ds@chat" / "runs" / "20260103T000000Z.summary.json").read_text())["metrics"]["hit"]["mean"] == 0.0   # the download keeps what was saved
        # the dataset page: every run of both systems, each with a question-by-question entry; a pair of runs on the same file has its paired test
        ds = page_data(out / "datasets" / "ds.html")
        assert [x["run"] for x in ds["runs"]] == ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z"] and {s["target"] for s in ds["systems"]} == {"rag", "chat"}
        assert ds["grid"]["20260103T000000Z"]["q4"] == [0.0, 0, 1, 1] and ds["grid"]["20260101T000000Z"]["q0"] == [0.5, 0, 0, 1] and ds["questions"]["q0"] == "Question q0?"
        pair = ds["paired"]["20260101T000000Z 20260102T000000Z"]
        assert pair["shared"] == 5 and pair["metrics"]["correctness"]["delta"] > 0 and "hit" not in pair["metrics"] and len(ds["paired"]) == 3, pair
        assert ds["runs"][0]["usage"]["per_answer"]["cost"] == 0.002 and ds["runs"][0]["answer_s"] == 2.0 and ds["runs"][0]["target_label"] == "The RAG"
        # the dashboard: each dataset with its systems' latest runs; recent runs newest first, across datasets
        ov = page_data(out / "index.html")
        assert [(d["name"], d["href"], d["runs"], [x["run"] for x in d["latest"]]) for d in ov["datasets"]] == [("ds", "datasets/ds.html", 3, ["20260102T000000Z", "20260103T000000Z"]), ("other", "datasets/other.html", 1, ["20260104T000000Z"])]
        assert [x["run"] for x in ov["runs"]] == ["20260104T000000Z", "20260103T000000Z", "20260102T000000Z", "20260101T000000Z"] and ov["runs"][0]["dataset"]["name"] == "other"
        # the old suite address sends the reader on, with the system named so the over-time charts open on it
        old = (out / "ds@rag" / "index.html").read_text()
        assert 'http-equiv="refresh" content="0; url=../datasets/ds.html#system=rag"' in old and "<script" not in old
        assert (out / "ds@rag" / "runs.csv").exists()
        # the page script hides what has nothing in it: the scatter without faithfulness, over-time charts under two runs
        js = (PKG / "assets" / "report.js").read_text()
        assert "q.means.faithfulness != null && q.means.correctness != null) ? scatterFigure" in js and "enough(rs, k)" in js and "sys = D.systems.filter(s => twoPlus(" in js


def init_demo_checks():
    """`nasute init --demo` writes settings that point at the demo server, so the quick start needs no editing."""
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        assert nasute.main(["init", f"{tmp}/d", "--demo"]) is None
        cfg = nasute.load_settings(f"{tmp}/d/nasute.toml")
        assert cfg["targets"]["mine"]["url"] == "http://127.0.0.1:8700/ask" and cfg["judge"]["url"] == "http://127.0.0.1:8700/v1" and cfg["targets"]["mine"]["sources"] == "$.sources[*].title"
        assert nasute.main(["init", f"{tmp}/e"]) is None and nasute.load_settings(f"{tmp}/e/nasute.toml")["targets"]["mine"]["url"] == "http://127.0.0.1:8000/ask"


def logging_checks():
    """How a run reads at a terminal and to a log reader, and the summary it ends with."""
    import io
    import logging
    rec = lambda event, level=logging.INFO, **d: logging.LogRecord("x", level, __file__, 1, event, None, None) if not d else setattr(r := logging.LogRecord("x", level, __file__, 1, event, None, None), "details", d) or r
    plain = nasute.Readable(colour=False)
    assert plain.format(rec("question_done", n=3, of=24, id="gold-79", repeat=1, repeats=1, outcome="right", error=None, judge_error=None, total_s=2.1)) == "[3/24] gold-79 ... right (2.1 s)"
    line = plain.format(rec("question_done", logging.WARNING, n=4, of=24, id="q9", repeat=2, repeats=3, outcome="system error", error="TimeoutError: slow", judge_error=None, total_s=180))
    assert line == "WARNING [4/24] q9 (repeat 2) ... system error: TimeoutError: slow (180 s)", line
    assert nasute.Readable(colour=True).format(rec("run_aborted", logging.ERROR, run="r", why="down")).startswith("\033[31;1mERROR\033[0m run aborted: run r, why down")
    assert plain.format(rec("odd_event", note=1)) == "odd event: note 1" and plain.format(rec("question_done", id="x")).startswith("question_done: ")   # missing details still print
    assert json.loads(nasute.JsonLines().format(rec("question_done", id="x", n=1)))["event"] == "question_done"
    # the look: asked for, else NASUTE_LOG, else text at a terminal and JSON lines anywhere else (the tests' stdout is not a terminal)
    import os
    was = os.environ.pop("NASUTE_LOG", None)
    try:
        assert nasute.setup_logging("text") == "text" and isinstance(logging.getLogger().handlers[0].formatter, nasute.Readable)
        os.environ["NASUTE_LOG"] = "json"
        assert nasute.setup_logging() == "json" and isinstance(logging.getLogger().handlers[0].formatter, nasute.JsonLines)
        del os.environ["NASUTE_LOG"]
        tty = sys.stdout.isatty()
        assert nasute.setup_logging() == ("text" if tty else "json") and len(logging.getLogger().handlers) == 1
    finally:
        nasute.setup_logging("json")
        if was is not None:
            os.environ["NASUTE_LOG"] = was
    # outcome words, the same rule as the page script's outcome()
    row = lambda c=None, a=None, err=None, answerable=True: {"error": err, "answerable": answerable, "scores": {"correctness": c, "abstention": a}}
    assert [nasute.outcome_word(x, 0.75, "knowledge") for x in (row(1.0), row(0.5), row(0.0), row(err="x"), row(a=1.0, answerable=False), row(a=0.0, answerable=False), row())] == \
        ["right", "right, with an error", "wrong", "system error", "declined", "made something up", "not judged"]
    assert nasute.outcome_word(row(0.5), 0.75, "quick") == "partly right"
    # the summary a run ends with: measured scores with their ranges, errors, tokens and cost, and the link to its page
    base = lambda i: {"id": i, "repeat": 1, "tags": ["t"], "difficulty": "easy", "judge_error": None, "reasons": {}, "judge_detail": None, "answerable": True, "first_text_s": None, "total_s": 1.0, "sources": []}
    rows = [{**base("q1"), "error": None, "scores": {**{m: None for m in nasute.METRICS}, "correctness": 1.0, "hit": 0.0, "error_rate": 0.0}},
            {**base("q2"), "error": "TimeoutError", "scores": {**{m: None for m in nasute.METRICS}, "correctness": 0.0, "hit": 0.0, "faithfulness": 0.0, "error_rate": 1.0}}]
    summary = nasute.summarise(rows, {"name": "ds", "version": 1, "sha256": "a"}, {**nasute.DEFAULTS, "profile": ""}, {"run": "20260101T000000Z", "target": "t", "total_s": 12.3, "usage": nasute.usage_totals([{"tokens_in": 10, "tokens_out": 20, "judge_cost": 0.001}])})
    summary["failures"] = [{"id": "q2", "error": "TimeoutError"}]
    lines = nasute.run_summary(summary, rows, "file:///r/ds@t/runs/20260101T000000Z.html")
    text = "\n".join(lines)
    assert "Run 20260101T000000Z finished in 12 s: 2 asked" in text and "Answer correctness  0.50  (95% range " in text and "Error rate" in text and "Hit rate" not in text and "Faithfulness" not in text, text
    assert "System errors: 1 (q2)" in text and "Used: 10 tokens in, 20 out; judging US$0.0010" in text and lines[-1] == "Report: file:///r/ds@t/runs/20260101T000000Z.html", text
    cfg = {**nasute.DEFAULTS, "report": "/tmp/r"}
    assert nasute.report_link(cfg, summary) == Path("/tmp/r/ds@t/runs/20260101T000000Z.html").resolve().as_uri()
    assert nasute.report_link({**cfg, "report_url": "https://reports.example.org/nasute/"}, summary) == "https://reports.example.org/nasute/ds@t/runs/20260101T000000Z.html"
    assert "--log" in (ROOT / "docs" / "reference" / "commands.md").read_text() and "report_url" in (ROOT / "README.md").read_text() + (ROOT / "docs" / "reference" / "settings.md").read_text()


def security_checks():
    """The 0.1.0 security audit's fixes: usage numbers, secrets in saved settings, CSV cells, serve's Host check,
    redirects to another host, the demo server's request size, and the vendored scripts' recorded SHA-256."""
    import hashlib
    import http.client
    import http.server
    import threading
    import urllib.request
    from nasute.targets import http as target_http

    # usage: NaN, Infinity and negatives are "not known", and page data stays valid JSON even for old runs that hold them
    for bad in (float("nan"), float("inf"), -1, True, "3"):
        assert not target_http.usage_number(bad), bad
    assert target_http.usage_number(0) and target_http.usage_number(12.5) and target_http.usage_number(10 ** 400)
    embedded = pages.embed({"usage": {"cost": float("nan"), "tokens": [float("inf"), 3]}})
    assert json.loads(embedded) == {"usage": {"cost": None, "tokens": [None, 3]}}, embedded

    # public(): anything under a secret-like name, at any depth; keys in URLs; ordinary names untouched
    cfg = {"targets": {"a": {"url": "https://u:DUMMY-USERINFO@api.example/ask?key=DUMMY-URL&model=x", "headers": {"Authorization": "DUMMY-HEADER"},
                             "request": {"q": "{question}", "authorization": "DUMMY-BODY", "credentials": "DUMMY-CRED", "passphrase": "DUMMY-PASS"},
                             "api_keys": ["DUMMY-LIST"], "token": {"value": "DUMMY-NESTED"}, "api_key": "DUMMY-SCALAR"}},
           "pass_at": 0.5, "judge": {"url": "http://127.0.0.1:8000/v1"}}
    out = json.dumps(nasute.public(cfg))
    assert "DUMMY" not in out, out
    shown = nasute.public(cfg)
    assert shown["pass_at"] == 0.5 and shown["judge"]["url"] == "http://127.0.0.1:8000/v1" and shown["targets"]["a"]["headers"] == ["Authorization"]
    assert shown["targets"]["a"]["url"] == "https://api.example/ask?key=(hidden)&model=(hidden)", shown["targets"]["a"]["url"]

    # CSV: a formula character after ; or tab gets an apostrophe too, as at the start
    assert nasute.csv_safe("ok;=1+1") == "ok;'=1+1" and nasute.csv_safe("a\t@SUM(1)") == "a\t'@SUM(1)" and nasute.csv_safe("=1") == "'=1"
    assert nasute.csv_safe("a; b") == "a; b" and nasute.csv_safe(3) == 3

    # serve on loopback answers only loopback names (a DNS-rebinding page would send its own)
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "index.html").write_text("hi")
        server = manage.make_server({"report": d}, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for host, want in (("127.0.0.1", 200), ("localhost", 200), ("[::1]", 200), ("127.0.0.2", 200), ("rebind.attacker.example", 421), ("", 421)):
                c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                c.putrequest("GET", "/index.html", skip_host=True)
                if host:
                    c.putheader("Host", f"{host}:{server.server_address[1]}")
                c.endheaders()
                got = c.getresponse().status
                assert got == want, (host, got)
                c.close()
        finally:
            server.shutdown()
            server.server_close()

    # any loopback address counts as this machine, so the Host check applies there too
    assert manage.loopback("127.0.0.2") and manage.loopback("::ffff:127.0.0.1") and manage.loopback("[::1]") and not manage.loopback("0.0.0.0") and not manage.loopback("example.com")
    # https to http on the same host is a downgrade: headers go no further either
    req = urllib.request.Request("https://api.example/x", headers={"Authorization": "Bearer DUMMY"})
    new = target_http.SameHostHeaders().redirect_request(req, None, 302, "Found", {}, "http://api.example/y")
    assert "Authorization" not in new.headers, new.headers

    # a redirect to another host drops the configured headers (they may hold the key); to the same host they stay
    seen = {}

    class Hop(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen[self.server.server_address[0], self.path] = self.headers.get("Authorization")
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", self.server.next_url)
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    servers = [http.server.HTTPServer((h, 0), Hop) for h in ("127.0.0.1", "127.0.0.2")]
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        a, b = servers
        for srv, target in ((a, b), (a, a)):
            srv.next_url = f"http://{target.server_address[0]}:{target.server_address[1]}/end"
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{a.server_address[1]}/start", headers={"Authorization": "Bearer DUMMY"}), timeout=5).read()
        assert seen[("127.0.0.1", "/start")] == "Bearer DUMMY" and seen[("127.0.0.2", "/end")] is None and seen[("127.0.0.1", "/end")] == "Bearer DUMMY", seen
    finally:
        for srv in servers:
            srv.shutdown()
            srv.server_close()

    # the demo server refuses a missing or huge Content-Length instead of waiting on it
    from nasute import demo_server
    srv = http.server.HTTPServer(("127.0.0.1", 0), demo_server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for length in (None, "99999999", "-5"):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.putrequest("POST", "/ask")
            if length is not None:
                c.putheader("Content-Length", length)
            c.endheaders()
            assert c.getresponse().status == 400, length
            c.close()
    finally:
        srv.shutdown()
        srv.server_close()

    # the vendored scripts are the ones whose SHA-256 the docs record
    recorded = dict(re.findall(r"`([\w.-]+\.(?:js|css))`[^`]*?SHA-256 `([0-9a-f]{64})`", (ROOT / "docs/reference/data-layout.md").read_text()))
    assert len(recorded) == 4, recorded
    for name, digest in recorded.items():
        assert hashlib.sha256((ROOT / "src/nasute/assets" / name).read_bytes()).hexdigest() == digest, name


def main():
    # retrieval maths
    s = nasute.retrieval_scores(["Iron", "Steel"], ["Gold", "iron", "Copper"], 5)
    assert s["hit"] == 1 and close(s["recall"], 0.5) and close(s["mrr"], 0.5), s
    s = nasute.retrieval_scores(["Iron"], ["Gold", "Copper", "iron"], 2)   # found, but outside k
    assert s["hit"] == 0 and s["recall"] == 0 and close(s["mrr"], 1 / 3), s
    assert nasute.retrieval_scores(["Iron"], [], 5) == {"hit": 0.0, "recall": 0.0, "mrr": 0.0}
    assert nasute.retrieval_scores([], ["x"], 5)["hit"] is None
    assert nasute.difficulty_of({"tags": ["x", "medium"]}) == "medium" and nasute.difficulty_of({"tags": []}) == "unknown"
    assert nasute.difficulty_of({"difficulty": "hard", "tags": ["easy"]}) == "hard"
    m = nasute.mean_std([1, 0, None])
    assert m == {"mean": 0.5, "std": 0.5, "n": 2}, m
    assert nasute.mean_std([None])["mean"] is None

    # settings: defaults without a file, and the example file lists every setting in the code
    assert nasute.load_settings("/nonexistent.toml")["k"] == 5
    example = tomllib.loads((ROOT / "nasute.example.toml").read_text())
    for key, value in nasute.DEFAULTS.items():
        assert key in example, f"{key} missing from nasute.example.toml"
        if isinstance(value, dict):
            assert value.keys() <= example[key].keys(), key
    # examples/: each loads, and uses only settings the code knows, so a typo there cannot mislead a reader
    for p in sorted((ROOT / "examples").glob("*.toml")):
        cfg = nasute.load_settings(p)
        ex = tomllib.loads(p.read_text())
        assert ex.keys() <= nasute.DEFAULTS.keys() and ex["judge"].keys() <= nasute.DEFAULTS["judge"].keys(), p.name
        assert cfg["judge"]["mode"] in ("quick", "claims", "knowledge"), p.name
        for t in ex["targets"].values():
            same = {"http": "web", "chat": "chat-model"}[t["kind"]]   # each kind against its own example, plus what any target may set
            allowed = example["targets"][same].keys() | {"label", "model_url", "concurrency", "temperature", "timeout", "headers", "system"}
            assert t.keys() <= allowed, (p.name, t.keys() - allowed)

    # the seed dataset is well formed and its fingerprint follows the file
    path, version = nasute.find_dataset(nasute.DEFAULTS, "demo")
    header, questions, fp = nasute.load_dataset(path, version)
    assert version == (1, 0, 0) and header["target"] == "demo" and len(questions) == 10, (version, len(questions))
    assert sum(q.get("answerable") is False for q in questions) == 2 and all(q["difficulty"] in ("easy", "medium", "hard") for q in questions)
    sections = set(re.findall(r"^## (.+)$", (path.parent / "handbook.md").read_text(), re.M))
    assert {x for q in questions for x in q["sources"]} <= sections   # every source is a heading of the handbook
    jpath, jv = nasute.find_dataset(nasute.DEFAULTS, "judge-demo")
    jitems = nasute.load_dataset(jpath, jv)[1]
    assert len(jitems) == 20 and all(lo <= hi for it in jitems for lo, hi in it["expect"].values()), len(jitems)
    assert all(i["answer"].count(".") == 1 for i in jitems if i["kind"] == "right")   # a right answer is one claim, so counting gives 1
    assert len(fp["sha256"]) == 64
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        copy = tmp / "v1.jsonl"
        copy.write_text(path.read_text())
        assert nasute.load_dataset(copy, 1)[2]["sha256"] == fp["sha256"]
        copy.write_text(path.read_text() + "\n")
        assert nasute.load_dataset(copy, 1)[2]["sha256"] != fp["sha256"]

        # compare and report, over two fake runs
        cfg = {**nasute.DEFAULTS, "runs": str(tmp / "runs"), "report": str(tmp / "report")}
        d1 = {"name": "x", "version": 1, "sha256": "aaa"}
        fake_run(cfg, "20260101T000000Z", d1, {"q1": {"hit": 1, "faithfulness": 1.0}, "q2": {"hit": 1, "faithfulness": 0.5}})
        fake_run(cfg, "20260102T000000Z", d1, {"q1": {"hit": 1, "faithfulness": 0.2}, "q2": {"hit": 1, "faithfulness": 0.9}})
        c = nasute.compare(cfg)
        assert (c["a"], c["b"], c["warning"], c["shared"]) == ("20260101T000000Z", "20260102T000000Z", None, 2), c
        assert close(c["metrics"]["faithfulness"]["delta"], -0.2) and c["metrics"]["hit"]["delta"] == 0
        assert c["metrics"]["mrr"]["delta"] is None   # nothing scored in either run
        assert [w["id"] for w in c["worse"]] == ["q1"] and [w["id"] for w in c["better"]] == ["q2"], c

        # a different dataset version: warned about, not compared question by question
        fake_run(cfg, "20260103T000000Z", {**d1, "version": 2, "sha256": "bbb"}, {"q1": {"hit": 0}})
        c = nasute.compare(cfg)
        assert "Different questions" in c["warning"] and c["worse"] == [] and c["shared"] == 0, c
        assert nasute.compare(cfg, "20260101T000000Z", "20260102T000000Z")["warning"] is None

        assert list(nasute.report(cfg)) == ["x@"] and (tmp / "report" / "index.html").exists()
        assert nasute.compare({**cfg, "runs": str(tmp / "none")}) is None   # fewer than two runs

    statistics_checks()
    robustness_checks()
    review_checks()
    judge_checks()
    reason_checks()
    settings_checks()
    judge_prompt_checks()
    release_020_checks()
    features_020_checks()
    target_checks()
    settings_form_checks()
    suite_checks()
    manage_checks()
    report_checks()
    review_round_checks()
    interval_checks()
    power_checks()
    http_usage_check()
    docs_checks()
    version_checks()
    chart_export_link_checks()
    label_checks()
    dashboard_checks()
    logging_checks()
    init_demo_checks()
    security_checks()
    print("nasute checks passed")


if __name__ == "__main__":
    main()
