import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Square,
  Menu,
  ChevronDown,
  Sparkles,
  AlertCircle,
  RotateCcw,
} from "lucide-react";
import { MessageItem } from "./MessageItem";

export function ChatView({
  thread,
  messages,
  isStreaming,
  statusText,
  error,
  onSend,
  onStop,
  onRegenerate,
  onRetry,
  onToggleSidebar,
}) {
  const [inputText, setInputText] = useState("");
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);
  const textareaRef = useRef(null);

  // Auto-scroll handler detecting user manual scroll
  const handleScroll = () => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 80;
    shouldAutoScrollRef.current = isAtBottom;
    setShowScrollBottom(!isAtBottom);
  };

  // Scroll to bottom when new messages or tokens arrive if auto-scroll is enabled
  useEffect(() => {
    if (shouldAutoScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({
        behavior: isStreaming ? "auto" : "smooth",
      });
    }
  }, [messages, isStreaming, statusText]);

  const scrollToBottom = () => {
    shouldAutoScrollRef.current = true;
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    setShowScrollBottom(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!inputText.trim() || isStreaming) return;
    onSend(inputText.trim());
    setInputText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleStarterClick = (prompt) => {
    onSend(prompt);
  };

  const handleTextareaInput = (e) => {
    setInputText(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  return (
    <main className="chat-main">
      {/* Top Navbar */}
      <header className="chat-navbar">
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <button
            className="mobile-menu-btn"
            onClick={onToggleSidebar}
            aria-label="Toggle navigation menu"
          >
            <Menu size={20} />
          </button>
          <span className="current-thread-title">
            {thread?.title || "New Conversation"}
          </span>
        </div>
      </header>

      {/* Error Banner with Retry */}
      {error && (
        <div className="error-banner">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
          {onRetry && (
            <button className="error-banner-retry-btn" onClick={onRetry}>
              <RotateCcw size={12} style={{ marginRight: "4px" }} />
              Retry
            </button>
          )}
        </div>
      )}

      {/* Messages Scroll Area */}
      <div
        className="messages-container"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Sparkles size={28} />
            </div>
            <h1 className="empty-title">What would you like to build?</h1>
            <p className="empty-desc">
              Ask questions, execute workflows, and collaborate with your stateful AI pair programmer.
            </p>
            <div className="starter-grid">
              <div
                className="starter-card"
                onClick={() =>
                  handleStarterClick("Explain python generators vs async generators with code examples.")
                }
              >
                Explain Python generators vs async generators
              </div>
              <div
                className="starter-card"
                onClick={() =>
                  handleStarterClick("How does LangGraph state machine with checkpointing work?")
                }
              >
                How does LangGraph checkpointing work?
              </div>
              <div
                className="starter-card"
                onClick={() =>
                  handleStarterClick("Write a python script with a tool that simulates file processing.")
                }
              >
                Python script with tool execution
              </div>
              <div
                className="starter-card"
                onClick={() =>
                  handleStarterClick("Design a clean microservice architecture with Keycloak auth.")
                }
              >
                Microservice architecture with Keycloak
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, index) => {
            const isLast = index === messages.length - 1;
            return (
              <MessageItem
                key={msg.id || index}
                message={msg}
                isLast={isLast}
                isStreaming={isStreaming}
                statusText={statusText}
                onRegenerate={isLast ? onRegenerate : null}
                onRetry={msg.status === "interrupted" ? onRegenerate : null}
              />
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Scroll to Bottom Floating Button */}
      {showScrollBottom && (
        <button
          className="scroll-bottom-btn"
          onClick={scrollToBottom}
          title="Scroll to latest messages"
        >
          <ChevronDown size={18} />
        </button>
      )}

      {/* Input Composer */}
      <div className="input-area">
        <div className="input-box-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            placeholder="Send a message (Enter to send, Shift+Enter for new line)..."
            rows={1}
            value={inputText}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
          />
          <div className="input-bottom-row">
            <span className="input-hint">
              {isStreaming ? (
                <span style={{ color: "var(--accent-primary)" }}>Streaming response...</span>
              ) : (
                "Markdown & code blocks supported"
              )}
            </span>
            <div className="input-actions">
              {isStreaming ? (
                <button className="stop-btn" onClick={onStop} title="Stop response generation">
                  <Square size={13} fill="currentColor" />
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  className="send-btn"
                  onClick={handleSubmit}
                  disabled={!inputText.trim()}
                  title="Send message"
                >
                  <Send size={15} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
