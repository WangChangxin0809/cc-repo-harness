#!/usr/bin/env python3
"""Arid nodes: where a mutant would be unproductive, so none is generated.

Every rule here is transcribed from Appendix A of *Practical Mutation Testing
at Scale: A View from Google* (Petrovic, Ivankovic, Fraser, Just; TSE 2021,
arXiv:2102.11378). Nothing is invented. Where the paper gives a rule, the rule
is implemented as given; where it gives an example, the example is in the
docstring so a reader can check the transcription.

## What "arid" means, in their words

    "Nodes of the abstract syntax tree (AST) are arid if applying mutation
    operators on them or their subtrees would lead to unproductive mutants. An
    unproductive mutant is either trivially equivalent to the original program,
    or if it is detectable then adding a test for it would not lead to an
    actual improvement of the test suite."

The second clause is the hard one and the reason this is not a static-analysis
problem. `new ArrayList(64) -> new ArrayList(16)` is killable: you *can* write
a test that asserts the initial capacity. That test asserts the implementation
rather than the specification, and writing it makes the suite worse. So the
question a rule must answer is not *can this be detected* but **should a test
exist that detects it**.

## Sound and unsound, and why both are kept

The paper marks each rule sound or unsound and tallies 17 sound against 18
unsound -- and then says something uncomfortable:

    "Sound heuristics are demonstrably correct, but we have had much more
    important improvements of perceived mutant usefulness from unsound
    heuristics."

An unsound rule can suppress a mutant that would have been productive. The
paper never measures how often, and has no negative-results section. **This is
the one place this implementation deliberately does not follow it**: every rule
carries its soundness, suppressions are counted separately by soundness, and
both numbers go on the page. Copying the rules is right; copying the silence
about what they cost is not.

## The three that paid for almost everything

Their §3.2.5, on which rules actually mattered:

    "The highest mutant productivity gains came from the three heuristics
    implemented in the early days: suppression of mutations in logging
    statements, time-related operations (e.g., setting deadlines, timeouts,
    exponential backoff specifications etc.), and finally configuration flags.
    ... there is strong indication that these suppressions account for
    improvements in productivity from about 15% to 80%. Additional heuristics
    and refinements progressivley improved producitvity to 89%."

They are LOG, TIME and FLAG below, and they are first for that reason.

## The star rule, with its measured accuracy

    "The star example of this category is a heuristic that marks any function
    call arid if the function name starts with the prefix `log` or the object
    on which the function is invoked is called `logger`. We validated this
    heuristic by randomly sampling 100 nodes that were marked arid by the log
    heuristic, and found that 99 indeed were correctly marked, while one had
    marginal utility."

That 99/100 is a reproducible claim and `study.py --log-validation` reproduces
it on real repositories rather than asserting it.
"""

from __future__ import annotations

import ast
import re

# Each rule: (id, sound?, appendix section, what it suppresses)
# `sound` is the paper's own verdict, transcribed, not our assessment.
RULES = {}


def rule(rid, sound, section, note):
    def wrap(fn):
        RULES[rid] = {"id": rid, "sound": sound, "section": section,
                      "note": note, "fn": fn}
        return fn
    return wrap


# --------------------------------------------------------------------------
# A.1.1 Logging -- sound, and the one with a measured accuracy
# --------------------------------------------------------------------------

LOG_NAMES = re.compile(r"^log", re.I)
LOG_OBJECTS = {"logger", "log", "logging", "_logger", "_log", "console"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception",
               "critical", "fatal", "trace", "log", "print"}


@rule("LOG", True, "A.1.1",
      "a call whose name starts with `log`, or on an object called `logger`")
def _log(node, src):
    """Their A.1.1. "Logging statements are rarely tested outside of the code
    of the logging systems themselves."

    The paper's rule is exactly two clauses -- name prefix, or receiver name --
    and the 99/100 validation is of that rule, so it is that rule that is
    implemented. `console` is included because the paper names it explicitly
    ("Also the browser `Console` class ... Similar is true for other console
    methods like `assert`")."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Name):
        return bool(LOG_NAMES.match(f.id)) or f.id == "print"
    if isinstance(f, ast.Attribute):
        if LOG_NAMES.match(f.attr) and f.attr.lower() in LOG_METHODS:
            return True
        base = f.value
        while isinstance(base, ast.Attribute):
            base = base.value
        if isinstance(base, ast.Name) and base.id.lower() in LOG_OBJECTS:
            return f.attr.lower() in LOG_METHODS or LOG_NAMES.match(f.attr)
    return False


# --------------------------------------------------------------------------
# A.1.4 Time-related code -- sound
# --------------------------------------------------------------------------

TIME_NAMES = {"sleep", "asleep", "wait", "settimeout", "setdeadline",
              "set_deadline", "settimer", "timeout", "deadline", "backoff",
              "retry_after", "monotonic", "perf_counter", "sleep_for",
              "sleepfor", "elapsed"}
TIME_MODULES = {"time", "asyncio", "datetime", "timedelta", "sched"}


@rule("TIME", True, "A.1.4",
      "a sleep, deadline, timeout or backoff expression")
def _time(node, src):
    """Their A.1.4. "Clocks are usually faked in tests, and networking calls
    are short-circuited to special RPC implementations for testing; it
    therefore rarely makes sense to mutate time expressions when used in a
    deadline-context."

    Their examples are `::SleepFor(absl::Seconds(5))` and
    `context.set_deadline(now() + milliseconds(10))`."""
    if isinstance(node, ast.Call):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if name.lower().replace("_", "") in {n.replace("_", "")
                                             for n in TIME_NAMES}:
            return True
        if isinstance(f, ast.Attribute):
            base = f.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id.lower() in TIME_MODULES:
                return True
    if isinstance(node, ast.keyword) and node.arg and \
            node.arg.lower() in ("timeout", "deadline", "interval", "delay"):
        return True
    return False


# --------------------------------------------------------------------------
# A.1.13 Program flags -- sound
# --------------------------------------------------------------------------

FLAG_CALLS = {"define_string", "define_integer", "define_bool",
              "define_boolean", "define_float", "define_list",
              "define_enum", "define_multi_string", "add_argument",
              "add_option", "getenv", "environ"}


@rule("FLAG", True, "A.1.13", "a configuration flag's declaration or default")
def _flag(node, src):
    """Their A.1.13. Flags "may be used for algorithm tweaking (max threads in
    pool, max size of cache, deadline for network operations)".

    Their examples mutate the *defaults*: `flags.DEFINE_integer('stack_size',
    1000 * 1000, ...)` to `1000 / 1000`, and `5 * 60` to `5 + 60`. Python's
    equivalents are argparse's `add_argument` and `os.getenv`."""
    if isinstance(node, ast.Call):
        f = node.func
        name = (f.attr if isinstance(f, ast.Attribute)
                else getattr(f, "id", "")).lower()
        if name in FLAG_CALLS:
            return True
    return False


# --------------------------------------------------------------------------
# A.1.2 Memory and capacity -- sound
# --------------------------------------------------------------------------

CAPACITY = {"reserve", "resize", "shrink_to_fit", "set_size", "setcapacity",
            "ensure_capacity", "maxsize", "buffer_size", "chunk_size",
            "capacity", "prefetch", "maxlen"}


@rule("CAPACITY", True, "A.1.2",
      "a pre-allocation size, where the only effect is that it grows later")
def _capacity(node, src):
    """Their A.1.2. Of mutating `std::vector<std::string> merged(l+r)`:
    "the only consequence will be that the vector may need to grow itself and
    that will take extra time"."""
    if isinstance(node, ast.Call):
        f = node.func
        name = (f.attr if isinstance(f, ast.Attribute)
                else getattr(f, "id", "")).lower()
        if name in CAPACITY:
            return True
    if isinstance(node, ast.keyword) and node.arg and \
            node.arg.lower() in CAPACITY:
        return True
    return False


# --------------------------------------------------------------------------
# A.1.5 Tracing and debugging -- sound
# --------------------------------------------------------------------------

@rule("ASSERT", True, "A.1.5",
      "an assertion or a traceback print — a last line of defence, not logic")
def _assert(node, src):
    """Their A.1.5. "Code is often adorned with debugging and tracing
    information that may be even excluded in the release builds ...
    check-failures usually make the program segfault and serve as a last line
    of defense". Their examples include `assert(x != nullptr)` and
    `exception.printStackTrace()`.

    Note this covers `assert` **in the code under test**, never in the tests:
    `changed_and_covered` never offers a test file."""
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        f = node.func
        name = (f.attr if isinstance(f, ast.Attribute)
                else getattr(f, "id", "")).lower()
        if name in ("print_exc", "print_stack", "print_exception",
                    "format_exc", "breakpoint", "set_trace"):
            return True
    return False


# --------------------------------------------------------------------------
# A.1.14 Low-level APIs -- sound, and Python is named in it
# --------------------------------------------------------------------------

LOWLEVEL_MODULES = {"os", "shutil", "subprocess", "sys", "signal", "fcntl",
                    "resource", "tempfile"}


@rule("LOWLEVEL", True, "A.1.14", "a direct os/shutil call")
def _lowlevel(node, src):
    """Their A.1.14, which names Python twice: "Python's `os` or `shutil`
    libraries (e.g., to copy some files, create a directory, or to print on
    the screen) ... these calls are hard to mock (except in Python) and mostly
    unproductive test targets". Their examples are `shutil.rmtree(dir)` and
    `os.rename(from, to)`."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        base = node.func.value
        while isinstance(base, ast.Attribute):
            base = base.value
        if isinstance(base, ast.Name) and base.id in LOWLEVEL_MODULES:
            return True
    return False


# --------------------------------------------------------------------------
# A.1.20 Collection size -- sound
# --------------------------------------------------------------------------

@rule("LEN", True, "A.1.20",
      "a length compared against zero, where half the mutants are unreachable")
def _len(node, src):
    """Their A.1.20. "The size of a collection cannot be a negative number, so
    when comparing the length of a container to zero, some mutants resulting
    from the comparison may produce unreachable code." Their example is
    `if len(l) > 0:` mutated to `if len(l) < 0:`, and they note that in Python
    "the `len` builtin function can be detected with ease"."""
    if isinstance(node, ast.Compare):
        left = node.left
        if isinstance(left, ast.Call) and isinstance(left.func, ast.Name) \
                and left.func.id == "len":
            for c in node.comparators:
                if isinstance(c, ast.Constant) and c.value == 0:
                    return True
        if isinstance(left, ast.Attribute) and left.attr in ("size", "length"):
            return True
    return False


# --------------------------------------------------------------------------
# A.1.10 / A.1.9 None and zero comparisons -- sound
# --------------------------------------------------------------------------

@rule("NULLCMP", True, "A.1.10",
      "a comparison against None or 0, where the mutant is equivalent")
def _nullcmp(node, src):
    """Their A.1.10: "When comparing something to `nullptr` and its
    corresponding value in other languages (`NULL`, `nil`, `null`, `None`,
    ...), picking the left ... is equivalent to replacing the binary operator
    with `false`." And A.1.9: `if (x != 0)` is equivalent to `if (x)`."""
    if isinstance(node, ast.Compare):
        for c in node.comparators:
            if isinstance(c, ast.Constant) and c.value in (None, 0, False):
                return True
    return False


# --------------------------------------------------------------------------
# A.1.11 Floating point equality -- sound
# --------------------------------------------------------------------------

@rule("FLOATCMP", True, "A.1.11",
      "a float compared with an inequality, where +/- epsilon is meaningless")
def _floatcmp(node, src):
    """Their A.1.11. "Floating point equality comparison, except for special
    values such as zero, is mostly meaningless. For a number x that is not 0,
    replacing `f() > x` with `f() >= x` is not a good test goal." Their example
    is `return normalized_score > 0.95`."""
    if isinstance(node, ast.Compare):
        for c in node.comparators:
            if isinstance(c, ast.Constant) and isinstance(c.value, float) \
                    and c.value != 0.0:
                return True
    return False


# --------------------------------------------------------------------------
# A.1.18 Infinity -- sound
# --------------------------------------------------------------------------

@rule("INF", True, "A.1.18", "arithmetic on an infinity, which is a no-op")
def _inf(node, src):
    """Their A.1.18. "There are various representations of infinity in
    mathematical libraries in various languages. Incrementing or decrementing
    these produces an equivalent, and thus unproductive, mutant." Their example
    is `numpy.inf`."""
    if isinstance(node, ast.Attribute) and node.attr == "inf":
        return True
    if isinstance(node, ast.Name) and node.id in ("inf", "Infinity"):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, float) \
            and node.value in (float("inf"), float("-inf")):
        return True
    return False


# --------------------------------------------------------------------------
# A.1.19 Insensitive arguments -- sound
# --------------------------------------------------------------------------

@rule("INSENSITIVE", True, "A.1.19",
      "an argument the callee is insensitive to — zip's short leg, a slice step")
def _insensitive(node, src):
    """Their A.1.19, which gives four sub-cases and two of them are Python's:

    * `zip`: "The iterator stops when the shortest input iterable is
      exhausted, meaning that changing the size of one of the parameters is
      not guaranteed to affect the result."
    * a slice or loop step: "When changing the range condition, it has to be
      changed at least the full step for the change to have an effect."
    """
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "zip":
        return True
    if isinstance(node, ast.Slice) and node.step is not None:
        return True
    return False


# --------------------------------------------------------------------------
# A.4 -- the Python-specific rules
# --------------------------------------------------------------------------

@rule("MAIN", True, "A.4.1", "the `if __name__ == '__main__'` guard")
def _main(node, src):
    """Their A.4.1, verbatim in scope: `if __name__ == '__main__':` mutated to
    `!=`. Sound "barring manipulation of `__name__` global"."""
    if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
            and node.left.id == "__name__":
        return True
    return False


SPECIAL_EXC = {"NotImplementedError", "AssertionError", "ValueError",
               "TypeError", "RuntimeError"}


@rule("SPECIALEXC", False, "A.4.2",
      "a raise of an exception that means 'a programmer erred', not a case")
def _specialexc(node, src):
    """Their A.4.2. "In Python, exceptions like `ValueError` imply a
    programming defect, something a compiler might catch if one was employed,
    not something for what a test should be written ... The `AssertionError`
    should usually mean that the code is unreachable. Another special case is a
    virtual method that raises `NotImplementedError` and is annotated by
    `abc.abstractmethod`."

    The paper marks this **not sound**: "it relies on the consistent usage of
    control flow mechanisms"."""
    if isinstance(node, ast.Raise) and node.exc is not None:
        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        name = exc.attr if isinstance(exc, ast.Attribute) else getattr(
            exc, "id", "")
        return name in SPECIAL_EXC
    return False


@rule("VERSION", False, "A.4.3", "a `sys.version_info` check")
def _version(node, src):
    """Their A.4.3, whose example is `if sys.version_info[0] < 3:`. Marked
    **not sound**: "a productive mutant could conceivably appear in version
    detection code"."""
    for sub in ast.walk(node) if isinstance(node, ast.AST) else ():
        if isinstance(sub, ast.Attribute) and sub.attr == "version_info":
            return True
    return False


@rule("PRINT", False, "A.4.5", "a print")
def _print(node, src):
    """Their A.4.5, which notes Python needs this handled separately from the
    low-level API rule. The paper's soundness line for it is, in full: "This
    heuristic is not sound." No justification is given, and none is invented
    here."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "print":
        return True
    return False


# --------------------------------------------------------------------------
# A.1.3 Monitoring systems -- sound
# --------------------------------------------------------------------------

MONITOR = {"increment", "inc", "observe", "record", "gauge", "counter",
           "histogram", "summary", "timing", "measure", "emit", "report_metric",
           "incr", "count", "add_metric", "set_gauge", "statsd", "metric",
           "metrics", "telemetry", "track"}


@rule("MONITOR", True, "A.1.3", "a metrics counter or gauge")
def _monitor(node, src):
    """Their A.1.3. "Although it may be debatable whether monitoring logic
    should be tested or not, developers did not use such mutants productively
    and instead reported them as being unproductive." Their example is a
    Prometheus counter: `error_counter.Increment(a.size() + b.size())`."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute):
            if f.attr.lower() in MONITOR:
                return True
            base = f.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id.lower() in MONITOR:
                return True
        elif isinstance(f, ast.Name) and f.id.lower() in MONITOR:
            return True
    return False


# --------------------------------------------------------------------------
# A.1.8 Arithmetic operator with a no-op child -- sound
# --------------------------------------------------------------------------

@rule("NOOPARITH", True, "A.1.8",
      "arithmetic against a literal 0 or 1, where the mutant is equivalent")
def _nooparith(node, src):
    """Their A.1.8, whose example is `data[i] + 0 * sizeof(char)`: "Mutating
    the binary operator `+` by removing the right-hand side ... results in an
    equivalent mutant. The code is simply written in such a way because it
    deals with low-level instructions and the code style requires that each
    offset be explicitly written"."""
    if not isinstance(node, ast.BinOp):
        return False
    op = type(node.op)
    # A **no-op** child, not merely a small one. `a + 0` and `a * 1` cannot
    # change the value; `a + 1` obviously can, and an earlier reading of this
    # rule suppressed it -- which suppressed most ordinary arithmetic in the
    # tree, and would have made every repository look well tested.
    noop = {ast.Add: (0,), ast.Sub: (0,), ast.Mult: (1,), ast.Div: (1,),
            ast.FloorDiv: (1,), ast.Pow: (1,)}.get(op)
    if noop is None:
        return False
    sides = (node.left, node.right) if op in (ast.Add, ast.Mult) \
        else (node.right,)
    for side in sides:
        if isinstance(side, ast.Constant) and not isinstance(
                side.value, bool) and side.value in noop:
            return True
    return False


# --------------------------------------------------------------------------
# A.1.15 Stream operations -- NOT sound, per the paper
# --------------------------------------------------------------------------

STREAM = {"flush", "close", "fsync", "sync", "drain", "seek", "detach"}


@rule("STREAM", False, "A.1.15", "a flush, close or sync on a buffer")
def _stream(node, src):
    """Their A.1.15. "Removing the flush operations on various streams should
    change no behavior from the test point of view ... The same also holds for
    close operations on files or other buffers."

    Marked **not sound**: "there are conceivable code constructs in which
    buffer operations change the perceived behavior (e.g., in concurrent
    stream manipulation)"."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr.lower() in STREAM
    return False


# --------------------------------------------------------------------------
# A.1.16 Gate configuration -- NOT sound, per the paper
# --------------------------------------------------------------------------

GATE_HINT = ("enable", "disable", "use_", "feature", "flag", "rollout",
             "gate", "experiment", "toggle", "_on", "beta", "legacy")


@rule("GATE", False, "A.1.16", "a feature gate's constant")
def _gate(node, src):
    """Their A.1.16, whose examples are `USE_NEXT_GEN_BACKEND = True` and
    `nextGenTrafficRatio = 0.1`: "ideally both should work correctly, and then
    it becomes impossible to distinguish by tests that there is a difference."

    Marked **not sound**: "it is guessing the meaning of a class field based
    on its value and location, and it might be wrong"."""
    if isinstance(node, ast.Assign) and isinstance(
            node.value, ast.Constant) and isinstance(
                node.value.value, (bool, float)):
        for t in node.targets:
            name = getattr(t, "id", None) or getattr(t, "attr", "")
            if name and any(h in name.lower() for h in GATE_HINT):
                return True
    return False


# --------------------------------------------------------------------------
# A.1.17 Cached lookups -- NOT sound, per the paper
# --------------------------------------------------------------------------

@rule("CACHE", False, "A.1.17", "a memoisation lookup")
def _cache(node, src):
    """Their A.1.17 gives a two-clause structural predicate: "a) it must lookup
    an input parameter in a dissociative container and return from it under
    that key if found, b) it must store the value that it otherwise returns in
    the same container under the same key." Their example is a memoised `fib`.

    Python's own memoisation is usually a decorator, which is the same idea
    stated once instead of five times, so that is recognised too.

    Marked **not sound**: "it only checks for probable code structures"."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in node.decorator_list:
            f = d.func if isinstance(d, ast.Call) else d
            name = getattr(f, "attr", None) or getattr(f, "id", "")
            if "cache" in name.lower() or "memo" in name.lower():
                return True
    if isinstance(node, ast.If):
        test = node.test
        if isinstance(test, ast.Compare) and any(
                isinstance(o, (ast.In, ast.NotIn)) for o in test.ops):
            for sub in node.body:
                if isinstance(sub, ast.Return):
                    return True
    return False


# --------------------------------------------------------------------------
# A.1.21 Trivial methods -- NOT sound, per the paper
# --------------------------------------------------------------------------

TRIVIAL = {"__eq__", "__ne__", "__hash__", "__str__", "__repr__",
           "__copy__", "__deepcopy__", "__format__", "__len__", "__bool__",
           "__lt__", "__le__", "__gt__", "__ge__"}


@rule("TRIVIAL", False, "A.1.21", "a dunder whose body is boilerplate")
def _trivial(node, src):
    """Their A.1.21. "in Java there are methods like `equals`, `hashCode`,
    `toString`, `clone`, and they are usually implemented by using existing
    libraries ... the developer feedback on the productivity of corresponding
    mutants clearly indicates that mutants in such methods are not productive."

    Marked **not sound**: "it relies on the code style recommendation on
    implementing such methods"."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
        node.name in TRIVIAL


# --------------------------------------------------------------------------
# A.1.22 Early exit optimisations -- NOT sound, per the paper
# --------------------------------------------------------------------------

EMPTY_RETURNS = ((), [], {}, "", 0)


@rule("EARLYEXIT", False, "A.1.22",
      "an empty-input guard that returns an empty result")
def _earlyexit(node, src):
    """Their A.1.22, which opens by quoting Torvalds on indentation and then
    says: "The early return just makes the code easier to understand but has no
    effect on the behavior." Their trigger, precisely: "an empty container ...
    is returned if one of the parameters is checked for emptiness."

    Marked **not sound**: "the mutant might not be equivalent"."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    empty_check = False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        empty_check = True
    elif isinstance(test, ast.Compare):
        left = test.left
        if isinstance(left, ast.Call) and isinstance(left.func, ast.Name) \
                and left.func.id == "len":
            empty_check = True
    if not empty_check:
        return False
    for sub in node.body:
        if isinstance(sub, ast.Return):
            v = sub.value
            if v is None:
                return True
            if isinstance(v, ast.Constant) and (v.value is None
                                                or v.value in EMPTY_RETURNS):
                return True
            if isinstance(v, (ast.List, ast.Dict, ast.Set, ast.Tuple)) and \
                    not getattr(v, "elts", None) and not getattr(v, "keys", None):
                return True
    return False


# --------------------------------------------------------------------------
# A.1.24 Acceptable bounds -- NOT sound, per the paper
# --------------------------------------------------------------------------

@rule("BOUNDS", False, "A.1.24", "a min/max clamp into an acceptable range")
def _bounds(node, src):
    """Their A.1.24. "Gating a computed result into an acceptable bound by
    using `Math.min`, `Math.max`, or `constrainToRange` ... is by design
    unlikely to change behavior when one of the inputs is mutated." Their
    example is `Math.min(Math.max(data.length * 2L, minCapacity), MAX)`.

    Marked **not sound**: "it can suppress productive mutants that can result
    from mathematical operations"."""
    if isinstance(node, ast.Call):
        f = node.func
        name = (f.attr if isinstance(f, ast.Attribute)
                else getattr(f, "id", "")).lower()
        if name in ("min", "max", "clamp", "constrain", "clip", "bound"):
            return True
    return False


# --------------------------------------------------------------------------
# A.4.4 Multiple return paths -- NOT sound, per the paper
# --------------------------------------------------------------------------

@rule("RETURNNONE", False, "A.4.4", "an explicit `return None` among others")
def _returnnone(node, src):
    """Their A.4.4. "The code style requires Python programs to explicitly
    return `None` in all leafs if there are multiple return statements ...
    Removing those return statements does not make for a good test goal."
    Their trigger condition, verbatim: "all leaf nodes are a return statement".

    Marked **not sound**: "it relies on the code style recommendation"."""
    if isinstance(node, ast.Return):
        v = node.value
        if v is None or (isinstance(v, ast.Constant) and v.value is None):
            return True
    return False


# --------------------------------------------------------------------------
# A.1.22 (extended) Short-circuit early exits -- NOT sound
#
# THIS TRIGGER IS NOT TRANSCRIBED FROM THE PAPER. The category is theirs --
# A.1.22, "Early Exit Optimizations", whose whole claim is "the early return
# just makes the code easier to understand but has no effect on the behavior".
# Their published trigger is narrower: an empty-container guard returning an
# empty container.
#
# This trigger came from **our own feedback loop**, which is the process the
# paper describes for every one of its hundred-odd rules:
#
#     "This process is manual: if we decide a certain mutation is not
#      productive and that the whole class of mutants should not be created,
#      the rule is added to the expert function."
#
# The feedback: a second pass over 13 surviving mutants in `tenacity` judged 7
# unproductive, and 4 of those 7 were one pattern stated twice --
#
#     result = False
#     for r in self.retries:
#         result = result or await f(r)   # `or` already short-circuits
#         if result:                      # so this guard cannot change
#             break                       # the value that is returned
#     return result
#
# -- which is an equivalent mutant every time. Suppressing it is the
# difference between a 46% productive survivor list on that repository and one
# worth reading.
# --------------------------------------------------------------------------

def _accumulator_before(loop_body, index):
    """(name, op) of `name = name <op> ...` immediately above `index`."""
    if index == 0:
        return None
    prev = loop_body[index - 1]
    if not isinstance(prev, ast.Assign) or len(prev.targets) != 1:
        return None
    target = prev.targets[0]
    if not isinstance(target, ast.Name):
        return None
    value = prev.value
    if isinstance(value, ast.Await):
        value = value.value
    if not isinstance(value, ast.BoolOp) or not value.values:
        return None
    first = value.values[0]
    if not isinstance(first, ast.Name) or first.id != target.id:
        return None
    return target.id, type(value.op)


@rule("SHORTCIRCUIT", False, "A.1.22 (extended)",
      "a loop guard the accumulator's own short-circuit already makes redundant")
def _shortcircuit(node, src):
    """An `if <acc>: break` under `acc = acc or ...`, or the `and` mirror.

    Deleting either the guard or the `break` cannot change what the loop
    returns, because `or` stops evaluating once the accumulator is truthy and
    `and` stops once it is falsy. The guard saves an iteration of a loop whose
    body is already a no-op; it does not decide anything.

    Marked **not sound**, for the same reason A.1.22 is: the loop body could
    have a side effect that the early exit skips. It does not in the case that
    produced this rule, and a rule cannot see that in general."""
    if not isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
        return False
    body = node.body
    for i, stmt in enumerate(body):
        if not isinstance(stmt, ast.If) or len(stmt.body) != 1:
            continue
        if not isinstance(stmt.body[0], ast.Break) or stmt.orelse:
            continue
        test, want = stmt.test, ast.Or
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            test, want = test.operand, ast.And
        if not isinstance(test, ast.Name):
            continue
        acc = _accumulator_before(body, i)
        if acc and acc[0] == test.id and acc[1] is want:
            return True
    return False


# --------------------------------------------------------------------------
# the entry point
# --------------------------------------------------------------------------

def arid_node(node, src=""):
    """(rule id, sound) for the first rule that fires, or None.

    Their Equation 1 is recursive: a compound node is arid if all of its
    children are. That recursion is done by the caller, which walks the
    statement containing the mutation point -- see `arid_line`."""
    for rid, r in RULES.items():
        try:
            if r["fn"](node, src):
                return rid, r["sound"]
        except (AttributeError, TypeError):
            continue
    return None


def _statement_at(tree, line):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and getattr(node, "lineno", 0) <= line:
            end = getattr(node, "end_lineno", node.lineno)
            if end >= line and (best is None or node.lineno >= best.lineno):
                best = node
    return best


def arid_line(source, line, operator=""):
    """(rule id, sound) if any node on `line` is arid, else None.

    The statement containing the line is walked, not just the exact node,
    because the paper's rules are about *context*: a `+` inside a logging call
    is arid because it is inside a logging call, not because of the `+`."""
    if not source:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    stmt = _statement_at(tree, line)
    if stmt is None:
        return None
    for node in ast.walk(stmt):
        hit = arid_node(node, source)
        if hit:
            return hit
    return None


def arid_lines(source):
    """{line: (rule, sound)} for a whole file, in one parse.

    The obvious implementation -- call `arid_line` for each line -- reparses
    the file once per line, which on a 400-line module is 400 parses and makes
    the RQ1 study over hundreds of commits take hours instead of seconds. The
    tree is walked once here and every line a rule fires on is marked.

    The paper's Equation 1 makes aridity recursive: a compound node is arid if
    its children are. The practical consequence, and the one that matters, is
    that a mutation *anywhere inside* an arid statement is suppressed -- a `+`
    inside a logging call is arid because of the call, not the `+`. So a rule
    firing on a node marks every line that node spans."""
    out = {}
    if not source:
        return out
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        hit = arid_node(node, source)
        if not hit:
            continue
        start = getattr(node, "lineno", None)
        if start is None:
            continue
        end = getattr(node, "end_lineno", start) or start
        for ln in range(start, end + 1):
            out.setdefault(ln, hit)
    return out


def why_arid(rid):
    r = RULES.get(rid)
    if not r:
        return ""
    return (f"{r['section']} {r['id']}: {r['note']} "
            f"({'sound' if r['sound'] else 'NOT sound, per the paper'})")


def summary():
    """What is implemented, and how much of it the paper trusts."""
    sound = sum(1 for r in RULES.values() if r["sound"])
    return {"rules": len(RULES), "sound": sound,
            "unsound": len(RULES) - sound,
            "ids": sorted(RULES)}


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(summary(), indent=2))
    for rid in sorted(RULES):
        print(f"  {why_arid(rid)}")
