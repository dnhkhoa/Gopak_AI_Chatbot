import { useCallback, useEffect, useMemo, useState } from "react";
import logoUrl from "./assets/isoft-logo.png";
import { api } from "./api/client";
import { ChatMessage } from "./components/ChatMessage";
import { ErrorMessage } from "./components/ErrorMessage";
import { ChatComposer } from "./features/chat/ChatComposer";
import { ConversationSidebar } from "./features/conversations/ConversationSidebar";
import { UploadedFilesPanel } from "./features/files/UploadedFilesPanel";
import { useFiles } from "./hooks/useFiles";
import { useLocalStorage } from "./hooks/useLocalStorage";
import type { ConversationPayload, HealthStatus, UiMessage } from "./types/api";

// Developer tools (debug panel, raw metadata) are hidden from the customer UI by
// default; only enabled when VITE_ENABLE_DEVELOPER_TOOLS=true. The capability
// remains in the backend and components for evaluation / developer mode.
const DEVELOPER_TOOLS = import.meta.env.VITE_ENABLE_DEVELOPER_TOOLS === "true";

function toUiMessages(messages: { id?: string | null; role: string; content: string }[]): UiMessage[] {
  return messages
    .filter((item) => item.role === "user" || item.role === "assistant")
    .map((item, index) => ({
      id: item.id ?? `stored-${index}`,
      role: item.role as "user" | "assistant",
      content: item.content
    }));
}

export default function App() {
  const [selectedId, setSelectedId] = useLocalStorage<string | null>("gopak:selected-conversation", null);
  const [collapsed, setCollapsed] = useLocalStorage("gopak:sidebar-collapsed", false);
  const [conversations, setConversations] = useState<ConversationPayload[]>([]);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [activeFileName, setActiveFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const files = useFiles();

  const selected = useMemo(() => conversations.find((item) => item.id === selectedId), [conversations, selectedId]);

  const loadConversations = useCallback(async () => {
    const list = await api.listConversations();
    if (!list.length) {
      const created = await api.createConversation();
      setConversations([created]);
      setSelectedId(created.id);
      return created.id;
    }
    setConversations(list);
    const nextId = selectedId && list.some((item) => item.id === selectedId) ? selectedId : list[0].id;
    setSelectedId(nextId);
    return nextId;
  }, [selectedId, setSelectedId]);

  const loadConversation = useCallback(async (id: string) => {
    const detail = await api.getConversation(id);
    setMessages(toUiMessages(detail.messages));
    setActiveFileId(detail.active_file_id ?? null);
    setActiveFileName(detail.active_file_name ?? null);
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextId, nextHealth] = await Promise.all([loadConversations(), api.health().catch(() => null)]);
      setHealth(nextHealth);
      await loadConversation(nextId);
    } catch {
      setError("Unable to reach the analysis service.");
    } finally {
      setLoading(false);
    }
  }, [loadConversation, loadConversations]);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const selectConversation = async (id: string) => {
    setSelectedId(id);
    setError(null);
    try {
      await loadConversation(id);
    } catch {
      setError("Couldn't load this conversation.");
    }
  };

  const createConversation = async () => {
    const created = await api.createConversation();
    setConversations((current) => [created, ...current]);
    setSelectedId(created.id);
    setMessages([]);
    setActiveFileId(null);
    setActiveFileName(null);
  };

  const deleteConversation = async (id: string) => {
    await api.deleteConversation(id);
    const remaining = conversations.filter((item) => item.id !== id);
    setConversations(remaining);
    if (id !== selectedId) {
      return;
    }
    if (!remaining.length) {
      await createConversation();
      return;
    }
    await selectConversation(remaining[0].id);
  };

  const renameConversation = async (id: string, title: string) => {
    const updated = await api.renameConversation(id, title);
    setConversations((current) => current.map((item) => (item.id === id ? { ...item, ...updated } : item)));
  };

  const sendMessage = async (message: string) => {
    if (!selectedId || sending) {
      return;
    }
    const userMessage: UiMessage = { id: crypto.randomUUID(), role: "user", content: message };
    setMessages((current) => [...current, userMessage]);
    setSending(true);
    setError(null);
    try {
      const response = await api.sendMessage(selectedId, message, DEVELOPER_TOOLS);
      const assistantMessage: UiMessage = {
        id: response.message_id,
        role: "assistant",
        content: response.primary_value ?? response.summary ?? response.title,
        response
      };
      setMessages((current) => [...current, assistantMessage]);
      const refreshed = await api.listConversations();
      setConversations(refreshed);
    } catch {
      setError("Unable to reach the analysis service.");
    } finally {
      setSending(false);
    }
  };

  const selectActiveFile = async (fileId: string) => {
    if (!selectedId) return;
    setError(null);
    try {
      const active = await api.setActiveFile(selectedId, fileId);
      setActiveFileId(active.active_file_id ?? null);
      setActiveFileName(active.active_file_name ?? null);
      setConversations((current) =>
        current.map((item) =>
          item.id === selectedId
            ? { ...item, active_file_id: active.active_file_id ?? null, active_file_name: active.active_file_name ?? null }
            : item
        )
      );
    } catch {
      setError("Couldn't select this file.");
    }
  };

  const removeFile = async (fileId: string) => {
    await files.remove(fileId);
    if (activeFileId === fileId) {
      setActiveFileId(null);
      setActiveFileName(null);
    }
  };

  return (
    <div className="app-shell">
      <ConversationSidebar
        conversations={conversations}
        activeId={selectedId}
        collapsed={collapsed}
        health={health}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        onNew={() => void createConversation()}
        onSelect={(id) => void selectConversation(id)}
        onDelete={(id) => void deleteConversation(id)}
        onRename={(id, title) => void renameConversation(id, title)}
      />
      <main className="chat-panel">
        <div className="chat-header">
          <div className="chat-title">{selected?.title ?? "Gopak"}</div>
        </div>
        <div className="message-scroll">
          {loading ? (
            <div className="empty-state">
              <div className="empty-sub">Loading…</div>
            </div>
          ) : null}
          {!loading && !messages.length ? (
            <div className="empty-state">
              <img className="empty-logo" src={logoUrl} alt="i-Soft" />
              <div className="empty-title">How can I help you?</div>
              <div className="empty-sub">Ask questions about your data.</div>
            </div>
          ) : null}
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} debug={DEVELOPER_TOOLS} />
          ))}
          {sending ? (
            <div className="thinking">
              <span className="dots"><span /><span /><span /></span>
              Analyzing…
            </div>
          ) : null}
          {error ? <ErrorMessage text={error} onRetry={() => void bootstrap()} /> : null}
        </div>
        <div className="composer-wrap">
          {activeFileName ? (
            <div className="active-file-pill">Using: {activeFileName}</div>
          ) : null}
          <ChatComposer disabled={sending || !selectedId} onSend={sendMessage} onUpload={(list) => void files.upload(list)} />
        </div>
      </main>
      <UploadedFilesPanel files={{ ...files, remove: removeFile }} activeFileId={activeFileId} onSelectActive={(id) => void selectActiveFile(id)} />
    </div>
  );
}
