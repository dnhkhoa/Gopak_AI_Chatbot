import { Bug, ChevronLeft, ChevronRight, Plus, RotateCcw, Trash2 } from "lucide-react";
import type { ConversationPayload, HealthStatus } from "../../types/api";

interface Props {
  conversations: ConversationPayload[];
  activeId?: string | null;
  collapsed: boolean;
  debug: boolean;
  health?: HealthStatus | null;
  onToggleCollapsed: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onReset: (id: string) => void;
  onDebugChange: (debug: boolean) => void;
}

export function ConversationSidebar(props: Props) {
  const active = props.conversations.find((item) => item.id === props.activeId);
  if (props.collapsed) {
    return (
      <aside className="sidebar collapsed">
        <button className="icon-button" onClick={props.onToggleCollapsed} aria-label="Mở sidebar">
          <ChevronRight size={18} />
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
        <div className="brand">Gopak</div>
        <button className="icon-button" onClick={props.onToggleCollapsed} aria-label="Thu gọn sidebar">
          <ChevronLeft size={18} />
        </button>
      </div>
      <button className="new-chat" onClick={props.onNew}>
        <Plus size={16} />
        Chat mới
      </button>
      <div className="conversation-list">
        {props.conversations.map((item) => (
          <button
            key={item.id}
            className={item.id === props.activeId ? "conversation active" : "conversation"}
            onClick={() => props.onSelect(item.id)}
            title={item.title}
          >
            {item.title}
          </button>
        ))}
      </div>
      <div className="sidebar-footer">
        {props.health && (!props.health.ollama_available || !props.health.memory_available) ? (
          <div className="system-warning">Hệ thống đang degraded</div>
        ) : null}
        <div className="side-actions">
          <button className="icon-button" disabled={!active} onClick={() => active && props.onReset(active.id)} aria-label="Reset context">
            <RotateCcw size={16} />
          </button>
          <button className="icon-button" disabled={!active} onClick={() => active && props.onDelete(active.id)} aria-label="Xóa conversation">
            <Trash2 size={16} />
          </button>
          <label className="debug-toggle">
            <Bug size={16} />
            <input type="checkbox" checked={props.debug} onChange={(event) => props.onDebugChange(event.target.checked)} />
          </label>
        </div>
      </div>
    </aside>
  );
}
