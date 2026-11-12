"""A stand-in system and a stand-in judge on one port, so the Nasute tutorial runs with no account and no model.

What it does: POST /ask answers a few known questions ({"question": ...} in, {"answer", "sources"} out).
POST /v1/chat/completions plays the judge: it marks by looking for the reference words in the answer, nothing smarter.
GET /v1/models lists one made-up model. Scores from this are for seeing the pipeline work. They mean nothing.
How it runs: by hand, `nasute demo-server` (Ctrl-C to stop). Standard library only. Port 8700, this machine only.
Reads and writes: nothing on disk. Settings: PORT below.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8700
FACTS = {   # a word in the question -> (answer, source article)
    "france": ("Paris is the capital of France.", "France"),
    "water": ("Water boils at 100 degrees Celsius at sea level.", "Boiling point"),
}


def field(prompt, name, stop):
    """The text after `NAME:` in the judge's prompt, up to the next label."""
    m = re.search(rf"^{name}:\s*(.*?)(?=^(?:{stop}):|\Z)", prompt, re.S | re.M)
    return m.group(1).strip() if m else ""


def judge(prompt):
    """A reply in the shape Nasute's judge prompts ask for."""
    if "holds no answer" in prompt:
        answer = field(prompt, "ANSWER", "XXXX")
        return {"verdict": "declined" if "don't know" in answer.lower() else "made_something_up", "why": "looked for 'don't know'"}
    answer, reference, extracts = (field(prompt, n, "QUESTION|REFERENCE|EXTRACTS|ANSWER") for n in ("ANSWER", "REFERENCE", "EXTRACTS"))
    agrees = reference.lower() in answer.lower()
    claims = [{"claim": answer, "supported": "yes" if reference.lower() in extracts.lower() else "no",
               "vs_reference": "agrees" if agrees else "contradicts", "why": "word match"}] if answer and "don't know" not in answer.lower() else []
    return {"claims": claims, "relevancy": "yes" if claims else "no", "relevancy_why": "word match"}


class Handler(BaseHTTPRequestHandler):
    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"data": [{"id": "fake-judge"}]})   # GET /v1/models

    def do_POST(self):
        length = self.headers.get("Content-Length") or ""
        size = int(length) if length.isdigit() else -1
        if not 0 <= size <= 1_000_000:   # a missing, negative or huge length would stall this one-at-a-time server
            self.send_error(400, "Content-Length needed, at most 1 MB")
            return
        body = json.loads(self.rfile.read(size))
        if self.path == "/ask":
            question = body["question"].lower()
            answer, source = next((v for k, v in FACTS.items() if k in question), ("I don't know.", None))
            self.reply({"answer": answer, "sources": [{"title": source, "text": answer}] if source else []})
        else:
            self.reply({"choices": [{"message": {"content": json.dumps(judge(body["messages"][0]["content"]))}}]})

    def log_message(self, *args):
        pass


def serve():
    print(f"fake system at http://127.0.0.1:{PORT}/ask and fake judge at http://127.0.0.1:{PORT}/v1 (Ctrl-C to stop)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
