"""Rule model + condition evaluator (tiny grammar in MVP)."""

from pydantic import BaseModel


class Rule(BaseModel):
    condition: str
    action: str


def evaluate_condition(rule: Rule, facts: dict) -> bool:
    raise NotImplementedError

