export function statusTone(status) {
  const value = String(status || "").toLowerCase();
  if (["active", "running", "ready"].some((item) => value.includes(item))) {
    return "success";
  }
  if (["creating", "updating", "pending"].some((item) => value.includes(item))) {
    return "warning";
  }
  if (["failed", "error", "deleting"].some((item) => value.includes(item))) {
    return "danger";
  }
  return "neutral";
}

export function readableStatus(status = "Unknown") {
  return String(status).replaceAll("_", " ");
}
