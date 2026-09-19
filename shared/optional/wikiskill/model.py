"""Executable control-flow model for WikiSkill, not an LLM or OS sandbox.

References: arXiv:2608.27454v1 sections 3.2 and Appendix A/C/E.
Adapters are trusted Python callbacks; production agents require separate
processes and restricted mounts. This model never invokes a shell or a model.
Engineering choices left unspecified in the paper are listed in design/implementation.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import difflib
import json
import math
import random
import re
from typing import Callable, Mapping, Sequence


class CannotJudge(RuntimeError):
    """Missing/invalid evidence is neither success nor failure of a proposal."""


@dataclass(frozen=True)
class Task:
    name: str
    group: str


@dataclass(frozen=True)
class Trace:
    task: str
    score: float
    text: str
    prediction: str = ""
    reference: str = ""


@dataclass(frozen=True)
class Skill:
    name: str
    instructions: str
    purpose: str


@dataclass(frozen=True)
class Edit:
    op: str
    content: str
    target: str = ""


@dataclass(frozen=True)
class Proposal:
    action: str
    name: str = ""
    instructions: str = ""
    purpose: str = ""
    edits: tuple[Edit, ...] = ()


@dataclass(frozen=True)
class WikiEdit:
    index: str
    log: str
    create: tuple[tuple[str, str], ...] = ()
    update: tuple[tuple[str, tuple[Edit, ...]], ...] = ()


@dataclass(frozen=True)
class InferenceInput:
    split: str
    tasks: tuple[Task, ...]
    skill_text: str


@dataclass
class State:
    skills: dict[str, Skill] = field(default_factory=dict)
    wiki: dict[str, str] = field(default_factory=lambda: {"index.md": "", "logs.md": "", "skill-impact.md": ""})
    raw: tuple[tuple[int, Trace], ...] = ()
    impacts: list[dict] = field(default_factory=list)
    best: float | None = None
    final_test: float | None = None


def check_splits(splits: Mapping[str, Sequence[Task]]) -> None:
    if set(splits) != {"train", "val", "test"}:
        raise CannotJudge("require train, val and test")
    all_ids: set[str] = set()
    groups: set[str] = set()
    for label in ("train", "val", "test"):
        tasks = splits[label]
        if not tasks or any(not t.name or not t.group for t in tasks):
            raise CannotJudge("empty split or missing task/group identity")
        ids = [t.name for t in tasks]
        gs = {t.group for t in tasks}
        if len(ids) != len(set(ids)) or all_ids.intersection(ids):
            raise CannotJudge("task identities overlap")
        if groups.intersection(gs):
            raise CannotJudge("related task groups cross split boundaries")
        all_ids.update(ids)
        groups.update(gs)


def scored(traces: Sequence[Trace], tasks: Sequence[Task]) -> tuple[tuple[Trace, ...], float]:
    traces = tuple(traces)
    ids = [t.task for t in traces]
    if len(set(ids)) != len(ids) or set(ids) != {t.name for t in tasks}:
        raise CannotJudge("evaluation is incomplete or contains duplicate/foreign tasks")
    if any(isinstance(t.score, bool) or not isinstance(t.score, (float, int))
           or not math.isfinite(t.score) or not 0 <= t.score <= 1 for t in traces):
        raise CannotJudge("invalid score; missing/NaN/inf is not zero")
    return traces, sum(t.score for t in traces) / len(tasks)


def sample_traces(traces: Sequence[Trace], rng: random.Random) -> tuple[Trace, ...]:
    bad = [t for t in traces if t.score < 1.0]
    good = [t for t in traces if t.score == 1.0]
    chosen = rng.sample(bad, min(5, len(bad))) + rng.sample(good, min(3, len(good)))
    return tuple(replace(t, text=t.text[:15000]) for t in chosen)


def patch(text: str, edits: Sequence[Edit]) -> str:
    for edit in edits:
        if edit.op == "append":
            text += edit.content
        elif edit.op in ("replace", "insert_after"):
            if not edit.target or text.count(edit.target) != 1:
                raise CannotJudge("patch anchor must match exactly once")
            replacement = edit.content if edit.op == "replace" else edit.target + edit.content
            text = text.replace(edit.target, replacement, 1)
        else:
            raise CannotJudge("unknown patch operation")
    return text


def page_name(name: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*\.md", name):
        raise CannotJudge("invalid pattern page name")


def apply_wiki(wiki: Mapping[str, str], edit: WikiEdit) -> dict[str, str]:
    if not isinstance(edit.index, str) or not isinstance(edit.log, str):
        raise CannotJudge("index and log are required strings")
    result = dict(wiki)
    seen = set()
    for name, content in edit.create:
        page_name(name)
        key = "patterns/" + name
        if key in result or key in seen:
            raise CannotJudge("new pattern would overwrite an existing page")
        seen.add(key)
        result[key] = content
    for name, edits in edit.update:
        page_name(name)
        key = "patterns/" + name
        if key not in result or key in seen:
            raise CannotJudge("unknown/duplicate pattern update")
        seen.add(key)
        result[key] = patch(result[key], edits)
    result["index.md"] = edit.index
    result["logs.md"] = result.get("logs.md", "") + edit.log + "\n"
    return result


def validate_skill(skill: Skill) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", skill.name):
        raise CannotJudge("skill name must be snake_case")
    if not skill.purpose.strip() or not skill.instructions.startswith("---\n"):
        raise CannotJudge("skill needs frontmatter and a nonempty PURPOSE")
    parts = skill.instructions.split("---", 2)
    if len(parts) != 3:
        raise CannotJudge("unterminated skill frontmatter")
    fields = dict(re.findall(r"^(name|description):\s*(.+)$", parts[1], re.M))
    if fields.get("name") != skill.name or not fields.get("description", "").strip():
        raise CannotJudge("frontmatter name/description missing or inconsistent")


def apply_proposal(skills: Mapping[str, Skill], p: Proposal) -> dict[str, Skill]:
    result = dict(skills)
    if p.action == "no_action":
        return result
    if p.action == "create":
        if p.name in result:
            raise CannotJudge("create cannot silently overwrite an existing skill")
        skill = Skill(p.name, p.instructions, p.purpose)
    elif p.action == "patch":
        if p.name not in result or not p.edits:
            raise CannotJudge("patch requires an existing skill and at least one edit")
        old = result[p.name]
        skill = replace(old, instructions=patch(old.instructions, p.edits),
                        purpose=p.purpose or old.purpose)
    else:
        raise CannotJudge("one create/patch/no_action proposal is required")
    validate_skill(skill)
    result[p.name] = skill
    return result


def inject(skills: Mapping[str, Skill]) -> str:
    return "\n\n".join(skills[name].instructions for name in sorted(skills))


class ProposerView:
    def __init__(self, wiki: Mapping[str, str], skills: Mapping[str, Skill],
                 traces: Sequence[Trace], impacts: Sequence[dict]):
        self._files = {"wiki/" + k: v for k, v in wiki.items()}
        self._files["wiki/skill-impact.md"] = json.dumps(list(impacts), ensure_ascii=False)
        self._traces = {"traces/" + t.task: t.text for t in traces}
        self.read_trace_ids: set[str] = set()
        self.initial = {
            "wiki_index": wiki["index.md"],
            "impacts": self._files["wiki/skill-impact.md"],
            "summary": tuple((t.task, t.score, t.prediction, t.reference) for t in traces),
            "active_skills": tuple(skills.values()),
        }

    def read_file(self, path: str) -> str:
        if not isinstance(path, str) or path.startswith("/") or ".." in path.split("/"):
            raise PermissionError("path outside proposer view")
        if path in self._traces:
            self.read_trace_ids.add(path)
            return self._traces[path]
        if path in self._files:
            return self._files[path]
        raise PermissionError("only wiki and this iteration's training traces are readable")


class Evolution:
    def __init__(self, splits: Mapping[str, Sequence[Task]],
                 rollout: Callable[[InferenceInput], Sequence[Trace]],
                 maintain: Callable[[Mapping[str, str], tuple[Trace, ...]], WikiEdit],
                 propose: Callable[[ProposerView], Proposal], *, iterations: int, seed: int = 0):
        check_splits(splits)
        if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
            raise ValueError("iterations must be a nonnegative integer")
        self.splits = {k: tuple(v) for k, v in splits.items()}
        self.rollout, self.maintain, self.propose = rollout, maintain, propose
        self.iterations, self.rng = iterations, random.Random(seed)
        self.state = State()
        self._started = False

    def evaluate(self, split: str, skills: Mapping[str, Skill]):
        context = InferenceInput(split, self.splits[split], inject(skills))
        return scored(self.rollout(context), context.tasks)

    def run(self) -> State:
        if self._started:
            raise CannotJudge("a completed or interrupted run is not implicitly restarted")
        self._started = True
        s = self.state
        _, s.best = self.evaluate("val", {})
        for iteration in range(self.iterations):
            if s.best == 1.0:
                break
            traces, _ = self.evaluate("train", s.skills)
            s.raw += tuple((iteration, t) for t in traces)
            sample = sample_traces(traces, self.rng)
            edit = self.maintain(dict(s.wiki), sample)
            s.wiki = apply_wiki(s.wiki, edit)
            view = ProposerView(s.wiki, s.skills, traces, s.impacts)
            p = self.propose(view)
            if p.action != "no_action" and len(view.read_trace_ids) < 4:
                raise CannotJudge("proposal must follow inspection of four distinct training traces")
            if p.action == "no_action":
                s.impacts.append({"iteration": iteration, "action": "no_action",
                                  "verdict": "no_action", "score": None, "diff": ""})
                s.wiki["skill-impact.md"] = json.dumps(s.impacts, ensure_ascii=False)
                continue
            candidate = apply_proposal(s.skills, p)
            old = s.skills.get(p.name)
            new = candidate[p.name]
            change = "".join(difflib.unified_diff(
                (old.instructions if old else "").splitlines(keepends=True),
                new.instructions.splitlines(keepends=True),
                fromfile=p.name + "/SKILL.md:active", tofile=p.name + "/SKILL.md:candidate"))
            purpose_change = "".join(difflib.unified_diff(
                (old.purpose if old else "").splitlines(keepends=True),
                new.purpose.splitlines(keepends=True),
                fromfile=p.name + "/PURPOSE.md:active", tofile=p.name + "/PURPOSE.md:candidate"))
            record = {"iteration": iteration, "action": p.action, "name": p.name,
                      "diff": change, "purpose_diff": purpose_change,
                      "candidate_instructions": new.instructions,
                      "candidate_purpose": new.purpose, "best_before": s.best}
            try:
                _, score = self.evaluate("val", candidate)
            except Exception as exc:
                record.update(verdict="unjudged", score=None, error=type(exc).__name__)
                s.impacts.append(record)
                s.wiki["skill-impact.md"] = json.dumps(s.impacts, ensure_ascii=False)
                raise CannotJudge("validation unavailable; active skills unchanged, wiki retained") from exc
            accept = score > s.best
            record.update(verdict="accepted" if accept else "rejected", score=score)
            s.impacts.append(record)
            s.wiki["skill-impact.md"] = json.dumps(s.impacts, ensure_ascii=False)
            if accept:
                s.skills, s.best = candidate, score
        _, s.final_test = self.evaluate("test", s.skills)
        return s
