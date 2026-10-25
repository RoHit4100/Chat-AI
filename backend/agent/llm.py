import os
from typing import Any, AsyncIterator, Iterator, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain.chat_models import init_chat_model as langchain_init_chat_model

class DeterministicFakeChatModel(BaseChatModel):
    """Deterministic fake chat model for tests and local development that can emit tokens and tool calls."""

    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "deterministic-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        # Return a runnable binding preserving tools for node invocation
        return self.bind(tools=tools, **kwargs)

    def _determine_response(self, messages: List[BaseMessage]) -> tuple[str, Optional[list]]:
        """Determine content and optional tool calls based on conversation history."""
        if not messages:
            return "Empty conversation.", None

        last_msg = messages[-1]

        # Check if last message was a tool message
        if isinstance(last_msg, ToolMessage):
            # Check if tool reported an error
            is_error = getattr(last_msg, "status", None) == "error" or "Error:" in str(last_msg.content)
            # Count consecutive tool errors in history
            tool_error_count = 0
            for m in reversed(messages):
                if isinstance(m, ToolMessage) and (getattr(m, "status", None) == "error" or "Error:" in str(m.content)):
                    tool_error_count += 1
                elif isinstance(m, HumanMessage):
                    break

            if is_error and "truncated or invalid" in str(last_msg.content):
                compact_spec = {"title": "Compact Doc", "paragraphs": ["Compact text"]}
                return "", [{
                    "name": "generate_file",
                    "args": {"kind": "pdf", "name": "compact.pdf", "spec": compact_spec},
                    "id": "call_gen_compact",
                    "type": "tool_call",
                }]

            if is_error and tool_error_count < 3:
                # Retry by emitting another tool call
                return "", [{"name": "failing_tool", "args": {"query": f"retry_{tool_error_count}"}, "id": f"call_err_{tool_error_count}", "type": "tool_call"}]
            if tool_error_count >= 3:
                return "Tool execution failed after 3 consecutive attempts. Stopping loop and explaining failure.", None
            return f"Processed tool output: {last_msg.content}. Completed.", None

        # Check user message text
        content = str(getattr(last_msg, "content", "")).lower()
        if "call tool" in content or "test tool" in content:
            return "", [{"name": "inspect_file", "args": {"file_id": "test_id"}, "id": "call_web_0", "type": "tool_call"}]

        if "simulate truncate" in content or "truncated spec" in content:
            return "", [{
                "name": "generate_file",
                "args": "{\"kind\": \"pdf\", \"name\": \"broken.pdf\", \"spec\": {\"title\": \"Broken",
                "id": "call_trunc_0",
                "type": "tool_call",
            }]

        if "fail" in content or "error" in content:
            return "", [{"name": "failing_tool", "args": {"query": "fail"}, "id": "call_err_0", "type": "tool_call"}]

        if "make it shorter" in content or "add a skills section" in content or "revise" in content or "based_on" in content or "add a column" in content:
            if "pdf" in content or "resume" in content:
                rev_spec = {
                    "title": "Rohit L. Udamale",
                    "subtitle": "Backend Developer",
                    "sections": [
                        {"heading": "Summary", "content": "Concise summary for version 2."},
                        {"heading": "Skills", "bullets": ["Python", "Django", "React Native"]}
                    ]
                }
                return "", [{
                    "name": "generate_file",
                    "args": {"kind": "pdf", "name": "Rohit_Udamale_Updated_Resume.pdf", "based_on": "1", "spec": rev_spec},
                    "id": "call_rev_pdf",
                    "type": "tool_call",
                }]
            return "", [{
                "name": "generate_file",
                "args": {
                    "kind": "xlsx",
                    "name": "metrics.xlsx",
                    "based_on": "1",
                    "spec": {"headers": ["Month", "Users", "Churn"], "rows": [["Jan", 100, 5], ["Feb", 200, 8]]},
                },
                "id": "call_rev_0",
                "type": "tool_call",
            }]

        if "resume" in content:
            resume_spec = {
                "title": "Rohit L. Udamale",
                "subtitle": "Backend & React Native Developer",
                "header": ["9373369378", "rohitudamale777@gmail.com", "Mumbai, India", "LinkedIn", "GitHub"],
                "sections": [
                    {
                        "heading": "Summary",
                        "content": "Backend-focused Software Engineer with 2+ years building high-performance systems and React Native apps."
                    },
                    {
                        "heading": "Technical Skills",
                        "groups": [
                            {"label": "Backend:", "items": "Django, DRF, REST APIs, Celery, Java"},
                            {"label": "Mobile/Frontend:", "items": "React Native, React, JavaScript"}
                        ]
                    },
                    {
                        "heading": "Work Experience",
                        "entries": [
                            {
                                "title": "Solution Analyst",
                                "subtitle": "Sankey Solutions",
                                "date": "Sept 2024 - Present",
                                "bullets": [
                                    "Architected backend microservices with Django and DRF.",
                                    "Engineered React Native mobile components for client applications."
                                ]
                            }
                        ]
                    }
                ]
            }
            kind = "docx" if "docx" in content or "word" in content else "pdf"
            return "", [{
                "name": "generate_file",
                "args": {
                    "kind": kind,
                    "name": f"Rohit_Udamale_Updated_Resume.{kind}",
                    "spec": resume_spec,
                },
                "id": f"call_gen_resume_{kind}",
                "type": "tool_call",
            }]

        if "generate" in content or "create" in content:
            for k in ["docx", "pdf", "xlsx", "csv", "pptx", "png", "code", "md"]:
                if k in content or (k == "png" and "chart" in content) or (k == "code" and "python" in content):
                    spec_map = {
                        "md": {"title": "Doc", "content": "Sample markdown content"},
                        "csv": {"headers": ["A", "B"], "rows": [[1, 2]]},
                        "docx": {"title": "Docx Report", "paragraphs": ["Sample paragraph"]},
                        "pdf": {"title": "Pdf Doc", "paragraphs": ["Sample paragraph"]},
                        "xlsx": {"headers": ["Col1"], "rows": [["Val1"]]},
                        "pptx": {"title": "Presentation", "slides": [{"title": "Slide 1", "content": "Bullets"}]},
                        "png": {"chart_type": "bar", "labels": ["X"], "values": [10]},
                        "code": {"language": "python", "code": "def solve(): return 42"},
                    }
                    return "", [{
                        "name": "generate_file",
                        "args": {
                            "kind": k,
                            "name": f"test.{k if k != 'png' else 'png'}",
                            "spec": spec_map[k],
                        },
                        "id": f"call_gen_{k}",
                        "type": "tool_call",
                    }]
            return "", [{
                "name": "generate_file",
                "args": {
                    "kind": "md",
                    "name": "report.md",
                    "spec": {"title": "Generated Report", "content": "Automatic markdown generation by DeterministicFakeChatModel."},
                },
                "id": "call_gen_0",
                "type": "tool_call",
            }]

        if "read" in content or "what " in content or "uploaded" in content:
            return "", [{"name": "read_file", "args": {"file_id": "1"}, "id": "call_read_0", "type": "tool_call"}]

        return "This is a deterministic fake response.", None

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        content, tool_calls = self._determine_response(messages)
        message = AIMessage(
            content=content,
            tool_calls=tool_calls or [],
            usage_metadata={"input_tokens": 10, "output_tokens": 15, "total_tokens": 25},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        content, tool_calls = self._determine_response(messages)

        if tool_calls:
            # Yield tool call chunk
            for tc in tool_calls:
                chunk = AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": str(tc.get("args", {})).replace("'", '"'),
                            "id": tc["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                    ],
                    usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                )
                yield ChatGenerationChunk(message=chunk)
        else:
            # Yield streaming token chunks
            tokens = [t + " " for t in content.split()]
            for idx, token in enumerate(tokens):
                is_last = idx == len(tokens) - 1
                usage = {"input_tokens": 10, "output_tokens": len(tokens), "total_tokens": 10 + len(tokens)} if is_last else None
                chunk = AIMessageChunk(content=token, usage_metadata=usage)
                yield ChatGenerationChunk(message=chunk)

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        content, tool_calls = self._determine_response(messages)
        if tool_calls:
            for tc in tool_calls:
                chunk = AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": str(tc.get("args", {})).replace("'", '"'),
                            "id": tc["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                    ],
                )
                yield ChatGenerationChunk(message=chunk)
        else:
            for token in [t + " " for t in content.split()]:
                yield ChatGenerationChunk(message=AIMessageChunk(content=token))

def get_llm():
    """Initialize and return the configured chat model, using DeterministicFakeChatModel when FAKE_LLM=1 or during tests."""
    import sys
    if os.getenv("FAKE_LLM", "0").lower() in ("1", "true") or "test" in sys.argv:
        return DeterministicFakeChatModel()

    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    api_key = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    elif provider in ("google", "google_genai"):
        api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError(
            f"Missing credentials for {provider}. Set {provider.upper()}_API_KEY in your .env file, or set FAKE_LLM=1 for local development without an external API key."
        )

    max_output_tokens = int(os.getenv("MAX_OUTPUT_TOKENS", "4096"))
    kwargs = {"api_key": api_key, "max_tokens": max_output_tokens}
    return langchain_init_chat_model(model=model, model_provider=provider, **kwargs)
