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
    "decisions":   [Decision, ...]     # every decision of the reading, d1's and the rules'
    "requests":    [Request, ...]      # every question the stand-in received during this step, as received
    "diagnostics": [(obligation index or None, path or None, rule), ...]
    "accepted":    bool                # for an edit, a save or a world proposal
    "corrections": [Correction, ...]
    "checks":      [Check, ...]
    "verdict":     PASS | FAIL | UNVERIFIED
    "world_change": {"activated": bool, "verdict": ..., "regressions": [(message, obligation), ...],
                     "faults": [(declaration name, rule), ...],   # of the proposed world
                     "draft": text,                               # the proposal, as the engine returns it
                     "active_world": text}                        # the source of the active world after the step
    "record":      dict                # a save: the JSON it wrote, parsed and not projected (RECORD)
    "rendered":    text                # a reload or restyle: the reading as the renderer displays it
    "model_calls": int                 # requests sent to d1 during this step
    "writes":      int                 # successful writes to the store during this step
    "error":       None | exception class name

A key for a judgment the engine does not make is left out; the adapter never
supplies it, and a predicate that needs it fails.

An obligation is one operation instance that the source asks for, including an
operation nested inside another term. Obligations are listed in the order of
their phrase in the message; within one phrase, an operation whose result
another operation of the phrase consumes comes first, and otherwise the order
in which the phrase asks for them. A binding value is one of:

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
import collections
import dataclasses
import functools
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
class Inside:
    """In EXPECTED: a span that may be the whole phrase or any part of it."""

    phrase: str


@dataclasses.dataclass(frozen=True)
class New:
    """A candidate that is a new application of an operation. Used in scripts and in offered candidates."""

    operation: str


@dataclasses.dataclass(frozen=True)
class Obligation:
    """One requested operation instance.

    Attributes:
        span: The text of the innermost source phrase that holds it, stripped.
            In EXPECTED it may be ``Inside(phrase)``: the phrase or any part of it.
        operation: The function name, or UNRESOLVED.
        bindings: The value at each argument path.
        status: The engine's own dependency judgment, never recomputed by the
            adapter: PENDING if its result is Later or any input, at any depth
            of Record, Many or Maybe, is the result of a PENDING obligation;
            else AVAILABLE. A hole is incompleteness, not pending. None for UNRESOLVED.
        reason: Why the operation is UNRESOLVED; None otherwise.
        brand: The brand of the phrase.
        complete: The engine's own completeness judgment: False if a binding,
            at any depth, is a hole, or it refers to an incomplete obligation.
        ready: The engine's own readiness judgment: valid, complete and AVAILABLE.
        at: (start, end), the characters of the span in the message read.
    """

    span: str
    operation: str
    bindings: dict = dataclasses.field(default_factory=dict)
    status: str | None = AVAILABLE
    reason: str | tuple | None = None
    brand: str = "Asked"
    complete: bool | tuple | None = True
    ready: bool | tuple | None = None
    at: tuple | None = None


@dataclasses.dataclass(frozen=True)
class Passage:
    """A span that is no obligation: a quote, a remark, a context or a constraint.

    Attributes:
        text: The text, stripped.
        brand: The brand of the phrase.
        origin: "user", or "reply N" for a quote of the N-th earlier reply given.
        relation: The relationship to the request. Never empty, "none" or "nothing".
        at: (start, end), the characters of the text in the message read.
    """

    text: str
    brand: str
    origin: str
    relation: str
    at: tuple | None = None


@dataclasses.dataclass(frozen=True)
class Decision:
    """One recorded decision about an operation (path None) or a binding.

    Attributes:
        obligation: The obligation index; None for a decision about phrasing.
        path: The argument path, or None for the choice of the operation.
        by: "model" for a d1 answer, "rule" for a declared deterministic default.
        offered: The candidates offered, as neutral values, operation names,
            ABSTAIN or NO_REQUEST.
        chosen: The chosen candidate; a tuple for a Many; REJECT, ABSENT, or
            INVALID for a malformed or missing answer. An edit never changes
            it: a correction is a separate record.
        cut: The candidates that a bound excluded.
        state: The exact text that d1 read; it holds the phrase.
        questions: Each question d1 received for it, as (instructions, options),
            exactly as sent; a Many chosen by yes/no questions has one per candidate.
        scores: The share of each option, as (option, share) pairs, options
            named as in ``offered``.
        rule: For a decision by rule, the declared rule.
    """

    obligation: int | None
    path: str | None
    by: str
    offered: tuple = ()
    chosen: object = None
    cut: tuple = ()
    state: str = ""
    questions: tuple = ()
    scores: tuple = ()
    rule: str = ""


@dataclasses.dataclass(frozen=True)
class Request:
    """One question that the stand-in d1 received, recorded by the stand-in before it answers."""

    state: str
    instructions: str
    options: tuple


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
INVALID = "INVALID"        # d1's answer was malformed or missing


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
class Probe:
    """A behaviour check that was run: a test-only pure function on a known input, with the result it gave."""

    function: str
    argument: object
    expected: object
    observed: object


def probed(function, argument, expected) -> Probe:
    """Runs a test-only pure function on a known input and records what it returned."""
    return Probe(function.__name__, argument, expected, function(argument))


@dataclasses.dataclass(frozen=True)
class Artifact:
    """Supplied evidence about one exact operation and its bindings: its value, and the behaviour check run on it."""

    operation: str
    bindings: dict
    value: object = None
    probe: Probe | None = None


@dataclasses.dataclass(frozen=True)
class Inputs:
    """What ``observe`` receives: execution inputs only, never an expected result."""

    world: World
    messages: tuple
    replies: tuple
    script: dict
    actions: tuple


@dataclasses.dataclass(frozen=True)
class Run:
    """One run of a case: its inputs, and the expectations that only the predicates read.

    Attributes:
        label: The name of the run.
        control: True for a successful control.
        world: The world.
        messages: The messages, read in order. Usually one.
        script: ``{"ops": {phrase: answer}, "binds": {(phrase, operation, path): answer}, "judge": share}``.
        actions: ``(step label, action)``, in order.
        expect: The expected step by step label, with only the keys that are compared.
        replies: The earlier replies.
    """

    label: str
    control: bool
    world: World
    messages: tuple
    script: dict
    actions: tuple
    expect: dict
    replies: tuple = ()

    def inputs(self) -> Inputs:
        """Returns what the engine may see."""
        return Inputs(self.world, self.messages, self.replies, self.script, self.actions)


def run(label, control, world, messages, script, steps, replies=()) -> Run:
    """Returns a run written as ``(label, action, expected step)`` triples, split into inputs and expectations."""
    return Run(label, control, world, messages, script, tuple((label, action) for label, action, _ in steps), {label: want for label, _, want in steps}, replies)


def steps_of(run: Run):
    """Yields each step of a run as (label, action, expected step)."""
    for label, action in run.actions:
        yield label, action, run.expect.get(label, {})


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


def observe(inputs: Inputs) -> dict:
    """Runs one run's inputs on the repaired engine and returns its neutral observation.

    The implementer writes this adapter once, in the test file, and applies a
    case's predicate to ``{run.label: observe(run.inputs()) for run in case.runs}``.
    It receives only execution inputs and must not be changed to make a
    predicate pass. Its contract:

    * World: the source is ``world_source(world)``; load it with
      ``test_scriptt16.world_of`` in a temporary folder that holds an empty file
      for each name in ``files``. Report the loader's hard faults as
      ``(declaration name, rule)`` with a rule from ``RULES``, and the loaded
      function names, sorted.
    * Stand-in d1: answer by meaning, from ``inputs.script``, and choose only by
      what d1 receives. It may learn from a question which operation and path
      it is about; it chooses an option only by its description, with
      ``option_for`` (an operation by its docstring in the world source, a
      literal by its words, a reference by the rendering of the obligation
      that ``script["refers"]`` names, a new application by its unbound
      rendering) and a yes/no candidate with ``option_for(..., whole=False)``
      on the question. ABSTAIN, NO_REQUEST, REJECT and ABSENT pick the options
      the engine declares for them. A scripted value that no description says
      gets an out-of-set answer, so a blank or swapped description fails the
      case. Before it answers,
      it appends every question it received, exactly as received, to the
      step's ``requests`` as ``Request(state, instructions, options)``, options
      being the option descriptions in order (``()`` for a yes/no question).
      An operation question about phrase P gets ``ops[P]``: a function name (or
      a tuple of names when the phrase asks for several), ``ABSTAIN`` (the
      engine's option for "no function fits"), ``NO_REQUEST`` (its option for
      "asks for nothing"), or a ``Malformed`` answer: "out_of_set" returns an
      option id that was not offered, "missing" returns no entry for the key,
      "not_numbers" returns a share that is not a number. A binding question
      about (P, operation, path) gets ``binds[...]``: the offered option whose
      neutral projection equals the value or ``New``, ``REJECT`` (the
      none-of-these option), ``ABSENT`` (the absence option), a ``Malformed``
      answer as above, or for a yes/no-per-candidate Many question, yes exactly
      for the members of the tuple. An absence question (an absence option, or
      a yes/no "deliberately absent?") gets the absence answer exactly when the
      script says ABSENT; REJECT for a yes/no Many is no to every candidate.
      A phrase is looked up by its exact text, stripped; else by the longest
      scripted phrase inside it; else by the shortest scripted phrase that
      holds it. Unscripted: an operation question gets NO_REQUEST, a
      binding question REJECT, a yes/no question about a reply
      ``script.get("judge", 0.1)``. The chosen option gets share 0.9 and the
      others share the rest equally. One request to d1 is one model call,
      however many questions it holds.
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
      script)`` (the messages read so far are the accepted corpus, read again
      under the active world), ``("load", kind)`` (save the reading, change the
      written JSON with ``mutated(record, kind)``, and load it). The restyle
      patches the function that the reading's display actually calls, and
      both reload and restyle report ``rendered``.
    * Each step reports what the engine produced, projected from its own data
      structures, never parsed from ``say()`` text, never recomputed or
      supplied by the adapter (``status``, ``complete``, ``ready`` and ``Ref``
      come from the engine's own judgments and object identity; a decision's
      ``chosen`` is the candidate the engine stored, never rebuilt from the
      bindings; automatic decisions, such as a record built from its fields or
      a hole with no candidate, are listed with ``by="rule"`` and their rule). A save
      reports the JSON it wrote as ``record``. ``model_calls`` and ``writes``
      count what happened during that step only. An exception is reported as
      ``error`` and the run goes on.

    Args:
        inputs: The run's inputs.

    Returns:
        The observation in the neutral form of this module's docstring.
    """
    raise NotImplementedError("the implementer writes this adapter in the test file")


# ---- The requirement inventory# ---- The requirement inventory ----------------------------------------------

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
    "P5": ("The state machine to implement", "A world with invalid types cannot activate. A changed world that contradicts an accepted meaning cannot activate silently. Preserve the draft on rejection.", "C02"),
    "P6": ("Use the system itself without making the check circular", "Keep live-d1 evaluation separate from deterministic conformance."),
    "P7": ("Deliver and stop only when the repair is concrete", "Report each invariant and acceptance case as pass, fail or unverified with a direct evidence reference."),
}


# The saved record that the engine writes and the interface loads (the coordinator's message of 10 Nov).
RECORD = {"R1": ("A save writes one JSON object per reading: {\"phrases\": [{\"start\": int, \"end\": int, \"brand\": str, \"terms\": [application, ...]}], "
                 "\"decisions\": [{\"path\": str or null, ...}, ...]}. An application is {\"id\": str, \"function\": str, \"arguments\": {name: value}}; a value is "
                 "{\"constant\": json, \"type\": str}, {\"ref\": id}, {\"several\": [value, ...]}, {\"fields\": {name: value}, \"type\": str}, {\"empty\": type}, "
                 "{\"hole\": type, \"reason\": str} or an application. A phrase may hold several applications; a member of several may be a reference.",
                 ("C10", "C15", "C16", "C17"))}


# Each change to this oracle after its first review. Version 1 is commit 5b524a0.
# Every observed result must be judged again against the version that holds it;
# no result had been produced against version 1.
ORACLE_VERSION = 6
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
    ("E20", 3, "C16 required the whole phrase as both spans and an exact phrase lookup, so an engine that splits the phrase at 'and' failed though it keeps both obligations",
     "each span may be the phrase or any part of it (Inside); the stand-in looks a sub-phrase up by containment; both obligations, and every word, must still be kept", ("C16",)),
    ("E21", 3, "E7 left open an optional with nothing in scope", "d1 is asked about absence: its recorded absence answer gives Empty; without one the result is Hole(no candidate); runs nothing_in_scope and nothing_in_scope_unanswered", ("C05",)),
    ("E22", 3, "completeness had no place in the neutral form, so a term with a hole input could be treated as complete", "Obligation.complete, the engine's own judgment, transitive through references; a complete term with a hole is rejected in every step", tuple(f"C{n:02}" for n in range(1, 23))),
    ("E23", 3, "the C17 note did not say that 'again' is not tested", "a line in the interpretation", ("C17",)),
    ("E24", 3, "nothing showed that a brand cannot create evidence", "run relabelled: redesign returns Observed and the artifacts are the reply relabelled Observed; the evidence criterion takes no brand on words as evidence", ("C20",)),
    ("E25", 3, "a rejected world change could lose its draft or switch the active world", "world_change reports the draft, the proposed source, its faults and the active functions; P5 is now checked by C02", ("C02",)),
    ("E26", 4, "observe() received each run with its expected steps", "a run holds inputs (world, messages, replies, script, actions) apart from its expectations; observe(run.inputs()) never sees an expected result; a judgment the engine does not make is left out, not supplied", tuple(f"C{n:02}" for n in range(1, 23))),
    ("E27", 4, "decisions were compared with expectations only, so a fabricated, missing or extra decision could pass", "the stand-in records every question it received; the decisions of a step must equal the questions of the latest step that asked any, exactly", tuple(f"C{n:02}" for n in range(1, 23))),
    ("E28", 4, "checks were read into a dict, so a later duplicate PASS overwrote an earlier outcome and unexpected results were ignored", "duplicate and unexpected checks are rejected; a PASS for an incomplete obligation is rejected", ("C01", "C06", "C20", "C21")),
    ("E29", 4, "the evidence criterion blacklisted four brand names and accepted an artifact by its operation and arguments alone", "evidence is an artifact whose behaviour check ran and gave the expected result; words of any type, a new brand included, are never evidence; C21 runs its fixture on a known input", ("C01", "C06", "C20", "C21")),
    ("E30", 4, "the draft was compared with a proposal that the adapter itself reported, and the active world by function names, so a schema change that kept the names passed", "the draft must equal world_source(proposal) from the inputs; the active world's declarations (types and signatures) must equal the expected world's", ("C02",)),
    ("E31", 4, "source coverage compared sets of words, so a repeated, misplaced or reordered span passed", "obligations and passages carry character positions; each must be the exact source text at its place, every non-space character is covered, obligations are in source order", ("C01", "C06", "C13", "C14", "C16", "C17")),
    ("E32", 4, "Empty needed a d1 answer even with nothing in scope, and the 'unanswered' run scripted a rejection", "Empty needs a recorded absence decision, by d1 or by a named declared rule; a rejection and a malformed or missing answer are separate runs, the latter giving Hole(invalid answer) with a diagnostic", ("C05",)),
    ("E33", 4, "nothing stopped an engine from splitting every 'and'", "control compare_conjunction: 'Compare the page and the mod.' stays one compare of both", ("C16",)),
    ("E34", 4, "readiness was not a judgment of the neutral form", "Obligation.ready; ready only if complete and available; no PASS for an incomplete obligation", tuple(f"C{n:02}" for n in range(1, 23))),
    ("E35", 4, "nothing checked that member words inside a quoted reply are not grounded as the user's values", "runs quoted_members and own_members", ("C13",)),
    ("E36", 4, "the saved record that the interface loads had no contract", "requirement R1 and its structural check on the JSON that save wrote", ("C10", "C15", "C16", "C17")),
    ("E37", 4, "fixtures could replace text that the base world does not contain, silently", "world_source builds every world from the base frozen at the snapshot commit; the self-test requires each replaced text to exist", ()),
    ("E38", 5, "runs later_removed and relabelled made the obligations available with dataclasses.replace but kept ready=False, computed while they were pending; by the oracle's own rule an available, complete, valid obligation is ready", "ready follows from complete and available in those runs", ("C20",)),
    ("E39", 6, "a Many with one candidate was never tested, so binding a singleton collection without asking passed", "run singleton_many: d1 is asked", ("C04",)),
    ("E40", 6, "a Many whose every candidate d1 rejects was untested; it could become an explicit empty collection", "run all_rejected: a rejected hole; a d1 rejection never yields a value", ("C06",)),
    ("E41", 6, "one phrase with an unknown and a known operation was untested", "run unknown_and_known: UNRESOLVED and redesign both kept; within a phrase, the asked order", ("C16",)),
    ("E42", 6, "a phrase asking for more operations than Limits.operations was untested", "run too_many_operations: the extra request is UNRESOLVED with reason bounded, and recorded", ("C14",)),
    ("E43", 6, "the gate was never shown an added obligation, a second proposal after an activation, or a changed hole reason", "runs added, second_proposal and reason_changed: each is a regression; reasons are meaning", ("C02",)),
    ("E44", 6, "invalidation on rerun was tested only for a removed member, and a reason was accepted if non-empty", "runs function_changed and reference_target_changed; a reason must name the operation or path; an invalidated reference is not re-pointed", ("C19",)),
    ("E45", 6, "an edit after a correction at the same place was untested", "run edit_after_correction: the later edit replaces the correction, and a rerun keeps it", ("C19",)),
    ("E46", 6, "a record inside a collection was never read, judged or gated", "run many_of_records: no step fails", ("C10",)),
    ("E47", 6, "loading never met a broken saved line", "run loads: a wrong-type binding, a dangling reference and a missing argument load with their exact diagnostics, and the affected obligation is not complete or ready", ("C11",)),
    ("E48", 6, "a kind fault reported as a type fault was not caught", "control C11h; edits set values, not types, so the edit level has no kind rule to report", ("C11",)),
    ("E49", 6, "a decision's chosen candidate could be rebuilt by the adapter, and automatic decisions could be missing", "chosen must be one of the offered candidates; automatic decisions (a record from its fields, a hole with no candidate, a bounded request) are expected with by rule", ("C06", "C11", "C14")),
    ("E50", 6, "a restyle that changed nothing the display uses passed C22", "reload and restyle report the rendered reading, and the restyle must change it", ("C22",)),
    ("E51", 6, "the stand-in chose candidates from engine terms, so a blank or swapped option description passed", "the stand-in chooses only by descriptions with option_for, and answers out of set when none says the scripted value; scripts name what a reference renders as (refers)", tuple(f"C{n:02}" for n in range(1, 23))),
)


# ---- Shorthand for the expected structures -----------------------------------

MOD, PAGE, SEARCH = Lit("Surface", "the mod"), Lit("Surface", "the page"), Lit("Code", "the search")
NOTES, THREE = Lit("Path", "notes.md"), Lit("int", 3)
TEST_FUNCTIONS = ["approve", "compare", "explain", "follow", "open_cell", "redesign", "review", "show"]


def values_of(bindings: dict) -> list:
    """Returns every value of the bindings, with the members of each Many."""
    return [value for binding in bindings.values() for value in (binding if isinstance(binding, tuple) else (binding,))]


def ob(span, operation, bindings=None, status=AVAILABLE, reason=None, complete=None):
    """Returns an expected obligation: complete unless a binding is a hole, ready if complete and available."""
    bindings = bindings or {}
    complete = (not any(isinstance(value, Hole) for value in values_of(bindings))) if complete is None else complete
    ready = tuple(one and status == AVAILABLE for one in complete) if isinstance(complete, tuple) else complete and status == AVAILABLE
    unresolved = operation == UNRESOLVED
    return Obligation(span, operation, bindings, None if unresolved else status, reason, complete=None if unresolved else complete, ready=None if unresolved else ready)


def script(ops, binds=None, judge=None, refers=None):
    """Returns the answers of the stand-in d1 for a run; ``refers`` says what each referenced obligation renders as."""
    found = {"ops": ops, "binds": binds or {}, "refers": refers or {}}
    return found | ({"judge": judge} if judge is not None else {})


def told(obligations: list, judge=None) -> dict:
    """Returns the answers of a stand-in d1 that means exactly these obligations.

    Each phrase gets its operations (ABSTAIN for an UNRESOLVED one), each argument its value.
    """
    ops, binds = {}, {}
    for one in obligations:
        ops[one.span] = ops.get(one.span, ()) + (ABSTAIN if one.operation == UNRESOLVED else one.operation,)
        binds |= {(one.span, one.operation, path): value for path, value in one.bindings.items() if not isinstance(value, Hole) and value not in (EMPTY, EMPTY_LIST)}
    return script({span: names[0] if len(names) == 1 else names for span, names in ops.items()}, binds, judge, refers_of(obligations))


def refers_of(obligations: list) -> dict:
    """Returns, for each obligation, its function and the words of its literals: what a reference to it renders as."""
    return {index: (one.operation, tuple(str(value.value) for value in values_of(one.bindings) if isinstance(value, Lit))) for index, one in enumerate(obligations)}


@functools.cache
def docstrings(world: World) -> dict:
    """Returns the docstring of each function of a world, white space collapsed: how d1 sees an operation."""
    return {node.name: " ".join(ast.get_docstring(node).split()) for node in ast.parse(world_source(world)).body if isinstance(node, ast.FunctionDef) and ast.get_docstring(node)}


def option_for(want, descriptions: tuple, refers: dict | None = None, world: World | None = None, whole: bool = True) -> int | None:
    """Returns the index of the one description that says ``want``, or None: how the stand-in chooses.

    An operation name is said by its docstring; a literal by its words, quoted or not; a reference by
    the referenced obligation's function and its literals' quoted words; a new application by its
    function with nothing bound. With ``whole`` False, a description need only hold the saying (a yes/no question).
    """
    def says(text: str) -> bool:
        text = " ".join(str(text).split())
        if isinstance(want, str) and world is not None and want in docstrings(world):
            return text == docstrings(world)[want] if whole else docstrings(world)[want] in text
        if isinstance(want, Lit):
            return text.strip("'\"") == str(want.value) if whole else f"'{want.value}'" in text
        if isinstance(want, Ref):
            function, words = (refers or {}).get(want.obligation, ("", ()))
            return bool(function) and (text.startswith(function + "(") if whole else function + "(" in text) and all(f"'{one}'" in text for one in words)
        if isinstance(want, New):
            return text.startswith(want.operation + "(") and "'" not in text if whole else want.operation + "(" in text
        return False
    found = [index for index, text in enumerate(descriptions) if says(text)]
    return found[0] if len(found) == 1 else None


def mutated(record: dict, kind: str) -> dict:
    """Returns a saved record of "Redesign the mod. Then show it." broken one way: wrong_type, dangling or missing."""
    broken = copy.deepcopy(record)
    applications = {term["function"]: term for phrase in broken["phrases"] for term in phrase["terms"]}
    if kind == "wrong_type":
        applications["redesign"]["arguments"]["surface"] = {"constant": 3, "type": "int"}
    elif kind == "dangling":
        applications["show"]["arguments"]["subject"] = {"ref": "no such application"}
    else:
        del applications["redesign"]["arguments"]["surface"]
    return broken


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


def checked(words: str) -> str:
    """A test-only pure function that stands in for the behaviour check of an artifact: it returns its input."""
    return words


def worked(operation: str, bindings: dict) -> Artifact:
    """Returns an artifact for this operation and these bindings whose behaviour check ran and passed."""
    return Artifact(operation, bindings, probe=probed(checked, "a known input", "a known input"))


def evidence(obligation, artifact) -> bool:
    """Criterion "evidence": an artifact for exactly this operation and these bindings whose behaviour check gave the expected result."""
    passed = artifact.probe is not None and artifact.probe.observed == artifact.probe.expected
    return (artifact.operation, artifact.bindings) == (obligation.operation, obligation.bindings) and passed


DOUBLED = ob("Double 3.", "double", {"number": THREE})
DOUBLE_WORLD = World(extra='\ndef double(number: int) -> int:\n    "double a number"\n')
DOUBLE_CRITERIA = (("type", "the result is an int", lambda obligation, artifact: isinstance(artifact.value, int)),
                   ("behavior", "doubling the bound number gave twice it", lambda obligation, artifact: artifact.probe is not None
                    and (artifact.probe.argument, artifact.probe.expected) == (obligation.bindings["number"].value, 2 * obligation.bindings["number"].value)
                    and artifact.probe.observed == artifact.probe.expected))
EVIDENCE_CRITERIA = (("evidence", "an artifact for exactly this operation and these bindings whose behaviour check passed; words of any type are no evidence", evidence),)

REDESIGN_SHOW = [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Then show it.", "show", {"subject": Ref(0)}, PENDING)]
REBOUND = [REDESIGN_SHOW[0], ob("Then show it.", "show", {"subject": MOD})]
CLEARED_SHOW = [REDESIGN_SHOW[0], ob("Then show it.", "show", {"subject": Hole("Subject", CLEARED)})]
SHOW_DECISION = Decision(1, "subject", "model", (Ref(0), MOD), Ref(0))
MAYBE_TYPES = ("Surface", "Maybe[Surface]")
QUOTED = "I compared the page and the mod for you today."
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
BOXES = '\ndef tag(boxes: Many[Box]) -> Written:\n    "tag several boxes"\n'
BOX_WORLD = World(extra='\n@dataclasses.dataclass\nclass Box:\n    "a box"\n    surface: Surface\n\ndef pack(box: Box) -> Written:\n    "pack a box"\n\ndef describe(surface: Maybe[Surface]) -> Written:\n    "describe a surface"\n')
MAYBE_SURFACE = World(replace=(("Maybe[Words]", "Maybe[Surface]"),))
TWO = ("Redesign the mod.", "Show the page.")
TWO_SCRIPT = script({"Redesign the mod.": "redesign", "Show the page.": "show"}, {("Redesign the mod.", "redesign", "surface"): MOD, ("Show the page.", "show", "subject"): PAGE})
REDESIGN_TWO = [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Redesign the page.", "redesign", {"surface": PAGE}, PENDING)]


SOURCE_COMMIT = "dcbce02"  # the snapshot of next that the worlds are built from


@functools.cache
def base_source(base: str) -> str:
    """Returns next/world.py ("next") or the WORLD text of the test file ("test"), as they stood at SOURCE_COMMIT."""
    path = "next/world.py" if base == "next" else "next/test_scriptt16.py"
    text = subprocess.run(["git", "-C", str(HERE), "show", f"{SOURCE_COMMIT}:{path}"], capture_output=True, text=True, check=True).stdout
    return text if base == "next" else next(node.value.value for node in ast.parse(text).body if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "WORLD")


def world_source(world: World) -> str:
    """Returns the source of a world: its base, each replacement in order, then its extra text."""
    text = base_source(world.base)
    for old, new in world.replace:
        text = text.replace(old, new)
    return text + world.extra


def declarations(source: str) -> list[str]:
    """Returns the declarations of a world source without docstrings, sorted: its types and signatures."""
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            continue
        for inner in ast.walk(node):
            body = getattr(inner, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                inner.body = body[1:] or [ast.Pass()]
        found.append(ast.unparse(node))
    return sorted(found)


def record_spec(obligations: list) -> list:
    """Returns what a saved record must hold: each application's function, and the argument paths that are references, to the application they name."""
    return [(one.operation, {path + ("[]" if isinstance(value, tuple) else ""): ref.obligation for path, value in one.bindings.items()
                             for ref in (value if isinstance(value, tuple) else (value,)) if isinstance(ref, Ref)}) for one in obligations]


def rejected_edit(rule_place):
    """The expected step of an edit that validation rejects: the base is kept."""
    return {"accepted": False, "diagnostics": [rule_place], "obligations": CELL_BASE, "model_calls": 0, "writes": 0}


# ---- The 22 cases -----------------------------------------------------------

CASES = (
    Case("C01", "Unsupported request, then “I did nothing”",
         "Typed source and unresolved interpretation persist; verification includes the obligation; overall acceptance is not pass. Do not fabricate Hole[Any], Hole[Unknown] or a guessed goal type. Legacy none/nothing may be retained as raw response metadata, never terminal semantic answers.",
         "An abstention leaves the phrase without a term and check() skips it (probe abstention_skips_verification); a fabricated Hole[Any].",
         (run("unsupported", False, World(), ("Email my accountant.",), script({"Email my accountant.": ABSTAIN}),
              (("read", READ, {"obligations": [ob("Email my accountant.", UNRESOLVED, reason=REJECTED)], "passages": []}),
               ("checked", ("check", "I did nothing.", (), EVIDENCE_CRITERIA),
                {"checks": [Check(0, None, "evidence", (UNVERIFIED, FAIL))], "verdict": (UNVERIFIED, FAIL)}))),
          run("supported", True, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)]}),
               ("checked", ("check", "I redesigned the mod.", (worked("redesign", {"surface": MOD}),), EVIDENCE_CRITERIA),
                {"checks": [Check(0, None, "evidence", PASS, 0)], "verdict": PASS})))),
         interpretation="The unresolved operation's reason is REJECTED: d1 was offered every operation and rejected them. The outcome of its check may be UNVERIFIED or FAIL; the brief only says it is not pass."),
    Case("C02", "Same-confidence world change deletes a request",
         "Reject the change regardless of probability. An empty acceptance corpus is unverified, never accepted.",
         "The confidence gate accepts a world that loses a request at equal bits, and accepts an empty corpus (probes gate_accepts_disappeared_request_when_confidence_is_equal, confidently_wrong_nothing_gate, empty_corpus_gate).",
         tuple(run(label, label == "harmless", World(), () if label == "empty_corpus" else TWO, TWO_SCRIPT,
                   (() if label == "empty_corpus" else (("read", READ, {}),))
                   + (("proposed", ("propose_world", world, answers), {"world_change": {
                       "activated": label == "harmless", "verdict": verdict, "regressions": lost, "faults": [("Broken", "kind")] if label == "invalid_world" else [],
                       "active_world": world if label == "harmless" else World()}}),))
               for label, world, answers, verdict, lost in (
                   ("deleted", World(replace=(("def redesign(", "def destroy("),)), script({"Redesign the mod.": NO_REQUEST, "Show the page.": "show"}, {("Show the page.", "show", "subject"): PAGE}), FAIL, [(0, 0)]),
                   ("confident_nothing", PAINT_WORLD, script({"Redesign the mod.": NO_REQUEST, "Show the page.": NO_REQUEST}), FAIL, [(0, 0), (1, 0)]),
                   ("weakened", World(replace=(('    PAGE: Asked = "the page"\n', ""),)), TWO_SCRIPT, FAIL, [(1, 0)]),
                   ("invalid_world", BROKEN_WORLD, TWO_SCRIPT, FAIL, []),
                   ("empty_corpus", PAINT_WORLD, script({}), UNVERIFIED, []),
                   ("harmless", PAINT_WORLD, TWO_SCRIPT, PASS, [])))
         + (run("added", False, World(), ("Redesign the mod.",), told(REDESIGN_SHOW[:1]),
                (("read", READ, {}),
                 ("proposed", ("propose_world", PAINT_WORLD, script({"Redesign the mod.": ("redesign", "paint")}, {("Redesign the mod.", "redesign", "surface"): MOD, ("Redesign the mod.", "paint", "surface"): MOD})),
                  {"world_change": {"activated": False, "verdict": FAIL, "regressions": [(0, 1)], "faults": [], "active_world": World()}}))),
            run("second_proposal", False, World(), TWO, TWO_SCRIPT,
                (("read", READ, {}),
                 ("proposed", ("propose_world", PAINT_WORLD, TWO_SCRIPT), {"world_change": {"activated": True, "verdict": PASS, "regressions": [], "faults": [], "active_world": PAINT_WORLD}}),
                 ("proposed_again", ("propose_world", World(replace=(("def redesign(", "def destroy("),), extra=PAINT_WORLD.extra),
                                     script({"Redesign the mod.": NO_REQUEST, "Show the page.": "show"}, {("Show the page.", "show", "subject"): PAGE})),
                  {"world_change": {"activated": False, "verdict": FAIL, "regressions": [(0, 0)], "faults": [], "active_world": PAINT_WORLD}}))),
            run("reason_changed", False, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): REJECT}),
                (("read", READ, {}),
                 ("proposed", ("propose_world", PAINT_WORLD, script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): Malformed("out_of_set")})),
                  {"world_change": {"activated": False, "verdict": FAIL, "regressions": [(0, 0)], "faults": [], "active_world": World()}})))),
         interpretation="A regression is a (message, obligation) of the accepted corpus whose operation or bindings change or disappear; run weakened removes the page member, so show's binding weakens to a hole. A world with an invalid kind cannot activate (the brief's state machine). An unverified world change does not activate. A rejected change returns its draft equal to the proposal built from the inputs, with its regressions or faults, and the active world keeps every declaration: types and signatures, not only names. An obligation added to an accepted message is a regression at its index in the new reading (run added). After an activation, the corpus is read again under the active world and the next proposal is judged against it (run second_proposal). A hole whose reason changes from rejected to invalid answer has changed meaning (run reason_changed)."),
    Case("C03", "“Compare the mod, not the page”",
         "With controlled semantic selection, include mod and exclude page. Assert the binding, not merely rendered text. d1 must be given the relevant choice.",
         "solve(Many) takes every local term without asking d1 (probe many_negated_literal_is_included).",
         (run("negated", False, World(), ("Compare the mod, not the page.",),
              script({"Compare the mod, not the page.": "compare"}, {("Compare the mod, not the page.", "compare", "surfaces"): (MOD,)}),
              (("read", READ, {"obligations": [ob("Compare the mod, not the page.", "compare", {"surfaces": (MOD,)})],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (MOD,))]}),)),
          run("follows_d1", False, World(), ("Compare the mod, not the page.",),
              script({"Compare the mod, not the page.": "compare"}, {("Compare the mod, not the page.", "compare", "surfaces"): (MOD, PAGE)}),
              (("read", READ, {"obligations": [ob("Compare the mod, not the page.", "compare", {"surfaces": (MOD, PAGE)})],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (MOD, PAGE))]}),)),
          run("both", True, World(), ("Compare the page and the mod.",),
              script({"Compare the page and the mod.": "compare"}, {("Compare the page and the mod.", "compare", "surfaces"): (PAGE, MOD)}),
              (("read", READ, {"obligations": [ob("Compare the page and the mod.", "compare", {"surfaces": (PAGE, MOD)})],
                               "decisions": [Decision(0, "surfaces", "model", (PAGE, MOD), (PAGE, MOD))]}),))),
         interpretation="Run follows_d1 is conformance, not meaning: when the stand-in includes both, both are bound, so the exclusion in run negated must come from d1 and not from a lexical negation rule applied over its answer.",
         real_d1="Whether real d1 excludes a negated item is effectiveness, unverified here; conformance shows only that d1 is asked and its answer is bound."),
    Case("C04", "Reject the only candidate", "Retain an unresolved obligation. A singleton is not compulsory.",
         "One candidate is taken with no question (scriptt16.solve: chosen_term = offered[0]).",
         (run("rejected", False, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): REJECT}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", REJECTED)}, PENDING)],
                               "decisions": [Decision(0, "surface", "model", (MOD,), REJECT)]}),)),
          run("accepted", True, World(), ("Redesign the mod.",), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)],
                               "decisions": [Decision(0, "surface", "model", (MOD,), MOD)]}),)),
          run("singleton_many", False, World(), ("Compare the mod.",), told([ob("Compare the mod.", "compare", {"surfaces": (MOD,)})]),
              (("read", READ, {"obligations": [ob("Compare the mod.", "compare", {"surfaces": (MOD,)})], "decisions": [Decision(0, "surfaces", "model", (MOD,), (MOD,))]}),))),
         interpretation="The obligation keeps its operation; the rejected argument becomes Hole(Surface, rejected). d1 is offered the singleton with a reject option. A declared automatic default that a correction can undo would not satisfy this case. A Many with one candidate is no exception: d1 is asked (run singleton_many)."),
    Case("C05", "Optional value: absent versus rejected/unknown",
         "Explicit absence produces Empty; unresolved selection remains unresolved; both survive save/load.",
         "A rejected or unresolved optional becomes Empty (probe optional_abstention_becomes_empty_rather_than_unresolved).",
         tuple(run(label, label == "given", MAYBE_SURFACE, (text,), script({text: "explain"}, {(text, "explain", "subject"): answer}),
                   (("read", READ, {"obligations": [ob(text, "explain", {"subject": value}, complete=(True, False) if isinstance(value, frozenset) else None)],
                                    "decisions": [Decision(0, "subject", by, offered, chosen)]} | ({"diagnostics": [(0, "subject", "model_answer")]} if chosen == INVALID else {})),
                    ("saved", SAVE, {}),
                    ("reloaded", RELOAD, {"obligations": [ob(text, "explain", {"subject": value}, complete=(True, False) if isinstance(value, frozenset) else None)], "model_calls": 0})))
               for label, text, answer, offered, value, by, chosen in (
                   ("absent", "Explain in general, not the mod.", ABSENT, (MOD,), EMPTY, "model", ABSENT),
                   ("unresolved", "Explain the mod and the page.", REJECT, (MOD, PAGE), Hole(MAYBE_TYPES, REJECTED), "model", REJECT),
                   ("malformed", "Explain the mod and the page.", Malformed("out_of_set"), (MOD, PAGE), Hole(MAYBE_TYPES, INVALID_ANSWER), "model", INVALID),
                   ("missing", "Explain the mod and the page.", Malformed("missing"), (MOD, PAGE), Hole(MAYBE_TYPES, INVALID_ANSWER), "model", INVALID),
                   ("nothing_in_scope", "Explain.", ABSENT, (), EMPTY, ("model", "rule"), ABSENT),
                   ("nothing_in_scope_rejected", "Explain.", REJECT, (), frozenset({EMPTY, Hole(MAYBE_TYPES, (NO_CANDIDATE, REJECTED))}), ("model", "rule"), frozenset({ABSENT, REJECT})),
                   ("given", "Explain the mod.", MOD, (MOD,), MOD, "model", MOD))),
         interpretation="Empty needs a recorded absence decision: d1's absence answer, or a named declared rule (E32). With the mod in scope the choice is d1's, so a rule there fails; with nothing in scope either may decide, and if d1 is asked and rejects absence, the result is a hole. A malformed or missing answer is not a rejection: it gives Hole(invalid answer) and a diagnostic. The hole of an optional may be typed Surface or Maybe[Surface]."),
    Case("C06", "Empty Many versus unknown Many",
         "Empty collection and typed hole remain distinguishable; selection can exclude local terms and include relevant earlier ones.",
         "An unknown Many becomes an empty collection, or local terms are always taken (scriptt16.solve, Many branch).",
         (run("unknown", False, World(), ("Compare them.",), script({"Compare them.": "compare"}),
              (("read", READ, {"obligations": [ob("Compare them.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), (NO_CANDIDATE, REJECTED))})],
                               "decisions": [Decision(0, "surfaces", ("rule", "model"), ())]}),
               ("saved", SAVE, {}),
               ("reloaded", RELOAD, {"obligations": [ob("Compare them.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), (NO_CANDIDATE, REJECTED))})]}),
               ("checked", ("check", "I compared them.", (worked("compare", {"surfaces": (MOD, PAGE)}),), EVIDENCE_CRITERIA),
                {"checks": [Check(0, None, "evidence", (UNVERIFIED, FAIL))], "verdict": (UNVERIFIED, FAIL)}))),
          run("explicit_empty", False, World(), ("Compare them.",), script({"Compare them.": "compare"}),
              (("read", READ, {}),
               ("emptied", ("stage", Edit("set", 0, "surfaces", EMPTY_LIST)), {"accepted": True, "obligations": [ob("Compare them.", "compare", {"surfaces": EMPTY_LIST})]}),
               ("saved", SAVE, {}),
               ("reloaded", RELOAD, {"obligations": [ob("Compare them.", "compare", {"surfaces": EMPTY_LIST})]}))),
          run("earlier_not_local", True, World(), ("I like the page. Compare it, not the mod.",),
              script({"I like the page.": NO_REQUEST, "Compare it, not the mod.": "compare"}, {("Compare it, not the mod.", "compare", "surfaces"): (PAGE,)}),
              (("read", READ, {"obligations": [ob("Compare it, not the mod.", "compare", {"surfaces": (PAGE,)})],
                               "passages": [Passage("I like the page.", "Asked", "user", "context")],
                               "decisions": [Decision(0, "surfaces", "model", (MOD, PAGE), (PAGE,))]}),)),
          run("all_rejected", False, World(), ("Compare the page and the mod.",),
              script({"Compare the page and the mod.": "compare"}, {("Compare the page and the mod.", "compare", "surfaces"): REJECT}),
              (("read", READ, {"obligations": [ob("Compare the page and the mod.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), REJECTED)})],
                               "decisions": [Decision(0, "surfaces", "model", (PAGE, MOD), frozenset({REJECT, ()}))]}),))),
         interpretation="When d1 rejects every candidate of a Many, the result is a rejected hole, not an explicit empty collection (run all_rejected). The hole with no candidate is an automatic decision, recorded. The explicit empty collection comes from an explicit edit; zero members is a valid Many. The hole of an unknown Many may be typed Many[Surface] or Surface, with reason no candidate or rejected (if the engine offers d1 an empty choice). Passage relations are compared only for being present and not none/nothing."),
    Case("C07", "Reshape a Cell, then open that Cell",
         "Reuse the structured result, not a fresh record reconstructed from old fields. Retain pending dependency.",
         "Product synthesis rebuilds Cell from fields (probe product_result_is_reconstructed_from_original_fields).",
         (run("reshape_open", False, World(extra='\ndef reshape_cell(cell: Cell) -> Later[Cell]:\n    "reshape a cell"\n', files=("notes.md",)),
              ("Reshape cell 3 of notes.md. Open that cell.",), told(RESHAPED),
              (("read", READ, {"obligations": RESHAPED,
                               "decisions": [Decision(1, "cell", "model", (Ref(0),), Ref(0))]}),)),)),
    Case("C08", "Redesign page, then request redesigned mod",
         "Preserve/generate redesign(mod); an existing redesign(page) must not suppress it.",
         "derivations() skips a function already present among candidates (probe earlier_application_suppresses_new_application_of_same_function).",
         (run("page_then_mod", False, World(), ("Redesign the page. Show the mod redesigned.",),
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
         (run("chain", False, TOKEN_WORLD,
              ("Make a token for the mod. Use that token.",),
              script({"Make a token for the mod.": "make_token", "Use that token.": "use_token"},
                     {("Make a token for the mod.", "make_token", "surface"): MOD, ("Use that token.", "use_token", "token"): Ref(0)}, refers={0: ("make_token", ("the mod",))}),
              (("read", READ, {"obligations": [ob("Make a token for the mod.", "make_token", {"surface": MOD}), ob("Use that token.", "use_token", {"token": Ref(0)})]}),)),
          run("contrast", True, TOKEN_WORLD,
              ("Use a token.",), script({"Use a token.": "use_token"}, {("Use a token.", "use_token", "token"): REJECT}),
              (("read", READ, {"obligations": [ob("Use a token.", "use_token", {"token": Hole("Token", (NO_CANDIDATE, REJECTED))})]}),))),
         interpretation="The producer takes a Surface rather than words, so the expected bindings do not depend on how a phrase's own words become a value. In the contrast, d1 may or may not be offered New(make_token); either way no make_token obligation exists. The contrast is labelled a control because it is the case's second required behavior."),
    Case("C10", "Pending value nested in Record/Several/Maybe",
         "Recursive dependency inspection still reports pending; no wrapper can manufacture availability.",
         "type_of reports a Record or Several by its declared type, so its consumer is available (probe later_is_lost_through_records_and_collections).",
         tuple(run(label, label == "plain", BOX_WORLD, (" ".join(dict.fromkeys(one.span for one in obligations)),), told(obligations),
                   (("read", READ, {"obligations": obligations}), ("saved", SAVE, {"record": record_spec(obligations)})))
               for label, obligations in (
                   ("record", [REDESIGN_SHOW[0], ob("Pack it in a box.", "pack", {"box.surface": Ref(0)}, PENDING)]),
                   ("several", [REDESIGN_SHOW[0], ob("Compare it with the page.", "compare", {"surfaces": (Ref(0), PAGE)}, PENDING)]),
                   ("maybe", [REDESIGN_SHOW[0], ob("Describe it.", "describe", {"surface": Ref(0)}, PENDING)]),
                   ("through_result", [REDESIGN_SHOW[0], ob("Pack it in a box.", "pack", {"box.surface": Ref(0)}, PENDING), ob("Explain that.", "explain", {"subject": Ref(1)}, PENDING)]),
                   ("plain", [ob("Pack the mod in a box.", "pack", {"box.surface": MOD})])))
         + (run("many_of_records", False, World(extra=BOX_WORLD.extra + BOXES), ("Tag the mod in a box.",), script({"Tag the mod in a box.": "tag"}),
                (("read", READ, {}),
                 ("checked", ("check", "I tagged it.", (), EVIDENCE_CRITERIA), {"verdict": (UNVERIFIED, FAIL)}),
                 ("proposed", ("propose_world", World(extra=BOX_WORLD.extra + BOXES + PAINT_WORLD.extra), script({"Tag the mod in a box.": "tag"})),
                  {"world_change": {"activated": True, "verdict": PASS, "regressions": [], "faults": [], "active_world": World(extra=BOX_WORLD.extra + BOXES + PAINT_WORLD.extra)}}))),),
         interpretation="Run through_result: explain consumes the Written result of a pack that waits on the redesign, so it is pending although no Later appears in its own argument. Run many_of_records only requires that reading, checking and gating a record inside a collection work: no step reports an error."),
    Case("C11", "Invalid union kind, wrong child type, missing/extra argument or field, invalid reference",
         "Validation rejects each precisely. A deliberately typed hole remains a valid partial term.",
         "Kind checking accepts Many | int (probe unapplied_constructor_is_accepted_inside_union); Application and Record take any dict.",
         (run("edits", False, CELL_WORLD, ("Redesign the mod. Open cell 3 of notes.md.",), told(CELL_BASE),
              (("read", READ, {"obligations": CELL_BASE, "decisions": [Decision(1, "cell", "rule")]}),
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
          run("loads", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("saved", SAVE, {}),
               ("load_wrong_type", ("load", "wrong_type"), {"diagnostics": [(0, "surface", "type")], "model_calls": 0}),
               ("load_dangling", ("load", "dangling"), {"diagnostics": [(1, "subject", "reference")], "model_calls": 0}),
               ("load_missing", ("load", "missing"), {"diagnostics": [(0, "surface", "missing")], "model_calls": 0}))),
          run("invalid_kind", False, BROKEN_WORLD, (), script({}), ()),
          run("valid_world", True, World(), (), script({}), ())),
         interpretation="Each preview starts from the reading of step read. A reference to its own obligation is an unsupported cycle. A rejected preview reports the unchanged base as its obligations and exactly the one diagnostic named: a validator that reports extra rules is not precise. A hole is valid only at its own type. The record built from the cell's fields is an automatic decision, recorded. Loading validates too: a saved line with a wrong-type binding, a dangling reference or a missing argument loads with exactly its diagnostic, and the obligation it breaks is reported neither complete nor ready (run loads). A kind fault is reported as kind, never type; edits set values, not types, so only the world reports kinds."),
    Case("C12", "Two legitimate same-signature operations; one-use domain type",
         "Both are allowed. No extra dummy operation or wrapper type is introduced.",
         "agree.duplicates and agree.single_use make these hard faults (test_world_rules asserts them).",
         (run("archive_and_colour", False, World(extra='\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef archive(surface: Surface) -> Later[Surface]:\n    "archive it"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n'),
              ("Archive the page. Redesign the mod.",), told(ARCHIVED), (("read", READ, {"obligations": ARCHIVED}),)),)),
    Case("C13", "Entire message quotes a previous reply",
         "Source is preserved, origin is inspectable and reading does not crash. A quote alone does not fabricate a request.",
         "unfold raises on a same-sized child (probe whole_message_quote_crashes); or a quote becomes a request.",
         (run("whole_quote", False, World(), (QUOTE,), script({}),
              (("read", READ, {"error": None, "obligations": [], "passages": [Passage(QUOTE, "Written", "reply 0", "quote")]}),), replies=(QUOTE,)),
          run("quoted_members", False, World(), (f'"{QUOTED}" Compare them.',), script({"Compare them.": "compare"}),
              (("read", READ, {"obligations": [ob("Compare them.", "compare", {"surfaces": Hole(("Many[Surface]", "Surface"), (NO_CANDIDATE, REJECTED))})],
                               "passages": [Passage(f'"{QUOTED}"', "Written", "reply 0", "quote")]}),), replies=(QUOTED,)),
          run("own_members", True, World(), (f'"{QUOTED}" Compare the page and the mod.',), told([ob("Compare the page and the mod.", "compare", {"surfaces": (PAGE, MOD)})]),
              (("read", READ, {"obligations": [ob("Compare the page and the mod.", "compare", {"surfaces": (PAGE, MOD)})],
                               "passages": [Passage(f'"{QUOTED}"', "Written", "reply 0", "quote")],
                               "decisions": [Decision(0, "surfaces", "model", (PAGE, MOD), (PAGE, MOD))]}),), replies=(QUOTED,)),
          run("quote_and_request", True, World(), (f'"{QUOTE}" Redesign the mod.',), script({"Redesign the mod.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"error": None, "obligations": [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING)],
                               "passages": [Passage(f'"{QUOTE}"', "Written", "reply 0", "quote")]}),), replies=(QUOTE,))),
         interpretation="A quote is a passage of brand Written whose origin names the reply; its relation label is free but present. Its text is compared without the quote marks around it, which the span may or may not include. Member words inside a quoted reply are Written, not the user's Asked words: they ground no Surface and no candidate offered to d1 (run quoted_members); the same words in the user's own sentence do (run own_members)."),
    Case("C14", "Model metadata and world declarations",
         "No name collision can turn an abstention into a function call. Malformed, missing or out-of-set model answers produce diagnostics, not silent acceptance. Enforce configured choice bounds.",
         "A world function named none hijacks abstention (probe reserved_none_function_hijacks_abstention); ask_all indexes answers unchecked; candidates past Limits.offered vanish unrecorded.",
         (run("reserved_name", False, World(extra='\ndef none(rule: Asked) -> Later[Observed]:\n    "a distinct command"\n'), ("Email an accountant.",), script({"Email an accountant.": ABSTAIN}),
              (("read", READ, {"obligations": [ob("Email an accountant.", UNRESOLVED, reason=REJECTED)]}),)),)
         + tuple(run(kind, False, World(), ("Redesign the mod.",), script({"Redesign the mod.": Malformed(kind)}),
                     (("read", READ, {"obligations": [ob("Redesign the mod.", UNRESOLVED, reason=INVALID_ANSWER)], "diagnostics": [(0, None, "model_answer")]}),))
                 for kind in ("out_of_set", "missing", "not_numbers"))
         + (run("bounded", False, World("next"), (BOUNDED_TEXT,), script({BOUNDED_TEXT: "show"}, {(BOUNDED_TEXT, "show", "subject"): REJECT}),
                (("read", READ, {"obligations": [ob(BOUNDED_TEXT, "show", {"subject": Hole("Subject", (REJECTED, BOUNDED))})],
                                 "decisions": [Decision(0, "subject", "model", NINE[:8], REJECT, NINE[8:])]}),)),
            run("too_many_operations", False, World(), ('Redesign the mod, show it, compare it with the page and explain it.',),
                script({'Redesign the mod, show it, compare it with the page and explain it.': ("redesign", "show", "compare", "explain")},
                       {('Redesign the mod, show it, compare it with the page and explain it.', "redesign", "surface"): MOD, ('Redesign the mod, show it, compare it with the page and explain it.', "show", "subject"): Ref(0), ('Redesign the mod, show it, compare it with the page and explain it.', "compare", "surfaces"): (Ref(0), PAGE)},
                       refers={0: ("redesign", ("the mod",))}),
                (("read", READ, {"obligations": [ob(Inside('Redesign the mod, show it, compare it with the page and explain it.'), "redesign", {"surface": MOD}, PENDING), ob(Inside('Redesign the mod, show it, compare it with the page and explain it.'), "show", {"subject": Ref(0)}, PENDING),
                                                 ob(Inside('Redesign the mod, show it, compare it with the page and explain it.'), "compare", {"surfaces": (Ref(0), PAGE)}, PENDING), ob(Inside('Redesign the mod, show it, compare it with the page and explain it.'), UNRESOLVED, reason=BOUNDED)],
                                 "decisions": [Decision(3, None, ("rule", "model"))]}),)),
            run("well_formed", True, World(), ("Redesign the mod.",), told(REDESIGN_SHOW[:1]), (("read", READ, {"obligations": REDESIGN_SHOW[:1]}),))),
         interpretation="A world that declares `none` may either be refused with fault (none, name) or load with the abstention kept apart; either way the request stays one UNRESOLVED obligation (unless the whole world is refused and the read reports an error), and an application of none fails. The bound is Limits.offered = 8 candidates per hole; the excess must be recorded as cut, and offered plus cut must hold all nine named values. The bounded message asks to show one unknown item, so d1's rejection is its meaning; the hole may say rejected or bounded, since d1 never saw the cut candidates. A phrase that asks for more operations than Limits.operations = 3 keeps the extra request as an UNRESOLVED obligation with reason bounded, and records the decision (run too_many_operations)."),
    Case("C15", "“Redesign the mod. Then show it. Test the search too.”",
         "Three obligations; original mod and redesign result are separately selectable; result binding and dependency survive record/reload. Rebinding show to the original does not erase redesign or request it twice.",
         "The saved record duplicates the shared tree (probe in_memory_shared_result_becomes_duplicated_saved_tree); a rebind drops or repeats redesign.",
         (run("specimen", False, World("next"), (SPECIMEN,),
              told(TESTED),
              (("read", READ, {"obligations": TESTED, "decisions": [SHOW_DECISION]}),
               ("saved", SAVE, {"writes": 1, "record": record_spec(TESTED)}),
               ("reloaded", RELOAD, {"obligations": TESTED, "model_calls": 0}),
               ("rebound", ("stage", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": TESTED_REBOUND, "model_calls": 0}),
               ("rebound_saved", SAVE, {"writes": 1}),
               ("rebound_reloaded", RELOAD, {"obligations": TESTED_REBOUND, "model_calls": 0}))),)),
    Case("C16", "Two operations within one source phrase",
         "Preserve both obligations using the smallest valid grouping/term representation; do not silently choose only one or require the user to rewrite punctuation.",
         "choose() selects one function per phrase.",
         (run("conjunction", False, World(), ("Redesign the mod and show it.",),
              script({"Redesign the mod and show it.": ("redesign", "show"), "Redesign the mod": "redesign", "show it.": "show"},
                     {(span, operation, path): value for span in ("Redesign the mod and show it.", "Redesign the mod", "show it.")
                      for operation, path, value in (("redesign", "surface", MOD), ("show", "subject", Ref(0)))}, refers={0: ("redesign", ("the mod",))}),
              (("read", READ, {"obligations": [ob(Inside("Redesign the mod and show it."), "redesign", {"surface": MOD}, PENDING),
                                               ob(Inside("Redesign the mod and show it."), "show", {"subject": Ref(0)}, PENDING)]}),
               ("saved", SAVE, {"record": [("redesign", {}), ("show", {"subject": 0})]}))),
          run("unknown_and_known", False, World(), ('Frobnicate the widget and redesign the mod.',),
              script({'Frobnicate the widget and redesign the mod.': (ABSTAIN, "redesign"), "Frobnicate the widget": ABSTAIN, "redesign the mod.": "redesign"},
                     {('Frobnicate the widget and redesign the mod.', "redesign", "surface"): MOD, ("redesign the mod.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob(Inside('Frobnicate the widget and redesign the mod.'), UNRESOLVED, reason=REJECTED), ob(Inside('Frobnicate the widget and redesign the mod.'), "redesign", {"surface": MOD}, PENDING)]}),)),
          run("compare_conjunction", True, World(), ("Compare the page and the mod.",), told([ob("Compare the page and the mod.", "compare", {"surfaces": (PAGE, MOD)})]),
              (("read", READ, {"obligations": [ob(Inside("Compare the page and the mod."), "compare", {"surfaces": (PAGE, MOD)})]}),)),
          run("nested", True, World(), ("Show me the mod, redesigned.",),
              script({"Show me the mod, redesigned.": "show"},
                     {("Show me the mod, redesigned.", "show", "subject"): New("redesign"), ("Show me the mod, redesigned.", "redesign", "surface"): MOD}),
              (("read", READ, {"obligations": [ob(Inside("Show me the mod, redesigned."), "redesign", {"surface": MOD}, PENDING),
                                               ob(Inside("Show me the mod, redesigned."), "show", {"subject": Ref(0)}, PENDING)]}),))),
         interpretation="Both obligations must exist; each span is the phrase or a part of it, so the two may share the phrase or split it (E20). A split must still cover every word, the conjunction included, in some span or passage (I1). The stand-in names both operations of the phrase and each operation of its parts; how the engine asks for a second operation is the implementer's choice. Splitting is not splitting every 'and': 'Compare the page and the mod.' stays one compare of both (E33). An unknown operation beside a known one keeps both: UNRESOLVED, then redesign, in the order asked (run unknown_and_known).",
         real_d1="Whether real d1 finds both operations in one sentence is effectiveness, unverified here."),
    Case("C17", "Two identical-looking requested operations versus two references to one result",
         "Preserve the distinction across serialization. Display equality must not merge them.",
         "derivations() deduplicates by say() text; serialization copies trees.",
         tuple(run(label, False, World(), (text,), told(obligations),
                   (("read", READ, {"obligations": obligations}), ("saved", SAVE, {"record": record_spec(obligations)}), ("reloaded", RELOAD, {"obligations": obligations})))
               for label, text, obligations in (
                   ("identical_operations", "Redesign the mod. Redesign the mod again.",
                    [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Redesign the mod again.", "redesign", {"surface": MOD}, PENDING)]),
                   ("shared_result", "Redesign the mod. Show it. Compare it with the page.",
                    [ob("Redesign the mod.", "redesign", {"surface": MOD}, PENDING), ob("Show it.", "show", {"subject": Ref(0)}, PENDING),
                     ob("Compare it with the page.", "compare", {"surfaces": (Ref(0), PAGE)}, PENDING)]))),
         interpretation="In the neutral form, two operation instances are two obligations and one result is one Ref index; the distinction is structural, so the predicate compares counts and Ref targets after reload. The stand-in scripts the choice of the original mod for 'again', so the case tests identity, not the reading of 'again'."),
    Case("C18", "Preview invalid edit, cancel valid preview, stage/save/reload, failed save, restore previous snapshot",
         "Exact expected identities/bindings are preserved at each transition; previews perform no work. Use a tiny local persistence boundary and failure injection.",
         "No preview/cancel/stage/save boundary exists in next; a failed save loses the draft; cancel keeps the preview.",
         (run("transitions", False, World("next"), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
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
         (run("rerun", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": REBOUND}),
               ("saved", SAVE, {}),
               ("rerun", ("rerun",), {"obligations": REBOUND, "corrections": [Correction(1, "subject", MOD, RETAINED)]}))),
          run("world_change", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", World(replace=(('    MOD: Asked = "the mod"\n', ""),))),
                {"obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", (REJECTED, NO_CANDIDATE, INVALID_ANSWER))}, PENDING),
                                 ob("Then show it.", "show", {"subject": frozenset({Ref(0), Hole("Subject", (REJECTED, NO_CANDIDATE, CLEARED, INVALID_ANSWER))})}, (PENDING, AVAILABLE), complete=False)],
                 "corrections": [Correction(1, "subject", MOD, INVALIDATED, "subject: the mod is no member of Surface")]}))),
          run("unrelated_change", True, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", PAINT_WORLD),
                {"obligations": REBOUND, "corrections": [Correction(1, "subject", MOD, RETAINED)]}))),
          run("function_changed", False, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", World(replace=(("def show(", "def present("),))),
                {"obligations": [REDESIGN_SHOW[0], ob("Then show it.", "present", {"subject": Hole("Subject", (REJECTED, NO_CANDIDATE, CLEARED, INVALID_ANSWER))})],
                 "corrections": [Correction(1, "subject", MOD, INVALIDATED, "show became present, so the correction of subject no longer applies")]}))),
          run("reference_target_changed", False, World(), ("Redesign the mod. Then show it.",), told(REBOUND),
              (("read", READ, {"obligations": REBOUND}),
               ("corrected", ("correct", Edit("set", 1, "subject", Ref(0))), {"accepted": True, "obligations": REDESIGN_SHOW}),
               ("saved", SAVE, {}),
               ("changed", ("change_world", World(replace=(('    MOD: Asked = "the mod"\n', ""),))),
                {"obligations": [ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", (REJECTED, NO_CANDIDATE, INVALID_ANSWER))}, PENDING),
                                 ob("Then show it.", "show", {"subject": Hole("Subject", (REJECTED, NO_CANDIDATE, CLEARED, INVALID_ANSWER))})],
                 "corrections": [Correction(1, "subject", Ref(0), INVALIDATED, "subject referred to redesign, whose surface changed")]}))),
          run("edit_after_correction", True, World(), ("Redesign the mod. Then show it.",), told(REDESIGN_SHOW),
              (("read", READ, {"obligations": REDESIGN_SHOW}),
               ("corrected", ("correct", Edit("set", 1, "subject", MOD)), {"accepted": True, "obligations": REBOUND}),
               ("edited", ("stage", Edit("clear", 1, "subject")), {"accepted": True, "obligations": CLEARED_SHOW}),
               ("saved", SAVE, {}),
               ("rerun", ("rerun",), {"obligations": CLEARED_SHOW, "corrections": [Correction(1, "subject", Hole("Subject", CLEARED), RETAINED)]})))),
         interpretation="The invalidating world change removes the member that the correction names; the predicate requires status invalidated, a non-empty reason, both obligations still present, and that the invalid value is no longer bound. Show may then hold the model's Ref(0) or a hole: with the invalidation reported, neither is silent. A reason must name its cause: the operation or the path (E44). A correction is also invalidated when its operation's function changes (run function_changed), and a correction that names an earlier result is invalidated, not re-pointed, when that result's meaning changes (run reference_target_changed). A later edit at the same place replaces the correction, and a rerun keeps it (run edit_after_correction)."),
    Case("C20", "“Redesign mod. Redesign page,” reply/evidence for mod only",
         "Mod and page get separate criterion outcomes. The page obligation cannot pass from the mod's evidence. Explicit refusal is not PROMISED.",
         "check() asks the same argument-blind question twice (probe argument_blind_duplicate_checks); Later makes a refusal PROMISED (probe refusal_becomes_promised).",
         tuple(run(label, label == "both", world, ("Redesign the mod. Redesign the page.",),
                   script({"Redesign the mod.": "redesign", "Redesign the page.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): MOD, ("Redesign the page.", "redesign", "surface"): PAGE}, judge),
                   (("read", READ, {"obligations": REDESIGN_TWO if world == World() else [dataclasses.replace(one, status=AVAILABLE, ready=one.complete) for one in REDESIGN_TWO]}),
                    ("checked", ("check", reply, artifacts, EVIDENCE_CRITERIA), {"checks": checks, "verdict": verdict})))
               for label, world, reply, judge, artifacts, checks, verdict in (
                   ("mod_only", World(), "I redesigned the mod.", 0.99, (worked("redesign", {"surface": MOD}),),
                    [Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", (UNVERIFIED, FAIL))], (UNVERIFIED, FAIL)),
                   ("refusal", World(), "I cannot redesign either of them.", 0.01, (),
                    [Check(0, None, "evidence", (FAIL, UNVERIFIED)), Check(1, None, "evidence", (FAIL, UNVERIFIED))], (FAIL, UNVERIFIED)),
                   ("later_removed", World(replace=(("-> Later[Surface]:", "-> Surface:"),)), "I redesigned the mod and the page.", 0.99, (),
                    [Check(0, None, "evidence", (UNVERIFIED, FAIL)), Check(1, None, "evidence", (UNVERIFIED, FAIL))], (UNVERIFIED, FAIL)),
                   ("relabelled", World(replace=(("-> Later[Surface]:", "-> Observed:"),), extra='\nProof = typing.NewType("Proof", Words)\n'), "I redesigned the mod and the page.", 0.99,
                    (Artifact("redesign", {"surface": MOD}, Lit("Observed", "I redesigned the mod.")), Artifact("redesign", {"surface": PAGE}, Lit("Proof", "I redesigned the page."))),
                    [Check(0, None, "evidence", (UNVERIFIED, FAIL)), Check(1, None, "evidence", (UNVERIFIED, FAIL))], (UNVERIFIED, FAIL)),
                   ("both", World(), "I redesigned the mod and the page.", 0.99, (worked("redesign", {"surface": MOD}), worked("redesign", {"surface": PAGE})),
                    [Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", PASS, 1)], PASS))),
         interpretation="A reply's claim and d1's yes share are not evidence, so a reply alone never passes; an obligation with no evidence may be UNVERIFIED or FAIL. A refusal may be FAIL or UNVERIFIED; the outcome vocabulary has no PROMISED. Run later_removed makes redesign return Surface: its obligations become available, and still nothing passes without evidence (I6). Run relabelled makes redesign return Observed and supplies artifacts that are the reply's words labelled Observed and a newly declared brand Proof, with no behaviour check: words of any type are no evidence, and an artifact's operation and arguments alone show no work (E29).",
         real_d1="Judging refusal prose with real d1 is unverified; the stand-in answers 0.99 and 0.01."),
    Case("C21", "Type-correct but wrong computation",
         "A tiny test-only pure function returns the right type but the wrong known result. Its independent behavioral criterion fails while its type check still passes. Keep this fixture out of the production world; do not invent a verify operation.",
         "A type check is reported as fulfillment.",
         tuple(run(label, control, DOUBLE_WORLD, ("Double 3.",), told([DOUBLED]),
                   (("read", READ, {"obligations": [DOUBLED]}),
                    ("checked", ("check", "Done.", (Artifact("double", {"number": THREE}, fixture(3), probed(fixture, 3, 6)),), DOUBLE_CRITERIA),
                     {"checks": [Check(0, None, "type", PASS, 0), Check(0, None, "behavior", behavior, 0)], "verdict": behavior})))
               for label, control, fixture, behavior in (("wrong", False, wrong_double, FAIL), ("right", True, right_double, PASS))),
         interpretation="The test-only fixture runs here on the known input 3, expecting 6, and the probe records what it returned; no product executor runs. The predicate also requires that next/world.py declares neither double nor verify, read from the file itself, not from the observation."),
    Case("C22", "Saved decision and semantic edits",
         "Reload recovers typed literal values, shared references, explicit unresolved state and exact model decision context without a model call. Cosmetic rendering changes do not change meaning.",
         "record() saves only keys and scores, drops Constant.value and copies shared trees (probes saved_decisions_drop_full_request_context, in_memory_shared_result_becomes_duplicated_saved_tree).",
         (run("saved_reading", False, World("next"), ("Redesign the mod. Then show it. Email my accountant.",),
              told(REDESIGN_SHOW + [EMAIL]),
              (("read", READ, {"obligations": REDESIGN_SHOW + [EMAIL]}),
               ("edited", ("stage", Edit("set", 0, "surface", Lit("Surface", "the page"))), {"accepted": True}),
               ("saved", SAVE, {"writes": 1}),
               ("reloaded", RELOAD, {"model_calls": 0}),
               ("restyled", ("restyle",), {"model_calls": 0}),
               ("other_world", ("reload", PAINT_WORLD), {"diagnostics": [(None, None, "identity")], "model_calls": 0}))),),
         interpretation="The predicate compares the reloaded and restyled steps with the edited step, field by field, including every decision's state, instructions, offered, chosen and scores; it requires state, instructions and scores for model decisions, the phrase in the state, and d1's own choice of the mod kept beside the edit to the page. Loading the saved reading under another world reports the mismatch (the brief's state machine). The restyle changes the renderer that the display uses, so its rendered text must differ from the reload's while the meaning stays (E50)."),
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
        inside = isinstance(want.span, Inside) and plain(got.span) and plain(got.span) in plain(want.span.phrase)
        if not inside and plain(want.span) != plain(got.span):
            found.append(f"{where}: obligation {index} span: expected {want.span!r}, observed {got.span!r}")
        for field in ("operation", "brand", "status", "reason", "complete", "ready"):
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
    earlier obligation, a complete or ready claim that the bindings contradict,
    a passage with no relationship, and (for the reading of one message) a
    span that is not the source at its place or a source character that no
    obligation or passage covers.
    """
    found: list[str] = []
    obligations = step.get("obligations") or []
    for index, one in enumerate(obligations):
        if one.operation in ("none", "nothing"):
            found.append(f"{where}: obligation {index} has the terminal answer {one.operation!r}; it must be UNRESOLVED")
        if one.operation == UNRESOLVED and one.bindings:
            found.append(f"{where}: unresolved obligation {index} has a guessed goal: {one.bindings}")
        incomplete = [value for value in values_of(one.bindings) if isinstance(value, Hole)
                      or (isinstance(value, Ref) and 0 <= value.obligation < index and obligations[value.obligation].complete is not True)]
        if one.operation == UNRESOLVED and (one.complete is not None or one.ready):
            found.append(f"{where}: unresolved obligation {index} reported complete={one.complete} ready={one.ready}")
        elif one.complete and incomplete:
            found.append(f"{where}: obligation {index} reported complete with an incomplete input {incomplete}")
        if one.ready and not (one.complete is True and not incomplete and one.status == AVAILABLE):
            found.append(f"{where}: obligation {index} reported ready although it is {'incomplete' if incomplete or not one.complete else one.status}")
        for value in values_of(one.bindings):
            if isinstance(value, Hole) and value.type in ("Any", "Unknown", "", None):
                found.append(f"{where}: obligation {index} has an untyped hole {value!r}")
            if isinstance(value, Ref) and not 0 <= value.obligation < index:
                found.append(f"{where}: obligation {index} refers to obligation {value.obligation}, which is not an earlier obligation")
    for passage in step.get("passages") or []:
        if plain(passage.relation).lower() in ("", "none", "nothing"):
            found.append(f"{where}: passage {passage.text!r} has no relationship (relation {passage.relation!r})")
    if message is None or step.get("obligations") is None:
        return found
    covered: set[int] = set()
    for text, at in [(one.span, one.at) for one in obligations] + [(one.text, one.at) for one in step.get("passages") or []]:
        if not (isinstance(at, tuple) and len(at) == 2 and 0 <= at[0] < at[1] <= len(message)):
            found.append(f"{where}: {text!r} has no place in the message (at {at!r})")
        elif plain(message[at[0]:at[1]]) != plain(text):
            found.append(f"{where}: {text!r} is not the source at {at}: {message[at[0]:at[1]]!r}")
        else:
            covered.update(range(*at))
    lost = [index for index, character in enumerate(message) if not character.isspace() and index not in covered]
    if lost:
        found.append(f"{where}: source characters in no obligation or passage, from {lost[0]}: {''.join(message[index] for index in lost)!r}")
    starts = [one.at[0] for one in obligations if isinstance(one.at, tuple)]
    if starts != sorted(starts):
        found.append(f"{where}: obligations out of source order: {starts}")
    return found


def checks_diagnostics(where: str, expected: list, observed: list, obligations: list) -> list[str]:
    """Compares checks by (obligation, item, criterion): exactly the expected ones, once each, and one for every obligation."""
    found: list[str] = []
    key = lambda one: (one.obligation, repr(one.item), one.criterion)
    keys = [key(one) for one in observed]
    found += [f"{where}: duplicate check {one}" for one in sorted({one for one in keys if keys.count(one) > 1})]
    wanted = [key(one) for one in expected]
    found += [f"{where}: unexpected check {one}" for one in keys if one not in wanted]
    for want in expected:
        got = [one for one in observed if key(one) == key(want)]
        if not got:
            found.append(f"{where}: no {want.criterion!r} check for obligation {want.obligation}")
        for one in got:
            if one.outcome not in acceptable(want.outcome) or (want.evidence is not None and one.evidence != want.evidence):
                found.append(f"{where}: obligation {want.obligation} {want.criterion!r}: expected {want.outcome} by artifact {want.evidence}, observed {one.outcome} by artifact {one.evidence}")
    unchecked = sorted(set(range(len(obligations))) - {one.obligation for one in observed})
    if unchecked:
        found.append(f"{where}: obligations {unchecked} have no check")
    found += [f"{where}: obligation {one.obligation} fulfilled while incomplete" for one in observed
              if one.outcome == PASS and one.obligation < len(obligations) and obligations[one.obligation].complete is not True]
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
    """Compares every expected key of every step of the case's runs, the forbidden answers and the decision inventory.

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
        for label, action, expected in steps_of(run):
            where = f"{case.id} {run.label}/{label}"
            step = observation.get("steps", {}).get(label)
            if step is None:
                found.append(f"{where}: no step")
                continue
            if step.get("error") and "error" not in expected:
                found.append(f"{where}: error {step['error']}")
            found += forbidden_diagnostics(where, step, run.messages[0] if action == READ and len(run.messages) == 1 else None)
            if "decisions" in step:
                found += inventory_diagnostics(where, observation, label) + absence_diagnostics(where, step)
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
                    found += world_change_diagnostics(where, want, got, action[1])
                elif key == "record":
                    found += record_diagnostics(where, got, want)
                elif key in ("decisions", "corrections"):
                    continue  # compared by asked_diagnostics and the case's own predicate
                elif got != want:
                    found.append(f"{where}: {key} expected {want!r}, observed {got!r}")
    return found


def world_change_diagnostics(where: str, want: dict, got: dict | None, proposal: World) -> list[str]:
    """Compares a world change; a rejected one returns the proposal from the inputs intact, and the active world keeps every declaration."""
    if got is None or (got["activated"], sorted(got["regressions"])) != (want["activated"], sorted(want["regressions"])) or got["verdict"] not in acceptable(want["verdict"]):
        return [f"{where}: world change expected {want}, observed {got}"]
    found = []
    if not want["activated"] and got.get("draft") != world_source(proposal):
        found.append(f"{where}: the rejected draft is not the proposal returned intact")
    if declarations(got.get("active_world") or "") != declarations(world_source(want["active_world"])):
        found.append(f"{where}: the active world's declarations are not those of {want['active_world']}")
    if [one for one in want.get("faults", []) if one not in got.get("faults", [])]:
        found.append(f"{where}: the rejection does not report the faults {want['faults']}, observed {got.get('faults')}")
    return found


def inventory_diagnostics(where: str, observation: dict, label: str) -> list[str]:
    """The model decisions of a step are exactly the questions that the stand-in received in the latest step that asked any."""
    requests: list = []
    for name, step in observation.get("steps", {}).items():
        requests = step.get("requests") or requests
        if name == label:
            break
    decisions = observation["steps"][label]["decisions"]
    asked = collections.Counter((one.state, one.instructions, tuple(one.options)) for one in requests)
    saved = collections.Counter((one.state, instructions, tuple(options)) for one in decisions if one.by == "model" for instructions, options in one.questions)
    found = [f"{where}: decision by rule names no declared rule: {one}" for one in decisions if one.by == "rule" and not one.rule]
    found += [f"{where}: the chosen candidate was not offered: {one}" for one in decisions if one.by == "model" and one.chosen not in (REJECT, ABSENT, INVALID, ABSTAIN, NO_REQUEST)
              and not all(member in one.offered for member in (one.chosen if isinstance(one.chosen, tuple) else (one.chosen,)))]
    if asked != saved:
        found.append(f"{where}: decisions differ from the requests d1 received: missing {list((asked - saved).elements())}, not asked {list((saved - asked).elements())}")
    return found


def absence_diagnostics(where: str, step: dict) -> list[str]:
    """Empty only by a recorded absence decision; a rejected or invalid answer of d1 leaves a hole."""
    decided = {(one.obligation, one.path): one for one in step["decisions"]}
    found = []
    for index, one in enumerate(step.get("obligations", [])):
        for path, value in one.bindings.items():
            decision = decided.get((index, path))
            if (value == EMPTY) != (decision is not None and decision.chosen == ABSENT):
                found.append(f"{where}: obligation {index} {path} is {value!r} with decision {decision}: Empty exactly when absence was decided")
            if decision is not None and decision.by == "model" and decision.chosen in (REJECT, INVALID, ()) and not isinstance(value, Hole):
                found.append(f"{where}: obligation {index} {path} is bound to {value!r} although d1's answer was {decision.chosen}")
    return found


def record_diagnostics(where: str, record, spec: list) -> list[str]:
    """Checks a saved record against the shape of RECORD and against the applications and references it must hold."""
    if not (isinstance(record, dict) and isinstance(record.get("phrases"), list) and isinstance(record.get("decisions"), list)):
        return [f"{where}: the record has no phrases and decisions lists: {str(record)[:120]}"]
    found, applications, references = [], [], []

    def value(item, owner: int, path: str) -> None:
        if not isinstance(item, dict):
            found.append(f"{where}: record value at {path} is not an object: {item!r}")
        elif "ref" in item:
            references.append((owner, path, item["ref"]))
        elif "several" in item:
            for member in item["several"]:
                value(member, owner, path + "[]")
        elif "fields" in item:
            for name, member in item["fields"].items():
                value(member, owner, f"{path}.{name}")
        elif "function" in item:
            application(item)
        elif not ({"constant", "type"} <= item.keys() or "empty" in item or {"hole", "reason"} <= item.keys()):
            found.append(f"{where}: record value at {path} has no documented form: {item!r}")

    def application(item) -> None:
        if not (isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("function"), str) and isinstance(item.get("arguments"), dict)):
            found.append(f"{where}: record application without id, function and arguments: {str(item)[:120]}")
            return
        applications.append(item)
        for name, argument in item["arguments"].items():
            value(argument, len(applications) - 1, name)

    for phrase in record["phrases"]:
        if not (isinstance(phrase, dict) and isinstance(phrase.get("start"), int) and isinstance(phrase.get("end"), int) and "brand" in phrase and isinstance(phrase.get("terms"), list)):
            found.append(f"{where}: record phrase without start, end, brand and terms: {str(phrase)[:120]}")
            continue
        for term in phrase["terms"]:
            application(term)
    found += [f"{where}: record decision without a path: {str(one)[:120]}" for one in record["decisions"] if not (isinstance(one, dict) and "path" in one)]
    ids = [one["id"] for one in applications]
    if len(set(ids)) != len(ids):
        found.append(f"{where}: record ids are not unique: {ids}")
    if [one["function"] for one in applications] != [function for function, _ in spec]:
        found.append(f"{where}: record applications {[one['function'] for one in applications]}, expected {[function for function, _ in spec]}")
        return found
    for owner, path, target in references:
        if target not in ids:
            found.append(f"{where}: record reference at {path} names no application: {target!r}")
    for index, (_, refs) in enumerate(spec):
        held = {path: ids.index(target) for owner, path, target in references if owner == index and target in ids}
        if held != refs:
            found.append(f"{where}: record application {index} references {held}, expected {refs}")
    return found


def decision_for(observation: dict, step: str, obligation: int, path: str | None) -> Decision | None:
    """Returns the recorded decision about one obligation and path at a step."""
    return next((one for one in observation.get("steps", {}).get(step, {}).get("decisions", []) if (one.obligation, one.path) == (obligation, path)), None)


def asked_diagnostics(case: Case, observed: dict, labels: tuple = ()) -> list[str]:
    """Requires each expected decision of the case: by whom, with its candidates, choice and context.

    A decision by d1 keeps its questions and a state that holds the phrase; a decision by rule names its rule.
    """
    found: list[str] = []
    for run in case.runs:
        if labels and run.label not in labels:
            continue
        observation = observed.get(run.label, {})
        for label, _, expected in steps_of(run):
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
                if want.chosen is not None and not value_fits(want.chosen, got.chosen):
                    found.append(f"{where}: the choice is recorded as {got.chosen!r}, expected {want.chosen!r}")
                obligations = observation.get("steps", {}).get(label, {}).get("obligations") or previous_obligations(observation, label)
                span = obligations[want.obligation].span if want.obligation < len(obligations) else ""
                if got.by == "model" and not (got.questions and plain(span) in plain(got.state)):
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
    """The malformed world is refused for its kind, the valid one is not, and a broken saved line loads with the obligation it breaks neither complete nor ready."""
    found = []
    if ("Broken", "kind") not in observed.get("invalid_kind", {}).get("world_faults", []):
        found.append(f"C11 invalid_kind: expected world fault ('Broken', 'kind'), observed {observed.get('invalid_kind', {}).get('world_faults')}")
    if observed.get("valid_world", {}).get("world_faults"):
        found.append(f"C11 valid_world: unexpected faults {observed['valid_world']['world_faults']}")
    for label, _, want in steps_of(CASE["C11"].runs[1]):
        if label.startswith("load_"):
            obligations = observed.get("loads", {}).get("steps", {}).get(label, {}).get("obligations")
            index = want["diagnostics"][0][0]
            if not obligations or index >= len(obligations):
                found.append(f"C11 loads/{label}: the loaded reading reports no obligation {index}")
            elif obligations[index].complete is True or obligations[index].ready is True:
                found.append(f"C11 loads/{label}: the broken obligation {index} is reported complete={obligations[index].complete} ready={obligations[index].ready}")
    return found


def c12(observed: dict) -> list[str]:
    """Same signature and one use are no faults, and no declaration is added."""
    run, functions = observed.get("archive_and_colour", {}), sorted(TEST_FUNCTIONS + ["archive", "tint"])
    found = [f"C12: same signature or one use reported as faults: {run['world_faults']}"] if run.get("world_faults") else []
    if run.get("world_functions") != functions:
        found.append(f"C12: functions expected {functions}, observed {run.get('world_functions')}")
    return found


def c13(observed: dict) -> list[str]:
    """Member words inside a quoted reply ground no candidate."""
    read = observed.get("quoted_members", {}).get("steps", {}).get("read", {})
    return [f"C13 quoted_members/read: a member of the quote was offered as the user's value: {one}" for one in read.get("decisions", [])
            if one.obligation == 0 and {PAGE, MOD} & set(one.offered)]


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
    """A correction is retained, replaced by a later edit, or invalidated with a reason that names its cause; never silently replaced or re-pointed."""
    found = []
    for run in CASE["C19"].runs:
        label, _, want = list(steps_of(run))[-1]
        step = observed.get(run.label, {}).get("steps", {}).get(label, {})
        for expected in want.get("corrections", []):
            where = f"C19 {run.label}/{label} correction of {expected.obligation}.{expected.path}"
            got = [one for one in step.get("corrections", []) if (one.obligation, one.path) == (expected.obligation, expected.path)]
            if len(got) != 1:
                found.append(f"{where}: expected one correction there, observed {got}")
                continue
            got = got[0]
            if got.status != expected.status or not value_fits(expected.value, got.value):
                found.append(f"{where}: expected {expected.status} {expected.value!r}, observed {got.status} {got.value!r}")
            if expected.status != INVALIDATED:
                continue
            obligations = step.get("obligations", [])
            names = {expected.path, expected.path.split(".")[-1], *(one.operation for one in obligations), *(one.operation for one in run.expect[run.actions[0][0]].get("obligations", []))}
            reason = plain(got.reason).lower()
            if reason in ("", "none", "nothing"):
                found.append(f"{where}: invalidated with no reason")
            elif not any(name.lower() in reason for name in names if name and name != UNRESOLVED):
                found.append(f"{where}: the reason {got.reason!r} names neither the operation nor the path")
            if expected.obligation < len(obligations) and obligations[expected.obligation].bindings.get(expected.path) == expected.value:
                found.append(f"{where}: an invalidated correction is still bound")
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
                  for one in step.get("decisions", []) if one.by == "model" and not (one.state and one.questions and one.scores)]
        if label == "restyled" and not (step.get("rendered") and steps.get("reloaded", {}).get("rendered") and step["rendered"] != steps["reloaded"]["rendered"]):
            found.append("C22 restyled: the restyle did not change the rendered reading, so it changed nothing the display uses")
        original = decision_for(observed.get("saved_reading", {}), label, 0, "surface")
        if original is None or (original.by, original.chosen) != ("model", MOD):
            found.append(f"C22 {label}: d1's own choice of the mod is not kept beside the edit (decision {original})")
    return found


EXTRA = {"C01": c01, "C09": c09, "C13": c13, "C11": c11, "C12": c12, "C14": c14, "C18": c18, "C19": c19, "C21": c21, "C22": c22}
STEP_LABELS = {"C11": ("edits", "loads"), "C14": ("out_of_set", "missing", "not_numbers", "bounded", "too_many_operations", "well_formed")}


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
    + [{"id": key, "kind": "record", "source": "the coordinator's message of 10 Nov", "words": words, "checked_by": ", ".join(cases)} for key, (words, cases) in RECORD.items()]
    + [{"id": key, "kind": "process", "source": f"{BRIEF} § {section}", "words": words, "checked_by": checked[0] if checked else "the final report"} for key, (section, words, *checked) in PROCESS.items()]
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
    decision by d1 gets the phrase as its state, a question and its share, and
    the step that asks gets the matching requests.
    """
    message = run.messages[0] if len(run.messages) == 1 else None
    steps, latest = {}, []
    for label, action, expected in steps_of(run):
        latest = [concrete(one, message) for one in expected["obligations"]] if "obligations" in expected else latest
        step = dict(expected) | ({"obligations": latest} if "obligations" in expected else {})
        if "passages" in expected:
            step["passages"] = [dataclasses.replace(one, at=place(one.text, message)) for one in expected["passages"]]
        if "verdict" in expected:
            step["verdict"] = acceptable(expected["verdict"])[0]
        if "checks" in expected:
            step["checks"] = [dataclasses.replace(one, outcome=acceptable(one.outcome)[0]) for one in expected["checks"]]
        if "decisions" in expected:
            step["decisions"] = [with_context(one, latest) for one in expected["decisions"]]
        if "world_change" in expected:
            change = expected["world_change"]
            step["world_change"] = change | {"verdict": acceptable(change["verdict"])[0], "draft": world_source(action[1]), "active_world": world_source(change["active_world"])}
        if "record" in expected:
            step["record"] = record_of(expected["record"])
        steps[label] = step
    observation = {"world_faults": [("Broken", "kind")] if run.label == "invalid_kind" else [],
                   "world_functions": sorted(TEST_FUNCTIONS + ["archive", "tint"]) if case.id == "C12" else [], "steps": steps}
    if case.id == "C22":
        decisions = [with_context(Decision(index, None, "model", ("redesign", "show", ABSTAIN, NO_REQUEST), choice), EDITED) for index, choice in enumerate(("redesign", "show", ABSTAIN))]
        decisions += [with_context(Decision(0, "surface", "model", (MOD,), MOD), EDITED), with_context(SHOW_DECISION, EDITED)]
        for label in ("read", "edited", "reloaded", "restyled"):
            steps[label] |= {"decisions": decisions} | ({} if label == "read" else {"obligations": [concrete(one) for one in EDITED]})
    if case.id == "C22":
        steps["reloaded"]["rendered"], steps["restyled"]["rendered"] = "redesign(surface='the page')", "redesign ← surface: the page"
    for label, action, expected in steps_of(run):
        if action[0] == "load":
            broken = expected["diagnostics"][0][0]
            steps[label]["obligations"] = [dataclasses.replace(one, complete=False, ready=False) if index == broken or Ref(broken) in values_of(one.bindings) else one
                                           for index, one in enumerate(concrete(one) for one in REDESIGN_SHOW)]
        if action[0] in ("read", "rerun", "change_world") and steps[label].get("decisions"):
            steps[label]["requests"] = [Request(one.state, instructions, options) for one in steps[label]["decisions"] if one.by == "model" for instructions, options in one.questions]
    return observation


def place(text: str, message: str | None) -> tuple | None:
    """Returns the place of a text in the message, or None for a run of several messages."""
    start = message.find(text) if message is not None else -1
    return (start, start + len(text)) if start >= 0 else None


def record_of(spec: list) -> dict:
    """Returns a saved record of the documented shape that holds the applications and references of a spec."""
    def argument(path: str, target: int) -> tuple:
        ref = {"ref": f"t{target}"}
        if path.endswith("[]"):
            return path[:-2], {"several": [ref, {"constant": "the page", "type": "Surface"}]}
        if "." in path:
            name, field = path.split(".", 1)
            return name, {"fields": {field: ref}, "type": "Record"}
        return path, ref
    terms = [{"id": f"t{index}", "function": function, "arguments": dict(argument(path, target) for path, target in refs.items())} for index, (function, refs) in enumerate(spec)]
    return {"phrases": [{"start": 0, "end": 1, "brand": "Asked", "terms": terms}], "decisions": [{"path": None, "term": "t0", "by": "model"}]}


def with_context(decision: Decision, obligations: list) -> Decision:
    """Returns a decision with one acceptable decider and choice, and the context that decider leaves."""
    by, chosen = acceptable(decision.by)[0], decision.chosen
    chosen = min(chosen, key=repr) if isinstance(chosen, frozenset) else chosen
    if by == "rule":
        return dataclasses.replace(decision, by=by, chosen=chosen, rule=decision.rule or "absence when nothing is in scope")
    question = ("Which of these does the text mean?", tuple(map(repr, decision.offered)) + ("none of these",))
    return dataclasses.replace(decision, by=by, chosen=chosen, state=decision.state or obligations[decision.obligation].span,
                               questions=decision.questions or (question,), scores=decision.scores or ((chosen, 0.9),))


def concrete(obligation: Obligation, message: str | None = None) -> Obligation:
    """Returns an obligation with one acceptable answer where the expected one allows several, placed in the message."""
    def one(value):
        if isinstance(value, frozenset):
            return one(min(value, key=repr))
        if isinstance(value, Hole):
            return Hole(acceptable(value.type)[0], acceptable(value.reason)[0])
        return value
    span = obligation.span.phrase if isinstance(obligation.span, Inside) else obligation.span
    return dataclasses.replace(obligation, span=span, bindings={path: one(value) for path, value in obligation.bindings.items()}, at=place(span, message),
                               reason=acceptable(obligation.reason)[0] if obligation.reason else None,
                               status=acceptable(obligation.status)[0] if obligation.status else None,
                               complete=acceptable(obligation.complete)[0] if isinstance(obligation.complete, tuple) else obligation.complete,
                               ready=acceptable(obligation.ready)[0] if isinstance(obligation.ready, tuple) else obligation.ready)


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


def changed_change(observation: dict, run: str, **keys) -> dict:
    """Returns the observation with keys of the world change of a run's proposed step replaced."""
    return changed(observation, run, "proposed", world_change=observation[run]["steps"]["proposed"]["world_change"] | keys)


def split(observation: dict, first: str, second: str) -> list:
    """Returns the conjunction's obligations with the phrase split into two spans, placed in the message."""
    obligations = observation["conjunction"]["steps"]["read"]["obligations"]
    message = "Redesign the mod and show it."
    return [dataclasses.replace(obligations[0], span=first, at=place(first, message)), dataclasses.replace(obligations[1], span=second, at=place(second, message, ))]


# Right projections that differ from EXPECTED in a way the brief allows: each must pass.
RIGHT_ALTERNATIVES = (
    ("C16r", "the phrase split at 'and', every word kept", "C16", lambda e: changed(e, "conjunction", "read", obligations=split(e, "Redesign the mod and", "show it."))),
    ("C16s", "the phrase split after 'and'", "C16", lambda e: changed(e, "conjunction", "read", obligations=split(e, "Redesign the mod", "and show it."))),
    ("C13r", "the quote's text without its quote marks, placed on the marks too", "C13",
     lambda e: changed(e, "quote_and_request", "read", passages=[Passage(QUOTE, "Written", "reply 0", "quote", place(f'"{QUOTE}"', f'"{QUOTE}" Redesign the mod.'))])),
    ("C05r", "absence with nothing in scope decided by a named declared rule", "C05",
     lambda e: changed(e, "nothing_in_scope", "read", decisions=[Decision(0, "subject", "rule", (), ABSENT, rule="absence when nothing is in scope")], requests=[])),
    ("C05s", "absence rejected by d1 with nothing in scope: a hole", "C05",
     lambda e: changed(changed_ob(e, "nothing_in_scope_rejected", "read", 0, bindings={"subject": Hole("Maybe[Surface]", NO_CANDIDATE)}, complete=False, ready=False),
                       "nothing_in_scope_rejected", "read", decisions=[dataclasses.replace(one, chosen=REJECT) for one in e["nothing_in_scope_rejected"]["steps"]["read"]["decisions"]])),
    ("C20r", "the page with no evidence reported FAIL", "C20",
     lambda e: changed(e, "mod_only", "checked", checks=[Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", FAIL)], verdict=FAIL)),
    ("C19r", "the invalidated show left as a cleared hole", "C19",
     lambda e: changed_ob(e, "world_change", "changed", 1, bindings={"subject": Hole("Subject", CLEARED)}, status=AVAILABLE)),
)


def no_context(observation, run, step):
    """Strips d1's questions and state from the decisions of a step: a record that is not d1's actual request."""
    return changed(observation, run, step, decisions=[dataclasses.replace(one, state="", questions=()) for one in observation[run]["steps"][step]["decisions"]])


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
     lambda e: changed(e, "page_then_mod", "read", decisions=[dataclasses.replace(one, offered=(New("redesign"), MOD)) for one in e["page_then_mod"]["steps"]["read"]["decisions"]]), "not offered"),
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
     lambda e: changed(e, "world_change", "changed", obligations=[ob("Redesign the mod.", "redesign", {"surface": Hole("Surface", REJECTED)}, PENDING)]), "expected 2 obligations"),
    ("C20c", "removing Later turns a reply's claim into a pass", "C20",
     lambda e: changed(e, "later_removed", "checked", checks=[Check(0, None, "evidence", PASS), Check(1, None, "evidence", PASS)], verdict=PASS), "verdict expected"),
    ("C22d", "the edit rewrites d1's recorded choice instead of keeping it beside the correction", "C22",
     lambda e: {**e, "saved_reading": {**e["saved_reading"], "steps": {label: step | ({"decisions": [dataclasses.replace(one, chosen=PAGE) if one.path == "surface" else one for one in step["decisions"]]} if "decisions" in step else {})
                                                                        for label, step in e["saved_reading"]["steps"].items()}}}, "d1's own choice"),
    ("C22e", "a saved reading loads under another world as compatible history", "C22", lambda e: changed(e, "saved_reading", "other_world", diagnostics=[]), "diagnostics expected exactly"),
    # Version 3 (CORRECTIONS E20 to E25).
    ("C16b", "a split whose span lies outside the phrase", "C16",
     lambda e: changed_ob(e, "conjunction", "read", 0, span="Redesign the page"), "span"),
    ("C16c", "a split that drops the conjunction from every span", "C16",
     lambda e: changed(e, "conjunction", "read", obligations=split(e, "Redesign the mod", "show it.")), "source characters in no obligation"),
    ("C05f", "Empty with nothing in scope and no recorded absence decision", "C05", lambda e: changed(e, "nothing_in_scope", "read", decisions=[]), "no recorded decision"),
    ("C05g", "Empty although d1 rejected absence", "C05",
     lambda e: changed(e, "nothing_in_scope_rejected", "read", decisions=[dataclasses.replace(one, chosen=REJECT) for one in e["nothing_in_scope_rejected"]["steps"]["read"]["decisions"]]), "Empty exactly when absence was decided"),
    ("C18h", "a cleared show reported complete", "C18", lambda e: changed_ob(e, "transitions", "cleared", 1, complete=True), "reported complete"),
    ("C06e", "an unknown Many reported complete", "C06", lambda e: changed_ob(e, "unknown", "read", 0, complete=True), "reported complete"),
    ("C19d", "a show of an incomplete redesign reported complete", "C19", lambda e: changed_ob(e, "world_change", "changed", 1, bindings={"subject": Ref(0)}, complete=True), "reported complete"),
    ("C01d", "an unresolved request reported complete", "C01", lambda e: changed_ob(e, "unsupported", "read", 0, complete=True), "unresolved obligation 0 reported complete"),
    ("C20d", "a relabelled reply counted as evidence", "C20",
     lambda e: changed(e, "relabelled", "checked", checks=[Check(0, None, "evidence", PASS, 0), Check(1, None, "evidence", PASS, 1)], verdict=PASS), "verdict expected"),
    ("C02e", "a rejected world change loses its draft", "C02", lambda e: changed_change(e, "deleted", draft=None), "draft is not the proposal"),
    ("C02f", "a rejected world change returns an altered draft", "C02", lambda e: changed_change(e, "weakened", draft="another source"), "draft is not the proposal"),
    ("C02g", "a rejected world change still becomes the active world", "C02",
     lambda e: changed_change(e, "confident_nothing", active_world=world_source(PAINT_WORLD)), "the active world's declarations"),
    ("C02h", "an invalid world rejected without its faults", "C02", lambda e: changed_change(e, "invalid_world", faults=[]), "does not report the faults"),
    # Version 4 (CORRECTIONS E26 to E37).
    ("C15f", "a saved question replaced with a fabricated one", "C15",
     lambda e: changed(e, "specimen", "read", decisions=[dataclasses.replace(one, questions=(("FABRICATED QUESTION", ()),)) for one in e["specimen"]["steps"]["read"]["decisions"]]), "decisions differ from the requests"),
    ("C03y", "a question d1 received with no saved decision", "C03", lambda e: changed(e, "negated", "read", decisions=[]), "decisions differ from the requests"),
    ("C04y", "a saved decision for a question d1 never received", "C04",
     lambda e: changed(e, "rejected", "read", decisions=e["rejected"]["steps"]["read"]["decisions"] + [Decision(0, None, "model", ("redesign",), "redesign", (), "Redesign the mod.", (("Which function?", ("redesign",)),), (("redesign", 0.9),))]),
     "decisions differ from the requests"),
    ("C20e", "a later duplicate PASS overwrites the page's outcome", "C20",
     lambda e: changed(e, "mod_only", "checked", checks=e["mod_only"]["steps"]["checked"]["checks"] + [Check(1, None, "evidence", PASS, 0)], verdict=PASS), "duplicate check"),
    ("C20f", "an unexpected check result", "C20",
     lambda e: changed(e, "both", "checked", checks=e["both"]["steps"]["checked"]["checks"] + [Check(0, None, "speed", PASS)]), "unexpected check"),
    ("C06f", "an available but incomplete obligation fulfilled", "C06",
     lambda e: changed(e, "unknown", "checked", checks=[Check(0, None, "evidence", PASS, 0)], verdict=PASS), "fulfilled while incomplete"),
    ("C18i", "an available but incomplete show reported ready", "C18", lambda e: changed_ob(e, "transitions", "cleared", 1, ready=True), "reported ready"),
    ("C02i", "a rejected change whose schema change keeps every name becomes active", "C02",
     lambda e: changed_change(e, "weakened", active_world=world_source(World(replace=(('    PAGE: Asked = "the page"\n', ""),)))), "the active world's declarations"),
    ("C02j", "a rejected change returns the old world as its draft", "C02", lambda e: changed_change(e, "deleted", draft=world_source(World())), "draft is not the proposal"),
    ("C17d", "the second of two like sentences placed on the first", "C17",
     lambda e: changed_ob(e, "identical_operations", "read", 1, at=e["identical_operations"]["steps"]["read"]["obligations"][0].at), "is not the source at"),
    ("C17e", "obligations out of source order", "C17",
     lambda e: changed(e, "shared_result", "read", obligations=[dataclasses.replace(one, at=(one.at[0] + 0, one.at[1])) for one in e["shared_result"]["steps"]["read"]["obligations"]][::-1]), "out of source order"),
    ("C05h", "Empty by a rule that names no rule", "C05",
     lambda e: changed(e, "nothing_in_scope", "read", decisions=[Decision(0, "subject", "rule", (), ABSENT)], requests=[]), "names no declared rule"),
    ("C05i", "a malformed answer becomes Empty", "C05",
     lambda e: changed_ob(e, "malformed", "read", 0, bindings={"subject": EMPTY}, complete=True, ready=True), "binding subject"),
    ("C05j", "a missing answer gives no diagnostic", "C05", lambda e: changed(e, "missing", "read", diagnostics=[]), "diagnostics expected exactly"),
    ("C16d", "every 'and' split: the compare of both becomes two", "C16",
     lambda e: changed(e, "compare_conjunction", "read", obligations=[dataclasses.replace(e["compare_conjunction"]["steps"]["read"]["obligations"][0], span="Compare the page", bindings={"surfaces": (PAGE,)}),
                                                                        dataclasses.replace(e["compare_conjunction"]["steps"]["read"]["obligations"][0], span="and the mod.", bindings={"surfaces": (MOD,)})]),
     "expected 1 obligations"),
    ("C13c", "member words of a quoted reply grounded and offered as the user's", "C13",
     lambda e: changed(e, "quoted_members", "read", decisions=[Decision(0, "surfaces", "model", (PAGE, MOD), (PAGE, MOD), (), "Compare them.", (("Which?", ("'the page'", "'the mod'")),), (((PAGE, MOD), 0.9),))],
                       requests=[Request("Compare them.", "Which?", ("'the page'", "'the mod'"))]), "a member of the quote was offered"),
    ("C15g", "the saved record copies the redesign into show instead of a reference", "C15",
     lambda e: changed(e, "specimen", "saved", record=record_of([("redesign", {}), ("redesign", {}), ("show", {"subject": 1}), ("test", {})])), "record applications"),
    ("C15h", "the saved record references an application that does not exist", "C15",
     lambda e: changed(e, "specimen", "saved", record={**e["specimen"]["steps"]["saved"]["record"], "phrases": [{"start": 0, "end": 1, "brand": "Asked", "terms": [
         {"id": "t0", "function": "redesign", "arguments": {}}, {"id": "t1", "function": "show", "arguments": {"subject": {"ref": "t9"}}}, {"id": "t2", "function": "test", "arguments": {}}]}]}), "names no application"),
    ("C15i", "a saved decision without its path", "C15",
     lambda e: changed(e, "specimen", "saved", record={**e["specimen"]["steps"]["saved"]["record"], "decisions": [{"term": "t0", "by": "model"}]}), "decision without a path"),
    ("C16e", "the record of one phrase keeps only one of its applications", "C16",
     lambda e: changed(e, "conjunction", "saved", record=record_of([("show", {})])), "record applications"),
    ("C17f", "a member of several saved as a copied constant instead of a reference", "C17",
     lambda e: changed(e, "shared_result", "saved", record=record_of([("redesign", {}), ("show", {"subject": 0}), ("compare", {})])), "record application 2 references"),
    # Version 6 (CORRECTIONS E39 to E51).
    ("C04z", "a singleton Many bound without asking d1", "C04", lambda e: no_decision(e, "singleton_many", "read", "surfaces"), "no recorded decision"),
    ("C06g", "every candidate rejected becomes an explicit empty collection", "C06",
     lambda e: changed_ob(e, "all_rejected", "read", 0, bindings={"surfaces": EMPTY_LIST}, complete=True, ready=True), "binding surfaces"),
    ("C06h", "the hole with no candidate is not recorded as an automatic decision", "C06", lambda e: changed(e, "unknown", "read", decisions=[]), "no recorded decision"),
    ("C16f", "the unknown operation of a phrase dropped beside the known one", "C16",
     lambda e: changed(e, "unknown_and_known", "read", obligations=e["unknown_and_known"]["steps"]["read"]["obligations"][1:]), "expected 2 obligations"),
    ("C14e", "the request beyond the bound vanishes", "C14",
     lambda e: changed(e, "too_many_operations", "read", obligations=e["too_many_operations"]["steps"]["read"]["obligations"][:3], decisions=[]), "expected 4 obligations"),
    ("C14f", "the request beyond the bound is unresolved for another reason", "C14", lambda e: changed_ob(e, "too_many_operations", "read", 3, reason=REJECTED), "reason"),
    ("C02k", "an added obligation is accepted", "C02", lambda e: changed_change(e, "added", activated=True, verdict=PASS, regressions=[]), "world change expected"),
    ("C02l", "the second proposal after an activation is accepted", "C02",
     lambda e: changed(e, "second_proposal", "proposed_again", world_change=e["second_proposal"]["steps"]["proposed_again"]["world_change"] | {"activated": True, "verdict": PASS, "regressions": []}), "world change expected"),
    ("C02m", "the second proposal crashes", "C02", lambda e: changed(e, "second_proposal", "proposed_again", error="KeyError", world_change=None), "error KeyError"),
    ("C02n", "a rejected hole that becomes an invalid-answer hole is accepted", "C02", lambda e: changed_change(e, "reason_changed", activated=True, verdict=PASS, regressions=[]), "world change expected"),
    ("C19e", "a correction kept after its operation's function changed", "C19",
     lambda e: changed(e, "function_changed", "changed", corrections=[Correction(1, "subject", MOD, RETAINED)]), "expected invalidated"),
    ("C19f", "a reference correction silently re-pointed after its target changed", "C19",
     lambda e: changed(changed_ob(e, "reference_target_changed", "changed", 1, bindings={"subject": Ref(0)}, status=PENDING), "reference_target_changed", "changed",
                       corrections=[Correction(1, "subject", Ref(0), RETAINED)]), "expected invalidated"),
    ("C19g", "an invalidation reason that names no cause", "C19",
     lambda e: changed(e, "function_changed", "changed", corrections=[Correction(1, "subject", MOD, INVALIDATED, "changed")]), "names neither the operation nor the path"),
    ("C19h", "a rerun restores the correction over the later edit", "C19",
     lambda e: changed(e, "edit_after_correction", "rerun", obligations=[concrete(one) for one in REBOUND], corrections=[Correction(1, "subject", MOD, RETAINED)]), "binding subject"),
    ("C10x", "reading a record inside a collection crashes", "C10", lambda e: changed(e, "many_of_records", "read", error="AttributeError"), "error AttributeError"),
    ("C10y", "checking a record inside a collection crashes", "C10", lambda e: changed(e, "many_of_records", "checked", error="TypeError"), "error TypeError"),
    ("C11i", "a saved wrong-type binding loads with no diagnostic", "C11", lambda e: changed(e, "loads", "load_wrong_type", diagnostics=[]), "diagnostics expected exactly"),
    ("C11j", "a saved dangling reference fails to load", "C11", lambda e: {**e, "loads": {**e["loads"], "steps": e["loads"]["steps"] | {"load_dangling": {"error": "KeyError", "model_calls": 0}}}}, "error KeyError"),
    ("C11k", "a saved line with a missing argument loads as complete", "C11", lambda e: changed_ob(e, "loads", "load_missing", 0, complete=True), "is reported complete=True"),
    ("C11h", "a kind fault reported as a type fault", "C11", lambda e: {**e, "invalid_kind": {**e["invalid_kind"], "world_faults": [("Broken", "type")]}}, "expected world fault ('Broken', 'kind')"),
    ("C11l", "the record built from the cell's fields is not recorded as an automatic decision", "C11", lambda e: changed(e, "edits", "read", decisions=[]), "no recorded decision"),
    ("C04w", "a chosen candidate rebuilt rather than one that was offered", "C04",
     lambda e: changed(e, "accepted", "read", decisions=[dataclasses.replace(one, chosen=PAGE) for one in e["accepted"]["steps"]["read"]["decisions"]]), "was not offered"),
    ("C22g", "a restyle that changes nothing the display uses", "C22",
     lambda e: changed(e, "saved_reading", "restyled", rendered=e["saved_reading"]["steps"]["reloaded"]["rendered"]), "changed nothing the display uses"),
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
        ("S1", "a blank option description is chosen", lambda: [] if option_for(MOD, ("", "")) is None else ["S1: a blank description was chosen"], "S1"),
        ("S2", "the option is chosen by place rather than by its description", lambda: [] if option_for(MOD, ("'the page'", "'the mod'")) == 1 else ["S2: not chosen by description"], "S2"),
        ("S3", "a reference chosen by a rendering of another function", lambda: [] if option_for(Ref(0), ("show(subject='the mod')",), {0: ("redesign", ("the mod",))}) is None else ["S3: wrong function accepted"], "S3"),
        ("S4", "an operation chosen with a blank docstring", lambda: [] if option_for("redesign", ("", "show it"), world=World()) is None else ["S4: a blank docstring was chosen"], "S4"),
        ("S5", "two descriptions that both say the value", lambda: [] if option_for(MOD, ("'the mod'", "the mod")) is None else ["S5: an ambiguous choice was made"], "S5"),
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

    absent = [(run.label, old) for case in CASES for run in case.runs for world in [run.world] + [part for _, action in run.actions for part in action if isinstance(part, World)]
              for old, _ in world.replace if old not in base_source(world.base)]
    failures += [f"a fixture replaces text that its base world does not hold: {one}" for one in absent]
    expected = {case_id: expected_runs(case_id) for case_id in CASE}
    delivered = provenance["files"]
    rights = [(case_id, f"{len(CASE[case_id].runs)} runs", lambda case_id=case_id: PREDICATES[case_id](expected[case_id])) for case_id in CASE]
    rights += [(key, "current snapshot", lambda key=key: l4(provenance, delivered) if key == "L4" else LOCATION_PREDICATES[key](provenance)) for key in LOCATION_PREDICATES]
    for key, words, found in ((key, words, check()) for key, words, check in rights):
        failures += [f"{key} rejects its own EXPECTED: {line}" for line in found]
        print(f"{key} EXPECTED ({words}): {'pass' if not found else found}")
    for key, words, case_id, right in RIGHT_ALTERNATIVES:
        found = PREDICATES[case_id](right(expected[case_id]))
        failures += [f"{key} ({words}) rejected: {line}" for line in found]
        print(f"{key:<5} {case_id} {'accepted' if not found else 'REJECTED'}: {words}")
    wrongs = [(key, f"{case_id} {words}", lambda wrong=wrong, case_id=case_id: PREDICATES[case_id](wrong(expected[case_id])), diagnostic) for key, words, case_id, wrong, diagnostic in NEGATIVE_CONTROLS]
    wrongs += [one for one in static_controls(provenance, delivered) if not one[0].startswith("S")]
    for key, words, check, _ in [one for one in static_controls(provenance, delivered) if one[0].startswith("S")]:
        found = check()
        failures += [f"{key} ({words}): {line}" for line in found]
        print(f"{key:<5} {'refused' if not found else 'ACCEPTED'}: {words}")
    unrendered = [(run.label, value) for case in CASES for run in case.runs for value in values_of(dict(enumerate(run.script.get("binds", {}).values())))
                  if isinstance(value, Ref) and value.obligation not in run.script.get("refers", {})]
    failures += [f"a script binds a reference without saying what it renders as: {one}" for one in unrendered]
    for key, words, wrong, diagnostic in wrongs:
        found = wrong()
        caught = [line for line in found if diagnostic in line]
        failures += [] if caught else [f"{key} ({words}) not caught: {found}"]
        print(f"{key:<5} {'caught' if caught else 'MISSED'}: {words} -> {(caught[0] if caught else str(found))[:160]}")
    assert not failures, "\n".join(failures)
    print(f"self-test passed: 22 cases pass on EXPECTED; {len(RIGHT_ALTERNATIVES)} allowed variants accepted; {len(NEGATIVE_CONTROLS)} wrong projections and "
          f"{len(wrongs) - len(NEGATIVE_CONTROLS)} wrong locations or worlds rejected; 5 wrong stand-in choices refused. This shows that the comparisons discriminate; it checks no engine. "
          "The engine is checked only when observe() runs it and these predicates judge its output.")


if __name__ == "__main__":
    self_test()
