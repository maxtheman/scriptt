"""A small System One endpoint for testing the hook with a d1 model on this Mac. Not for production.

    PYTHONPATH=<an mlx-vlm checkout that has d1> python tests/systemone_local.py <model folder> [port]

It serves POST /v1/systemone with {"state", "questions"} and answers with model.system_one(state, questions).
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from mlx_vlm import load

model, _ = load(sys.argv[1])


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply = json.dumps(model.system_one(body["state"], body["questions"])).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[2]) if len(sys.argv) > 2 else 8791), Handler).serve_forever()
