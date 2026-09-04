import { readableStatus, statusTone } from "../lib/status";

export default function StatusBadge({ status = "Unknown" }) {
  return (
    <span className={`status-badge ${statusTone(status)}`}>
      <span aria-hidden="true" />
      {readableStatus(status)}
    </span>
  );
}
