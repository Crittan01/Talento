"""Tests del response_parser.

Usa objetos sinteticos que simulan response.output del Foundry Responses API.
"""
from dataclasses import dataclass, field
from typing import Any, List

from eval.response_parser import parse_response_output, get_output_text_fallback


# ============================================================================
# Sintetizadores de items (simulan los objetos del SDK OpenAI/Foundry)
# ============================================================================
@dataclass
class _FnCallItem:
    name: str
    arguments: str
    call_id: str
    type: str = "function_call"


@dataclass
class _FileSearchItem:
    type: str = "file_search_call"


@dataclass
class _TextContent:
    text: Any


@dataclass
class _TextValue:
    value: str


@dataclass
class _MessageItem:
    content: List[Any]
    type: str = "message"


@dataclass
class _FakeResponse:
    output: List[Any] = field(default_factory=list)
    output_text: str = ""


# ============================================================================
# Tests
# ============================================================================
def test_parse_message_only_extracts_text():
    """response con un mensaje → texto extraido."""
    response = _FakeResponse(output=[
        _MessageItem(content=[_TextContent(text=_TextValue(value="Hola mundo"))]),
    ])
    parsed = parse_response_output(response, turn=1, hop=1)
    assert parsed.text == "Hola mundo"
    assert parsed.has_pending_calls is False
    assert parsed.observed_tool_calls == []


def test_parse_function_call_captures_pending():
    """function_call → registrado en pending + en observed."""
    response = _FakeResponse(output=[
        _FnCallItem(
            name="query_log_analytics",
            arguments='{"query": "ContainerInstanceLog_CL | take 1"}',
            call_id="call_abc",
        ),
    ])
    parsed = parse_response_output(response, turn=1, hop=2)
    assert parsed.has_pending_calls is True
    assert len(parsed.function_calls) == 1
    assert parsed.function_calls[0].name == "query_log_analytics"
    assert parsed.function_calls[0].args == {"query": "ContainerInstanceLog_CL | take 1"}
    assert parsed.function_calls[0].call_id == "call_abc"
    assert len(parsed.observed_tool_calls) == 1
    assert parsed.observed_tool_calls[0].name == "query_log_analytics"
    assert parsed.observed_tool_calls[0].turn == 1
    assert parsed.observed_tool_calls[0].hop == 2


def test_parse_file_search_call_registered_without_args():
    """file_search_call → observed sin args, sin pending."""
    response = _FakeResponse(output=[
        _FileSearchItem(),
    ])
    parsed = parse_response_output(response, turn=1, hop=1)
    assert parsed.has_pending_calls is False
    assert len(parsed.observed_tool_calls) == 1
    assert parsed.observed_tool_calls[0].name == "file_search"
    assert parsed.observed_tool_calls[0].args == {}


def test_parse_mixed_items():
    """Mezcla function_call + file_search + message en mismo hop."""
    response = _FakeResponse(output=[
        _FileSearchItem(),
        _FnCallItem(
            name="run_awx_job_template",
            arguments='{"template_id": 36, "extra_vars_json": "{}"}',
            call_id="call_xyz",
        ),
        _MessageItem(content=[_TextContent(text=_TextValue(value="Analisis intermedio"))]),
    ])
    parsed = parse_response_output(response, turn=2, hop=3)
    assert parsed.text == "Analisis intermedio"
    assert parsed.has_pending_calls is True
    assert len(parsed.function_calls) == 1
    assert len(parsed.observed_tool_calls) == 2  # file_search + awx
    names = sorted(tc.name for tc in parsed.observed_tool_calls)
    assert names == ["file_search", "run_awx_job_template"]


def test_parse_malformed_arguments_keeps_raw():
    """Si arguments no es JSON valido, captura raw."""
    response = _FakeResponse(output=[
        _FnCallItem(
            name="query_log_analytics",
            arguments="not valid json {",
            call_id="call_bad",
        ),
    ])
    parsed = parse_response_output(response, turn=1, hop=1)
    assert len(parsed.function_calls) == 1
    assert "_raw" in parsed.function_calls[0].args


def test_parse_empty_output():
    """Response vacio → todo vacio."""
    response = _FakeResponse(output=[])
    parsed = parse_response_output(response, turn=1, hop=1)
    assert parsed.text == ""
    assert parsed.has_pending_calls is False
    assert parsed.observed_tool_calls == []


def test_fallback_output_text_when_no_message():
    response = _FakeResponse(output=[], output_text="Texto fallback")
    text = get_output_text_fallback(response)
    assert text == "Texto fallback"


def test_parse_multiple_function_calls_same_hop():
    """Agente puede emitir varias function_calls en un solo hop."""
    response = _FakeResponse(output=[
        _FnCallItem(name="query_log_analytics", arguments='{"query": "X"}', call_id="c1"),
        _FnCallItem(name="run_awx_job_template", arguments='{"template_id": 39, "extra_vars_json": "{}"}', call_id="c2"),
    ])
    parsed = parse_response_output(response, turn=1, hop=1)
    assert len(parsed.function_calls) == 2
    assert len(parsed.observed_tool_calls) == 2
