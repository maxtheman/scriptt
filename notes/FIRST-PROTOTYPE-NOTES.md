# UI Inventory, User Notes, Critique & Architectural Diagrams

Generated: 2026-11-10

---

## 1. Directory Inventory of All UI Files

### A. Existing Production / Repo UI (`scriptt-release`)
1. **[`/Users/max/Documents/scriptt-release/web/public/index.html`](file:///Users/max/Documents/scriptt-release/web/public/index.html)** *(39,975 bytes — Original Dragology 0.2.0 Web Board)*
   - **What it is:** The existing Dragology-powered SVG web board served by `harness.py serve` on `http://127.0.0.1:8787`, reading `WORLD` and `EVENTS` from [`web/public/data.js`](file:///Users/max/Documents/scriptt-release/web/public/data.js) and rendering via [`web/public/vendor/dragology-0.2.0.iife.js`](file:///Users/max/Documents/scriptt-release/web/public/vendor/dragology-0.2.0.iife.js).
   - **How it works:**
     - **Closed mode (`OPEN = false`):** Renders the message as a single continuous paragraph with colored spans (`piece`) and sentence-end function tags (`tag`).
     - **Open mode (`OPEN = true`):** Splits into a 2-column layout (sentence bubbles on the left, function `brick`s and `hole`s on the right) plus the dynamic `WORLD` tray below (functions, dashed type chips, sum type members).
     - **Key architectural rule (Line 133):** `// Every word drawn below comes from the record (events.jsonl), from the world (world.py) or from the message. Nothing names a type or a function of a world.`

2. **[`/Users/max/Documents/scriptt-release/mod/hooks/row.tsx`](file:///Users/max/Documents/scriptt-release/mod/hooks/row.tsx)** *(Claude Desktop / Claude Code inline hook renderer)*
   - **What it is:** The inline message decorator inside the Claude Desktop app (installed via `/plugin install scriptt`).
   - **Current state:** Static inline renderer for `form 2` / `form 3` records; does not yet expose the interactive Dragology state transitions or `form 4` recursive `Term` trees.

3. **[`/Users/max/Documents/scriptt-release/next/notebook.py`](file:///Users/max/Documents/scriptt-release/next/notebook.py)** *(Marimo interactive notebook — specifically `drawn(reading)` at lines 643–730)*
   - **What it is:** The 4-part literate Marimo notebook explaining `agree.py` and `scriptt16.py`. Cell `drawn(reading)` folds a `Reading` (`form 4`) into a single HTML paragraph with inline badges (`➊ redesign ➔ Later[Surface]`), colored constants (`the mod : surface ∶ Surface`), and trailing sockets (`◻ path: Type` or `path ↩ ➊ ...`).

---

### B. Prototype UI Files Created During This Session (and Their Iteration History)
4. **[`/Users/max/Documents/scriptt-release/web/public/prototype.html`](file:///Users/max/Documents/scriptt-release/web/public/prototype.html)** *(74,108 bytes — Standalone copy in `web/public/`)*
5. **[`/Users/max/.gemini/antigravity/brain/0f6d8ab7-d06e-448c-9ee9-bcab04e07516/scriptt_unified_canvas.html`](file:///Users/max/.gemini/antigravity/brain/0f6d8ab7-d06e-448c-9ee9-bcab04e07516/scriptt_unified_canvas.html)** *(74,108 bytes — Artifact copy)*
6. **[`/Users/max/.gemini/antigravity/brain/0f6d8ab7-d06e-448c-9ee9-bcab04e07516/inline_paragraph_demo.html`](file:///Users/max/.gemini/antigravity/brain/0f6d8ab7-d06e-448c-9ee9-bcab04e07516/inline_paragraph_demo.html)** *(74,108 bytes — Chat `<agent-embed>` copy)*

---

## 2. Saved User Notes & Feedback Across All 3 Prototype Iterations

### Iteration 1 Critique (User Rating: 2/10)
- **What worked:**
  - Highlighting multiple items in place.
  - Starting to use different types in `Subject`.
  - Showing how the prompt is compiled and what is sent to `d1`.
- **What failed:**
  - **No visual alphabet:** Impossible to unpack what `notebook` or `Later` is, what the probability numbers mean, what blue means, what the circled numbers (`#1=#2`, `➊`) mean, or why outlines/colors/colons (`:`) vs. arrows (`➔`) look the way they do ("nonsense slop").
  - **Fake `context[n]` trace:** Wrote `context[n]` at the bottom as a flat list of pills, which does not compile into or look anything remotely like a real execution/derivation trace (`Agent(context[n]) => context[n+1], process_executions`).
  - **No real dragging:** Clicking didn't do anything meaningful and nothing could actually be dragged in the inline widget.
  - **Ignored core inspirations:**
    - **Dragology (`permutation-lab`, `animate-algebra-tree`):** Continuous state-manifold interpolation (`d.between`) over algebraic structures.
    - **Ink & Switch Potluck (`all-ingredients`):** Plain text stays plain text; live extraction and computation happen quietly in place.
    - **Ink & Switch Embark:** Structured progressive computation inline with prose.
    - **Graspable Math (`activities.graspablemath.com`):** Terms in the expression *are* the manipulable algebraic objects.

### Iteration 2 Critique (Graspable English Canvas v1)
- **User Notes:**
  1. *"For the top panel, the graspable English canvas: I like being able to drag things together to show they are related in some way. I wish I could also drag things out of the context."*
  2. *"The dragging itself and the synthesized states is very hard to use and visually unclear."*
  3. *"I like the state reset. I like the derivation. I like the sockets."*
  4. *"Why are many/bind/whatever the only things we're showing though? What about the types and branding and kinds and how we organize the world? Like where why aren't those here? And why don't those have different things in here? And how would we show if we were showing the search process the search happening to visualize it? Because I feel like we should be able to visualize the search happening in the same language if we want to."*
  5. *"I don't have any clue what two [Panel 2] is. And three [Panel 3] is unusable too. So try those again."*

### Iteration 3 Critique & Self-Critique (World Grid + Search Stepper Canvas)
- **User Note:**
  - *"I'll let you self-critique this one. Uh I have no idea what it is if I'm being honest. Don't rewrite anything, just write a self-critique with all the feedback I've given you."*
  - *"When I click on something, there is an explicit world that is related to each of these words or phrases or whatever it is, each of the tag things that is opening up and they are built into the data structure with levels and the AI is responsible for tagging them and building up these levels and hierarchy itself. Isn't it? Like, isn't that how this works?"*
- **Distilled Self-Critique of Iteration 3:**
  1. **Shattered the English paragraph into metadata cards:** Broke the message into 5 separate gray cards with headers like `Phrase 1 · Brand: Asked < Words (start of message)`. Destroyed reading flow instead of keeping a Potluck-style paragraph where clicking a word/phrase progressively unfolds its level in the hierarchy.
  2. **Triplicated every entity on screen:** Drew `"the mod"` three separate times in Panel 1 (in the sentence, inside the socket below it, and in a "Context Shelf" below that) plus a fourth time in Panel 3, connected by spaghetti lines. In Graspable Math and Dragology's `animate-algebra-tree`, **there is only one copy of a term**.
  3. **Built a Windows 95 "Unbind / Evict" Trash Box (`⊖ DRAG HERE TO UNBIND / EVICT`):** Instead of using Dragology's native `whenFar(out)` (where pulling a term away into open space naturally unbinds it, as `index.html:379` already does for `value`), Iteration 3 forced the user to drag items into a red corner box.
  4. **Hardcoded `world.py` into a 5-column textbook glossary:** Instead of deriving the UI dynamically from `WORLD` (`events.jsonl` + `world.py`, as `index.html:133` mandates) and letting clicking a phrase/word unfold its relevant slice of the hierarchy, Iteration 3 dumped a static 5-column cheat sheet (`1. Kinds`, `2. Brands`, `3. Sum Types`, `4. Constructors`, `5. World Functions`).
  5. **Turned "Visualizing Search" into a text-caption slideshow (`Step 1/6..6/6`):** Instead of showing candidate terms physically testing against holes in the same visual language, it hid/showed badges and printed a paragraph of Python documentation at the bottom.

---

## 3. Additional Architectural Critique: What the Next Real UI Must Do

When we synthesize your insight—*"When I click on something, there is an explicit world that is related to each of these words or phrases... built into the data structure with levels and the AI is responsible for tagging them and building up these levels and hierarchy itself"*—with `web/public/index.html` and `next/scriptt16.py`:

1. **Zero Hardcoded Types (`index.html` Line 133 Principle):**
   - The UI must never hardcode `Surface`, `Code`, `redesign`, or a static 5-column table. Every type, brand, sum member, product field, and function comes dynamically from the AI-authored `world.py` (`WORLD`) and the `form 4` reading in `events.jsonl`.
2. **Progressive Unfolding by Clicking (Levels of the Hierarchy, Not All-At-Once Noise):**
   - **Level 0 (Reading the Message):** Clean running English paragraph (Potluck style). Grounded spans have subtle underline marks; each sentence has its quiet outcome pill (`redesign`, `show`, `test`, `explain`).
   - **Level 1 (Clicking a Phrase or Verb):** Opens *only* that phrase's synthesized `Application` frame and its immediate parameter sockets (`surface`, `subject`), plus the local/context candidates that `derivations()` found for those sockets.
   - **Level 2 (Clicking a Socket or Type):** Opens the `world.py` definition for *that specific type*—if it's a `Product`, it unfolds the nested field sockets; if it's a `Sum` (`Subject = Surface | Code | Path`), it unfolds the union branches and enum members so you can drag one in; if it has multiple candidates, it unfolds `d1`'s probability bars and prompt template right there.
3. **True Dragology `whenFar` & `d.between` (No Trash Cans, No Duplicate Clones):**
   - Pulling any bound term *away* from its socket (`whenFar(emptyState)`) detaches it back into open space.
   - Dragging a term toward a compatible socket (`d.between`) interpolates the layout continuously without duplicating the word into three separate shelves.

---

## 4. Reference Diagrams: The 4-Level AI-Built Hierarchy & Allowed Transitions

### A. The 4-Level Hierarchical Data Structure
```mermaid
flowchart TD
  subgraph L0["LEVEL 0: THE AI-AUTHORED WORLD (.scriptt/world.py → agree.load)"]
    direction LR
    W_Brands["<b>Brands (NewType)</b><br/>Provenance hierarchy<br/><code>Asked &lt; Words</code><br/><code>Written &lt; Words</code><br/><code>Observed &lt; Words</code>"]
    W_Sums["<b>Sum Types (Enum / Union)</b><br/>Closed vocabularies &amp; unions<br/>e.g. <code>Surface</code>, <code>Code</code>,<br/><code>Subject = Surface | Code | Path</code>"]
    W_Products["<b>Product Types (dataclass)</b><br/>Nested multi-field records<br/><code>field_1: T1, field_2: T2...</code>"]
    W_Ctors["<b>Constructors (* → *)</b><br/><code>Many[T]</code>, <code>Maybe[T]</code>, <code>Later[T]</code>"]
    W_Fns["<b>Functions (Arrows)</b><br/><code>fn(p1: T1, p2: Product...) → Ret</code><br/>flattened to dotted hole paths:<br/><code>fn.p1</code>, <code>fn.p2.field_1</code>"]
  end

  subgraph L1["LEVEL 1: PHRASE TREE (unfold via Phrase[Inner] Functor)"]
    direction TB
    Msg["<b>Root Phrase (Whole Message)</b><br/><code>Phrase(start=0, end=N, brand=None)</code>"]
    P_Block["<b>Intermediate Phrase (Paragraph / List Block)</b><br/><code>starts_by: 'a blank line' | 'a list item'</code>"]
    P_Asked["<b>Leaf Phrase (User Sentence)</b><br/><code>brand: Asked</code><br/><code>choice: d1 OneOf(world.functions | none | nothing)</code>"]
    P_Written["<b>Leaf Phrase (Quoted Reply)</b><br/><code>brand: Written</code> (matched by <code>written()</code>)<br/>Enters context as <code>Constant(Written)</code>"]
    Msg --> P_Block --> P_Asked
    Msg --> P_Written
  end

  subgraph L2["LEVEL 2: SYNTHESIZED TERM TREE (solve &amp; derivations per Asked Phrase)"]
    direction TB
    App["<b>Application Node</b><br/><code>Application(function, arguments)</code><br/>Produces output token <code>➊ fn(...) : ResultType</code>"]
    Rec["<b>Record Node (Product Intro)</b><br/><code>Record(product, fields={name: Term})</code><br/>Expands into nested dotted holes<br/><code>fn.param.field</code>"]
    Sev["<b>Several Node (Many[T])</b><br/><code>Several(inner_type, terms=(t1, t2, ...))</code>"]
    Emp["<b>Empty Node (Maybe[T])</b><br/><code>Empty(Maybe[T])</code> (faint optional hole)"]
    HoleNode["<b>Open Hole Node</b><br/><code>Hole(goal_type)</code><br/>When no term fits or <code>d1</code> picks <code>none</code>"]
    ConstNode["<b>Leaf Constant / Earlier App</b><br/><code>Constant(type, value, start, end)</code><br/>or <code>↩ Earlier Application (Later[T])</code>"]

    P_Asked --> App
    App --> Rec
    App --> Sev
    App --> Emp
    App --> HoleNode
    App --> ConstNode
    Rec --> ConstNode
    Rec --> HoleNode
    Sev --> ConstNode
  end

  subgraph L3["LEVEL 3: BOARD EDIT STATE (decided(ev) in index.html)"]
    direction LR
    BoardState["<b>st.parts[n]</b><br/>• <code>fns</code>: <code>[{id, fn}, ...]</code><br/>• <code>things</code>: <code>{'fn.path.subpath': value | null}</code><br/>• <code>by</code>: <code>{'fn.path.subpath': pieceId}</code>"]
  end

  L0 ==>|"Governs unfolding &amp; hole types"| L1
  L0 ==>|"Provides candidate types &amp; functions"| L2
  L2 ==>|"Flattens via leaves(term, path) / term_record"| L3
```

### B. Complete State-Transition Workflow Chart
```mermaid
flowchart TD
  Closed["<b>CLOSED MODE (OPEN = false)</b><br/>Single running paragraph.<br/>• Grounded spans highlighted in place by type color<br/>• End of each sentence shows tag: <code>fn</code>, <code>nothing</code>, or <code>none</code>"]
  OpenMode["<b>OPEN MODE (OPEN = true)</b><br/>Click message or press <code>Edit</code>:<br/>1. Each phrase unpacks its active <b>Function Bricks</b> &amp; nested <b>Holes</b> (<code>path=value</code> or <code>path=Type1 | Type2</code>)<br/>2. The <b>World Tray</b> unfolds below with all <code>world.py</code> Functions, Types, &amp; Sum Members"]

  Closed -->|"Click message / toggle OPEN"| OpenMode
  OpenMode -->|"Click message / toggle CLOSED"| Closed

  subgraph Draggables["6 DRAGGABLE SOURCES IN OPEN MODE (draggable() in index.html)"]
    D_Piece["<b>1. Grounded Piece in Sentence</b><br/><code>piece (pc-id)</code><br/>Span of text grounded to <code>p.type</code>"]
    D_Value["<b>2. Value Inside a Hole</b><br/><code>value (v-fn-key)</code><br/>Currently filling <code>parts[n].things[key]</code>"]
    D_Brick["<b>3. Function Brick on a Phrase</b><br/><code>brick (f-id)</code><br/>An active function call on <code>parts[n]</code>"]
    D_WorldFn["<b>4. World Function in Tray</b><br/><code>tfn (tf-fn)</code><br/>Any function defined in <code>world.py</code>"]
    D_WorldMember["<b>5. Sum Type Member in Tray</b><br/><code>member (m-ti-vi)</code><br/>Any Enum member defined in <code>world.py</code>"]
    D_WorldType["<b>6. Type Chip in Tray</b><br/><code>type (ty-ti)</code><br/>Dashed type chip in <code>world.py</code>"]
  end

  OpenMode --> D_Piece & D_Value & D_Brick & D_WorldFn & D_WorldMember & D_WorldType

  subgraph Transitions["ALLOWED STATE TRANSITIONS (Pure Functions: State → NextState)"]
    T_FillFromPiece["<b>fill(st, n, key, p.value, p.id)</b>"]
    T_UnlinkPiece["<b>unlink(st, p.id)</b>"]
    T_MoveValue["<b>fill(empty(st, n1, key1), n2, key2, v, pid)</b>"]
    T_PullOutValue["<b>empty(st, n, key) via whenFar(out)</b>"]
    T_MoveFn["<b>moveFn(st, a, b, f)</b>"]
    T_DropFn["<b>dropFn(st, n, f)</b>"]
    T_AddFn["<b>addFn(ev, st, n, fn)</b>"]
    T_FillFromMember["<b>fill(st, n, key, member, null)</b>"]
    T_EmptyByType["<b>empty(st, n, key) / Activate Faint Hole</b>"]
  end

  D_Piece -->|"Drop on compatible hole"| T_FillFromPiece
  D_Piece -->|"Drop on Tray (if linked)"| T_UnlinkPiece
  D_Value -->|"Drop on another compatible hole"| T_MoveValue
  D_Value -->|"Drag away anywhere (whenFar)"| T_PullOutValue
  D_Brick -->|"Drop on another phrase p-b"| T_MoveFn
  D_Brick -->|"Drop on World Tray"| T_DropFn
  D_WorldFn -->|"Drop on phrase p-n"| T_AddFn
  D_WorldMember -->|"Drop on compatible hole"| T_FillFromMember
  D_WorldType -->|"Drop on hole of that type"| T_EmptyByType
```
