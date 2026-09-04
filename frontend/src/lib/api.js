export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const message =
      data !== null && typeof data === "object"
        ? Object.values(data).flat().join(" ")
        : data;
    throw new Error(message || response.statusText);
  }
  return data;
}

export function listData(data) {
  return data?.results || data || [];
}
