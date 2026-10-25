import React, { useState, useEffect, useCallback } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { useChatStream } from "./hooks/useChatStream";
import { initAuth, getToken, getUserInfo, handleAuthSessionExpired, login } from "./auth";

export default function App() {
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [user, setUser] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isLoadingThreads, setIsLoadingThreads] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  // Callback to update thread title in list when first message is sent
  const handleTitleGenerated = useCallback((prompt) => {
    const newTitle = prompt.slice(0, 50).trim() || "New Thread";
    setThreads((prev) =>
      prev.map((t) => (t.id === activeThreadId ? { ...t, title: newTitle } : t))
    );
  }, [activeThreadId]);

  const {
    messages,
    setMessages,
    isStreaming,
    statusText,
    error,
    send,
    stop,
    regenerate,
  } = useChatStream(activeThreadId, handleTitleGenerated);

  // Fetch threads list from backend API
  const fetchThreads = useCallback(async () => {
    try {
      setIsLoadingThreads(true);
      const token = await getToken();
      const res = await fetch("/api/threads/", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (res.status === 401) {
        handleAuthSessionExpired();
        return [];
      }
      if (res.ok) {
        const data = await res.json();
        setThreads(data);
        return data;
      }
    } catch (err) {
      console.warn("Could not load threads from API:", err);
    } finally {
      setIsLoadingThreads(false);
    }
    return [];
  }, []);

  // Fetch messages and generated files for a specific thread
  const loadThreadMessages = useCallback(async (threadId) => {
    if (!threadId) return;
    try {
      const token = await getToken();
      const [msgRes, genRes] = await Promise.all([
        fetch(`/api/threads/${threadId}/messages/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`/api/threads/${threadId}/generated/`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);

      let msgs = msgRes.ok ? await msgRes.json() : [];
      const genFiles = genRes.ok ? await genRes.json() : [];

      if (msgs.length > 0 && genFiles.length > 0) {
        // Map to latest version per file name so revised files update to latest version
        const latestGenMap = new Map();
        genFiles
          .filter((gf) => gf.kind !== "uploaded" && gf.download_url)
          .forEach((gf) => {
            const key = (gf.name || "").toLowerCase();
            if (!latestGenMap.has(key) || (latestGenMap.get(key).version || 0) < (gf.version || 0)) {
              latestGenMap.set(key, gf);
            }
          });
        const distinctGenFiles = Array.from(latestGenMap.values());

        // Attach distinct latest generated files to the last assistant message
        let lastAssistantIdx = -1;
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === "assistant") {
            lastAssistantIdx = i;
            break;
          }
        }

        if (lastAssistantIdx >= 0) {
          msgs = msgs.map((m, idx) =>
            idx === lastAssistantIdx
              ? { ...m, generatedFiles: distinctGenFiles }
              : m
          );
        }
      }

      setMessages(msgs);
    } catch (err) {
      console.warn("Failed to load thread messages:", err);
    }
  }, [setMessages]);

  // Initial authentication & thread reload on refresh
  useEffect(() => {
    async function setup() {
      setIsAuthLoading(true);
      const authenticated = await initAuth();
      setIsAuthenticated(authenticated);
      setIsAuthLoading(false);

      if (!authenticated) {
        return;
      }

      setUser(getUserInfo());

      const loadedThreads = await fetchThreads();
      const savedThreadId = localStorage.getItem("active_thread_id");

      if (savedThreadId && loadedThreads.some((t) => t.id === savedThreadId)) {
        setActiveThreadId(savedThreadId);
        loadThreadMessages(savedThreadId);
      } else if (loadedThreads.length > 0) {
        const firstId = loadedThreads[0].id;
        setActiveThreadId(firstId);
        localStorage.setItem("active_thread_id", firstId);
        loadThreadMessages(firstId);
      } else {
        // Create initial thread if none exists
        handleNewThread();
      }
    }
    setup();
  }, []);

  // When active thread changes, load its message history
  const handleSelectThread = useCallback(
    (threadId) => {
      if (threadId === activeThreadId) return;
      setActiveThreadId(threadId);
      localStorage.setItem("active_thread_id", threadId);
      loadThreadMessages(threadId);
    },
    [activeThreadId, loadThreadMessages]
  );

  // Create a new thread via API
  const handleNewThread = async () => {
    try {
      const token = await getToken();
      const res = await fetch("/api/threads/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title: "New Thread" }),
      });
      if (res.ok) {
        const newThread = await res.json();
        setThreads((prev) => [newThread, ...prev]);
        setActiveThreadId(newThread.id);
        localStorage.setItem("active_thread_id", newThread.id);
        setMessages([]);
      }
    } catch (err) {
      console.warn("Failed to create new thread:", err);
    }
  };

  // Delete a thread via API
  const handleDeleteThread = async (threadId) => {
    try {
      const token = await getToken();
      const res = await fetch(`/api/threads/${threadId}/`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (res.ok) {
        setThreads((prev) => prev.filter((t) => t.id !== threadId));
        if (activeThreadId === threadId) {
          const remaining = threads.filter((t) => t.id !== threadId);
          if (remaining.length > 0) {
            handleSelectThread(remaining[0].id);
          } else {
            handleNewThread();
          }
        }
      }
    } catch (err) {
      console.warn("Failed to delete thread:", err);
    }
  };

  const activeThread = threads.find((t) => t.id === activeThreadId);

  if (isAuthLoading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-card">
          <div className="auth-spinner"></div>
          <h2>Connecting to Keycloak...</h2>
          <p>Verifying secure identity session</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="auth-card-badge">Keycloak OIDC</div>
          <h1 className="auth-card-title">Chat-AI Platform</h1>
          <p className="auth-card-subtitle">
            Enterprise conversational AI with multi-tenant document intelligence. Sign in to access your chat history and files.
          </p>
          <div className="auth-card-actions">
            <button className="auth-login-btn" onClick={login}>
              Log In with Keycloak
            </button>
          </div>
          <div className="auth-card-hints">
            <p>Demo credentials: <code>demo</code> / <code>demo1234</code></p>
            <p>Or click <strong>Register</strong> on the Keycloak screen to create a new account.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Sidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
        onDeleteThread={handleDeleteThread}
        user={user}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      <ChatView
        thread={activeThread}
        messages={messages}
        isStreaming={isStreaming}
        statusText={statusText}
        error={error}
        onSend={send}
        onStop={stop}
        onRegenerate={regenerate}
        onRetry={regenerate}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
      />
    </div>
  );
}
