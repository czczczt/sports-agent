import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.recipe_agent.contracts import RecipeProposal, ReviewDecision
from app.recipe_agent.extraction import (
    GoldenCase,
    InvalidProtocol,
    Sample,
    compact_html,
    extract,
    protocol_digest,
    validate_protocol,
)
from app.recipe_agent.provider import ModelProposal, ProviderUnavailable
from app.recipe_agent.repository import SnapshotUnavailable

MAX_REPAIRS = 3
TOKEN_BUDGET = 15000
Proposal = Callable[
    [list[str], dict[str, Any] | None, list[str]],
    Awaitable[ModelProposal],
]


class RepairState(TypedDict, total=False):
    base_version_id: int | None
    candidate: dict[str, Any] | None
    proposed: bool
    repairs: int
    tokens_in: int
    tokens_out: int
    errors: list[str]
    attempts: list[dict[str, Any]]
    sample_errors: list[str]
    passed: bool
    golden_passed: int
    outcome: str
    reviewer: str
    review_id: str
    comment: str
    reviewed: bool
    halt_repairs: bool


def build_graph(
    samples: Callable[[], Awaitable[list[Sample]]],
    golden: Callable[[], Awaitable[list[GoldenCase]]],
    propose: Proposal,
    auto_apply: bool,
    saver: BaseCheckpointSaver,
) -> CompiledStateGraph:
    async def ask_model(state: RepairState, repair: bool) -> RepairState:
        try:
            html = await samples()
        except SnapshotUnavailable as exc:
            return _unavailable(state, str(exc))
        excerpts = await asyncio.to_thread(
            lambda: [compact_html(sample.html) for sample in html]
        )
        try:
            response = await propose(
                excerpts, state.get("candidate"), state.get("errors", [])
            )
        except ProviderUnavailable as exc:
            return _unavailable(state, str(exc))
        candidate = response.recipe
        total_in = state.get("tokens_in", 0) + response.tokens_in
        total_out = state.get("tokens_out", 0) + response.tokens_out
        errors = (
            []
            if candidate
            else list(response.errors or ("Модель вернула некорректный JSON-рецепт",))
        )
        if total_in + total_out > TOKEN_BUDGET:
            errors = ["Превышен бюджет токенов"]
        return {
            "candidate": candidate.model_dump(exclude_none=True)
            if candidate
            else state.get("candidate"),
            "proposed": bool(candidate) or state.get("proposed", False),
            "repairs": state.get("repairs", 0) + int(repair),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "passed": not errors,
            "errors": errors,
            "golden_passed": 0,
            "attempts": [
                *state.get("attempts", []),
                {
                    "step": "repair" if repair else "generate",
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                    "errors": errors,
                },
            ],
        }

    async def generate_recipe(state: RepairState) -> RepairState:
        return await ask_model(state, repair=False)

    async def repair_recipe(state: RepairState) -> RepairState:
        return await ask_model(state, repair=True)

    async def execute_sample(state: RepairState) -> RepairState:
        recipe = RecipeProposal.model_validate(state["candidate"])
        try:
            inputs = await samples()
        except SnapshotUnavailable as exc:
            return {"sample_errors": [str(exc)], "halt_repairs": True}
        # Keep participant rows out of the durable checkpoint.
        errors = await asyncio.to_thread(_sample_errors, recipe, inputs)
        return {"sample_errors": errors}

    def validate_contract(state: RepairState) -> RepairState:
        return _record_check(state, "sample", state["sample_errors"])

    async def check_golden_set(state: RepairState) -> RepairState:
        recipe = RecipeProposal.model_validate(state["candidate"])
        try:
            cases = await golden()
        except SnapshotUnavailable as exc:
            return _unavailable(state, str(exc))
        errors, count = await asyncio.to_thread(_golden_errors, recipe, cases)
        return {**_record_check(state, "golden", errors), "golden_passed": count}

    def escalate_human(state: RepairState) -> RepairState:
        response = interrupt(
            {
                "candidate": state.get("candidate"),
                "errors": state.get("errors", []),
                "can_approve": state.get("passed", False),
            }
        )
        decision = ReviewDecision.model_validate(response["decision"])
        result: RepairState = {
            "reviewed": True,
            "review_id": response["id"],
            "reviewer": response["reviewer"],
            "comment": decision.comment,
        }
        if decision.action == "reject":
            return {**result, "outcome": "rejected"}
        if decision.action == "edit" and decision.candidate is not None:
            return {
                **result,
                "candidate": decision.candidate.model_dump(exclude_none=True),
                "proposed": True,
                "passed": True,
                "errors": [],
                "golden_passed": 0,
            }
        return result

    def finish(state: RepairState) -> RepairState:
        unchanged = state.get("base_version_id") and not (
            state.get("repairs") or state.get("reviewed")
        )
        return {"outcome": "unchanged" if unchanged else "activated"}

    def retry_or_escalate(state: RepairState) -> str:
        if (
            state.get("reviewed")
            or state.get("halt_repairs")
            or state.get("repairs", 0) >= MAX_REPAIRS
            or state.get("tokens_in", 0) + state.get("tokens_out", 0) >= TOKEN_BUDGET
        ):
            return "escalate_human"
        return "repair_recipe"

    def after_proposal(state: RepairState) -> str:
        return (
            "execute_sample" if state.get("passed", True) else retry_or_escalate(state)
        )

    def after_sample(state: RepairState) -> str:
        return "check_golden_set" if state["passed"] else retry_or_escalate(state)

    def after_golden(state: RepairState) -> str:
        if not state["passed"]:
            return retry_or_escalate(state)
        if state.get("reviewed") or (
            state.get("base_version_id") is not None
            and (auto_apply or not state.get("repairs"))
        ):
            return "finish"
        return "escalate_human"

    def after_review(state: RepairState) -> str:
        return END if state.get("outcome") == "rejected" else "execute_sample"

    graph = StateGraph(RepairState)
    graph.add_node("generate_recipe", generate_recipe)
    graph.add_node("execute_sample", execute_sample)
    graph.add_node("validate_contract", validate_contract)
    graph.add_node("repair_recipe", repair_recipe)
    graph.add_node("check_golden_set", check_golden_set)
    graph.add_node("escalate_human", escalate_human)
    graph.add_node("finish", finish)
    graph.add_conditional_edges(
        START,
        lambda state: "execute_sample" if state.get("candidate") else "generate_recipe",
        ["execute_sample", "generate_recipe"],
    )
    proposal_routes = ["execute_sample", "repair_recipe", "escalate_human"]
    graph.add_conditional_edges("generate_recipe", after_proposal, proposal_routes)
    graph.add_conditional_edges("repair_recipe", after_proposal, proposal_routes)
    graph.add_edge("execute_sample", "validate_contract")
    graph.add_conditional_edges(
        "validate_contract",
        after_sample,
        ["check_golden_set", "repair_recipe", "escalate_human"],
    )
    graph.add_conditional_edges(
        "check_golden_set", after_golden, ["finish", "repair_recipe", "escalate_human"]
    )
    graph.add_conditional_edges("escalate_human", after_review, [END, "execute_sample"])
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=saver)


def _record_check(state: RepairState, step: str, errors: list[str]) -> RepairState:
    return {
        "passed": not errors,
        "errors": errors,
        "attempts": [*state.get("attempts", []), {"step": step, "errors": errors}],
    }


def _unavailable(state: RepairState, error: str) -> RepairState:
    return {
        **_record_check(state, "unavailable", [error]),
        "halt_repairs": True,
        "golden_passed": 0,
    }


def _sample_errors(recipe: RecipeProposal, samples: list[Sample]) -> list[str]:
    errors = []
    for sample in samples:
        try:
            validate_protocol(
                extract(recipe, sample.html), sample.place_by, sample.total
            )
        except InvalidProtocol as exc:
            errors.append(f"Образец {sample.raw_id}: {exc}")
    return errors


def _golden_errors(
    recipe: RecipeProposal, cases: list[GoldenCase]
) -> tuple[list[str], int]:
    errors = []
    if not 3 <= len(cases) <= 5:
        return ["Для активации нужны 3–5 эталонных страниц"], 0
    for case in cases:
        sample = case.sample
        try:
            rows = extract(recipe, sample.html)
            validate_protocol(rows, sample.place_by, sample.total)
            if protocol_digest(rows) != case.digest:
                raise InvalidProtocol("Строки отличаются от эталона")
        except InvalidProtocol as exc:
            errors.append(f"Эталон {sample.raw_id}: {exc}")
    return errors, len(cases) - len(errors)
