"""The independent oracle for the repair of next: requirements, expected results and predicates.

This is test code. It imports nothing from the engine and never asks d1. It holds:

* ``REQUIREMENTS``: the complete requirement inventory, as data, each item with
  the exact words of its source.
* ``CASES``: for each of the 22 acceptance cases, the runs that exercise it:
  the message, the world, the answers that the stand-in d1 gives, the steps,
  and the expected outcome in the neutral form below.
* ``PREDICATES``: one function per case. Each takes what the system produced,
  in the neutral form, compares its expected steps and decisions, adds what
  the case needs beyond them, and returns specific diagnostics. An empty list
  is a pass.
* ``NEGATIVE_CONTROLS``: what each known wrong implementation would produce,
  and the diagnostic that must reject it.
* ``INVARIANT_TABLE``: each invariant, the cases that check it, and an empty
  ``observed`` field that the final run fills.
* ``observe``: the signature of the one adapter that the implementer writes.
* ``CORRECTIONS``: each versioned change to this oracle, why, and the cases it affects.

The neutral form
----------------
An observation of one run is a dict::

    {"world_faults": [(declaration name, rule), ...],  # hard faults only: the declaration is refused
     "world_functions": [function name, ...],      # sorted
     "steps": {step label: step, ...}}             # in the order of the run

A design advisory (a shared signature, a type with one use) is no fault and is
not reported in ``world_faults``.

A step is a dict. A step has only the keys that its action produces:

    "obligations": [Obligation, ...]   # the current reading; a draft if one exists
    "passages":    [Passage, ...]      # every span of the message that is no obligation
    "decisions":   [Decision, ...]
    "diagnostics": [(obligation index or None, path or None, rule), ...]
    "accepted":    bool                # for an edit, a save or a world proposal
    "corrections": [Correction, ...]
    "checks":      [Check, ...]
    "verdict":     PASS | FAIL | UNVERIFIED
    "world_change": {"activated": bool, "verdict": ..., "regressions": [(message, obligation), ...]}
    "model_calls": int                 # requests sent to d1 during this step
    "writes":      int                 # successful writes to the store during this step
    "error":       None | exception class name

An obligation is one operation instance that the source asks for, including an
operation nested inside another term. Obligations are listed in the order of
their phrase in the message; within one phrase, an operation whose result
another operation of the phrase consumes comes first. A binding value is one of:

* ``Lit(type, value)``: a literal. ``value`` is the member's words, an int, or a path as text.
* ``Ref(i)``: the result of obligation ``i``: the engine holds a reference to
  that same operation instance, by identity. A copy of an application, however
  equal, is another obligation, never a ``Ref``. Two equal ``Ref`` are one
  result; two obligations are always two operation instances, however alike
  they read. ``i`` is smaller than the index of the obligation that holds it.
* ``EMPTY``: a deliberate absence in a ``Maybe``.
* ``EMPTY_LIST``: an explicit empty ``Many``.
* ``Hole(type, reason)``: a typed hole, with one of the reasons below.
* a tuple of the above: the members of a ``Many``. Membership counts; order does not.
* in EXPECTED only, a frozenset of the above: any one of them is acceptable.

A record is not a value of its own: its fields are bindings at dotted paths,
such as ``"cell.number"``. An unknown operation is ``UNRESOLVED``, never
"none" or "nothing". Its ``bindings`` report every term or hole that the
engine attaches to it (a term for the whole phrase at path ``""``), so a
guessed goal type is visible; a correct engine attaches none.
"""

import ast
import copy
import dataclasses
import hashlib
import importlib.util
import pathlib
import re
import subprocess
import sys

BRIEF = "/Users/max/Documents/scriptt-design-review-2026-11-10/repair-next-prompt.md"
LOCATION_MESSAGE = "Max's message of 10 Nov, \"declared repair worktree\""
HERE = pathlib.Path(__file__).resolve().parent
DECLARED_ROOT = pathlib.Path("/Users/max/Documents/scriptt-repair")
REFERENCE_ROOTS = (pathlib.Path("/Users/max/Documents/scriptt-next"), pathlib.Path("/Users/max/Documents/scriptt-release"))
SNAPSHOT_FILES = ("next/agree.py", "next/scriptt16.py", "next/world.py", "next/test_scriptt16.py", "next/notebook.py", "next/expected.py", ".scriptt/harness.py")
IMPORTED_MODULES = ("agree", "scriptt16", "harness", "test_scriptt16", "expected")

# ---- The neutral form -------------------------------------------------------

PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "UNVERIFIED"
PENDING, AVAILABLE = "pending", "available"
UNRESOLVED = "UNRESOLVED"
EMPTY, EMPTY_LIST = "EMPTY", "EMPTY_LIST"
RETAINED, INVALIDATED = "retained", "invalidated"

# Why a hole or an unresolved operation has no value.
REJECTED = "rejected"            # d1 was offered the candidates and rejected every one
NO_CANDIDATE = "no candidate"    # no well-typed candidate was in scope; nobody was asked
BOUNDED = "bounded"              # a search limit cut the candidates
INVALID_ANSWER = "invalid answer"  # the answer of d1 was malformed, missing or out of set
CLEARED = "cleared"              # an explicit edit cleared the binding

# The rules that a diagnostic or a world fault names.
RULES = ("kind", "type", "missing", "extra", "reference", "name", "model_answer", "identity")


@dataclasses.dataclass(frozen=True)
class Lit:
    """A literal value: member words, an int, or a path as text, with its type name."""

    type: str
    value: object


@dataclasses.dataclass(frozen=True)
class Ref:
    """The result of the obligation with this index."""

    obligation: int


@dataclasses.dataclass(frozen=True)
class Hole:
    """A typed hole. In EXPECTED, ``type`` and ``reason`` can be tuples of acceptable answers."""

    type: str | tuple
    reason: str | tuple


@dataclasses.dataclass(frozen=True)
class New:
    """A candidate that is a new application of an operation. Used in scripts and in offered candidates."""

    operation: str


@dataclasses.dataclass(frozen=True)
class Obligation:
    """One requested operation instance.

    Attributes:
        span: The text of the innermost source phrase that holds it, stripped.
        operation: The function name, or UNRESOLVED.
        bindings: The value at each argument path.
        status: The engine's own dependency judgment, never recomputed by the
            adapter: PENDING if its result is Later or any input, at any depth
            of Record, Many or Maybe, is the result of a PENDING obligation;
            else AVAILABLE. A hole is incompleteness, not pending. None for UNRESOLVED.
        reason: Why the operation is UNRESOLVED; None otherwise.
        brand: The brand of the phrase.
    """

    span: str
    operation: str
    bindings: dict = dataclasses.field(default_factory=dict)
    status: str | None = AVAILABLE
    reason: str | tuple | None = None
    brand: str = "Asked"


@dataclasses.dataclass(frozen=True)
class Passage:
    """A span that is no obligation: a quote, a remark, a context or a constraint.

    Attributes:
        text: The text, stripped.
        brand: The brand of the phrase.
        origin: "user", or "reply N" for a quote of the N-th earlier reply given.
        relation: The relationship to the request. Never empty, "none" or "nothing".
    """

    text: str
    brand: str
    origin: str
    relation: str


@dataclasses.dataclass(frozen=True)
class Decision:
    """One recorded decision about an operation (path None) or a binding.

    Attributes:
        obligation: The obligation index.
        path: The argument path, or None for the choice of the operation.
        by: "model" for a d1 answer, "rule" for a declared deterministic default.
        offered: The candidates offered, as neutral values, operation names,
            ABSTAIN or NO_REQUEST.
        chosen: The chosen candidate; a tuple for a Many; REJECT or ABSENT.
            An edit never changes it: a correction is a separate record.
        cut: The candidates that a bound excluded.
        state: The exact text that d1 read; it holds the phrase.
        instructions: The exact question.
        scores: The share of each option, as (option, share) pairs, options
            named as in ``offered``.

    A Many chosen by one yes/no question per candidate is one Decision.
    """

    obligation: int
    path: str | None
    by: str
    offered: tuple = ()
    chosen: object = None
    cut: tuple = ()
    state: str = ""
    instructions: str = ""
    scores: tuple = ()


@dataclasses.dataclass(frozen=True)
class Correction:
    """An accepted manual binding and what became of it."""

    obligation: int
    path: str
    value: object
    status: str
    reason: str = ""


@dataclasses.dataclass(frozen=True)
class Check:
    """One criterion-specific fulfillment outcome.

    Attributes:
        obligation: The obligation index.
        item: A member of a Many argument that this check is about, or None.
        criterion: The criterion name given by the case.
        outcome: PASS, FAIL or UNVERIFIED.
        evidence: The index of the supplied artifact that justifies the outcome, or None.
    """

    obligation: int
    item: object
    criterion: str
    outcome: str | tuple
    evidence: int | None = None


# ---- What a case gives the system ------------------------------------------

ABSTAIN = "ABSTAIN"        # d1: the phrase asks for something that no function fits
NO_REQUEST = "NO_REQUEST"  # d1: the phrase asks for nothing; it is a remark, a context or a rule
REJECT = "REJECT"          # d1: none of the offered candidates
ABSENT = "ABSENT"          # d1: the optional value is deliberately absent


@dataclasses.dataclass(frozen=True)
class Malformed:
    """A malformed answer of d1: "out_of_set", "missing" or "not_numbers"."""

    kind: str


@dataclasses.dataclass(frozen=True)
class World:
    """A world: the test file's WORLD ("test") or next/world.py ("next"), changed as given."""

    base: str = "test"
    replace: tuple = ()
    extra: str = ""
    files: tuple = ()


@dataclasses.dataclass(frozen=True)
class Edit:
    """A semantic edit. ``set`` binds a value, ``clear`` makes a hole, ``remove`` deletes the key."""

    op: str
    obligation: int
    path: str
    value: object = None


@dataclasses.dataclass(frozen=True)
class Artifact:
    """Supplied evidence about one exact operation and its bindings, with its value."""

    operation: str
    bindings: dict
    value: object = None


@dataclasses.dataclass(frozen=True)
class Run:
    """One run of a case.

    Attributes:
        label: The name of the run.
        control: True for a successful control.
        world: The world.
        messages: The messages, read in order. Usually one.
        replies: The earlier replies.
        script: ``{"ops": {phrase: answer}, "binds": {(phrase, operation, path): answer}, "judge": share}``.
        steps: ``(label, action, expected step)``. The expected step has only the keys that are compared.
    """

    label: str
    control: bool
    world: World
    messages: tuple
    script: dict
    steps: tuple
    replies: tuple = ()


@dataclasses.dataclass(frozen=True)
class Case:
    """One acceptance case of the brief."""

    id: str
    words: str
    required: str
    catches: str
    runs: tuple
    interpretation: str = ""
    real_d1: str = ""


def observe(case: Case, run: Run) -> dict:
    """Runs one run of a case on the repaired engine and returns its neutral observation.

    The implementer writes this adapter once, in the test file. It must not be
    changed to make a predicate pass. Its contract:

    * World: ``World("test")`` is ``test_scriptt16.WORLD``, ``World("next")`` is
      the text of ``next/world.py``; apply ``replace`` with ``str.replace`` in
      order, append ``extra``, load with ``test_scriptt16.world_of`` in a
      temporary folder that holds an empty file for each name in ``files``.
      Report the loader's hard faults as ``(declaration name, rule)`` with a
      rule from ``RULES``, and the loaded function names, sorted.
    * Stand-in d1: answer by meaning, from ``run.script``. An operation question
      about phrase P gets ``ops[P]``: a function name (or a tuple of names when
      the phrase asks for several), ``ABSTAIN`` (the engine's option for "no
      function fits"), ``NO_REQUEST`` (its option for "asks for nothing"), or a
      ``Malformed`` answer: "out_of_set" returns ``{"probabilities":
      {"frobnicate": 1.0}}``, "missing" returns no entry for the key,
      "not_numbers" returns ``{"probabilities": {"redesign": "high"}}``. A
      binding question about (P, operation, path) gets ``binds[...]``: the
      offered option whose neutral projection equals the value or ``New``,
      ``REJECT`` (the none-of-these option), ``ABSENT`` (the absence option),
      or for a yes/no-per-candidate Many question, yes exactly for the members
      of the tuple. Phrases are looked up by their exact text, stripped.
      Unscripted, or when no offered option equals the scripted value: an
      operation question gets NO_REQUEST, a binding question REJECT, a yes/no
      question about a reply ``script.get("judge", 0.1)``. The chosen option
      gets share 0.9 and the others share the rest equally. One request to d1
      is one model call, however many questions it holds.
    * Steps, each acting on the state that the previous step left:
      ``("read",)`` reads every message; ``("preview", Edit)``,
      ``("stage", Edit)``, ``("correct", Edit)`` (stage as an accepted manual
      correction), ``("cancel",)``, ``("save",)``, ``("save_fail",)`` (save with
      the store's write made to raise), ``("reload",)`` (load from the store
      into a fresh process state, with a model that raises if called;
      ``("reload", World)`` loads it under that world), ``("inspect", i,
      path)`` (select and expand the binding, its type and its decision),
      ``("restore", n)`` (the n-th successful save, from 1), ``("rerun",)``
      (read the saved source again with the same script), ``("change_world",
      World)`` (read again with the new world), ``("restyle",)`` (reload with
      the display renderer scoped-monkeypatched to another format),
      ``("check", reply, artifacts, criteria)``, ``("propose_world", World,
      script)`` (the messages read so far are the accepted corpus).
    * Each step reports the keys of the neutral form that its action produces,
      projected from the engine's own data structures, never parsed from
      ``say()`` text and never recomputed by the adapter (``status`` and
      ``Ref`` come from the engine's dependency judgment and object identity).
      ``model_calls`` and ``writes`` count what happened during that step
      only. An exception is reported as ``error`` and the run goes on.

    Args:
        case: The case.
        run: One of its runs.

    Returns:
        The observation in the neutral form of this module's docstring.
    """
    raise NotImplementedError("the implementer writes this adapter in the test file")


# ---- The requirement inventory ----------------------------------------------

INVARIANTS = {
    "I1": ("Mandatory invariants", "Coverage:", "Every source span remains traceable through its enclosing typed phrase. Every requested obligation remains represented, even if the operation is unresolved. Context and constraints have explicit relationships. No unresolved demand disappears from verification through none/nothing, splitting, optional omission or gate scoring."),
    "I2": ("Mandatory invariants", "Recursive validity:", "One validation judgment checks terms and supported edits, including exact argument/field ownership, child types, recursive kind validity, scope, reference targets and dependencies. Partial terms use explicit typed holes. Invalid edits preserve the prior state. `type_of` on a trusted declaration is not validation of a malformed term."),
    "I3": ("Mandatory invariants", "Compatibility versus meaning:", "Compatible values are candidates, not proven arguments. Semantic selection can exclude a singleton, handle negation and choose a subset for Many. Missing, deliberately empty and unresolved remain distinct. Explain and record deterministic defaults and limits."),
    "I4": ("Mandatory invariants", "Composition:", "Eligible existing values/results are considered before reconstructing them. Typed producer/consumer chains do not require every intermediate type to occur lexically. New applications must also be licensed by the source meaning or an explicit accepted world rule; a fitting output type alone does not authorize unrequested work. Repeated applications of one function with different arguments remain available. Bounds limit search, not the language's definition of validity."),
    "I5": ("Mandatory invariants", "Identity:", "Distinguish a source occurrence, an operation instance, its original input and its result. A reference to a result preserves that identity through save/load and does not imply another execution. Two intentionally separate identical operations remain separate. Display text is not semantic equality. Add only the minimum fields/links needed to preserve this."),
    "I6": ("Mandatory invariants", "Constructor semantics:", "A pending or unresolved dependency remains so through nested records, collections and optional values. Maybe absence requires an absence decision; rejected candidates do not imply absence. Define whether Many permits zero elements; for this repair use an explicit empty collection distinct from a hole. Removing Later or changing a brand cannot create completion or evidence."),
    "I7": ("Mandatory invariants", "Reversible edits:", "Inspect/expand is view-only. Preview is pure. Cancel is exact restoration. A staged edit uses the same AST as synthesis. Save/load preserves it; failed saves retain it; restoring a prior snapshot restores interpretation, not external effects. Minimal snapshot reversal suffices; do not build event sourcing."),
    "I8": ("Mandatory invariants", "Faithful decisions:", "Preserve actual d1 state, instructions, options, scores and selected candidate identity, linked to the goal/path and relevant source/world. Record automatic bindings and consequential exclusions/bounds. Distinguish type rejection, semantic rejection, heuristic pruning and unexamined candidates. Reconstructing a saved explanation does not call d1 or invent its hidden reasoning."),
    "I9": ("Mandatory invariants", "Acceptance:", "Accepted meaning and required evidence cannot be weakened by a world edit. Confidence is separate. An empty corpus, skipped criterion, missing required evidence or unresolved demand cannot yield overall acceptance. Check exact obligations and bound arguments, including repeated operations, rather than repeating a generic docstring question."),
    "I10": ("Mandatory invariants", "Minimality:", "One implementation of each rule; no artificial domain nouns/functions, parallel status hierarchies or generic infrastructure. Every added abstraction must serve a demonstrated invariant that simpler existing data cannot express."),
}

WRONG_IMPLEMENTATIONS = {
    "W1": ("always accept gate changes", "C02"),
    "W2": ("drop an unresolved obligation", "C01"),
    "W3": ("include every local Many item", "C03"),
    "W4": ("ignore nested pending dependencies", "C10"),
    "W5": ("duplicate a shared result", "C15"),
    "W6": ("certify all repeated operations from one generic reply", "C20"),
}

LOCATION = {
    "L1": ("The declared repair worktree is /Users/max/Documents/scriptt-repair (it overrides the brief's \"Work in scriptt-release/next\"); /Users/max/Documents/scriptt-next is reference only.",
           "provenance.worktree is the declared root, and no reference root"),
    "L2": ("Every test and review result identifies the working path and the source snapshot (git commit + sha256 of the engine files).",
           "provenance has the worktree, a 40-hex commit and a sha256 for every snapshot file"),
    "L3": ("Verify which files Python actually imports (agree, scriptt16, harness/shipped and any other next module must resolve under the declared worktree — e.g. by module __file__ against the worktree root derived from the test file's own path / git rev-parse).",
           "every required module's file resolves under the worktree"),
    "L4": ("Before completion, the delivered files must match the tested and reviewed snapshot (hashes recorded at test time equal the files delivered).",
           "the recorded hashes equal the hashes of the delivered files"),
    "L5": ("Temporary fixtures and isolated negative-control copies are allowed and do not count as delivered implementation; changes made elsewhere must be disclosed and transferred to the target before acceptance.",
           "every disclosed change elsewhere is transferred"),
    "L6": ("Location checks are deterministic, from existing path/configuration data — no framework, never ask d1.",
           "provenance.method is path and git data"),
}

# Requirements of the brief that are about the deliverable, not about behavior. The
# final report checks them; no predicate over an observation can.
PROCESS = {
    "P1": ("Smallest code is an acceptance requirement", "Use the existing `World`, `Phrase`, `Term`, `Model` and constructor representations."),
    "P2": ("Smallest code is an acceptance requirement", "Consolidate the notebook's copied algorithms so demonstrations exercise the repaired implementation."),
    "P3": ("Smallest code is an acceptance requirement", "Report production, tests, notebook duplication and documentation separately, before and after."),
    "P4": ("The state machine to implement", "Validity, completeness, availability and fulfillment are separate judgments, derived where possible rather than maintained as redundant flags."),
    "P5": ("The state machine to implement", "A world with invalid types cannot activate. A changed world that contradicts an accepted meaning cannot activate silently."),
    "P6": ("Use the system itself without making the check circular", "Keep live-d1 evaluation separate from deterministic conformance."),
    "P7": ("Deliver and stop only when the repair is concrete", "Report each invariant and acceptance case as pass, fail or unverified with a direct evidence reference."),
}


# Each change to this oracle after its first review. Version 1 is commit 5b524a0.
# Every observed result must be judged again against the version that holds it;
# no result had been produced against version 1.
ORACLE_VERSION = 2
CORRECTIONS = (
    ("E1", 2, "status could be recomputed by the adapter from the projected bindings, making C10 circular, and was not transitive through a pending operation's non-Later result",
     "observe() now takes status from the engine's own dependency judgment and defines it transitively; run C10 through_result", ("C10", "C15", "C18", "C19")),
    ("E2", 2, "Ref(i) could be projected by structural equality, hiding a duplicated tree", "Ref is engine object identity; a copy is another obligation; a Ref must name an earlier obligation in every step", ("C15", "C17", "C22")),
    ("E3", 2, "the neutral form had no place for a goal type guessed for an unknown operation", "an UNRESOLVED obligation reports any attached term or hole in bindings, which the guessed-goal rule rejects", ("C01", "C14", "C22")),
    ("E4", 2, "the contract put design advisories (duplicate, single_use, grounding) in world_faults, so a correct engine that only advised failed C09 and C12", "world_faults hold hard faults only", ("C09", "C11", "C12")),
    ("E5", 2, "the stand-in had no answer when the scripted value is not offered, no rule for counting a request with several questions, and no projection for a Many chosen by yes/no questions",
     "it answers REJECT/NO_REQUEST; one request is one call; such a Many is one Decision", ("C03", "C05", "C06", "C19")),
    ("E6", 2, "a lexical negation rule applied over d1's answer passed both runs of C03, so 'd1 must be given the relevant choice' was not shown to decide the binding", "run follows_d1, where d1's answer differs from the lexical rule", ("C03",)),
    ("E7", 2, "C05 absent had no candidate and accepted Empty from a declared rule, which merges missing with deliberately empty (I3, I6: 'absence requires an absence decision'); the rejected run did not require d1's rejection",
     "the absent run has the mod in scope and requires d1's absence answer; the rejected run requires d1's rejection; the no-candidate optional is left to Max", ("C05",)),
    ("E8", 2, "the unknown Many forced reason no candidate, though an engine may offer d1 an empty choice", "reason no candidate or rejected", ("C06",)),
    ("E9", 2, "a rejected edit passed if its diagnostic was among others, so an imprecise validator passed; nothing checked recursion into fields or the type of a hole",
     "diagnostics are compared exactly; edits wrong_field_type and wrong_hole_type", ("C11", "C14", "C18", "C22")),
    ("E10", 2, "the quote passage had to include its quote marks, an arbitrary span choice", "texts are compared without the quote marks around them", ("C13",)),
    ("E11", 2, "a world refusing `none` could drop the request entirely and pass; the bounded message asked to show nine things, so one show with a hole was not its meaning",
     "the request must stay UNRESOLVED unless the read itself is refused; the bounded message asks for one unknown item; its hole may say bounded", ("C14",)),
    ("E12", 2, "cancel and restore were checked on bindings only, and inspect was untested (I7)", "an inspect step; cancel and restore keep the reading's decisions", ("C18",)),
    ("E13", 2, "the C19 note said Ref(0) after invalidation is silent, but the predicate allowed it, and a world change could drop the show obligation", "note corrected; both obligations required", ("C19",)),
    ("E14", 2, "the page with no evidence had to be UNVERIFIED, though FAIL is allowed; 'removing Later cannot create completion' (I6) was untested", "UNVERIFIED or FAIL; run later_removed", ("C20",)),
    ("E15", 2, "the production-world check read a key that observe() never defines, so it was vacuous", "it reads next/world.py itself", ("C21",)),
    ("E16", 2, "an edit could rewrite d1's recorded choice consistently and pass; decisions could lose the phrase d1 read; a world mismatch on load was untested",
     "d1's choice is kept beside the edit; model decisions keep their question and phrase; step other_world", ("C03", "C04", "C05", "C06", "C07", "C08", "C15", "C18", "C22")),
    ("E17", 2, "a check, save or inspect step could change the reading unseen; a word of the message could vanish from every obligation and passage",
     "those steps must leave the reading as it was; a read of one message covers every word", ("C01", "C06", "C13", "C14")),
    ("E18", 2, "C02 never changed a binding or proposed an invalid world, so a gate comparing operation names only, or one activating an invalid world, passed",
     "runs weakened and invalid_world", ("C02",)),
    ("E19", 2, "L4 compared only the files listed as delivered, so a missing file passed", "it compares every snapshot file", ()),
)


# ---- Shorthand for the expected structures -----------------------------------

MOD, PAGE, SEARCH = Lit("Surface", "the mod"), Lit("Surface", "the page"), Lit("Code", "the search")
NOTES, THREE = Lit("Path", "notes.md"), Lit("int", 3)
TEST_FUNCTIONS = ["approve", "compare", "explain", "follow", "open_cell", "redesign", "review", "show"]


def ob(span, operation, bindings=None, status=AVAILABLE, reason=None):
    """Returns an expected obligation."""
    return Obligation(span, operation, bindings or {}, None if operation == UNRESOLVED else status, reason)


def script(ops, binds=None, judge=None):
    """Returns the answers of the stand-in d1 for a run."""
    found = {"ops": ops, "binds": binds or {}}
    return found | ({"judge": judge} if judge is not None else {})


def told(obligations: list, judge=None) -> dict:
    """Returns the answers of a stand-in d1 that means exactly these obligations.

    Each phrase gets its operations (ABSTAIN for an UNRESOLVED one), each argument its value.
    """
    ops, binds = {}, {}
    for one in obligations:
        ops[one.span] = ops.get(one.span, ()) + (ABSTAIN if one.operation == UNRESOLVED else one.operation,)
        binds |= {(one.span, one.operation, path): value for path, value in one.bindings.items() if not isinstance(value, Hole) and value not in (EMPTY, EMPTY_LIST)}
    return script({span: names[0] if len(names) == 1 else names for span, names in ops.items()}, binds, judge)


READ = ("read",)
SAVE = ("save",)
RELOAD = ("reload",)
SPECIMEN = "Redesign the mod. Then show it. Test the search too."
QUOTE = "These seven words are the entire earlier reply."
BOUNDED_TEXT = "Show whichever of the page, the site, the ui, the mod, the pane, the visualization, the harness, the hook and the tests changed."
NINE = (PAGE, Lit("Surface", "the site"), Lit("Surface", "the ui"), MOD, Lit("Surface", "the pane"), Lit("Surface", "the visualization"),
        Lit("Code", "the harness"), Lit("Code", "the hook"), Lit("Code", "the tests"))


def wrong_double(number: int) -> int:
    """The test-only fixture of C21: the right type, the wrong result."""
    return number + 1


def right_double(number: int) -> int:
    """The control fixture of C21."""
    return number * 2


def exact_artifact(obligation, artifact):
    """Criterion "evidence": the artifact is about exactly this operation and these bindings."""
    return artifact.operation == obligation.operation and artifact.bindings == obligation.bindings


DOUBLED = ob("Double 3.", "double", {"number": THREE})
DOUBLE_WORLD = World(extra='\ndef double(number: int) -> int:\n    "double a number"\n')
DOUBLE_CRITERIA = (("type", "the result is an int", lambda obligation, artifact: isinstance(artifact.value, int)),
                   ("behavior", "the result is twice the number", lambda obligation, artifact: artifact.value == 2 * obligation.bindings["number"].value))
EVIDENCE_CRITERIA = (("evidence", "an artifact for exactly this operation and these bindings", exact_artifact),)

REDESIGN_SHOW = [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Then show it.", "show", {"subject": Ref(0)}, PENDING)]
REBOUND = [REDESIGN_SHOW[0], ob("Then show it.", "show", {"subject": MOD})]
CLEARED_SHOW = [REDESIGN_SHOW[0], ob("Then show it.", "show", {"subject": Hole("Subject", CLEARED)})]
SHOW_DECISION = Decision(1, "subject", "model", (Ref(0), MOD), Ref(0))
CELL_WORLD = World(files=("notes.md",))
CELL_BASE = [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING),
             ob("Open cell 3 of notes.md.", "open_cell", {"cell.notebook": NOTES, "cell.number": THREE})]
EMAIL = ob("Email my accountant.", UNRESOLVED, reason=REJECTED)
TESTED = REDESIGN_SHOW + [ob("Test the search too.", "test", {"subject": SEARCH})]
TESTED_REBOUND = REBOUND + TESTED[2:]
RESHAPED = [ob("Reshape cell 3 of notes.md.", "reshape_cell", {"cell.notebook": NOTES, "cell.number": THREE}, PENDING), ob("Open that cell.", "open_cell", {"cell": Ref(0)}, PENDING)]
ARCHIVED = [ob("Archive the page.", "archive", {"surface": PAGE}, PENDING), ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)]
EDITED = [ob("Redesign the mod.", "redesign", {"surface": PAGE}, PENDING), REDESIGN_SHOW[1], EMAIL]


PAINT_WORLD = World(extra='\ndef paint(surface: Surface) -> Observed:\n    "paint it"\n')
BROKEN_WORLD = World(extra="\ntype Broken = Many | int\n")
TOKEN_WORLD = World(extra='\nToken = typing.NewType("Token", str)\n\ndef make_token(surface: Surface) -> Token:\n    "make a token"\n\ndef use_token(token: Token) -> Observed:\n    "use a token"\n')
BOX_WORLD = World(extra='\n@dataclasses.dataclass\nclass Box:\n    "a box"\n    surface: Surface\n\ndef pack(box: Box) -> Written:\n    "pack a box"\n\ndef describe(surface: Maybe[Surface]) -> Written:\n    "describe a surface"\n')
MAYBE_SURFACE = World(replace=(("Maybe[Words]", "Maybe[Surface]"),))
TWO = ("Redesign the mod.", "Show the page.")
TWO_SCRIPT = script({"Redesign the mod.": "redesign", "Show the page.": "show"}, {("Redesign the mod.", "redesign", "surface"): MOD, ("Show the page.", "show", "subject"): PAGE})
REDESIGN_TWO = [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Redesign the page.", "redesign", {"surface": PAGE}, PENDING)]


def rejected_edit(rule_place):
    """The expected step of an edit that validation rejects: the base is kept."""
    return {"accepted": False, "diagnostics": [rule_place], "obligations": CELL_BASE, "model_calls": 0, "writes": 0}


# ---- The 22 cases -----------------------------------------------------------

CASES = (
    Case("C01", "Unsupported request, then “I did nothing”",
         "Typed source and unresolved interpretation persist; verification includes the obligation; overall acceptance is not pass. Do not fabricate Hole[Any], Hole[Unknown] or a guessed goal type. Legacy none/nothing may be retained as raw response metadata, never terminal semantic answers.",
         "An abstention leaves the phrase without a term and check() skips it (probe abstention_skips_verification); a fabricated Hole[Any].",
         (Run("unsupported", False, World(), ("Email my accountant.",), script({"Email my accountant.": ABSTAIN}),
              (("read", READ, {"obligations": [ob("Email my accountant.", UNRESOLVED, reason=REJECTED)], "passages": []}),
               ("checked", ("check", "I did nothing.", (), EVIDENCE_CRITERIA),
                {"checks": [Check(0, None, "evidence", (UNVERIFIED, FAIL))], "verdict": (UNVERIFIED, FAIL)}))),
          Run("supported", True, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)]}),
               ("checked", ("check", "I redesigned the mod.", (Artifact("redesign", {"surface": MOD}),), EVIDENCE_CRITERIA),
                {"checks": [Check(0, None, "evidence", PASS, 0)], "verdict": PASS})))),
         interpretation="The unresolved operation's reason is REJECTED: d1 was offered every operation and rejected them. The outcome of its check may be UNVERIFIED or FAIL; the brief only says it is not pass."),
    Case("C02", "Same-confidence world change deletes a request",
         "Reject the change regardless of probability. An empty acceptance corpus is unverified, never accepted.",
         "The confidence gate accepts a world that loses a request at equal bits, and accepts an empty corpus (probes gate_accepts_disappeared_request_when_confidence_is_equal, confidently_wrong_nothing_gate, empty_corpus_gate).",
         tuple(Run(label, label == "harmless", World(), () if label == "empty_corpus" else TWO, TWO_SCRIPT,
                   (() if label == "empty_corpus" else (("read", READ, {}),))
                   + (("proposed", ("propose_world", world, answers), {"world_change": {"activated": label == "harmless", "verdict": verdict, "regressions": lost}}),))
               for label, world, answers, verdict, lost in (
                   ("deleted", World(replace=(("def redesign(", "def destroy("),)), script({"Redesign the mod.": NO_REQUEST, "Show the page.": "show"}, {("Show the page.", "show", "subject"): PAGE}), FAIL, [(0, 0)]),
                   ("confident_nothing", PAINT_WORLD, script({"Redesign the mod.": NO_REQUEST, "Show the page.": NO_REQUEST}), FAIL, [(0, 0), (1, 0)]),
                   ("weakened", World(replace=(('    PAGE: Asked = "the page"\n', ""),)), TWO_SCRIPT, FAIL, [(1, 0)]),
                   ("invalid_world", BROKEN_WORLD, TWO_SCRIPT, FAIL, []),
                   ("empty_corpus", PAINT_WORLD, script({}), UNVERIFIED, []),
                   ("harmless", PAINT_WORLD, TWO_SCRIPT, PASS, []))),
         interpretation="A regression is a (message, obligation) of the accepted corpus whose operation or bindings change or disappear; run weakened removes the page member, so show's binding weakens to a hole. A world with an invalid kind cannot activate (the brief's state machine). An unverified world change does not activate."),
    Case("C03", "“Compare the mod, not the page”",
         "With controlled semantic selection, include mod and exclude page. Assert the binding, not merely rendered text. d1 must be given the relevant choice.",
         "solve(Many) takes every local term without asking d1 (probe many_negated_literal_is_included).",
         (Run("negated", False, World(), ("Compare the mod, not the page.",),
              script({"Compare the mod, not the page.": "compare"}, {("Compare the mod, not the page.", "compare", "surfaces"): (MOD,)}),
              (("read", READ, {"obligations": [ob("Compare the mod, not the page.", "compare", {"surfaces": (MOD,)})],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (MOD,))]}),)),
          Run("follows_d1", False, World(), ("Compare the mod, not the page.",),
              script({"Compare the mod, not the page.": "compare"}, {("Compare the mod, not the page.", "compare", "surfaces"): (MOD, PAGE)}),
              (("read", READ, {"obligations": [ob("Compare the mod, not the page.", "compare", {"surfaces": (MOD, PAGE)})],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (MOD, PAGE))]}),)),
          Run("both", True, World(), ("Compare the page and the mod.",),
              script({"Compare the page and the mod.": "compare"}, {("Compare the page and the mod.", "compare", "surfaces"): (PAGE, MOD)}),
              (("read", READ, {"obligations": [ob("Compare the page and the mod.", "compare", {"surfaces": (PAGE, MOD)})],
                               "decisions": [Decision(0, "surfaces", "model", (PAGE, MOD), (PAGE, MOD))]}),))),
         interpretation="Run follows_d1 is conformance, not meaning: when the stand-in includes both, both are bound, so the exclusion in run negated must come from d1 and not from a lexical negation rule applied over its answer.",
         real_d1="Whether real d1 excludes a negated item is effectiveness, unverified here; conformance shows only that d1 is asked and its answer is bound."),
    Case("C04", "Reject the only candidate", "Retain an unresolved obligation. A singleton is not compulsory.",
         "One candidate is taken with no question (scriptt16.solve: chosen_term = offered[0]).",
         (Run("rejected", False, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): REJECT}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", REJECTED)}, PENDING)],
                               "decisions": [Decision(0, "surface", "model", (MOD,), REJECT)]}),)),
          Run("accepted", True, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)],
                               "decisions": [Decision(0, "surface", "model", (MOD,), MOD)]}),))),
         interpretation="The obligation keeps its operation; the rejected argument becomes Hole(Surface, rejected). d1 is offered the singleton with a reject option. A declared automatic default that a correction can undo would not satisfy this case."),
    Case("C05", "Optional value: absent versus rejected/unknown",
         "Explicit absence produces Empty; unresolved selection remains unresolved; both survive save/load.",
         "A rejected or unresolved optional becomes Empty (probe optional_abstention_becomes_empty_rather_than_unresolved).",
         tuple(Run(label, label == "given", MAYBE_SURFACE, (text,), script({text: "explain"}, {(text, "explain", "subject"): answer}),
                   (("read", READ, {"obligations": [ob(text, "explain", {"subject": value})], "decisions": [Decision(0, "subject", "model", offered, answer)]}),
                    ("saved", SAVE, {}), ("reloaded", RELOAD, {"obligations": [ob(text, "explain", {"subject": value})], "model_calls": 0})))
               for label, text, answer, offered, value in (
                   ("absent", "Explain in general, not the mod.", ABSENT, (MOD,), EMPTY),
                   ("unresolved", "Explain the mod and the page.", REJECT, (MOD, PAGE), Hole(("Surface", "Maybe[Surface]"), REJECTED)),
                   ("given", "Explain the mod.", MOD, (MOD,), MOD))),
         interpretation="Absence and rejection are answers of d1 to the same kind of question, with a candidate in scope: Empty only from its absence option, a hole from its none-of-these option. The hole of a rejected optional may be typed Surface or Maybe[Surface]. Whether an optional with no candidate in scope must ask d1 about absence is left open (see CORRECTIONS E7)."),
    Case("C06", "Empty Many versus unknown Many",
         "Empty collection and typed hole remain distinguishable; selection can exclude local terms and include relevant earlier ones.",
         "An unknown Many becomes an empty collection, or local terms are always taken (scriptt16.solve, Many branch).",
         (Run("unknown", False, World(), ("Compare them.",), script({"Compare them.": "compare"}),
              (("read", READ, {"obligations": [ob("Compare them.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), (NO_CANDIDATE, REJECTED))})]}),
               ("saved", SAVE, {}),
               ("reloaded", RELOAD, {"obligations": [ob("Compare them.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), (NO_CANDIDATE, REJECTED))})]}))),
          Run("explicit_empty", False, World(), ("Compare them.",), script({"Compare them.": "compare"}),
              (("read", READ, {}),
               ("emptied", ("stage", Edit("set", 0, "surfaces", EMPTY_LIST)), {"accepted": True, "obligations": [ob("Compare them.", "compare", {"surfaces": EMPTY_LIST})]}),
               ("saved", SAVE, {}),
               ("reloaded", RELOAD, {"obligations": [ob("Compare them.", "compare", {"surfaces": EMPTY_LIST})]}))),
          Run("earlier_not_local", True, World(), ("I like the page. Compare it, not the mod.",),
              script({"I like the page.": NO_REQUEST, "Compare it, not the mod.": "compare"}, {("Compare it, not the mod.", "compare", "surfaces"): (PAGE,)}),
              (("read", READ, {"obligations": [ob("Compare it, not the mod.", "compare", {"surfaces": (PAGE,)})],
                               "passages": [Passage("I like the page.", "Asked", "user", "context")],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (PAGE,))]}),))),
         interpretation="The explicit empty collection comes from an explicit edit; zero members is a valid Many. The hole of an unknown Many may be typed Many[Surface] or Surface, with reason no candidate or rejected (if the engine offers d1 an empty choice). Passage relations are compared only for being present and not none/nothing."),
    Case("C07", "Reshape a Cell, then open that Cell",
         "Reuse the structured result, not a fresh record reconstructed from old fields. Retain pending dependency.",
         "Product synthesis rebuilds Cell from fields (probe product_result_is_reconstructed_from_original_fields).",
         (Run("reshape_open", False, World(extra='\ndef reshape_cell(cell: Cell) -> Later[Cell]:\n    "reshape a cell"\n', files=("notes.md",)),
              ("Reshape cell 3 of notes.md. Open that cell.",), told(RESHAPED),
              (("read", READ, {"obligations": RESHAPED,
                               "decisions": [Decision(1, "cell", "model", (Ref(0),), Ref(0))]}),)),)),
    Case("C08", "Redesign page, then request redesigned mod",
         "Preserve/generate redesign(mod); an existing redesign(page) must not suppress it.",
         "derivations() skips a function already present among candidates (probe earlier_application_suppresses_new_application_of_same_function).",
         (Run("page_then_mod", False, World(), ("Redesign the page. Show the mod redesigned.",),
              script({"Redesign the page.": "redesign", "Show the mod redesigned.": "show"},
                     {("Redesign the page.", "redesign", "surface"): PAGE, ("Show the mod redesigned.", "show", "subject"): New("redesign"),
                      ("Show the mod redesigned.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Redesign the page.", "redesign", {"surface": PAGE}, PENDING),
                                               ob("Show the mod redesigned.", "redesign", {"surface": MOD}, PENDING),
                                               ob("Show the mod redesigned.", "show", {"subject": Ref(1)}, PENDING)],
                               "decisions": [Decision(2, "subject", "model", (New("redesign"), Ref(0), MOD), New("redesign"))]}),)),)),
    Case("C09", "Typed intermediate with no lexical spelling",
         "For an explicitly requested producer-then-consumer chain, the producer can supply it; lexical absence is not a world fault. A contrasting case must leave a hole rather than invent unrequested production.",
         "ungrounded() rejects a nominal type that only a producer makes (probe produced_nominal_type_is_rejected_as_ungrounded_input); or production is invented for an unrequested input.",
         (Run("chain", False, TOKEN_WORLD,
              ("Make a token for the mod. Use that token.",),
              script({"Make a token for the mod.": "make_token", "Use that token.": "use_token"},
                     {("Make a token for the mod.", "make_token", "surface"): MOD, ("Use that token.", "use_token", "token"): Ref(0)}),
              (("read", READ, {"obligations": [ob("Make a token for the mod.", "make_token", {"surface": MOD}), ob("Use that token.", "use_token", {"token": Ref(0)})]}),)),
          Run("contrast", True, TOKEN_WORLD,
              ("Use a token.",), script({"Use a token.": "use_token"}, {("Use a token.", "use_token", "token"): REJECT}),
              (("read", READ, {"obligations": [ob("Use a token.", "use_token", {"token": Hole("Token", (NO_CANDIDATE, REJECTED))})]}),))),
         interpretation="The producer takes a Surface rather than words, so the expected bindings do not depend on how a phrase's own words become a value. In the contrast, d1 may or may not be offered New(make_token); either way no make_token obligation exists. The contrast is labelled a control because it is the case's second required behavior."),
    Case("C10", "Pending value nested in Record/Several/Maybe",
         "Recursive dependency inspection still reports pending; no wrapper can manufacture availability.",
         "type_of reports a Record or Several by its declared type, so its consumer is available (probe later_is_lost_through_records_and_collections).",
         tuple(Run(label, label == "plain", BOX_WORLD, (" ".join(dict.fromkeys(one.span for one in obligations)),), told(obligations), (("read", READ, {"obligations": obligations}),))
               for label, obligations in (
                   ("record", [REDESIGN_SHOW[0], ob("Pack it in a box.", "pack", {"box.surface": Ref(0)}, PENDING)]),
                   ("several", [REDESIGN_SHOW[0], ob("Compare it with the page.", "compare", {"surfaces": (Ref(0), PAGE)}, PENDING)]),
                   ("maybe", [REDESIGN_SHOW[0], ob("Describe it.", "describe", {"surface": Ref(0)}, PENDING)]),
                   ("through_result", [REDESIGN_SHOW[0], ob("Pack it in a box.", "pack", {"box.surface": Ref(0)}, PENDING), ob("Explain that.", "explain", {"subject": Ref(1)}, PENDING)]),
                   ("plain", [ob("Pack the mod in a box.", "pack", {"box.surface": MOD})]))),
         interpretation="Run through_result: explain consumes the Written result of a pack that waits on the redesign, so it is pending although no Later appears in its own argument."),
    Case("C11", "Invalid union kind, wrong child type, missing/extra argument or field, invalid reference",
         "Validation rejects each precisely. A deliberately typed hole remains a valid partial term.",
         "Kind checking accepts Many | int (probe unapplied_constructor_is_accepted_inside_union); Application and Record take any dict.",
         (Run("edits", False, CELL_WORLD, ("Redesign the mod. Open cell 3 of notes.md.",), told(CELL_BASE),
              (("read", READ, {"obligations": CELL_BASE}),
               ("wrong_child", ("preview", Edit("set", 0, "surface", NOTES)), rejected_edit((0, "surface", "type"))),
               ("missing_argument", ("preview", Edit("remove", 0, "surface")), rejected_edit((0, "surface", "missing"))),
               ("extra_argument", ("preview", Edit("set", 0, "colour", PAGE)), rejected_edit((0, "colour", "extra"))),
               ("missing_field", ("preview", Edit("remove", 1, "cell.number")), rejected_edit((1, "cell.number", "missing"))),
               ("extra_field", ("preview", Edit("set", 1, "cell.colour", PAGE)), rejected_edit((1, "cell.colour", "extra"))),
               ("wrong_field_type", ("preview", Edit("set", 1, "cell.number", PAGE)), rejected_edit((1, "cell.number", "type"))),
               ("wrong_hole_type", ("preview", Edit("set", 0, "surface", Hole("Cell", CLEARED))), rejected_edit((0, "surface", "type"))),
               ("dangling_reference", ("preview", Edit("set", 0, "surface", Ref(7))), rejected_edit((0, "surface", "reference"))),
               ("self_reference", ("preview", Edit("set", 0, "surface", Ref(0))), rejected_edit((0, "surface", "reference"))),
               ("typed_hole", ("preview", Edit("clear", 0, "surface")),
                {"accepted": True, "diagnostics": [], "obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", CLEARED)}, PENDING), CELL_BASE[1]]}))),
          Run("invalid_kind", False, BROKEN_WORLD, (), script({}), ()),
          Run("valid_world", True, World(), (), script({}), ())),
         interpretation="Each preview starts from the reading of step read. A reference to its own obligation is an unsupported cycle. A rejected preview reports the unchanged base as its obligations and exactly the one diagnostic named: a validator that reports extra rules is not precise. A hole is valid only at its own type."),
    Case("C12", "Two legitimate same-signature operations; one-use domain type",
         "Both are allowed. No extra dummy operation or wrapper type is introduced.",
         "agree.duplicates and agree.single_use make these hard faults (test_world_rules asserts them).",
         (Run("archive_and_colour", False, World(extra='\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef archive(surface: Surface) -> Later[Surface]:\n    "archive it"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n'),
              ("Archive the page. Redesign the mod.",), told(ARCHIVED), (("read", READ, {"obligations": ARCHIVED}),)),)),
    Case("C13", "Entire message quotes a previous reply",
         "Source is preserved, origin is inspectable and reading does not crash. A quote alone does not fabricate a request.",
         "unfold raises on a same-sized child (probe whole_message_quote_crashes); or a quote becomes a request.",
         (Run("whole_quote", False, World(), (QUOTE,), script({}),
              (("read", READ, {"error": None, "obligations": [], "passages": [Passage(QUOTE, "Written", "reply 0", "quote")]}),), replies=(QUOTE,)),
          Run("quote_and_request", True, World(), (f'"{QUOTE}" Redesign the mod.',), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"error": None, "obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)],
                               "passages": [Passage(f'"{QUOTE}"', "Written", "reply 0", "quote")]}),), replies=(QUOTE,))),
         interpretation="A quote is a passage of brand Written whose origin names the reply; its relation label is free but present. Its text is compared without the quote marks around it, which the span may or may not include."),
    Case("C14", "Model metadata and world declarations",
         "No name collision can turn an abstention into a function call. Malformed, missing or out-of-set model answers produce diagnostics, not silent acceptance. Enforce configured choice bounds.",
         "A world function named none hijacks abstention (probe reserved_none_function_hijacks_abstention); ask_all indexes answers unchecked; candidates past Limits.offered vanish unrecorded.",
         (Run("reserved_name", False, World(extra='\ndef none(rule: Asked) -> Later[Observed]:\n    "a distinct command"\n'), ("Email an accountant.",), script({"Email an accountant.": ABSTAIN}),
              (("read", READ, {"obligations": [ob("Email an accountant.", UNRESOLVED, reason=REJECTED)]}),)),)
         + tuple(Run(kind, False, World(), ("Redesign the mod.",), script({"Redesign the mod.": Malformed(kind)}),
                     (("read", READ, {"obligations": [ob("Redesign the mod.", UNRESOLVED, reason=INVALID_ANSWER)], "diagnostics": [(0, None, "model_answer")]}),))
                 for kind in ("out_of_set", "missing", "not_numbers"))
         + (Run("bounded", False, World("next"), (BOUNDED_TEXT,), script({BOUNDED_TEXT: "show"}, {(BOUNDED_TEXT, "show", "subject"): REJECT}),
                (("read", READ, {"obligations": [ob(BOUNDED_TEXT, "show", {"subject": Hole("Subject", (REJECTED, BOUNDED))})],
                                 "decisions": [Decision(0, "subject", "model", NINE[:8], REJECT, NINE[8:])]}),)),
            Run("well_formed", True, World(), ("Redesign the mod.",), told(REDESIGN_SHOW[:1]), (("read", READ, {"obligations": REDESIGN_SHOW[:1]}),))),
         interpretation="A world that declares `none` may either be refused with fault (none, name) or load with the abstention kept apart; either way the request stays one UNRESOLVED obligation (unless the whole world is refused and the read reports an error), and an application of none fails. The bound is Limits.offered = 8 candidates per hole; the excess must be recorded as cut, and offered plus cut must hold all nine named values. The bounded message asks to show one unknown item, so d1's rejection is its meaning; the hole may say rejected or bounded, since d1 never saw the cut candidates."),
    Case("C15", "“Redesign the mod. Then show it. Test the search too.”",
         "Three obligations; original mod and redesign result are separately selectable; result binding and dependency survive record/reload. Rebinding show to the original does not erase redesign or request it twice.",
         "The saved record duplicates the shared tree (probe in_memory_shared_result_becomes_duplicated_saved_tree); a rebind drops or repeats redesign.",
         (Run("specimen", False, World("next"), (SPECIMEN,),
              told(TESTED),
              (("read", READ, {"obligations": TESTED, "decisions": [SHOW_DECISION]}),
               ("saved", SAVE, {"writes": 1}),
               ("reloaded", RELOAD, {"obligations": TESTED, "model_calls": 0}),
               ("rebound", ("stage", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": TESTED_REBOUND, "model_calls": 0}),
               ("rebound_saved", SAVE, {"writes": 1}),
               ("rebound_reloaded", RELOAD, {"obligations": TESTED_REBOUND, "model_calls": 0}))),)),
    Case("C16", "Two operations within one source phrase",
         "Preserve both obligations using the smallest valid grouping/term representation; do not silently choose only one or require the user to rewrite punctuation.",
         "choose() selects one function per phrase.",
         (Run("conjunction", False, World(), ("Redesign the mod and show it.",),
              script({"Redesign the mod and show it.": ("redesign", "show")},
                     {("Redesign the mod and show it.", "redesign", "surface"): MOD, ("Redesign the mod and show it.", "show", "subject"): Ref(0)}),
              (("read", READ, {"obligations": [ob("Redesign the mod and show it.", "redesign", {"surface": MOD}, PENDING),
                                               ob("Redesign the mod and show it.", "show", {"subject": Ref(0)}, PENDING)]}),)),
          Run("nested", True, World(), ("Show me the mod, redesigned.",),
              script({"Show me the mod, redesigned.": "show"},
                     {("Show me the mod, redesigned.", "show", "subject"): New("redesign"), ("Show me the mod, redesigned.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Show me the mod, redesigned.", "redesign", {"surface": MOD}, PENDING),
                                               ob("Show me the mod, redesigned.", "show", {"subject": Ref(0)}, PENDING)]}),))),
         interpretation="Both obligations keep the whole phrase as their span. The stand-in names both operations of the phrase; how the engine asks for a second operation is the implementer's choice. Open for Max: an engine that splits the phrase at 'and' also keeps both obligations, but fails here on the span and on the stand-in's exact phrase lookup.",
         real_d1="Whether real d1 finds both operations in one sentence is effectiveness, unverified here."),
    Case("C17", "Two identical-looking requested operations versus two references to one result",
         "Preserve the distinction across serialization. Display equality must not merge them.",
         "derivations() deduplicates by say() text; serialization copies trees.",
         tuple(Run(label, False, World(), (text,), told(obligations),
                   (("read", READ, {"obligations": obligations}), ("saved", SAVE, {}), ("reloaded", RELOAD, {"obligations": obligations})))
               for label, text, obligations in (
                   ("identical_operations", "Redesign the mod. Redesign the mod again.",
                    [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Redesign the mod again.", "redesign", {"surface": MOD}, PENDING)]),
                   ("shared_result", "Redesign the mod. Show it. Compare it with the page.",
                    [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Show it.", "show", {"subject": Ref(0)}, PENDING),
                     ob("Compare it with the page.", "compare", {"surfaces": (Ref(0), PAGE)}, PENDING)]))),
         interpretation="In the neutral form, two operation instances are two obligations and one result is one Ref index; the distinction is structural, so the predicate compares counts and Ref targets after reload."),
    Case("C18", "Preview invalid edit, cancel valid preview, stage/save/reload, failed save, restore previous snapshot",
         "Exact expected identities/bindings are preserved at each transition; previews perform no work. Use a tiny local persistence boundary and failure injection.",
         "No preview/cancel/stage/save boundary exists in next; a failed save loses the draft; cancel keeps the preview.",
         (Run("transitions", False, World("next"), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW, "decisions": [SHOW_DECISION]}),
               ("inspected", ("inspect", 1, "subject"), {"obligations": REDESIGN_SHOW, "model_calls": 0, "writes": 0}),
               ("saved_base", SAVE, {"accepted": True, "writes": 1}),
               ("preview_invalid", ("preview", Edit("set", 0, "surface", SEARCH)), {"accepted": False, "diagnostics": [(0, "surface", "type")], "obligations": REDESIGN_SHOW, "model_calls": 0, "writes": 0}),
               ("preview_valid", ("preview", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": REBOUND, "model_calls": 0, "writes": 0}),
               ("cancelled", ("cancel",), {"obligations": REDESIGN_SHOW, "decisions": [SHOW_DECISION], "model_calls": 0, "writes": 0}),
               ("staged", ("stage", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": REBOUND, "model_calls": 0, "writes": 0}),
               ("saved_rebound", SAVE, {"accepted": True, "writes": 1}),
               ("reloaded", RELOAD, {"obligations": REBOUND, "model_calls": 0}),
               ("cleared", ("stage", Edit("clear", 1, "subject")), {"accepted": True, "obligations": CLEARED_SHOW, "writes": 0}),
               ("save_failed", ("save_fail",), {"accepted": False, "obligations": CLEARED_SHOW, "writes": 0}),
               ("store_after_failure", RELOAD, {"obligations": REBOUND, "model_calls": 0}),
               ("restored", ("restore", 1), {"obligations": REDESIGN_SHOW, "decisions": [SHOW_DECISION], "model_calls": 0}))),),
         interpretation="'Previews perform no work' is observed as zero model calls and zero store writes during inspect, preview, cancel and stage. Cancel and restore return the decisions of the reading as well as its bindings. Reloading after a failed save reads the store, which still holds the last good save."),
    Case("C19", "Accepted manual correction, then rerun or world change",
         "Correction is retained or explicitly invalidated with a reason; it is never silently overwritten by model preference.",
         "A rerun recomputes every binding from d1 and forgets the correction.",
         (Run("rerun", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": REBOUND}),
               ("saved", SAVE, {}),
               ("rerun", ("rerun",), {"obligations": REBOUND, "corrections": [Correction(1, "subject", MOD, RETAINED)]}))),
          Run("world_change", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", World(replace=(('    MOD: Asked = "the mod"\n', ""),))),
                {"obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", (REJECTED, NO_CANDIDATE))}, PENDING),
                                 ob("Then show it.", "show", {"subject": frozenset({Ref(0), Hole("Subject", (REJECTED, NO_CANDIDATE, CLEARED))})}, (PENDING, AVAILABLE))],
                 "corrections": [Correction(1, "subject", MOD, INVALIDATED, "the mod is no member of Surface")]}))),
          Run("unrelated_change", True, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", PAINT_WORLD),
                {"obligations": REBOUND, "corrections": [Correction(1, "subject", MOD, RETAINED)]})))),
         interpretation="The invalidating world change removes the member that the correction names; the predicate requires status invalidated, a non-empty reason, both obligations still present, and that the invalid value is no longer bound. Show may then hold the model's Ref(0) or a hole: with the invalidation reported, neither is silent. The reason text is not compared."),
    Case("C20", "“Redesign mod. Redesign page,” reply/evidence for mod only",
         "Mod and page get separate criterion outcomes. The page obligation cannot pass from the mod's evidence. Explicit refusal is not PROMISED.",
         "check() asks the same argument-blind question twice (probe argument_blind_duplicate_checks); Later makes a refusal PROMISED (probe refusal_becomes_promised).",
         tuple(Run(label, label == "both", world, ("Redesign the mod. Redesign the page.",),
                   script({"Redesign the mod.": "redesign", "Redesign the page.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD, ("Redesign the page.", "redesign", "surface"): PAGE}, judge),
                   (("read", READ, {"obligations": REDESIGN_TWO if world == World() else [dataclasses.replace(one, status=AVAILABLE) for one in REDESIGN_TWO]}),
                    ("checked", ("check", reply, artifacts, EVIDENCE_CRITERIA), {"checks": checks, "verdict": verdict})))
               for label, world, reply, judge, artifacts, checks, verdict in (
                   ("mod_only", World(), "I redesigned the mod.", 0.99, (Artifact("redesign", {"surface": MOD}),),
                    [Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", (UNVERIFIED, FAIL))], (UNVERIFIED, FAIL)),
                   ("refusal", World(), "I cannot redesign either of them.", 0.01, (),
                    [Check(0, None, "evidence", (FAIL, UNVERIFIED)), Check(1, None, "evidence", (FAIL, UNVERIFIED))], (FAIL, UNVERIFIED)),
                   ("later_removed", World(replace=(("-> Later[Surface]:", "-> Surface:"),)), "I redesigned the mod and the page.", 0.99, (),
                    [Check(0, None, "evidence", (UNVERIFIED, FAIL)), Check(1, None, "evidence", (UNVERIFIED, FAIL))], (UNVERIFIED, FAIL)),
                   ("both", World(), "I redesigned the mod and the page.", 0.99, (Artifact("redesign", {"surface": MOD}), Artifact("redesign", {"surface": PAGE})),
                    [Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", PASS, 1)], PASS))),
         interpretation="A reply's claim and d1's yes share are not evidence, so a reply alone never passes; an obligation with no evidence may be UNVERIFIED or FAIL. A refusal may be FAIL or UNVERIFIED; the outcome vocabulary has no PROMISED. Run later_removed makes redesign return Surface: its obligations become available, and still nothing passes without evidence (I6).",
         real_d1="Judging refusal prose with real d1 is unverified; the stand-in answers 0.99 and 0.01."),
    Case("C21", "Type-correct but wrong computation",
         "A tiny test-only pure function returns the right type but the wrong known result. Its independent behavioral criterion fails while its type check still passes. Keep this fixture out of the production world; do not invent a verify operation.",
         "A type check is reported as fulfillment.",
         tuple(Run(label, control, DOUBLE_WORLD, ("Double 3.",), told([DOUBLED]),
                   (("read", READ, {"obligations": [DOUBLED]}),
                    ("checked", ("check", "Done.", (Artifact("double", {"number": THREE}, fixture(3)),), DOUBLE_CRITERIA),
                     {"checks": [Check(0, None, "type", PASS, 0), Check(0, None, "behavior", behavior, 0)], "verdict": behavior})))
               for label, control, fixture, behavior in (("wrong", False, wrong_double, FAIL), ("right", True, right_double, PASS))),
         interpretation="The artifact's value is computed here by the test-only fixture on the bound literal; no executor runs. The predicate also requires that next/world.py declares neither double nor verify, read from the file itself, not from the observation."),
    Case("C22", "Saved decision and semantic edits",
         "Reload recovers typed literal values, shared references, explicit unresolved state and exact model decision context without a model call. Cosmetic rendering changes do not change meaning.",
         "record() saves only keys and scores, drops Constant.value and copies shared trees (probes saved_decisions_drop_full_request_context, in_memory_shared_result_becomes_duplicated_saved_tree).",
         (Run("saved_reading", False, World("next"), ("Redesign the mod. Then show it. Email my accountant.",),
              told(REDESIGN_SHOW + [EMAIL]),
              (("read", READ, {"obligations": REDESIGN_SHOW + [EMAIL]}),
               ("edited", ("stage", Edit("set", 0, "surface", Lit("Surface", "the page"))), {"accepted": True}),
               ("saved", SAVE, {"writes": 1}),
               ("reloaded", RELOAD, {"model_calls": 0}),
               ("restyled", ("restyle",), {"model_calls": 0}),
               ("other_world", ("reload", PAINT_WORLD), {"diagnostics": [(None, None, "identity")], "model_calls": 0}))),),
         interpretation="The predicate compares the reloaded and restyled steps with the edited step, field by field, including every decision's state, instructions, offered, chosen and scores; it requires state, instructions and scores for model decisions, the phrase in the state, and d1's own choice of the mod kept beside the edit to the page. Loading the saved reading under another world reports the mismatch (the brief's state machine)."),
)

CASE = {case.id: case for case in CASES}


# ---- Comparison ------------------------------------------------------------


def acceptable(expected) -> tuple:
    """Returns the acceptable answers: a tuple of alternatives, or the one value."""
    return expected if isinstance(expected, tuple) else (expected,)


def value_fits(expected, observed) -> bool:
    """Decides whether an observed binding value is what the expected one allows."""
    if isinstance(expected, frozenset):
        return any(value_fits(one, observed) for one in expected)
    if isinstance(expected, Hole):
        return isinstance(observed, Hole) and observed.type in acceptable(expected.type) and observed.reason in acceptable(expected.reason)
    if isinstance(expected, tuple):
        return isinstance(observed, tuple) and sorted(map(repr, expected)) == sorted(map(repr, observed))
    return expected == observed


def plain(text: str) -> str:
    """Returns text with its white space collapsed and the quote marks around it removed."""
    return " ".join(str(text).split()).strip("\"'“”‘’")


def words(text: str) -> set[str]:
    """Returns the words of a text, in lower case."""
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def obligations_diagnostics(where: str, expected: list, observed: list) -> list[str]:
    """Compares observed obligations with the expected ones, field by field."""
    found: list[str] = []
    if len(expected) != len(observed):
        found.append(f"{where}: expected {len(expected)} obligations {[one.operation for one in expected]}, observed {len(observed)} {[one.operation for one in observed]}")
    for index, (want, got) in enumerate(zip(expected, observed)):
        if plain(want.span) != plain(got.span):
            found.append(f"{where}: obligation {index} span: expected {want.span!r}, observed {got.span!r}")
        for field in ("operation", "brand", "status", "reason"):
            if getattr(got, field) not in acceptable(getattr(want, field)):
                found.append(f"{where}: obligation {index} {field}: expected {getattr(want, field)!r}, observed {getattr(got, field)!r}")
        if set(want.bindings) != set(got.bindings):
            found.append(f"{where}: obligation {index} binding paths: expected {sorted(want.bindings)}, observed {sorted(got.bindings)}")
        for path in want.bindings.keys() & got.bindings.keys():
            if not value_fits(want.bindings[path], got.bindings[path]):
                found.append(f"{where}: obligation {index} binding {path}: expected {want.bindings[path]!r}, observed {got.bindings[path]!r}")
    return found


def forbidden_diagnostics(where: str, step: dict, message: str | None) -> list[str]:
    """Finds answers that the brief forbids in any reading.

    None/nothing, a guessed goal, an untyped hole, a reference that is not to an
    earlier obligation, a passage with no relationship, and (for the reading of
    one message) a word of the message that no obligation or passage covers.
    """
    found: list[str] = []
    obligations = step.get("obligations", [])
    for index, one in enumerate(obligations):
        if one.operation in ("none", "nothing"):
            found.append(f"{where}: obligation {index} has the terminal answer {one.operation!r}; it must be UNRESOLVED")
        if one.operation == UNRESOLVED and one.bindings:
            found.append(f"{where}: unresolved obligation {index} has a guessed goal: {one.bindings}")
        for value in (value for binding in one.bindings.values() for value in (binding if isinstance(binding, tuple) else (binding,))):
            if isinstance(value, Hole) and value.type in ("Any", "Unknown", "", None):
                found.append(f"{where}: obligation {index} has an untyped hole {value!r}")
            if isinstance(value, Ref) and not 0 <= value.obligation < index:
                found.append(f"{where}: obligation {index} refers to obligation {value.obligation}, which is not an earlier obligation")
    for passage in step.get("passages", []):
        if plain(passage.relation).lower() in ("", "none", "nothing"):
            found.append(f"{where}: passage {passage.text!r} has no relationship (relation {passage.relation!r})")
    if message is not None and "obligations" in step:
        lost = words(message) - words(" ".join([one.span for one in obligations] + [one.text for one in step.get("passages", [])]))
        if lost:
            found.append(f"{where}: words of the message in no obligation or passage: {sorted(lost)}")
    return found


def checks_diagnostics(where: str, expected: list, observed: list, obligations: list) -> list[str]:
    """Compares checks by (obligation, item, criterion), and requires a check for every obligation."""
    found: list[str] = []
    by_key = {(one.obligation, repr(one.item), one.criterion): one for one in observed}
    for want in expected:
        got = by_key.get((want.obligation, repr(want.item), want.criterion))
        if got is None:
            found.append(f"{where}: no {want.criterion!r} check for obligation {want.obligation}")
        elif got.outcome not in acceptable(want.outcome) or (want.evidence is not None and got.evidence != want.evidence):
            found.append(f"{where}: obligation {want.obligation} {want.criterion!r}: expected {want.outcome} by artifact {want.evidence}, observed {got.outcome} by artifact {got.evidence}")
    unchecked = sorted(set(range(len(obligations))) - {one.obligation for one in observed})
    if unchecked:
        found.append(f"{where}: obligations {unchecked} have no check")
    return found


def previous_obligations(observation: dict, label: str) -> list:
    """Returns the obligations of the last step before ``label`` that has them."""
    latest: list = []
    for name, step in observation.get("steps", {}).items():
        if name == label:
            break
        latest = step.get("obligations", latest)
    return latest


def step_diagnostics(case: Case, observed_runs: dict, labels: tuple = ()) -> list[str]:
    """Compares every expected key of every step of the case's runs, and the forbidden answers.

    A step that is no semantic edit (check, save, inspect) must also leave the
    reading as it was.
    """
    found: list[str] = []
    for run in case.runs:
        if labels and run.label not in labels:
            continue
        observation = observed_runs.get(run.label)
        if observation is None:
            found.append(f"{case.id} {run.label}: no observation")
            continue
        for label, action, expected in run.steps:
            where = f"{case.id} {run.label}/{label}"
            step = observation.get("steps", {}).get(label)
            if step is None:
                found.append(f"{where}: no step")
                continue
            if step.get("error") and "error" not in expected:
                found.append(f"{where}: error {step['error']}")
            found += forbidden_diagnostics(where, step, run.messages[0] if action == READ and len(run.messages) == 1 else None)
            if action[0] in ("check", "save", "inspect") and "obligations" in step and "obligations" not in expected:
                found += obligations_diagnostics(f"{where} (a {action[0]} changed the reading)", previous_obligations(observation, label), step["obligations"])
            for key, want in expected.items():
                got = step.get(key)
                if key == "obligations":
                    found += obligations_diagnostics(where, want, got or [])
                elif key == "checks":
                    found += checks_diagnostics(where, want, got or [], step.get("obligations") or previous_obligations(observation, label))
                elif key == "verdict":
                    if got not in acceptable(want):
                        found.append(f"{where}: verdict expected {want}, observed {got}")
                elif key == "diagnostics":
                    if sorted(map(repr, want)) != sorted(map(repr, got or [])):
                        found.append(f"{where}: diagnostics expected exactly {want}, observed {got}")
                elif key == "passages":
                    if [(plain(one.text), one.brand, one.origin) for one in want] != [(plain(one.text), one.brand, one.origin) for one in got or []]:
                        found.append(f"{where}: passages expected {[(one.text, one.brand, one.origin) for one in want]}, observed {[(one.text, one.brand, one.origin) for one in got or []]}")
                elif key == "world_change":
                    if got is None or (got["activated"], sorted(got["regressions"])) != (want["activated"], sorted(want["regressions"])) or got["verdict"] not in acceptable(want["verdict"]):
                        found.append(f"{where}: world change expected {want}, observed {got}")
                elif key in ("decisions", "corrections"):
                    continue  # compared by the case's own predicate
                elif got != want:
                    found.append(f"{where}: {key} expected {want!r}, observed {got!r}")
    return found


def decision_for(observation: dict, step: str, obligation: int, path: str | None) -> Decision | None:
    """Returns the recorded decision about one obligation and path at a step."""
    return next((one for one in observation.get("steps", {}).get(step, {}).get("decisions", []) if (one.obligation, one.path) == (obligation, path)), None)


def asked_diagnostics(case: Case, observed: dict, labels: tuple = ()) -> list[str]:
    """Requires each expected decision of the case: by d1 when expected so, with its candidates, choice and context.

    A decision by d1 must keep the exact question and a state that holds the phrase.
    """
    found: list[str] = []
    for run in case.runs:
        if labels and run.label not in labels:
            continue
        observation = observed.get(run.label, {})
        for label, _, expected in run.steps:
            for want in expected.get("decisions", []):
                where = f"{case.id} {run.label}/{label} decision on {want.obligation}.{want.path}"
                got = decision_for(observation, label, want.obligation, want.path)
                if got is None:
                    found.append(f"{where}: no recorded decision; d1 was not given the choice")
                    continue
                if got.by not in acceptable(want.by):
                    found.append(f"{where}: decided by {got.by!r}, expected {want.by}")
                pool = got.offered + got.cut if want.cut else got.offered  # where a bound applies, a candidate is offered or recorded as cut
                missing = [one for one in want.offered + want.cut if one not in pool]
                if missing:
                    found.append(f"{where}: candidates not offered to d1{' nor recorded as cut' if want.cut else ''}: {missing}")
                if not value_fits(want.chosen, got.chosen):
                    found.append(f"{where}: d1's choice recorded as {got.chosen!r}, expected {want.chosen!r}")
                obligations = observation.get("steps", {}).get(label, {}).get("obligations") or previous_obligations(observation, label)
                span = obligations[want.obligation].span if want.obligation < len(obligations) else ""
                if got.by == "model" and not (got.instructions and plain(span) in plain(got.state)):
                    found.append(f"{where}: the decision lost d1's question or the phrase it read (state {got.state!r})")
    return found


# ---- Predicates: one per case ------------------------------------------------
#
# Every case checks its expected steps and its expected decisions; the
# functions below add what a step comparison cannot say.


def c01(observed: dict) -> list[str]:
    """The unresolved obligation never passes."""
    checks = observed.get("unsupported", {}).get("steps", {}).get("checked", {}).get("checks", [])
    return ["C01 unsupported/checked: the unresolved obligation passed"] if any(one.obligation == 0 and one.outcome == PASS for one in checks) else []


def c09(observed: dict) -> list[str]:
    """Lexical absence is not a world fault."""
    return [f"C09 {run}: world faults {observed[run]['world_faults']}; lexical absence is not a world fault"
            for run in ("chain", "contrast") if observed.get(run, {}).get("world_faults")]


def c11(observed: dict) -> list[str]:
    """The malformed world is refused for its kind, and the valid one is not."""
    found = []
    if ("Broken", "kind") not in observed.get("invalid_kind", {}).get("world_faults", []):
        found.append(f"C11 invalid_kind: expected world fault ('Broken', 'kind'), observed {observed.get('invalid_kind', {}).get('world_faults')}")
    if observed.get("valid_world", {}).get("world_faults"):
        found.append(f"C11 valid_world: unexpected faults {observed['valid_world']['world_faults']}")
    return found


def c12(observed: dict) -> list[str]:
    """Same signature and one use are no faults, and no declaration is added."""
    run, functions = observed.get("archive_and_colour", {}), sorted(TEST_FUNCTIONS + ["archive", "tint"])
    found = [f"C12: same signature or one use reported as faults: {run['world_faults']}"] if run.get("world_faults") else []
    if run.get("world_functions") != functions:
        found.append(f"C12: functions expected {functions}, observed {run.get('world_functions')}")
    return found


def c14(observed: dict) -> list[str]:
    """An abstention never becomes `none`, and the bound records what it cut."""
    found = []
    reserved = observed.get("reserved_name", {})
    read = reserved.get("steps", {}).get("read", {})
    if any(one.operation == "none" for one in read.get("obligations", [])):
        found.append("C14 reserved_name: the abstention became an application of none")
    elif not (read.get("error") and ("none", "name") in reserved.get("world_faults", [])):
        found += step_diagnostics(CASE["C14"], observed, ("reserved_name",))
    decision = decision_for(observed.get("bounded", {}), "read", 0, "subject")
    if decision is None:
        return found + ["C14 bounded: no decision on subject"]
    if len(decision.offered) > 8:
        found.append(f"C14 bounded: {len(decision.offered)} candidates offered, the bound is 8")
    if not decision.cut:
        found.append("C14 bounded: no candidate recorded as cut by the bound")
    return found


def c18(observed: dict) -> list[str]:
    """Cancel and restore return the decisions of the reading, not only its bindings."""
    steps = observed.get("transitions", {}).get("steps", {})
    return [f"C18 transitions/{label}: decisions differ from the reading: {steps.get(label, {}).get('decisions')} != {steps.get('read', {}).get('decisions')}"
            for label in ("cancelled", "restored") if steps.get(label, {}).get("decisions") != steps.get("read", {}).get("decisions")]


def c19(observed: dict) -> list[str]:
    """A correction is retained, or invalidated with a reason; never silently replaced."""
    found = []
    for run, status in (("rerun", RETAINED), ("world_change", INVALIDATED), ("unrelated_change", RETAINED)):
        step = (list(observed.get(run, {}).get("steps", {}).values())[-1:] or [{}])[0]
        corrections = [one for one in step.get("corrections", []) if (one.obligation, one.path) == (1, "subject")]
        if not corrections:
            found.append(f"C19 {run}: the correction of show.subject is not reported")
            continue
        if corrections[0].status != status:
            found.append(f"C19 {run}: correction status expected {status}, observed {corrections[0].status}")
        if status == INVALIDATED:
            obligations = step.get("obligations", [])
            if not plain(corrections[0].reason):
                found.append(f"C19 {run}: correction invalidated with no reason")
            if [one.operation for one in obligations] != ["redesign", "show"]:
                found.append(f"C19 {run}: the world change lost an obligation: {[one.operation for one in obligations]}")
            elif obligations[1].bindings.get("subject") == MOD:
                found.append(f"C19 {run}: an invalidated correction is still bound")
    return found


def production_world_diagnostics(source: str) -> list[str]:
    """The production world declares neither the test fixture nor a verify operation."""
    declared = {node.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)}
    return [f"C21: the production world declares {sorted(declared & {'double', 'verify'})}"] if declared & {"double", "verify"} else []


def c21(observed: dict) -> list[str]:
    """The fixture stays out of the production world, read from next/world.py itself."""
    return production_world_diagnostics((HERE / "world.py").read_text())


def c22(observed: dict) -> list[str]:
    """Reload and restyle recover the edited reading and every decision without d1; d1's choice survives the edit."""
    found = []
    steps = observed.get("saved_reading", {}).get("steps", {})
    edited = steps.get("edited", {})
    found += obligations_diagnostics("C22 edited", EDITED, edited.get("obligations", []))
    for label in ("edited", "reloaded", "restyled"):
        step = steps.get(label, {})
        if label != "edited":
            found += [f"C22 {label}: {key} differ from the edited reading: {step.get(key)} != {edited.get(key)}" for key in ("obligations", "decisions") if step.get(key) != edited.get(key)]
        found += [f"C22 {label}: decision on obligation {one.obligation} path {one.path} lost its state, instructions or scores"
                  for one in step.get("decisions", []) if one.by == "model" and not (one.state and one.instructions and one.scores)]
        original = decision_for(observed.get("saved_reading", {}), label, 0, "surface")
        if original is None or (original.by, original.chosen) != ("model", MOD):
            found.append(f"C22 {label}: d1's own choice of the mod is not kept beside the edit (decision {original})")
    return found


EXTRA = {"C01": c01, "C09": c09, "C11": c11, "C12": c12, "C14": c14, "C18": c18, "C19": c19, "C21": c21, "C22": c22}
STEP_LABELS = {"C11": ("edits",), "C14": ("out_of_set", "missing", "not_numbers", "bounded", "well_formed")}


def predicate(case_id: str):
    """Returns the predicate of a case: its steps, its decisions and what the case adds."""
    def check(observed: dict) -> list[str]:
        case, labels = CASE[case_id], STEP_LABELS.get(case_id, ())
        return step_diagnostics(case, observed, labels) + asked_diagnostics(case, observed, labels) + EXTRA.get(case_id, lambda _: [])(observed)
    check.__doc__ = f"Checks {case_id}: {CASE[case_id].words}"
    return check


PREDICATES = {case_id: predicate(case_id) for case_id in CASE}


# ---- Location: where the tested code lives ---------------------------------


def snapshot(root: pathlib.Path = HERE.parent) -> dict:
    """Returns the provenance of a worktree from path and git data only.

    Finds each module as Python would, after putting next/ and .scriptt/ first
    on the path as the test file does, without running it.
    """
    root = pathlib.Path(subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SNAPSHOT_FILES if (root / name).exists()}
    saved_path = sys.path[:]
    sys.path[:0] = [str(root / "next"), str(root / ".scriptt")]
    try:
        imported = {name: str(pathlib.Path(importlib.util.find_spec(name).origin).resolve()) for name in IMPORTED_MODULES}
    finally:
        sys.path[:] = saved_path
    return {"worktree": str(root), "commit": commit, "files": files, "imported": imported, "elsewhere": [], "method": "path and git data"}


def l1(provenance: dict) -> list[str]:
    """The work is in the declared worktree, not a reference copy."""
    path = pathlib.Path(provenance.get("worktree", ""))
    if path != DECLARED_ROOT or any(path.is_relative_to(reference) for reference in REFERENCE_ROOTS):
        return [f"L1: worktree {path}, expected {DECLARED_ROOT}"]
    return []


def l2(provenance: dict) -> list[str]:
    """The result names its commit and the sha256 of every snapshot file."""
    commit = provenance.get("commit", "")
    found = [] if len(commit) == 40 and all(character in "0123456789abcdef" for character in commit) else [f"L2: no git commit (observed {commit!r})"]
    missing = [name for name in SNAPSHOT_FILES if len(provenance.get("files", {}).get(name, "")) != 64]
    return found + ([f"L2: no sha256 for {missing}"] if missing else [])


def l3(provenance: dict) -> list[str]:
    """Every module that the tests import resolves under the worktree."""
    root = pathlib.Path(provenance.get("worktree", ""))
    imported = provenance.get("imported", {})
    return [f"L3: {name} imports from {imported.get(name)}, outside {root}" for name in IMPORTED_MODULES
            if not imported.get(name) or not pathlib.Path(imported[name]).resolve().is_relative_to(root)]


def l4(provenance: dict, delivered: dict) -> list[str]:
    """The recorded hashes equal the delivered files, for every snapshot file."""
    tested = provenance.get("files", {})
    return [f"L4: {name} tested as {tested.get(name, '')[:12]}, delivered as {delivered.get(name, '')[:12]}"
            for name in SNAPSHOT_FILES if tested.get(name) != delivered.get(name)]


def l5(provenance: dict) -> list[str]:
    """Every disclosed change elsewhere has been transferred to the worktree."""
    return [f"L5: change at {one['path']} is not transferred" for one in provenance.get("elsewhere", []) if not one.get("transferred")]


def l6(provenance: dict) -> list[str]:
    """The location checks use path and git data only."""
    return [] if provenance.get("method") == "path and git data" else [f"L6: provenance came from {provenance.get('method')!r}"]


LOCATION_PREDICATES = {"L1": l1, "L2": l2, "L3": l3, "L4": None, "L5": l5, "L6": l6}


# ---- Inventory as data -------------------------------------------------------


REQUIREMENTS = (
    [{"id": key, "kind": "invariant", "source": f"{BRIEF} § {section}", "words": f"{name} {words}"} for key, (section, name, words) in INVARIANTS.items()]
    + [{"id": case.id, "kind": "case", "source": f"{BRIEF} § Acceptance cases and wrong implementations the tests must catch",
        "words": case.words, "required": case.required, "catches": case.catches, "interpretation": case.interpretation,
        "real_d1": case.real_d1 or "not needed for conformance", "runs": [run.label for run in case.runs]} for case in CASES]
    + [{"id": key, "kind": "wrong implementation", "source": f"{BRIEF} § Acceptance cases and wrong implementations the tests must catch",
        "words": words, "case": case_id} for key, (words, case_id) in WRONG_IMPLEMENTATIONS.items()]
    + [{"id": key, "kind": "location", "source": LOCATION_MESSAGE, "words": words, "required": required} for key, (words, required) in LOCATION.items()]
    + [{"id": key, "kind": "process", "source": f"{BRIEF} § {section}", "words": words, "checked_by": "the final report"} for key, (section, words) in PROCESS.items()]
)

INVARIANT_TABLE = [
    {"invariant": "I1", "checks": ["C01", "C06", "C13", "C14", "C16", "C22"], "expected": "every requested obligation present, unresolved ones UNRESOLVED; every other span a passage with a relationship", "observed": None},
    {"invariant": "I2", "checks": ["C11", "C18"], "expected": "each malformed edit or world rejected for its exact rule with the base kept; a typed hole accepted", "observed": None},
    {"invariant": "I3", "checks": ["C03", "C04", "C05", "C06", "C14"], "expected": "d1 decides singletons, negation and subsets; Empty, EMPTY_LIST and Hole distinct; bounds recorded", "observed": None},
    {"invariant": "I4", "checks": ["C07", "C08", "C09", "C14", "C17", "C20"], "expected": "results reused before reconstruction; repeated functions available; produced types need no spelling; no unrequested production", "observed": None},
    {"invariant": "I5", "checks": ["C15", "C16", "C17", "C22"], "expected": "Ref targets and obligation counts unchanged through save, reload, rebind and restyle", "observed": None},
    {"invariant": "I6", "checks": ["C05", "C06", "C10", "C20"], "expected": "pending through Record, Several and Maybe; absence only by an absence decision; explicit empty Many", "observed": None},
    {"invariant": "I7", "checks": ["C18", "C15", "C05", "C06"], "expected": "inspect view-only, preview pure, cancel exact, failed save keeps the draft, restore returns the base", "observed": None},
    {"invariant": "I8", "checks": ["C03", "C04", "C14", "C22"], "expected": "decisions with state, instructions, offered, chosen, scores and cut, recovered without d1", "observed": None},
    {"invariant": "I9", "checks": ["C01", "C02", "C19", "C20", "C21"], "expected": "no overall pass with an unresolved demand, missing evidence or empty corpus; per-obligation outcomes", "observed": None},
    {"invariant": "I10", "checks": ["C12", "C21"], "expected": "no dummy operation, wrapper type or verify function; code counts in the final report", "observed": None},
]


# ---- Negative controls -------------------------------------------------------


def expected_observation(case: Case, run: Run) -> dict:
    """Returns the observation that a correct engine produces, written from the expected steps.

    Where the expected structure allows several answers, the first is taken; a
    decision by d1 gets the phrase as its state, a question and its share.
    """
    steps, latest = {}, []
    for label, _, expected in run.steps:
        latest = [concrete(one) for one in expected["obligations"]] if "obligations" in expected else latest
        step = dict(expected) | ({"obligations": latest} if "obligations" in expected else {})
        if "verdict" in expected:
            step["verdict"] = acceptable(expected["verdict"])[0]
        if "checks" in expected:
            step["checks"] = [dataclasses.replace(one, outcome=acceptable(one.outcome)[0]) for one in expected["checks"]]
        if "decisions" in expected:
            step["decisions"] = [with_context(one, latest) for one in expected["decisions"]]
        steps[label] = step
    observation = {"world_faults": [("Broken", "kind")] if run.label == "invalid_kind" else [],
                   "world_functions": sorted(TEST_FUNCTIONS + ["archive", "tint"]) if case.id == "C12" else [], "steps": steps}
    if case.id == "C22":
        decisions = [with_context(Decision(index, None, "model", ("redesign", "show", ABSTAIN, NO_REQUEST), choice), EDITED) for index, choice in enumerate(("redesign", "show", ABSTAIN))]
        decisions += [with_context(Decision(0, "surface", "model", (MOD,), MOD), EDITED), with_context(SHOW_DECISION, EDITED)]
        for label in ("edited", "reloaded", "restyled"):
            steps[label] |= {"obligations": EDITED, "decisions": decisions}
    return observation


def with_context(decision: Decision, obligations: list) -> Decision:
    """Returns a decision by its first acceptable decider, with the phrase as state, a question and a share."""
    return dataclasses.replace(decision, by=acceptable(decision.by)[0], state=decision.state or obligations[decision.obligation].span,
                               instructions=decision.instructions or "Which of these does the text mean?", scores=decision.scores or ((decision.chosen, 0.9),))


def concrete(obligation: Obligation) -> Obligation:
    """Returns an obligation with one acceptable answer where the expected one allows several."""
    def one(value):
        if isinstance(value, frozenset):
            return one(min(value, key=repr))
        if isinstance(value, Hole):
            return Hole(acceptable(value.type)[0], acceptable(value.reason)[0])
        return value
    return dataclasses.replace(obligation, bindings={path: one(value) for path, value in obligation.bindings.items()},
                               reason=acceptable(obligation.reason)[0] if obligation.reason else None,
                               status=acceptable(obligation.status)[0] if obligation.status else None)


def changed(observation: dict, run: str, step: str, **keys) -> dict:
    """Returns the observation of a case with keys of one step replaced."""
    wrong = copy.deepcopy(observation)
    wrong[run]["steps"][step] |= keys
    return wrong


def changed_ob(observation: dict, run: str, step: str, index: int, **fields) -> dict:
    """Returns the observation with fields of one obligation replaced."""
    obligations = list(observation[run]["steps"][step]["obligations"])
    obligations[index] = dataclasses.replace(obligations[index], **fields)
    return changed(observation, run, step, obligations=obligations)


def expected_runs(case_id: str) -> dict:
    """Returns the expected observation of every run of a case."""
    case = CASE[case_id]
    return {run.label: expected_observation(case, run) for run in case.runs}


def no_context(observation, run, step):
    """Strips d1's question and state from the decisions of a step: a record that is not d1's actual request."""
    return changed(observation, run, step, decisions=[dataclasses.replace(one, state="", instructions="") for one in observation[run]["steps"][step]["decisions"]])


def no_decision(observation, run, step, path):
    """Removes the decisions on a path: the engine bound it without asking d1."""
    return changed(observation, run, step, decisions=[one for one in observation[run]["steps"][step].get("decisions", []) if one.path != path])


NEGATIVE_CONTROLS = (
    # The six wrong implementations named in the brief; W1 and W4 in every run they apply to.
    *((f"W1{suffix}", f"always accept gate changes: {run}", "C02", lambda e, run=run: changed(e, run, "proposed", world_change={"activated": True, "verdict": PASS, "regressions": []}), "world change expected")
      for suffix, run in zip("abcde", ("deleted", "confident_nothing", "weakened", "invalid_world", "empty_corpus"))),
    *((f"W4{suffix}", f"ignore nested pending dependencies: {run}", "C10", lambda e, run=run, index=index: changed_ob(e, run, "read", index, status=AVAILABLE), "status: expected 'pending'")
      for suffix, run, index in (("a", "record", 1), ("b", "several", 1), ("c", "maybe", 1), ("d", "through_result", 2))),
    ("W2", "drop an unresolved obligation", "C01",
     lambda e: changed(changed(e, "unsupported", "read", obligations=[], passages=[Passage("Email my accountant.", "Asked", "user", "nothing")]), "unsupported", "checked", checks=[], verdict=PASS),
     "expected 1 obligations"),
    ("W3", "include every local Many item", "C03",
     lambda e: no_decision(changed_ob(e, "negated", "read", 0, bindings={"surfaces": (MOD, PAGE)}), "negated", "read", "surfaces"), "binding surfaces"),
    ("W5", "duplicate a shared result", "C15",
     lambda e: changed(e, "specimen", "reloaded", obligations=[REDESIGN_SHOW[0], REDESIGN_SHOW[0], ob("Then show it.", "show", {"subject": Ref(1)}, PENDING), ob("Test the search too.", "test", {"subject": SEARCH})]),
     "expected 3 obligations"),
    ("W6", "certify all repeated operations from one generic reply", "C20",
     lambda e: changed(e, "mod_only", "checked", checks=[Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", PASS, 0)], verdict=PASS), "obligation 1 'evidence'"),
    # Per-case failures of the table.
    ("C01a", "none as a terminal semantic answer", "C01", lambda e: changed_ob(e, "unsupported", "read", 0, operation="none", status=None), "terminal answer 'none'"),
    ("C01b", "fabricated Hole[Any] for an unknown operation", "C01",
     lambda e: changed_ob(e, "unsupported", "read", 0, bindings={"goal": Hole("Any", REJECTED)}), "guessed goal"),
    ("C02b", "an empty corpus is unverified but activates anyway", "C02",
     lambda e: changed(e, "empty_corpus", "proposed", world_change={"activated": True, "verdict": UNVERIFIED, "regressions": []}), "world change expected"),
    ("C03a", "the right binding without asking d1", "C03", lambda e: no_decision(e, "negated", "read", "surfaces"), "d1 was not given the choice"),
    ("C04", "the singleton is taken automatically", "C04",
     lambda e: no_decision(changed_ob(e, "rejected", "read", 0, bindings={"surface": MOD}), "rejected", "read", "surface"), "binding surface"),
    ("C05a", "a rejected optional becomes Empty", "C05",
     lambda e: changed_ob(e, "unresolved", "read", 0, bindings={"subject": EMPTY}), "binding subject"),
    ("C05b", "an unresolved optional is lost on reload", "C05",
     lambda e: changed_ob(e, "unresolved", "reloaded", 0, bindings={"subject": EMPTY}), "binding subject"),
    ("C05c", "Empty with no absence decision", "C05", lambda e: changed(e, "absent", "read", decisions=[]), "no recorded decision"),
    ("C06a", "an unknown Many becomes an empty collection", "C06",
     lambda e: changed_ob(e, "unknown", "read", 0, bindings={"surfaces": EMPTY_LIST}), "binding surfaces"),
    ("C06b", "an explicit empty Many reloads as a hole", "C06",
     lambda e: changed_ob(e, "explicit_empty", "reloaded", 0, bindings={"surfaces": Hole("Many[Surface]", NO_CANDIDATE)}), "binding surfaces"),
    ("C06c", "local terms always taken over earlier ones", "C06",
     lambda e: changed_ob(e, "earlier_not_local", "read", 0, bindings={"surfaces": (MOD,)}), "binding surfaces"),
    ("C07", "a fresh Cell rebuilt from the old fields", "C07",
     lambda e: changed_ob(e, "reshape_open", "read", 1, bindings={"cell.notebook": NOTES, "cell.number": THREE}, status=AVAILABLE), "binding paths"),
    ("C08", "redesign(page) suppresses redesign(mod)", "C08",
     lambda e: changed(e, "page_then_mod", "read", obligations=[ob("Redesign the page.", "redesign", {"surface": PAGE}, PENDING), ob("Show the mod redesigned.", "show", {"subject": Ref(0)}, PENDING)]),
     "expected 3 obligations"),
    ("C09a", "a produced type reported as a world fault", "C09",
     lambda e: {**e, "chain": {**e["chain"], "world_faults": [("use_token", "grounding")]}}, "lexical absence is not a world fault"),
    ("C09b", "unrequested production invented", "C09",
     lambda e: changed(e, "contrast", "read", obligations=[ob("Use a token.", "make_token", {"surface": MOD}), ob("Use a token.", "use_token", {"token": Ref(0)})]), "expected 1 obligations"),
    ("C11a", "a wrong child type accepted", "C11",
     lambda e: changed(e, "edits", "wrong_child", accepted=True, diagnostics=[], obligations=[ob("Redesign the mod.", "redesign", {"surface": NOTES}, PENDING), CELL_BASE[1]]), "accepted expected False"),
    ("C11b", "an extra field rejected for the wrong rule", "C11",
     lambda e: changed(e, "edits", "extra_field", diagnostics=[(1, "cell.colour", "type")]), "diagnostics expected"),
    ("C11c", "an unapplied constructor in a union accepted", "C11", lambda e: {**e, "invalid_kind": {**e["invalid_kind"], "world_faults": []}}, "expected world fault"),
    ("C11d", "a typed hole rejected as invalid", "C11",
     lambda e: changed(e, "edits", "typed_hole", accepted=False, diagnostics=[(0, "surface", "missing")], obligations=CELL_BASE), "accepted expected True"),
    ("C12a", "same signature and one use kept as faults", "C12",
     lambda e: {**e, "archive_and_colour": {**e["archive_and_colour"], "world_faults": [("archive", "duplicate"), ("Colour", "single_use")]}}, "reported as faults"),
    ("C12b", "a dummy operation added to satisfy a count", "C12",
     lambda e: {**e, "archive_and_colour": {**e["archive_and_colour"], "world_functions": sorted(TEST_FUNCTIONS + ["archive", "tint", "verify"])}}, "functions expected"),
    ("C13a", "a whole-message quote crashes", "C13", lambda e: changed(e, "whole_quote", "read", error="ValueError", obligations=[], passages=[]), "error"),
    ("C13b", "a quote fabricates a request", "C13",
     lambda e: changed(e, "whole_quote", "read", obligations=[ob(QUOTE, "follow", {"rule": Lit("Asked", QUOTE)})], passages=[]), "expected 0 obligations"),
    ("C14a", "a world function named none hijacks abstention", "C14",
     lambda e: changed_ob(e, "reserved_name", "read", 0, operation="none", bindings={"rule": Lit("Asked", "Email an accountant.")}, status=PENDING, reason=None), "application of none"),
    ("C14b", "an out-of-set answer silently accepted", "C14",
     lambda e: changed(e, "out_of_set", "read", obligations=[ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)], diagnostics=[]), "operation"),
    ("C14c", "candidates past the bound vanish unrecorded", "C14",
     lambda e: changed(e, "bounded", "read", decisions=[Decision(0, "subject", "model", NINE[:7] + (New("redesign"),), REJECT)]), "no candidate recorded as cut"),
    ("C15a", "rebinding show erases redesign", "C15",
     lambda e: changed(e, "specimen", "rebound", obligations=[ob("Then show it.", "show", {"subject": MOD}), ob("Test the search too.", "test", {"subject": SEARCH})]), "expected 3 obligations"),
    ("C15b", "reload makes a model call", "C15", lambda e: changed(e, "specimen", "reloaded", model_calls=2), "model_calls expected 0"),
    ("C16", "only one operation of the phrase kept", "C16",
     lambda e: changed(e, "conjunction", "read", obligations=[ob("Redesign the mod and show it.", "show", {"subject": MOD})]), "expected 2 obligations"),
    ("C17a", "display equality merges two operations", "C17",
     lambda e: changed(e, "identical_operations", "reloaded", obligations=[ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)]), "expected 2 obligations"),
    ("C17b", "two references to one result become two results on reload", "C17",
     lambda e: changed_ob(e, "shared_result", "reloaded", 2, bindings={"surfaces": (Ref(1), PAGE)}), "binding surfaces"),
    ("C18a", "cancel keeps the preview", "C18", lambda e: changed(e, "transitions", "cancelled", obligations=REBOUND), "binding subject"),
    ("C18b", "a preview writes to the store", "C18", lambda e: changed(e, "transitions", "preview_valid", writes=1), "writes expected 0"),
    ("C18c", "a failed save loses the draft", "C18", lambda e: changed(e, "transitions", "save_failed", obligations=REBOUND), "binding subject"),
    ("C18d", "an invalid preview changes the reading", "C18",
     lambda e: changed(e, "transitions", "preview_invalid", obligations=[ob("Redesign the mod.", "redesign", {"surface": SEARCH}, PENDING), REDESIGN_SHOW[1]]), "binding surface"),
    ("C18e", "restore does not return to the first snapshot", "C18", lambda e: changed(e, "transitions", "restored", obligations=REBOUND), "binding subject"),
    ("C19a", "a rerun overwrites the correction with the model's preference", "C19",
     lambda e: changed(e, "rerun", "rerun", obligations=REDESIGN_SHOW, corrections=[]), "binding subject"),
    ("C19b", "a correction invalidated with no reason", "C19",
     lambda e: changed(e, "world_change", "changed", corrections=[Correction(1, "subject", MOD, INVALIDATED, "")]), "no reason"),
    ("C20a", "a refusal reported as passed", "C20",
     lambda e: changed(e, "refusal", "checked", checks=[Check(0, None, "evidence", PASS), Check(1, None, "evidence", PASS)], verdict=PASS), "verdict expected"),
    ("C20b", "the page obligation is never checked", "C20",
     lambda e: changed(e, "mod_only", "checked", checks=[Check(0, None, "evidence", PASS, 0)], verdict=PASS), "no 'evidence' check for obligation 1"),
    ("C21a", "a passing type check reported as fulfillment", "C21",
     lambda e: changed(e, "wrong", "checked", checks=[Check(0, None, "type", PASS, 0), Check(0, None, "behavior", PASS, 0)], verdict=PASS), "'behavior'"),
    ("C22a", "reload loses the decision context", "C22",
     lambda e: changed(e, "saved_reading", "reloaded", decisions=[dataclasses.replace(one, state="", scores=()) for one in e["saved_reading"]["steps"]["reloaded"]["decisions"]]), "decisions differ"),
    ("C22b", "a cosmetic renderer change merges or rebinds", "C22",
     lambda e: changed_ob(e, "saved_reading", "restyled", 1, bindings={"subject": PAGE}), "obligations differ"),
    ("C22c", "reload loses the unresolved state", "C22",
     lambda e: changed(e, "saved_reading", "reloaded", obligations=e["saved_reading"]["steps"]["edited"]["obligations"][:2]), "obligations differ"),
    # Wrong implementations that the first version of this oracle accepted (CORRECTIONS).
    *((f"{case_id}x", "a decision recorded without d1's question or the phrase it read", case_id, lambda e, run=run: no_context(e, run, "read"), "lost d1's question")
      for case_id, run in (("C03", "negated"), ("C04", "rejected"), ("C06", "earlier_not_local"), ("C07", "reshape_open"), ("C08", "page_then_mod"), ("C15", "specimen"))),
    ("C01c", "the check step drops the unresolved obligation from its reading", "C01",
     lambda e: changed(e, "unsupported", "checked", obligations=[]), "a check changed the reading"),
    ("C03b", "a lexical negation rule applied over d1's answer", "C03",
     lambda e: changed_ob(e, "follows_d1", "read", 0, bindings={"surfaces": (MOD,)}), "binding surfaces"),
    ("C05d", "deliberate absence produced by a rule, not by d1's absence answer", "C05",
     lambda e: changed(e, "absent", "read", decisions=[dataclasses.replace(one, by="rule") for one in e["absent"]["steps"]["read"]["decisions"]]), "decided by 'rule'"),
    ("C05e", "a rejected-optional hole that d1 never decided", "C05", lambda e: changed(e, "unresolved", "read", decisions=[]), "no recorded decision"),
    ("C08b", "the existing redesign(page) is not offered beside the new application", "C08",
     lambda e: changed(e, "page_then_mod", "read", decisions=[Decision(2, "subject", "model", (New("redesign"), MOD), New("redesign"), (), "Show the mod redesigned.", "q", ((New("redesign"), 0.9),))]), "not offered"),
    ("C11e", "a validator that reports every rule, not the precise one", "C11",
     lambda e: changed(e, "edits", "extra_field", diagnostics=[(1, "cell.colour", rule) for rule in ("type", "missing", "extra", "reference")]), "diagnostics expected exactly"),
    ("C11f", "a hole of the wrong type accepted", "C11",
     lambda e: changed(e, "edits", "wrong_hole_type", accepted=True, diagnostics=[], obligations=[ob("Redesign the mod.", "redesign", {"surface": Hole("Cell", CLEARED)}, PENDING), CELL_BASE[1]]), "accepted expected False"),
    ("C11g", "a wrong field type accepted: validation does not recurse into a record", "C11",
     lambda e: changed(e, "edits", "wrong_field_type", accepted=True, diagnostics=[]), "accepted expected False"),
    ("C14d", "the world refuses `none` and the unresolved request vanishes", "C14",
     lambda e: changed({**e, "reserved_name": {**e["reserved_name"], "world_faults": [("none", "name")]}}, "reserved_name", "read", obligations=[]), "expected 1 obligations"),
    ("C17c", "a save step that leaves show referring to itself", "C17",
     lambda e: changed(e, "shared_result", "saved", obligations=[ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Show it.", "show", {"subject": Ref(1)}, PENDING)]), "not an earlier obligation"),
    ("C18f", "cancel restores the bindings but drops d1's decisions", "C18", lambda e: changed(e, "transitions", "cancelled", decisions=[]), "decisions differ"),
    ("C18g", "inspecting a binding asks d1", "C18", lambda e: changed(e, "transitions", "inspected", model_calls=1), "model_calls expected 0"),
    ("C19c", "a world change invalidates the correction and drops the show obligation", "C19",
     lambda e: changed(e, "world_change", "changed", obligations=[ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", REJECTED)}, PENDING)]), "lost an obligation"),
    ("C20c", "removing Later turns a reply's claim into a pass", "C20",
     lambda e: changed(e, "later_removed", "checked", checks=[Check(0, None, "evidence", PASS), Check(1, None, "evidence", PASS)], verdict=PASS), "verdict expected"),
    ("C22d", "the edit rewrites d1's recorded choice instead of keeping it beside the correction", "C22",
     lambda e: {**e, "saved_reading": {**e["saved_reading"], "steps": {label: step | ({"decisions": [dataclasses.replace(one, chosen=PAGE) if one.path == "surface" else one for one in step["decisions"]]} if "decisions" in step else {})
                                                                        for label, step in e["saved_reading"]["steps"].items()}}}, "d1's own choice"),
    ("C22e", "a saved reading loads under another world as compatible history", "C22", lambda e: changed(e, "saved_reading", "other_world", diagnostics=[]), "diagnostics expected exactly"),
    ("C22f", "an unresolved request saved with a guessed goal type", "C22",
     lambda e: changed_ob(e, "saved_reading", "reloaded", 2, bindings={"": Hole("Later[Observed]", NO_CANDIDATE)}), "guessed goal"),
)


def static_controls(right: dict, delivered: dict) -> tuple:
    """Returns wrong provenance records and wrong production worlds, the check that must reject each, and its diagnostic."""
    elsewhere = pathlib.Path("/Users/max/Documents/scriptt-next/next/scriptt16.py")
    return (
        ("L1", "tests run in the reference copy", lambda: l1(right | {"worktree": "/Users/max/Documents/scriptt-release"}), "L1: worktree"),
        ("L2", "a result with no commit", lambda: l2(right | {"commit": ""}), "L2: no git commit"),
        ("L2b", "a result with no hash for scriptt16", lambda: l2(right | {"files": {k: v for k, v in right["files"].items() if k != "next/scriptt16.py"}}), "L2: no sha256"),
        ("L3", "scriptt16 imported from the reference copy", lambda: l3(right | {"imported": right["imported"] | {"scriptt16": str(elsewhere)}}), "L3: scriptt16"),
        ("L4", "the delivered engine differs from the tested one", lambda: l4(right | {"files": right["files"] | {"next/scriptt16.py": "0" * 64}}, delivered), "L4: next/scriptt16.py"),
        ("L5", "a change made elsewhere and not transferred", lambda: l5(right | {"elsewhere": [{"path": str(elsewhere), "transferred": False}]}), "L5:"),
        ("L6", "location decided by asking d1", lambda: l6(right | {"method": "d1"}), "L6:"),
        ("C21b", "a verify operation in the production world", lambda: production_world_diagnostics((HERE / "world.py").read_text() + '\ndef verify(subject: Subject) -> Observed:\n    "verify it"\n'), "declares ['verify']"),
    )


# ---- Self-test ---------------------------------------------------------------


def source_links() -> list[str]:
    """Checks that the quoted words of every brief requirement occur in the brief."""
    brief = plain(pathlib.Path(BRIEF).read_text().replace("**", ""))
    quoted = [(one["id"], one["words"]) for one in REQUIREMENTS if one["source"].startswith(BRIEF)]
    quoted += [(case.id + " required", case.required) for case in CASES]
    return [f"{key}: words not found in the brief: {words[:60]!r}" for key, words in quoted if plain(words) not in brief]


def self_test() -> None:
    """Shows that the oracle passes its expected structures and rejects every wrong projection."""
    provenance = snapshot()
    print(f"oracle version {ORACLE_VERSION} ({len(CORRECTIONS)} corrections); working path: {provenance['worktree']}; commit: {provenance['commit']}")
    for name, sha in provenance["files"].items():
        print(f"  sha256 {sha}  {name}")
    for name, path in provenance["imported"].items():
        print(f"  import {name:<14} {path}")
    failures = source_links()
    print(f"requirements: {len(REQUIREMENTS)} items; source links checked: {'all found' if not failures else failures}")
    assert len(CASES) == 22 and len(INVARIANTS) == 10, "the inventory must hold 22 cases and 10 invariants"
    assert {row["invariant"] for row in INVARIANT_TABLE} == set(INVARIANTS)

    expected = {case_id: expected_runs(case_id) for case_id in CASE}
    delivered = provenance["files"]
    rights = [(case_id, f"{len(CASE[case_id].runs)} runs", lambda case_id=case_id: PREDICATES[case_id](expected[case_id])) for case_id in CASE]
    rights += [(key, "current snapshot", lambda key=key: l4(provenance, delivered) if key == "L4" else LOCATION_PREDICATES[key](provenance)) for key in LOCATION_PREDICATES]
    for key, words, found in ((key, words, check()) for key, words, check in rights):
        failures += [f"{key} rejects its own EXPECTED: {line}" for line in found]
        print(f"{key} EXPECTED ({words}): {'pass' if not found else found}")
    wrongs = [(key, f"{case_id} {words}", lambda wrong=wrong, case_id=case_id: PREDICATES[case_id](wrong(expected[case_id])), diagnostic) for key, words, case_id, wrong, diagnostic in NEGATIVE_CONTROLS]
    wrongs += static_controls(provenance, delivered)
    for key, words, wrong, diagnostic in wrongs:
        found = wrong()
        caught = [line for line in found if diagnostic in line]
        failures += [] if caught else [f"{key} ({words}) not caught: {found}"]
        print(f"{key:<5} {'caught' if caught else 'MISSED'}: {words} -> {(caught[0] if caught else str(found))[:160]}")
    assert not failures, "\n".join(failures)
    print(f"self-test passed: 22 cases pass on EXPECTED; {len(NEGATIVE_CONTROLS)} wrong projections and {len(wrongs) - len(NEGATIVE_CONTROLS)} wrong locations or worlds rejected")


if __name__ == "__main__":
    self_test()
