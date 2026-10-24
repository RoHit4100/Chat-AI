import { useState, useRef, useCallback } from "react";
import { getToken } from "../auth";

export function useChatStream(threadId, onTitleGenerated) {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [activeFiles, setActiveFiles] = useState([]);
  const [error, setError] = useState(null);

  const abortControllerRef = useRef(null);

  const formatStatus = (node) => {
    switch (node) {
      case "prepare":
        return "Preparing files & context...";
      case "agent":
        return "Thinking & generating...";
      case "tools":
        return "Executing tool...";
      case "summarize":
        return "Updating conversation summary...";
      default:
        return `Processing (${node})...`;
    }
  };

  const processStreamReader = async (response, isRegenerate = false) => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let receivedDone = false;

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";

        for (const block of blocks) {
          const trimmed = block.trim();
          if (!trimmed || trimmed.startsWith(":")) {
            // Heartbeat comment
            continue;
          }

          let eventName = "message";
          let dataText = "";

          const lines = block.split("\n");
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventName = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              dataText += line.slice(6);
            }
          }

          let parsedData = {};
          try {
            parsedData = dataText ? JSON.parse(dataText) : {};
          } catch (e) {
            console.warn("Failed to parse SSE JSON data:", dataText);
          }

          if (eventName === "token") {
            const tokenContent = parsedData.content || "";
            setMessages((prev) => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                updated[lastIdx] = {
                  ...updated[lastIdx],
                  content: updated[lastIdx].content + tokenContent,
                  status: "streaming",
                };
              }
              return updated;
            });
          } else if (eventName === "status") {
            if (parsedData.node) {
              setStatusText(formatStatus(parsedData.node));
            }
          } else if (eventName === "file") {
            setActiveFiles((prev) => [...prev, parsedData]);
          } else if (eventName === "done") {
            receivedDone = true;
            setStatusText("");
            setMessages((prev) => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                updated[lastIdx] = {
                  ...updated[lastIdx],
                  status: "complete",
                };
              }
              return updated;
            });
          } else if (eventName === "error") {
            setError(parsedData.error || "An error occurred during streaming.");
            setMessages((prev) => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                updated[lastIdx] = {
                  ...updated[lastIdx],
                  status: "failed",
                };
              }
              return updated;
            });
          }
        }
      }

      // If stream ended without a done event and was not explicitly aborted, mark as interrupted
      if (!receivedDone) {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant" && updated[lastIdx].status !== "complete") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              status: "interrupted",
            };
          }
          return updated;
        });
      }
    } catch (err) {
      if (err.name === "AbortError") {
        // User aborted the stream via Stop button
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              status: "stopped",
            };
          }
          return updated;
        });
      } else {
        setError(err.message || "Network error while reading stream.");
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              status: "interrupted",
            };
          }
          return updated;
        });
      }
    } finally {
      setIsStreaming(false);
      setStatusText("");
      abortControllerRef.current = null;
    }
  };

  const send = useCallback(
    async (userText) => {
      if (!userText.trim() || !threadId || isStreaming) return;

      setError(null);
      setIsStreaming(true);
      setStatusText("Connecting to stream...");

      // Append user message and new assistant message placeholder
      setMessages((prev) => [
        ...prev,
        { id: "usr-" + Date.now(), role: "user", content: userText },
        { id: "ast-" + Date.now(), role: "assistant", content: "", status: "streaming" },
      ]);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const token = await getToken();
        const response = await fetch(`/api/threads/${threadId}/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ message: userText }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const errBody = await response.text();
          let msg = `Request failed (${response.status})`;
          try {
            const parsed = JSON.parse(errBody);
            msg = parsed.detail || msg;
          } catch (e) {
            msg = errBody || msg;
          }
          throw new Error(msg);
        }

        // Trigger callback to reload thread title if first message
        if (onTitleGenerated) onTitleGenerated(userText);

        await processStreamReader(response, false);
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message);
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
              updated[lastIdx] = {
                ...updated[lastIdx],
                status: "failed",
              };
            }
            return updated;
          });
        }
        setIsStreaming(false);
        setStatusText("");
        abortControllerRef.current = null;
      }
    },
    [threadId, isStreaming, onTitleGenerated]
  );

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setStatusText("");
  }, []);

  const regenerate = useCallback(async () => {
    if (!threadId || isStreaming) return;

    setError(null);
    setIsStreaming(true);
    setStatusText("Regenerating response...");

    // Reset last assistant message content
    setMessages((prev) => {
      const updated = [...prev];
      const lastIdx = updated.length - 1;
      if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
        updated[lastIdx] = {
          ...updated[lastIdx],
          content: "",
          status: "streaming",
        };
      }
      return updated;
    });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const token = await getToken();
      const response = await fetch(`/api/threads/${threadId}/regenerate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        const errBody = await response.text();
        let msg = `Regenerate failed (${response.status})`;
        try {
          const parsed = JSON.parse(errBody);
          msg = parsed.detail || msg;
        } catch (e) {
          msg = errBody || msg;
        }
        throw new Error(msg);
      }

      await processStreamReader(response, true);
    } catch (err) {
      if (err.name !== "AbortError") {
        setError(err.message);
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              status: "interrupted",
            };
          }
          return updated;
        });
      }
      setIsStreaming(false);
      setStatusText("");
      abortControllerRef.current = null;
    }
  }, [threadId, isStreaming]);

  return {
    messages,
    setMessages,
    isStreaming,
    statusText,
    activeFiles,
    error,
    send,
    stop,
    regenerate,
    clearError: () => setError(null),
  };
}
