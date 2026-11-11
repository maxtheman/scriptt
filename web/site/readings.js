// Hand-written sample readings in the PLANNED shape of UI-HANDOFF.md (made by hand, not by any engine). fromReading() in index.html turns each into the board's state.
const READINGS = [
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "Implement all ten of these. Then delete it. Please reconcile the flux ledger.",
  "phrases": [
   {
    "start": 0,
    "end": 27,
    "brand": "Asked",
    "choice": {
     "pick": "implement",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.91,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "a1",
     "fn": "implement",
     "args": {
      "questions": {
       "kind": "Constant",
       "type": "Questions",
       "value": "all ten of these",
       "span": [
        10,
        26
       ]
      },
      "cells": {
       "kind": "Empty",
       "type": {
        "name": "Maybe",
        "args": [
         "int"
        ]
       }
      }
     }
    }
   },
   {
    "start": 28,
    "end": 43,
    "brand": "Asked",
    "choice": {
     "pick": "delete",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.88,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "a2",
     "fn": "delete",
     "args": {
      "notebook": {
       "ref": "a1"
      }
     }
    }
   },
   {
    "start": 44,
    "end": 77,
    "brand": "Asked",
    "choice": {
     "pick": "none",
     "scores": {
      "explain": 0.06,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.74,
      "nothing": 0.01
     }
    },
    "term": null,
    "unresolved": {
     "reason": "no function of the world matches (d1 chose none, 0.74); the phrase stays so the request is not lost"
    }
   }
  ],
  "constants": [
   {
    "start": 10,
    "end": 26,
    "type": "Questions",
    "value": "all ten of these"
   }
  ],
  "decisions": [
   {
    "id": "q1",
    "phrase": 0,
    "path": null,
    "state": "Implement all ten of these.",
    "instructions": "The text asks the reader to implement something in the notebook. What does this text ask the reader to do?",
    "options": [
     {
      "id": "implement",
      "description": "implement something in the notebook"
     },
     {
      "id": "rewrite",
      "description": "rewrite the notebook or a cell of it"
     },
     {
      "id": "none",
      "description": "none of these"
     }
    ],
    "answers": {
     "implement": 0.91,
     "rewrite": 0.05,
     "none": 0.04
    }
   },
   {
    "id": "q2",
    "phrase": 0,
    "path": "cells",
    "state": "Implement all ten of these.",
    "automatic": "cells is Maybe[int] and no span of the phrase is an int, so it is bound to Empty without a question",
    "instructions": "",
    "options": [],
    "answers": {}
   },
   {
    "id": "q3",
    "phrase": 1,
    "path": "notebook",
    "state": "Then delete it.",
    "instructions": "The text asks the reader to delete or get rid of cells of the notebook. Which Notebook does the text name for that? Candidates: the result of implement (a1).",
    "options": [
     {
      "id": "ref:a1",
      "description": "the result of implement (a1)"
     },
     {
      "id": "these cells",
      "description": "these cells"
     },
     {
      "id": "nothing",
      "description": "none of these"
     }
    ],
    "answers": {
     "ref:a1": 0.86,
     "these cells": 0.09,
     "nothing": 0.05
    }
   }
  ],
  "corrections": [],
  "fulfillment": [
   {
    "obligation": "a1",
    "verdict": "UNVERIFIED",
    "evidence": "no reply yet"
   }
  ]
 },
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "Restate all ten of these. Write the result to the usual place.",
  "phrases": [
   {
    "start": 0,
    "end": 25,
    "brand": "Asked",
    "choice": {
     "pick": "restate",
     "scores": {
      "explain": 0.01,
      "restate": 0.89,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "b1",
     "fn": "restate",
     "args": {
      "questions": {
       "kind": "Several",
       "type": {
        "name": "Many",
        "args": [
         "Questions"
        ]
       },
       "items": [
        {
         "kind": "Constant",
         "type": "Questions",
         "value": "all ten of these",
         "span": [
          8,
          24
         ]
        }
       ]
      },
      "concepts": {
       "kind": "Several",
       "type": {
        "name": "Many",
        "args": [
         "Concepts"
        ]
       },
       "items": []
      }
     }
    }
   },
   {
    "start": 26,
    "end": 62,
    "brand": "Asked",
    "choice": {
     "pick": "write",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.83,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "b2",
     "fn": "write",
     "args": {
      "path": {
       "kind": "Hole",
       "type": "Path",
       "reason": "d1 declined: \"the usual place\" names no path"
      }
     }
    }
   }
  ],
  "constants": [
   {
    "start": 8,
    "end": 24,
    "type": "Questions",
    "value": "all ten of these"
   }
  ],
  "decisions": [
   {
    "id": "q1",
    "phrase": 0,
    "path": "concepts",
    "state": "Restate all ten of these.",
    "instructions": "The message asks the reader to restate something in other terms. Is any Concept named for that, and not one that the message leaves out?",
    "options": [
     {
      "id": "yes",
      "description": "a concept is named"
     },
     {
      "id": "no",
      "description": "no concept is named"
     }
    ],
    "answers": {
     "yes": 0.04,
     "no": 0.96
    }
   },
   {
    "id": "q2",
    "phrase": 1,
    "path": "path",
    "state": "Write the result to the usual place.",
    "instructions": "The text asks the reader to write a file. Which Path does the text name for that?",
    "options": [
     {
      "id": "nothing",
      "description": "the text names none"
     },
     {
      "id": "the usual place",
      "description": "the usual place"
     }
    ],
    "answers": {
     "nothing": 0.62,
     "the usual place": 0.38
    }
   }
  ],
  "corrections": [],
  "fulfillment": []
 }
];
