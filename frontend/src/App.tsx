import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { ChatMessage } from "./components/ChatMessage";
import { ErrorMessage } from "./components/ErrorMessage";
import { ChatComposer } from "./features/chat/ChatComposer";
import { ConversationSidebar } from "./features/conversations/ConversationSidebar";
import { useLocalStorage } from "./hooks/useLocalStorage";
import type { ConversationPayload, HealthStatus, UiMessage } from "./types/api";

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
  const [debug, setDebug] = useLocalStorage("gopak:debug", false);
  const [collapsed, setCollapsed] = useLocalStorage("gopak:sidebar-collapsed", false);
  const [conversations, setConversations] = useState<ConversationPayload[]>([]);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextId, nextHealth] = await Promise.all([loadConversations(), api.health().catch(() => null)]);
      setHealth(nextHealth);
      await loadConversation(nextId);
    } catch {
      setError("Không thể kết nối với hệ thống xử lý.");
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
      setError("Không thể tải conversation.");
    }
  };

  const createConversation = async () => {
    const created = await api.createConversation();
    setConversations((current) => [created, ...current]);
    setSelectedId(created.id);
    setMessages([]);
  };

  const deleteConversation = async (id: string) => {
    await api.deleteConversation(id);
    const remaining = conversations.filter((item) => item.id !== id);
    setConversations(remaining);
    if (!remaining.length) {
      await createConversation();
      return;
    }
    await selectConversation(remaining[0].id);
  };

  const resetContext = async (id: string) => {
    await api.resetContext(id);
    await loadConversation(id);
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
      const response = await api.sendMessage(selectedId, message, debug);
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
      setError("Không thể kết nối với hệ thống xử lý.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="app-shell">
      <ConversationSidebar
        conversations={conversations}
        activeId={selectedId}
        collapsed={collapsed}
        debug={debug}
        health={health}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        onNew={() => void createConversation()}
        onSelect={(id) => void selectConversation(id)}
        onDelete={(id) => void deleteConversation(id)}
        onReset={(id) => void resetContext(id)}
        onDebugChange={setDebug}
      />
      <main className="chat-panel">
        <div className="chat-header">
          <div className="chat-title">{selected?.title ?? "Gopak"}</div>
        </div>
        <div className="message-scroll">
          {loading ? <div className="empty-state">Đang tải...</div> : null}
          {!loading && !messages.length ? <div className="empty-state">Tôi có thể giúp gì cho bạn?</div> : null}
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} debug={debug} />
          ))}
          {sending ? <div className="thinking">Đang phân tích...</div> : null}
          {error ? <ErrorMessage text={error} onRetry={() => void bootstrap()} /> : null}
        </div>
        <ChatComposer disabled={sending || !selectedId} onSend={sendMessage} />
      </main>
    </div>
  );
}
