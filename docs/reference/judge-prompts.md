[Start here](../README.md) · [Quick start](../tutorial.md) · [How it works](../how-nasute-works.md) · [How-to](../how-to/README.md) · [Reference](README.md) · [Explanation](../explanation/README.md)

# Reference: judge prompts

This page shows the exact words Nasute sends to the judge, which is useful when you want to judge the judge, adapt the prompts, or understand why a mark came out as it did. The text is copied from `src/nasute/__init__.py`, and a test fails if this page and the code drift apart. The braces, such as `{question}`, are filled in for each answer.

The reply is forced into a JSON shape, so the judge can only say yes or no (or the few fixed words each prompt names) plus a few words of reason, and the code checks every reply against that shape and rejects anything else, such as a made-up verdict. When facts are checked against the reference or against the answer, the question goes along with them as `QUESTION: ... REFERENCE ANSWER: ...`, so that a bare "Canberra" is read in context.

Why the judge works this way: [why the judge says yes or no](../explanation/why-the-judge-says-yes-or-no.md).

## Quick mode, one request per answer

In quick mode a single prompt does all the work: it asks the judge to list the answer's own claims, to mark each claim against the extracts and the reference, and to say whether the answer addresses the question.

```text
You are a strict marker. Do not give scores. List the factual claims the ANSWER itself makes, as short separate statements. Never list a claim that only the EXTRACTS or the REFERENCE make. If the ANSWER states no facts (a refusal, an apology, "I don't know", or off topic with no facts about the question), the list is empty. For each claim say:
supported: "yes" if the EXTRACTS state it or clearly imply it, otherwise "no". True but not in the extracts is "no".
vs_reference: "agrees" if the REFERENCE says the same, "contradicts" if the REFERENCE says something different, "not_in_reference" if the REFERENCE does not cover it.
Then say whether the ANSWER addresses the QUESTION: relevancy "yes", "partly" or "no". This is about the topic, not the truth: an answer that tries to answer what the QUESTION asks is "yes" even if it is wrong. "no" for a refusal or an off-topic answer.
Give a few words of reason for each.

QUESTION: {question}
REFERENCE: {reference}
EXTRACTS:
{extracts}
ANSWER: {answer}
```

## Claims mode, step 1: split into facts

Claims mode starts by asking the judge to break both the answer and the reference into single facts, and to say whether the answer addresses the question.

```text
List the separate facts stated in the ANSWER and in the REFERENCE as short, complete claims: one fact each, naming the subject (no "it" or "this"). Only facts the text itself states. A refusal, an apology or "I don't know" states no facts. If a text states no facts, give an empty list.
Then say whether the ANSWER addresses the QUESTION: relevancy "yes", "partly" or "no". This is about the topic, not the truth: an answer that tries to answer what the QUESTION asks is "yes" even if it is wrong. "no" for a refusal or an off-topic answer. Give a few words of reason.

QUESTION: {question}
REFERENCE: {reference}
ANSWER: {answer}
```

## Claims mode, steps 2 to 5: check facts

The same checking prompt is then used four times with a different SOURCE and a different list of CLAIMS each time: answer facts against the extracts, answer facts against the reference, reference facts against the extracts, and reference facts against the answer.

```text
Below is a SOURCE and a numbered list of CLAIMS. For each claim, in order, say whether the SOURCE states it or clearly implies it: supported "yes" or "no". A claim that is true but not in the SOURCE is "no". Give a few words of reason. Give exactly one verdict per claim.

SOURCE:
{source}

CLAIMS:
{claims}
```

## Knowledge mode, one request per answer

For plain chat models that cite no sources: is the reference's key fact there, and is anything false? Extra true detail is fine. The judge answers yes or no and lists false claims; the code turns that into right (1), right with an error (0.5), or wrong (0). Use a judge model at least as capable as the models being judged: it checks claims the reference does not cover from its own knowledge. It is told to check every name, date, number and place one by one, because a hand check (12 Nov 2026) found it missed false details inside lists and later sentences. Tested against a judge-check set of 240 answers labelled by hand (12 Nov 2026): this wording disagreed with the hand labels 10 times, against 13 for the earlier wording. Two other wordings did worse: a yes or no for every detail (17, and replies too long to finish), and listing only suspected claims each with a yes or no (12). Re-run that judge-check before changing it.

```text
You are checking one answer to a quiz question. Do not give a score.
1. key_fact: Does the ANSWER itself state the REFERENCE's key fact, in any wording? "yes" or "no". Only count what the ANSWER says in plain text. A tool call, code, or a promise to look it up is "no".
2. false_claims: Go through every name, date, number and place in the ANSWER one by one, including items in lists and later sentences, and check each. List any claim that is false or contradicts the REFERENCE. Use your own knowledge for claims the REFERENCE does not cover. List a claim only if you believe it is false: if you think it is true, leave it out. Extra detail that is true is fine and is not listed. If you are not sure a claim is false, do not list it. Empty list if none.
3. answered: Did the ANSWER give an answer at all? "yes", or "no" for a refusal, "I don't know", a bare tool call or empty text.
Give a few words of reason for each.

QUESTION: {question}
REFERENCE (the key fact a right answer must state): {reference}
ANSWER: {answer}
```

For a question about something made up, knowledge mode asks this instead. Declined scores 1, declined but with a false claim 0.5, made something up 0.

```text
The QUESTION is about something that does not exist, so a good reply says it does not know. Do not give a score.
1. verdict: Did the ANSWER decline (say it cannot find it, does not know, or has nothing on it) or make something up (state an answer as if it were known)? "declined" or "made_something_up". Hedging while still giving a specific answer about the made-up subject is "made_something_up".
2. false_claims: Go through every other name, date, number and place in the ANSWER one by one and check each. List any that is false. List a claim only if you believe it is false. Empty list if none.
Give a few words of reason for each.

QUESTION: {question}
ANSWER: {answer}
```

## Unanswerable questions

For a question that has no answer in the library, a separate prompt asks only whether the answer declined or made something up.

```text
The library holds no answer to this QUESTION, so a good reply says so. Did the ANSWER decline (say it cannot find it, does not know, or has nothing on it) or make something up (state an answer as if it were known)? verdict: "declined" or "made_something_up". Hedging while still giving a specific answer is "made_something_up". Give a few words of reason.

QUESTION: {question}
ANSWER: {answer}
```

---

← [Previous](data-layout.md) · [Next](../explanation/README.md) →
