"""Rule model + condition evaluator (tiny grammar in MVP).

Tenants author rules as strings:

    amount > 50000 and region == "IN"
    action in ["disburse", "refund"] and applicant.age < 21

Conditions are tokenised and parsed into an AST, then walked. There is no
``eval`` anywhere in this module and there never will be: rule text arrives from
tenant-supplied configuration, so ``eval`` would be a remote code execution hole
in the middle of the hot path. The grammar is small enough to parse properly, so
it is parsed properly.

Grammar
-------
    expr       := or_expr
    or_expr    := and_expr ( "or" and_expr )*
    and_expr   := not_expr ( "and" not_expr )*
    not_expr   := "not" not_expr | primary
    primary    := "(" expr ")" | comparison
    comparison := path OP literal
    OP         := == | != | > | >= | < | <= | in | not in
    literal    := number | string | true | false | null | "[" literal,* "]"
    path       := ident ( "." ident )*
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RuleSyntaxError(ValueError):
    """Raised when a condition cannot be parsed. Surfaced at write time."""


# --- Rule model ------------------------------------------------------------


class Rule(BaseModel):
    """One tenant policy rule."""

    condition: str
    action: str = "veto"
    rule_id: str = ""
    description: str = ""
    # Trust score contributed when a "warn" rule matches. Ignored for veto/deny.
    penalty: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("action")
    @classmethod
    def _known_action(cls, v: str) -> str:
        allowed = {"veto", "deny", "warn", "allow"}
        if v not in allowed:
            raise ValueError(f"action must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("condition")
    @classmethod
    def _parseable(cls, v: str) -> str:
        # Parse at construction so a malformed rule fails when it is written
        # via the control plane, not silently on live traffic.
        parse(v)
        return v


# --- Tokeniser -------------------------------------------------------------

_TOKEN_SPEC = [
    ("WS", r"\s+"),
    ("NUMBER", r"-?\d+(?:\.\d+)?"),
    ("STRING", r'"[^"]*"|\'[^\']*\''),
    ("OP", r"==|!=|>=|<=|>|<"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("COMMA", r","),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))

_KEYWORDS = {"and", "or", "not", "in", "true", "false", "null"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            raise RuleSyntaxError(f"unexpected character {source[pos]!r} at position {pos}")
        kind = match.lastgroup
        value = match.group()
        pos = match.end()
        if kind == "WS":
            continue
        if kind == "IDENT" and value.lower() in _KEYWORDS:
            kind = "KEYWORD"
            value = value.lower()
        tokens.append(Token(kind, value, match.start()))
    return tokens


# --- AST -------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    path: str
    op: str
    value: Any


@dataclass(frozen=True)
class BoolOp:
    op: str  # "and" | "or"
    left: Any
    right: Any


@dataclass(frozen=True)
class Not:
    operand: Any


# --- Parser (recursive descent) --------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._i = 0

    def _peek(self) -> Token | None:
        return self._tokens[self._i] if self._i < len(self._tokens) else None

    def _next(self) -> Token:
        token = self._peek()
        if token is None:
            raise RuleSyntaxError("unexpected end of condition")
        self._i += 1
        return token

    def _accept(self, kind: str, value: str | None = None) -> Token | None:
        token = self._peek()
        if token and token.kind == kind and (value is None or token.value == value):
            self._i += 1
            return token
        return None

    def _expect(self, kind: str, value: str | None = None) -> Token:
        token = self._accept(kind, value)
        if token is None:
            got = self._peek()
            raise RuleSyntaxError(f"expected {value or kind}, got {got.value if got else 'end'!r}")
        return token

    def parse(self) -> Any:
        node = self._or_expr()
        if self._peek() is not None:
            raise RuleSyntaxError(f"trailing input at position {self._peek().pos}")
        return node

    def _or_expr(self) -> Any:
        node = self._and_expr()
        while self._accept("KEYWORD", "or"):
            node = BoolOp("or", node, self._and_expr())
        return node

    def _and_expr(self) -> Any:
        node = self._not_expr()
        while self._accept("KEYWORD", "and"):
            node = BoolOp("and", node, self._not_expr())
        return node

    def _not_expr(self) -> Any:
        if self._accept("KEYWORD", "not"):
            return Not(self._not_expr())
        return self._primary()

    def _primary(self) -> Any:
        if self._accept("LPAREN"):
            node = self._or_expr()
            self._expect("RPAREN")
            return node
        return self._comparison()

    def _comparison(self) -> Comparison:
        path = self._expect("IDENT").value

        # "not in" is the only two-token operator.
        if self._accept("KEYWORD", "not"):
            self._expect("KEYWORD", "in")
            return Comparison(path, "not in", self._literal())
        if self._accept("KEYWORD", "in"):
            return Comparison(path, "in", self._literal())

        op = self._expect("OP").value
        return Comparison(path, op, self._literal())

    def _literal(self) -> Any:
        token = self._next()
        if token.kind == "NUMBER":
            return float(token.value) if "." in token.value else int(token.value)
        if token.kind == "STRING":
            return token.value[1:-1]
        if token.kind == "KEYWORD":
            if token.value == "true":
                return True
            if token.value == "false":
                return False
            if token.value == "null":
                return None
        if token.kind == "LBRACKET":
            items: list[Any] = []
            if self._accept("RBRACKET"):
                return items
            while True:
                items.append(self._literal())
                if self._accept("RBRACKET"):
                    return items
                self._expect("COMMA")
        raise RuleSyntaxError(f"expected a literal, got {token.value!r} at position {token.pos}")


def parse(condition: str) -> Any:
    """Parse a condition string into an AST. Raises RuleSyntaxError."""
    tokens = tokenize(condition)
    if not tokens:
        raise RuleSyntaxError("empty condition")
    return _Parser(tokens).parse()


# --- Evaluation ------------------------------------------------------------

_MISSING = object()


def _resolve(path: str, facts: dict) -> Any:
    """Walk a dotted path. Returns the sentinel when any segment is absent."""
    current: Any = facts
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return _MISSING
    return current


def _compare(left: Any, op: str, right: Any) -> bool:
    # A rule referencing a fact the caller did not send is *not a match*. It is
    # never an error and never a veto: a tenant adding a rule for a field that
    # some callers omit must not start blocking those callers' traffic.
    if left is _MISSING:
        return False

    if op == "in":
        return left in right if isinstance(right, (list, str, tuple)) else False
    if op == "not in":
        return left not in right if isinstance(right, (list, str, tuple)) else True
    if op == "==":
        return left == right
    if op == "!=":
        return left != right

    # Ordering comparisons need comparable operands; "high" > 5 is a rule bug,
    # and treating it as False keeps a bad rule inert rather than catastrophic.
    try:
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
    except TypeError:
        return False
    raise RuleSyntaxError(f"unknown operator {op!r}")


def _eval_node(node: Any, facts: dict) -> bool:
    if isinstance(node, Comparison):
        return _compare(_resolve(node.path, facts), node.op, node.value)
    if isinstance(node, BoolOp):
        if node.op == "and":
            return _eval_node(node.left, facts) and _eval_node(node.right, facts)
        return _eval_node(node.left, facts) or _eval_node(node.right, facts)
    if isinstance(node, Not):
        return not _eval_node(node.operand, facts)
    raise RuleSyntaxError(f"unknown AST node {node!r}")


def evaluate_condition(rule: Rule, facts: dict) -> bool:
    """True when ``rule``'s condition holds for ``facts``."""
    return _eval_node(parse(rule.condition), facts)
