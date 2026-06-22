import { ArrowUp, ArrowUpFromLine } from "lucide-react";
import { KeyboardEvent, useRef, useState } from "react";
import { UPLOAD_ACCEPT } from "../../types/files";

interface Props {
  disabled: boolean;
  onSend: (message: string) => void;
  onUpload?: (files: FileList) => void;
}

export function ChatComposer({ disabled, onSend, onUpload }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const submit = () => {
    const message = value.trim();
    if (!message || disabled) {
      return;
    }
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
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
      {onUpload ? (
        <>
          <button
            type="button"
            className="composer-upload"
            aria-label="Upload Excel file"
            title="Upload Excel file (.xlsx)"
            onClick={() => fileRef.current?.click()}
          >
            <ArrowUpFromLine size={18} />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept={UPLOAD_ACCEPT}
            hidden
            aria-label="Upload Excel file input"
            onChange={(event) => {
              if (event.target.files?.length) onUpload(event.target.files);
              event.target.value = "";
            }}
          />
        </>
      ) : null}

      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder=""
        aria-label="Message"
        onKeyDown={onKeyDown}
        onChange={(event) => {
          setValue(event.target.value);
          event.currentTarget.style.height = "auto";
          event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 180)}px`;
        }}
      />

      <button className="composer-send" aria-label="Send" disabled={disabled || !value.trim()} onClick={submit}>
        <ArrowUp size={18} />
      </button>
    </div>
  );
}
