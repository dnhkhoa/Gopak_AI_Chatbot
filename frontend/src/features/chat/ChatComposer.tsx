import { ArrowUp } from "lucide-react";
import { KeyboardEvent, useRef, useState } from "react";

export function ChatComposer({ disabled, onSend }: { disabled: boolean; onSend: (message: string) => void }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const submit = () => {
    const message = value.trim();
    if (!message || disabled) {
      return;
    }
    setValue("");
    onSend(message);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder=""
        aria-label="Tin nhắn"
        onKeyDown={onKeyDown}
        onChange={(event) => {
          setValue(event.target.value);
          event.currentTarget.style.height = "auto";
          event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 180)}px`;
        }}
      />
      <button className="composer-send" aria-label="Gửi" disabled={disabled || !value.trim()} onClick={submit}>
        <ArrowUp size={18} />
      </button>
    </div>
  );
}
