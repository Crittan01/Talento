"""Tests de FunctionalAssertion."""
from eval.schemas import (
    CaseDefinition,
    ExpectedBehavior,
    ObservedToolCall,
    RunResult,
    ToolArgsConstraint,
)
from eval.verdict import FunctionalAssertion


def test_functional_pass_tools_any_of(case_happy_simple):
    """tools_any_of matchea → pass."""
    run = RunResult(
        case_id="H99", final_text="OK",
        tool_calls=[ObservedToolCall(name="file_search", args={}, turn=1, hop=1)],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case_happy_simple, run)
    assert result.passed is True


def test_functional_fail_tools_any_of_missing(case_happy_simple):
    """tools_any_of NO matchea → fail."""
    run = RunResult(
        case_id="H99", final_text="OK",
        tool_calls=[ObservedToolCall(name="query_log_analytics", args={"query": "x"}, turn=1, hop=1)],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case_happy_simple, run)
    assert result.passed is False
    assert any("ninguno de" in f for f in result.failures)


def test_functional_pass_template_id_correct(case_happy_simple):
    """Constraint template_id matchea cuando tool fue llamado."""
    case = CaseDefinition(
        case_id="H97", category="happy",
        description="health check",
        query="health check",
        expected=ExpectedBehavior(
            tool_args_must_include={
                "run_awx_job_template": ToolArgsConstraint(template_id=39),
            },
            intent_summary="full health check",
        ),
    )
    run = RunResult(
        case_id="H97", final_text="OK",
        tool_calls=[ObservedToolCall(
            name="run_awx_job_template",
            args={"template_id": 39, "extra_vars_json": "{}"},
            turn=1, hop=1,
        )],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    assert result.passed is True


def test_functional_fail_template_id_wrong(case_happy_simple):
    """Constraint template_id NO matchea cuando tool fue llamado."""
    case = CaseDefinition(
        case_id="H97", category="happy",
        description="health check",
        query="health check",
        expected=ExpectedBehavior(
            tool_args_must_include={
                "run_awx_job_template": ToolArgsConstraint(template_id=39),
            },
            intent_summary="full health check",
        ),
    )
    run = RunResult(
        case_id="H97", final_text="OK",
        tool_calls=[ObservedToolCall(
            name="run_awx_job_template",
            args={"template_id": 36, "extra_vars_json": "{}"},
            turn=1, hop=1,
        )],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    assert result.passed is False
    assert any("template_id esperado 39" in f for f in result.failures)


def test_functional_skip_constraint_when_tool_not_called(case_happy_simple):
    """Si tool no fue llamado, constraints no se evaluan (skip silencioso)."""
    case = CaseDefinition(
        case_id="H97", category="happy",
        description="health check",
        query="health check",
        expected=ExpectedBehavior(
            tool_args_must_include={
                "run_awx_job_template": ToolArgsConstraint(template_id=39),
            },
            intent_summary="full health check",
        ),
    )
    run = RunResult(
        case_id="H97", final_text="OK",
        tool_calls=[ObservedToolCall(name="file_search", args={}, turn=1, hop=1)],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    # No falla porque el tool no fue llamado — la constraint es condicional
    assert result.passed is True


def test_functional_pass_time_range_hours_present():
    case = CaseDefinition(
        case_id="H97", category="happy",
        description="brute force con time_range",
        query="brute force ultimas 4h",
        expected=ExpectedBehavior(
            tool_args_must_include={
                "run_awx_job_template": ToolArgsConstraint(
                    template_id=35, time_range_hours_present=True,
                ),
            },
            intent_summary="brute force con time_range_hours custom",
        ),
    )
    run = RunResult(
        case_id="H97", final_text="OK",
        tool_calls=[ObservedToolCall(
            name="run_awx_job_template",
            args={"template_id": 35, "extra_vars_json": '{"time_range_hours": 4, "failed_threshold": 5}'},
            turn=1, hop=1,
        )],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    assert result.passed is True


def test_functional_fail_time_range_hours_missing():
    case = CaseDefinition(
        case_id="H97", category="happy",
        description="brute force con time_range",
        query="brute force ultimas 4h",
        expected=ExpectedBehavior(
            tool_args_must_include={
                "run_awx_job_template": ToolArgsConstraint(
                    template_id=35, time_range_hours_present=True,
                ),
            },
            intent_summary="brute force con time_range_hours custom",
        ),
    )
    run = RunResult(
        case_id="H97", final_text="OK",
        tool_calls=[ObservedToolCall(
            name="run_awx_job_template",
            args={"template_id": 35, "extra_vars_json": "{}"},
            turn=1, hop=1,
        )],
        hops=1, elapsed_seconds=2.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    assert result.passed is False
    assert any("time_range_hours" in f for f in result.failures)


def test_functional_pass_tools_all_of():
    case = CaseDefinition(
        case_id="M97", category="multi_turn",
        description="multi turn — KQL + file_search",
        turns=[{"role": "user", "content": "errores"}, {"role": "user", "content": "que es TLNT-007?"}],
        expected=ExpectedBehavior(
            tools_all_of=["query_log_analytics", "file_search"],
            intent_summary="diagnostico + lookup",
        ),
    )
    run = RunResult(
        case_id="M97", final_text="OK",
        tool_calls=[
            ObservedToolCall(name="query_log_analytics", args={"query": "x"}, turn=1, hop=1),
            ObservedToolCall(name="file_search", args={}, turn=2, hop=1),
        ],
        hops=2, elapsed_seconds=5.0,
    )
    result = FunctionalAssertion().evaluate(case, run)
    assert result.passed is True
