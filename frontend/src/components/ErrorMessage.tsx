export function ErrorMessage({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="error-message">
      <span>{text}</span>
      {onRetry ? <button onClick={onRetry}>Thử lại</button> : null}
    </div>
  );
}
