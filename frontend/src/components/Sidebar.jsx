import React from "react";
import { MessageSquarePlus, Trash2, X, MessageSquare, LogOut, Sparkles } from "lucide-react";
import { logout } from "../auth";

export function Sidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  user,
  isOpen,
  onClose,
}) {
  return (
    <>
      {isOpen && <div className="sidebar-backdrop" onClick={onClose} />}

      <aside className={`sidebar ${isOpen ? "open" : ""}`}>
        <div className="sidebar-header">
          <div className="brand-badge">
            <div className="brand-icon">
              <Sparkles size={16} />
            </div>
            <span>Chat AI</span>
          </div>
          {isOpen && (
            <button
              className="mobile-menu-btn"
              onClick={onClose}
              style={{ display: "flex" }}
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
          )}
        </div>

        <button className="new-chat-btn" onClick={onNewThread}>
          <MessageSquarePlus size={16} />
          <span>New Chat</span>
        </button>

        <div className="threads-list">
          <span className="threads-label">Recent Conversations</span>

          {threads.length === 0 ? (
            <div style={{ padding: "12px 6px", fontSize: "13px", color: "var(--text-muted)" }}>
              No conversations yet. Start a new chat!
            </div>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                className={`thread-item ${t.id === activeThreadId ? "active" : ""}`}
                onClick={() => {
                  onSelectThread(t.id);
                  if (onClose) onClose();
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden", flex: 1, minWidth: 0 }}>
                  <MessageSquare size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
                  <span className="thread-title">{t.title || "Untitled Conversation"}</span>
                </div>
                {t.total_tokens > 0 && (
                  <span className="thread-tokens-badge" title={`${t.total_tokens} total tokens`}>
                    {t.total_tokens.toLocaleString()} t
                  </span>
                )}
                <button
                  className="thread-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(t.id);
                  }}
                  title="Delete conversation"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="user-avatar">
              {(user?.username || "U")[0].toUpperCase()}
            </div>
            <div className="user-info">
              <span className="user-name">{user?.username || "Demo User"}</span>
              <span className="user-email">{user?.email || "demo@example.com"}</span>
            </div>
          </div>
          <button
            onClick={logout}
            className="thread-delete-btn"
            style={{ opacity: 1 }}
            title="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
    </>
  );
}
