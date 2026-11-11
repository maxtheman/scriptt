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
 },
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "Implement all ten of these in 3 cells. Implement all ten of these in 5 cells. Then delete it, and rewrite these cells with the functions.",
  "phrases": [
   {
    "start": 0,
    "end": 38,
    "brand": "Asked",
    "choice": {
     "pick": "implement",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.93,
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
     "id": "c1",
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
       "kind": "Constant",
       "type": {
        "name": "Maybe",
        "args": [
         "int"
        ]
       },
       "value": "3",
       "span": [
        30,
        31
       ]
      }
     }
    }
   },
   {
    "start": 39,
    "end": 77,
    "brand": "Asked",
    "choice": {
     "pick": "implement",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.92,
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
     "id": "c2",
     "fn": "implement",
     "args": {
      "questions": {
       "kind": "Constant",
       "type": "Questions",
       "value": "all ten of these",
       "span": [
        49,
        65
       ]
      },
      "cells": {
       "kind": "Constant",
       "type": {
        "name": "Maybe",
        "args": [
         "int"
        ]
       },
       "value": "5",
       "span": [
        69,
        70
       ]
      }
     }
    }
   },
   {
    "start": 78,
    "end": 93,
    "brand": "Asked",
    "choice": {
     "pick": "delete",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.81,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "c3",
     "fn": "delete",
     "args": {
      "notebook": {
       "ref": "c2"
      }
     }
    }
   },
   {
    "start": 94,
    "end": 137,
    "brand": "Asked",
    "choice": {
     "pick": "rewrite",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.86,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "c4",
     "fn": "rewrite",
     "args": {
      "change": {
       "kind": "Record",
       "fields": {
        "notebook": {
         "kind": "Constant",
         "type": "Notebook",
         "value": "these cells",
         "span": [
          106,
          117
         ]
        },
        "code": {
         "kind": "Constant",
         "type": "Code",
         "value": "the functions",
         "span": [
          123,
          136
         ]
        }
       }
      }
     }
    }
   }
  ],
  "constants": [
   {
    "start": 10,
    "end": 26,
    "type": "Questions",
    "value": "all ten of these"
   },
   {
    "start": 49,
    "end": 65,
    "type": "Questions",
    "value": "all ten of these"
   },
   {
    "start": 30,
    "end": 31,
    "type": "int",
    "value": "3"
   },
   {
    "start": 69,
    "end": 70,
    "type": "int",
    "value": "5"
   },
   {
    "start": 106,
    "end": 117,
    "type": "Notebook",
    "value": "these cells"
   },
   {
    "start": 123,
    "end": 136,
    "type": "Code",
    "value": "the functions"
   }
  ],
  "decisions": [
   {
    "id": "q1",
    "phrase": 2,
    "path": "notebook",
    "state": "Then delete it,",
    "instructions": "The text asks the reader to delete or get rid of cells of the notebook. Which Notebook does the text name for that? Candidates: the result of implement (c1), the result of implement (c2).",
    "options": [
     {
      "id": "ref:c1",
      "description": "the result of implement (c1)"
     },
     {
      "id": "ref:c2",
      "description": "the result of implement (c2)"
     },
     {
      "id": "nothing",
      "description": "none of these"
     }
    ],
    "answers": {
     "ref:c1": 0.21,
     "ref:c2": 0.74,
     "nothing": 0.05
    }
   },
   {
    "id": "q2",
    "phrase": 3,
    "path": "change.code",
    "state": "and rewrite these cells with the functions.",
    "instructions": "The text asks the reader to rewrite the notebook or a cell of it. Which Code does the text name for that?",
    "options": [
     {
      "id": "the functions",
      "description": "the functions"
     },
     {
      "id": "the template",
      "description": "the template"
     },
     {
      "id": "nothing",
      "description": "none of these"
     }
    ],
    "answers": {
     "the functions": 0.88,
     "the template": 0.07,
     "nothing": 0.05
    }
   }
  ],
  "corrections": [],
  "fulfillment": []
 },
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "> The old cells are gone.\nNow **delete** `the old cells` too.",
  "phrases": [
   {
    "start": 0,
    "end": 25,
    "brand": "Written",
    "choice": {
     "pick": "nothing",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.9
     }
    },
    "term": null
   },
   {
    "start": 26,
    "end": 61,
    "brand": "Asked",
    "choice": {
     "pick": "delete",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.95,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "d1",
     "fn": "delete",
     "args": {
      "notebook": {
       "kind": "Constant",
       "type": "Notebook",
       "value": "the old cells",
       "span": [
        42,
        55
       ]
      }
     }
    }
   }
  ],
  "constants": [
   {
    "start": 42,
    "end": 55,
    "type": "Notebook",
    "value": "the old cells"
   }
  ],
  "decisions": [],
  "corrections": [],
  "fulfillment": []
 },
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "> I rewrote the notebook and it now has 18 cells. Count the cells in this notebook. Then delete the old cells, and implement all ten of these in 12 cells. Restate all ten of these using the computer science concepts and the roles. After that rewrite these cells with the functions, then delete it. Please also reconcile the flux ledger against last quarter's invoices, which finance still has not sent over, and then tell me whether the template is typed. Write the summary to the usual place. Explain why the roles are defined the way they are in the result types, and what this is supposed to accomplish for the people who read the notebook at the end of the day. Solve for the result types. Mock the model. Is that all ten?",
  "phrases": [
   {
    "start": 0,
    "end": 49,
    "brand": "Written",
    "choice": {
     "pick": "nothing",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.9
     }
    },
    "term": null
   },
   {
    "start": 50,
    "end": 83,
    "brand": "Asked",
    "choice": {
     "pick": "count",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.86,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "e2",
     "fn": "count",
     "args": {
      "notebook": {
       "kind": "Constant",
       "type": "Notebook",
       "value": "this notebook",
       "span": [
        69,
        82
       ]
      }
     }
    }
   },
   {
    "start": 84,
    "end": 110,
    "brand": "Asked",
    "choice": {
     "pick": "delete",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.86,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "e3",
     "fn": "delete",
     "args": {
      "notebook": {
       "kind": "Constant",
       "type": "Notebook",
       "value": "the old cells",
       "span": [
        96,
        109
       ]
      }
     }
    }
   },
   {
    "start": 111,
    "end": 154,
    "brand": "Asked",
    "choice": {
     "pick": "implement",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.86,
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
     "id": "e4",
     "fn": "implement",
     "args": {
      "questions": {
       "kind": "Constant",
       "type": "Questions",
       "value": "all ten of these",
       "span": [
        125,
        141
       ]
      },
      "cells": {
       "kind": "Constant",
       "type": "int",
       "value": "12",
       "span": [
        145,
        147
       ]
      }
     }
    }
   },
   {
    "start": 155,
    "end": 230,
    "brand": "Asked",
    "choice": {
     "pick": "restate",
     "scores": {
      "explain": 0.01,
      "restate": 0.86,
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
     "id": "e5",
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
          163,
          179
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
       "items": [
        {
         "kind": "Constant",
         "type": "Concepts",
         "value": "the computer science concepts",
         "span": [
          186,
          215
         ]
        }
       ]
      }
     }
    }
   },
   {
    "start": 231,
    "end": 281,
    "brand": "Asked",
    "choice": {
     "pick": "rewrite",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.86,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "e6",
     "fn": "rewrite",
     "args": {
      "change": {
       "kind": "Record",
       "fields": {
        "notebook": {
         "kind": "Constant",
         "type": "Notebook",
         "value": "these cells",
         "span": [
          250,
          261
         ]
        },
        "code": {
         "kind": "Constant",
         "type": "Code",
         "value": "the functions",
         "span": [
          267,
          280
         ]
        }
       }
      }
     }
    }
   },
   {
    "start": 282,
    "end": 297,
    "brand": "Asked",
    "choice": {
     "pick": "delete",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.86,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "e7",
     "fn": "delete",
     "args": {
      "notebook": {
       "ref": "e6"
      }
     }
    }
   },
   {
    "start": 298,
    "end": 407,
    "brand": "Asked",
    "choice": {
     "pick": "none",
     "scores": {
      "explain": 0.1,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.7,
      "nothing": 0.01
     }
    },
    "term": null,
    "unresolved": {
     "reason": "no function of the world matches (d1 chose none, 0.70)"
    }
   },
   {
    "start": 408,
    "end": 455,
    "brand": "Asked",
    "choice": {
     "pick": "answer",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.86,
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
     "id": "e9",
     "fn": "answer",
     "args": {}
    }
   },
   {
    "start": 456,
    "end": 493,
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
      "write": 0.86,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "e10",
     "fn": "write",
     "args": {
      "path": {
       "kind": "Hole",
       "type": "Path",
       "reason": "d1 declined: the text names no path"
      }
     }
    }
   },
   {
    "start": 494,
    "end": 665,
    "brand": "Asked",
    "choice": {
     "pick": "explain",
     "scores": {
      "explain": 0.86,
      "restate": 0.01,
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
     "id": "e11",
     "fn": "explain",
     "args": {}
    }
   },
   {
    "start": 666,
    "end": 693,
    "brand": "Asked",
    "choice": {
     "pick": "solve",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01,
      "solve": 0.86
     }
    },
    "term": {
     "kind": "Application",
     "id": "e12",
     "fn": "solve",
     "args": {
      "types": {
       "kind": "Constant",
       "type": "Types",
       "value": "result types",
       "span": [
        680,
        692
       ]
      }
     }
    }
   },
   {
    "start": 694,
    "end": 709,
    "brand": "Asked",
    "choice": {
     "pick": "mock",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.01,
      "implement": 0.01,
      "delete": 0.01,
      "rewrite": 0.01,
      "count": 0.01,
      "write": 0.01,
      "none": 0.02,
      "nothing": 0.01,
      "mock": 0.86
     }
    },
    "term": {
     "kind": "Application",
     "id": "e13",
     "fn": "mock",
     "args": {
      "model": {
       "kind": "Constant",
       "type": "Model",
       "value": "the model",
       "span": [
        699,
        708
       ]
      }
     }
    }
   },
   {
    "start": 710,
    "end": 726,
    "brand": "Asked",
    "choice": {
     "pick": "answer",
     "scores": {
      "explain": 0.01,
      "restate": 0.01,
      "answer": 0.86,
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
     "id": "e14",
     "fn": "answer",
     "args": {}
    }
   }
  ],
  "constants": [
   {
    "start": 69,
    "end": 82,
    "type": "Notebook",
    "value": "this notebook"
   },
   {
    "start": 96,
    "end": 109,
    "type": "Notebook",
    "value": "the old cells"
   },
   {
    "start": 125,
    "end": 141,
    "type": "Questions",
    "value": "all ten of these"
   },
   {
    "start": 145,
    "end": 147,
    "type": "int",
    "value": "12"
   },
   {
    "start": 163,
    "end": 179,
    "type": "Questions",
    "value": "all ten of these"
   },
   {
    "start": 186,
    "end": 215,
    "type": "Concepts",
    "value": "the computer science concepts"
   },
   {
    "start": 250,
    "end": 261,
    "type": "Notebook",
    "value": "these cells"
   },
   {
    "start": 267,
    "end": 280,
    "type": "Code",
    "value": "the functions"
   },
   {
    "start": 680,
    "end": 692,
    "type": "Types",
    "value": "result types"
   },
   {
    "start": 699,
    "end": 708,
    "type": "Model",
    "value": "the model"
   }
  ],
  "decisions": [],
  "corrections": [],
  "fulfillment": []
 },
 {
  "form": 4,
  "world": "sha256:9f405426f2f0 (hand-written sample)",
  "text": "Write the summary into notes.md soon.",
  "phrases": [
   {
    "start": 0,
    "end": 37,
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
      "write": 0.9,
      "none": 0.02,
      "nothing": 0.01
     }
    },
    "term": {
     "kind": "Application",
     "id": "f1",
     "fn": "write",
     "args": {
      "path": {
       "kind": "Constant",
       "type": "Path",
       "value": "notes.md",
       "span": [
        23,
        31
       ]
      }
     }
    }
   }
  ],
  "constants": [
   {
    "start": 23,
    "end": 31,
    "type": "Path",
    "value": "notes.md"
   }
  ],
  "decisions": [],
  "corrections": [],
  "fulfillment": []
 }
];
