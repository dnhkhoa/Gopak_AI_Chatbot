import { ChevronLeft, Menu, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import logoUrl from "../../assets/isoft-logo.png";
import type { ConversationPayload, HealthStatus } from "../../types/api";

interface Props {
  conversations: ConversationPayload[];
  activeId?: string | null;
  collapsed: boolean;
  health?: HealthStatus | null;
  onToggleCollapsed: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}

function Brand() {
  return (
    <div className="brand">
      <img className="brand-logo" src={logoUrl} alt="i-Soft" />
      <span className="brand-divider" aria-hidden="true" />
      <span className="brand-name">Gopak</span>
    </div>
  );
}

function HistoryItem(props: {
  item: ConversationPayload;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(props.item.title);
  const rowRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onAway = (event: MouseEvent) => {
      if (rowRef.current && !rowRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onAway);
    return () => document.removeEventListener("mousedown", onAway);
  }, [menuOpen]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commitRename = () => {
    const next = draft.trim();
    setEditing(false);
    if (next && next !== props.item.title) props.onRename(next);
    else setDraft(props.item.title);
  };

  return (
    <div ref={rowRef} className={props.active ? "conversation active" : "conversation"}>
      {editing ? (
        <input
          ref={inputRef}
          className="conversation-rename"
          value={draft}
          aria-label="Đổi tên conversation"
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") {
              setDraft(props.item.title);
              setEditing(false);
            }
          }}
        />
      ) : (
        <button className="conversation-title" onClick={props.onSelect} title={props.item.title}>
          {props.item.title}
        </button>
      )}

      {!editing ? (
        <button
          className="conversation-menu-btn"
          aria-label="Tùy chọn conversation"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <MoreHorizontal size={16} />
        </button>
      ) : null}

      {menuOpen ? (
        <div className="menu-popover" role="menu">
          <button
            className="menu-item"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              setDraft(props.item.title);
              setEditing(true);
            }}
          >
            <Pencil size={15} /> Đổi tên
          </button>
          <button
            className="menu-item danger"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              if (window.confirm(`Xóa "${props.item.title}"?`)) props.onDelete();
            }}
          >
            <Trash2 size={15} /> Xóa
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function ConversationSidebar(props: Props) {
  const degraded = Boolean(props.health && (!props.health.ollama_available || !props.health.memory_available));

  if (props.collapsed) {
    return (
      <aside className="sidebar collapsed">
        <button className="icon-button" onClick={props.onToggleCollapsed} aria-label="Mở sidebar">
          <Menu size={18} />
        </button>
        <button className="icon-button" onClick={props.onNew} aria-label="Chat mới">
          <Plus size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <Brand />
        <button className="icon-button" onClick={props.onToggleCollapsed} aria-label="Thu gọn sidebar">
          <ChevronLeft size={18} />
        </button>
      </div>

      <button className="new-chat" onClick={props.onNew}>
        <Plus size={17} />
        New chat
      </button>

      <div className="sidebar-section-label">History</div>
      <div className="conversation-list">
        {props.conversations.length ? (
          props.conversations.map((item) => (
            <HistoryItem
              key={item.id}
              item={item}
              active={item.id === props.activeId}
              onSelect={() => props.onSelect(item.id)}
              onDelete={() => props.onDelete(item.id)}
              onRename={(title) => props.onRename(item.id, title)}
            />
          ))
        ) : (
          <div className="empty-inline">Chưa có cuộc trò chuyện nào.</div>
        )}
      </div>

      <div className="sidebar-footer">
        {degraded ? <div className="system-warning">Hệ thống đang hoạt động hạn chế</div> : null}
      </div>
    </aside>
  );
}
