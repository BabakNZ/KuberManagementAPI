import { Check, X } from "lucide-react";

export default function Toast({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="toast" role="status">
      <Check size={16} aria-hidden="true" />
      <span>{message}</span>
      <button aria-label="Dismiss notification" onClick={onDismiss}>
        <X size={14} />
      </button>
    </div>
  );
}
