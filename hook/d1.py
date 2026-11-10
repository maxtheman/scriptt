"""Two ways to answer a `text` read: a System One endpoint, or recorded answers.

A System One endpoint takes POST {url}/v1/systemone with {"model", "state", "questions": {name: question}}
and returns {"answers": {name: answer}}. A `text` answer has "span": [start, end] and "found".
"""

import json
import urllib.request

import program


def system_one(url, model, api_key="", timeout=30):
    def d1(state, cls):
        body = {"model": model, "state": state, "questions": {"q": {"type": "text", "instructions": program.prompt(cls)}}}
        headers = {"Content-Type": "application/json"} | ({"Authorization": "Bearer " + api_key} if api_key else {})
        request = urllib.request.Request(url.rstrip("/") + "/v1/systemone", json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            answer = json.load(reply)["answers"]["q"]
        found = answer.get("found")
        return {"found": found if isinstance(found, bool) else (found or 0) >= 0.5, "span": answer.get("span")}

    return d1


def recorded(answers):
    """Answers written down before: {"ClassName": [words, ...]}. It returns the first words that are still in the state."""

    def d1(state, cls):
        words = next((w for w in answers.get(cls.__name__, []) if w in state), None)
        if words is None:
            return {"found": False}
        return {"found": True, "span": [state.find(words), state.find(words) + len(words)]}

    return d1
