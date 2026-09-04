"""Condition matcher truth table, veto short-circuit.

Rule text is tenant-supplied and reaches the hot path, so the parser is tested
both for what it accepts and — more importantly — for what it refuses. Anything
resembling code execution must fail as a syntax error, not evaluate.
"""

from __future__ import annotations

import pytest

from engines.policy.rules import (
    BoolOp,
    Comparison,
    Rule,
    RuleSyntaxError,
    evaluate_condition,
    parse,
    tokenize,
)


def matches(condition: str, facts: dict) -> bool:
    return evaluate_condition(Rule(condition=condition), facts)


class TestTokenizer:
    def test_splits_a_comparison(self):
        kinds = [t.kind for t in tokenize("amount > 500")]
        assert kinds == ["IDENT", "OP", "NUMBER"]

    def test_keywords_are_recognised(self):
        assert [t.value for t in tokenize("a == 1 and b == 2")][3] == "and"

    def test_rejects_unexpected_characters(self):
        with pytest.raises(RuleSyntaxError):
            tokenize("amount $ 5")


class TestParser:
    def test_builds_a_comparison_node(self):
        node = parse('region == "IN"')
        assert node == Comparison("region", "==", "IN")

    def test_and_binds_tighter_than_or(self):
        node = parse("a == 1 or b == 2 and c == 3")
        assert isinstance(node, BoolOp) and node.op == "or"
        assert isinstance(node.right, BoolOp) and node.right.op == "and"

    def test_parentheses_override_precedence(self):
        node = parse("(a == 1 or b == 2) and c == 3")
        assert isinstance(node, BoolOp) and node.op == "and"

    def test_parses_a_list_literal(self):
        assert parse('action in ["a", "b"]') == Comparison("action", "in", ["a", "b"])

    def test_parses_dotted_paths(self):
        assert parse("applicant.age < 21").path == "applicant.age"

    @pytest.mark.parametrize(
        "condition",
        [
            "",
            "amount >",
            "> 5",
            "amount 5",
            "amount > > 5",
            "(amount > 5",
            "amount > 5)",
            "amount > 5 and",
            'action in ["a",',
        ],
    )
    def test_rejects_malformed_conditions(self, condition):
        with pytest.raises(RuleSyntaxError):
            parse(condition)

    @pytest.mark.parametrize(
        "condition",
        [
            "__import__('os').system('rm -rf /') == 1",
            "amount > 5; print('x')",
            "(lambda: 1)() == 1",
            "open('/etc/passwd').read() == 1",
        ],
    )
    def test_code_injection_attempts_fail_to_parse(self, condition):
        """There is no eval here, and these must not become one."""
        with pytest.raises(RuleSyntaxError):
            parse(condition)


class TestTruthTable:
    @pytest.mark.parametrize(
        "condition,facts,expected",
        [
            ("amount > 500", {"amount": 600}, True),
            ("amount > 500", {"amount": 500}, False),
            ("amount >= 500", {"amount": 500}, True),
            ("amount < 500", {"amount": 499}, True),
            ("amount <= 500", {"amount": 500}, True),
            ('region == "IN"', {"region": "IN"}, True),
            ('region == "IN"', {"region": "US"}, False),
            ('region != "IN"', {"region": "US"}, True),
            ('action in ["disburse", "refund"]', {"action": "disburse"}, True),
            ('action in ["disburse", "refund"]', {"action": "score"}, False),
            ('action not in ["disburse"]', {"action": "score"}, True),
            ("verified == true", {"verified": True}, True),
            ("verified == true", {"verified": False}, False),
            ("verified == false", {"verified": False}, True),
            ("applicant.age < 21", {"applicant": {"age": 19}}, True),
            ("applicant.age < 21", {"applicant": {"age": 25}}, False),
        ],
    )
    def test_single_comparison(self, condition, facts, expected):
        assert matches(condition, facts) is expected

    @pytest.mark.parametrize(
        "condition,facts,expected",
        [
            ("a == 1 and b == 2", {"a": 1, "b": 2}, True),
            ("a == 1 and b == 2", {"a": 1, "b": 3}, False),
            ("a == 1 or b == 2", {"a": 9, "b": 2}, True),
            ("a == 1 or b == 2", {"a": 9, "b": 9}, False),
            ("not a == 1", {"a": 2}, True),
            ("not a == 1", {"a": 1}, False),
            ("(a == 1 or b == 2) and c == 3", {"a": 1, "b": 9, "c": 3}, True),
            ("(a == 1 or b == 2) and c == 3", {"a": 1, "b": 9, "c": 9}, False),
            ("a == 1 or b == 2 and c == 3", {"a": 1, "b": 9, "c": 9}, True),
        ],
    )
    def test_boolean_combination(self, condition, facts, expected):
        assert matches(condition, facts) is expected


class TestMissingAndMistypedFacts:
    def test_missing_fact_never_matches(self):
        """A rule for a field the caller omits must not start blocking them."""
        assert matches("amount > 500", {}) is False
        assert matches("amount < 500", {}) is False

    def test_missing_fact_does_not_match_even_under_negation(self):
        assert matches('region != "IN"', {}) is False

    def test_missing_nested_path_never_matches(self):
        assert matches("applicant.age < 21", {"applicant": {}}) is False
        assert matches("applicant.age < 21", {}) is False

    def test_incomparable_types_do_not_match(self):
        """`"high" > 5` is a rule bug; it stays inert rather than blocking."""
        assert matches("amount > 5", {"amount": "high"}) is False

    def test_in_against_a_non_collection_does_not_match(self):
        assert matches("amount in 5", {"amount": 5}) is False


class TestRuleModel:
    def test_malformed_condition_is_rejected_at_construction(self):
        """Bad rules must fail on the cold write path, never on live traffic."""
        with pytest.raises(ValueError):
            Rule(condition="amount >")

    def test_unknown_action_is_rejected(self):
        with pytest.raises(ValueError):
            Rule(condition="amount > 1", action="explode")

    @pytest.mark.parametrize("action", ["veto", "deny", "warn", "allow"])
    def test_known_actions_are_accepted(self, action):
        assert Rule(condition="amount > 1", action=action).action == action


@pytest.mark.asyncio
class TestPolicyEngine:
    async def test_veto_short_circuits_remaining_rules(self, tenant):
        """The first veto wins; later rules must not be evaluated."""
        from engines.policy.engine import PolicyEngine, invalidate
        from shared.db.models import PolicyRule
        from shared.db.session import session_scope
        from shared.schemas.evaluation import EvaluationContext

        with session_scope() as db:
            db.add(
                PolicyRule(
                    tenant_id=tenant,
                    rule_id="veto-first",
                    condition="amount > 100",
                    action="veto",
                    description="over limit",
                )
            )
            db.add(
                PolicyRule(
                    tenant_id=tenant,
                    rule_id="warn-second",
                    condition="amount > 100",
                    action="warn",
                )
            )
        invalidate(tenant)

        result = await PolicyEngine().evaluate(
            EvaluationContext(tenant_id=tenant, model_id="m1", context={"amount": 500})
        )

        assert result.veto is not None
        assert result.veto.rule_id == "veto-first"
        assert result.score == 0.0
        assert [r["rule_id"] for r in result.detail["matched_rules"]] == ["veto-first"]

    async def test_no_rules_is_degraded_not_a_free_pass(self, tenant):
        from engines.policy.engine import PolicyEngine
        from shared.schemas.evaluation import EvaluationContext

        result = await PolicyEngine().evaluate(EvaluationContext(tenant_id=tenant, model_id="m1"))
        assert result.degraded
        assert result.detail["reason"] == "no_rules_configured"

    async def test_non_matching_rules_leave_full_trust(self, tenant, veto_rule):
        from engines.policy.engine import PolicyEngine
        from shared.schemas.evaluation import EvaluationContext

        result = await PolicyEngine().evaluate(
            EvaluationContext(
                tenant_id=tenant, model_id="m1", action="score", context={"amount": 10}
            )
        )
        assert result.score == 1.0
        assert result.veto is None
        assert not result.degraded

    async def test_features_cannot_shadow_the_action(self, tenant, veto_rule):
        """A feature named `action` must not be able to bypass a policy rule."""
        from engines.policy.engine import PolicyEngine
        from shared.schemas.evaluation import EvaluationContext

        result = await PolicyEngine().evaluate(
            EvaluationContext(
                tenant_id=tenant,
                model_id="m1",
                action="disburse",
                features={"action": 0.0},
                context={"amount": 900000},
            )
        )
        assert result.veto is not None
