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

            if is_error and tool_error_count < 3:
                # Retry by emitting another tool call
                return "", [{"name": "failing_tool", "args": {"query": f"retry_{tool_error_count}"}, "id": f"call_err_{tool_error_count}", "type": "tool_call"}]
            if tool_error_count >= 3:
                return "Tool execution failed after 3 consecutive attempts. Stopping loop and explaining failure.", None
            return f"Processed tool output: {last_msg.content}. Completed.", None

        # Check user message text
        content = str(getattr(last_msg, "content", "")).lower()
        if "fail tool" in content or "error tool" in content:
            return "", [{"name": "failing_tool", "args": {"query": "fail"}, "id": "call_err_0", "type": "tool_call"}]
        if "generate" in content or "create file" in content:
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
        if "call tool" in content or "test tool" in content:
            return "", [{"name": "search_web", "args": {"query": "test query"}, "id": "call_web_0", "type": "tool_call"}]

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

    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key

    return langchain_init_chat_model(model=model, model_provider=provider, **kwargs)
