"""Prototype (not part of the engine): give every word of a reading a kind from the world, with the real d1.

For each phrase of a saved reading, d1 gets one question per word: "the word ... is part of which kind of thing?",
with each type of the world (its docstring), each function (its docstring), and "none of these". Neighbouring words
with the same answer become one typed piece. Every question and answer is kept.
"""
import json, pathlib, sys

lab = pathlib.Path(sys.argv[1]); reading_id = sys.argv[2]; out = pathlib.Path(sys.argv[3])
sys.path.insert(0, str(lab))
import harness, agree, scriptt16  # the lab's engine and its d1 settings

line = [one for one in scriptt16.saved(lab / "events.jsonl") if one["id"] == reading_id][-1]
world = agree.loads((lab / "world.py").read_text(), lab.parent)
kinds = {name: (getattr(kind, "describes", "") or name) for name, kind in world.types.items() if name not in ("str", "NoneType")}
kinds |= {name: f"the action: {function.asks}" for name, function in world.functions.items()}
kinds["none"] = "none of these"
options = [{"id": key, "description": text} for key, text in kinds.items()]
text, pieces, exchanges = line["text"], [], []
for phrase in line["phrases"]:
    words = [(phrase["start"] + a, phrase["start"] + b) for a, b in scriptt16.chunks(text[phrase["start"]:phrase["end"]])]
    if not words:
        continue
    state = text[phrase["start"]:phrase["end"]].strip()
    questions = {f"w{i}": {"type": "choice", "options": options,
                           "instructions": f'In this text, the word "{text[a:b]}" (word {i + 1}) is part of which kind of thing?'}
                 for i, (a, b) in enumerate(words)}
    answers = harness.d1(state, questions)
    exchanges.append({"state": state, "questions": questions, "answers": answers})
    for i, (a, b) in enumerate(words):
        shares = answers[f"w{i}"]["probabilities"]
        kind = max(shares, key=shares.get)
        if pieces and pieces[-1]["kind"] == kind and pieces[-1]["phrase"] == phrase["start"]:
            pieces[-1]["end"] = b; pieces[-1]["shares"].append(shares[kind])
        else:
            pieces.append({"phrase": phrase["start"], "start": a, "end": b, "kind": kind, "shares": [shares[kind]]})
out.write_text(json.dumps({"reading": reading_id, "pieces": pieces, "kinds": kinds, "exchanges": exchanges}, indent=1))
print(len(pieces), "pieces;", sum(p["kind"] == "none" for p in pieces), "none;", len(exchanges), "requests")
