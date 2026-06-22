export function ErrorMessage({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="error-message">
      <span>{text}</span>
      {onRetry ? <button onClick={onRetry}>Retry</button> : null}
    </div>
  );
}
