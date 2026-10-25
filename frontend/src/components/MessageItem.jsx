import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, RotateCcw, AlertTriangle } from "lucide-react";
import { CodeBlock } from "./CodeBlock";
import { FileChip } from "./FileChip";
import { FileCard } from "./FileCard";

export function MessageItem({
  message,
  isLast,
  isStreaming,
  statusText,
  onRegenerate,
  onRetry,
}) {
  const isUser = message.role === "user";
  const isInterrupted = message.status === "interrupted";
  const isStopped = message.status === "stopped";
  const isCurrentlyStreaming = isLast && isStreaming && message.role === "assistant";

  // Only show file chips on the message they were attached to
  const userFiles = isUser && Array.isArray(message.files)
    ? message.files.filter((f) => !f.message || String(f.message) === String(message.id))
    : [];
  const generatedFiles = !isUser && Array.isArray(message.generatedFiles) ? message.generatedFiles : [];

  // Defensively strip any raw untrusted_file_content tags so user never sees corrupted XML wrappers
  const cleanContent = React.useMemo(() => {
    const raw = message.content || "";
    if (isUser || !raw.includes("<untrusted_file_content")) return raw;
    let cleaned = raw.replace(/<untrusted_file_content[\s\S]*?<\/untrusted_file_content>\s*/gi, "").trim();
    cleaned = cleaned.replace(/<untrusted_file_content[\s\S]*$/gi, "").trim();
    return cleaned || raw;
  }, [message.content, isUser]);

  return (
    <div className={`message-row ${message.role}`}>
      {!isUser && (
        <div className="message-avatar ai-avatar">
          <Bot size={18} />
        </div>
      )}

      <div className="message-bubble">
        {isUser ? (
          <div>
            {userFiles.length > 0 && (
              <div className="message-user-files">
                {userFiles.map((f, idx) => (
                  <FileChip key={f.id || idx} file={f} readOnly />
                ))}
              </div>
            )}
            {message.content && <div>{message.content}</div>}
          </div>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");

                  if (!inline && match) {
                    return <CodeBlock language={match[1]} value={codeString} />;
                  }
                  return (
                    <code className="inline-code" {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {cleanContent}
            </ReactMarkdown>

            {generatedFiles.length > 0 && (
              <div className="message-generated-files">
                {generatedFiles.map((gf) => (
                  <FileCard
                    key={gf.id || gf.name}
                    file={gf}
                    isStreaming={isCurrentlyStreaming}
                  />
                ))}
              </div>
            )}

            {isCurrentlyStreaming && <span className="streaming-cursor" />}

            {/* Status Line badge while streaming */}
            {isCurrentlyStreaming && statusText && (
              <div className="status-line">
                <div className="status-spinner" />
                <span>{statusText}</span>
              </div>
            )}

            {/* Interrupted stream state with Retry button */}
            {isInterrupted && (
              <div className="interrupted-box">
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <AlertTriangle size={14} />
                  <span>Stream was interrupted</span>
                </div>
                {onRetry && (
                  <button className="retry-interrupted-btn" onClick={onRetry}>
                    <RotateCcw size={12} />
                    <span>Retry</span>
                  </button>
                )}
              </div>
            )}

            {/* Stopped by user badge */}
            {isStopped && (
              <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--text-muted)", fontStyle: "italic" }}>
                Generation stopped by user
              </div>
            )}

            {/* Regenerate button on the last assistant message (when not streaming) */}
            {isLast && !isStreaming && onRegenerate && (
              <div className="message-actions">
                <button
                  className="regenerate-btn"
                  onClick={onRegenerate}
                  title="Regenerate this response"
                >
                  <RotateCcw size={13} />
                  <span>Regenerate</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="message-avatar user-avatar">
          <User size={18} />
        </div>
      )}
    </div>
  );
}
