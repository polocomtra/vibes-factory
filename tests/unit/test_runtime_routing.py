from types import SimpleNamespace
from uuid import uuid4

from apps.api.app.runtime.routing import should_retrieve_knowledge


def runtime_request(prompt: str, *, web_search: bool = True, mode: str = "auto"):
    tools = (SimpleNamespace(name="web_search"),) if web_search else ()
    return SimpleNamespace(
        input=SimpleNamespace(text=prompt),
        agent_version=SimpleNamespace(
            knowledge_bases=(SimpleNamespace(mode=mode),),
            tools=tools,
        ),
        workspace_id=uuid4(),
    )


def test_explicit_external_research_skips_auto_knowledge_retrieval() -> None:
    assert (
        should_retrieve_knowledge(
            runtime_request(
                "Search the web for the latest information about Jensen Huang"
            )
        )
        is False
    )


def test_document_question_keeps_knowledge_retrieval() -> None:
    request = runtime_request(
        "According to the uploaded document, what is VibesFactory?"
    )
    assert should_retrieve_knowledge(request) is True


def test_attached_knowledge_instruction_with_slash_keeps_retrieval() -> None:
    request = runtime_request(
        "don't use web_search, please use attached knowledge/ documents"
    )
    assert should_retrieve_knowledge(request) is True


def test_explicit_no_web_search_instruction_keeps_retrieval() -> None:
    assert (
        should_retrieve_knowledge(
            runtime_request("Don't use web search and answer from the attached docs")
        )
        is True
    )


def test_ordinary_kb_question_keeps_retrieval_with_web_search_available() -> None:
    assert (
        should_retrieve_knowledge(
            runtime_request("What is the code name for the sample rollout?")
        )
        is True
    )


def test_always_mode_overrides_external_research_routing() -> None:
    assert (
        should_retrieve_knowledge(
            runtime_request("Research Jensen Huang", mode="always")
        )
        is True
    )


def test_auto_retrieval_is_kept_without_external_tool() -> None:
    assert (
        should_retrieve_knowledge(
            runtime_request("Summarize the available context", web_search=False)
        )
        is True
    )
