import { CircleAlert, X } from "lucide-react";

export default function AlertBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <CircleAlert size={18} aria-hidden="true" />
      <span>{message}</span>
      <button aria-label="Dismiss error" onClick={onDismiss}>
        <X size={15} />
      </button>
    </div>
  );
}
