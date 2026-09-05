import axios from "axios";
import { storage } from "@/src/utils/storage";

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const TOKEN_KEY = "traap_admin_token";

export const api = axios.create({ baseURL: API_BASE, timeout: 60000 });

api.interceptors.request.use(async (cfg) => {
  const token = await storage.secureGet<string>(TOKEN_KEY, "");
  if (token) {
    cfg.headers = cfg.headers ?? {};
    cfg.headers.Authorization = `Bearer ${token}`;
  }
  return cfg;
});

// SSE streaming helper for Carmelo endpoints. React Native fetch buffers the
// whole streamed body then resolves; we parse the accumulated `data:` events.
export async function streamCarmelo(
  path: string,
  body: unknown,
  onDelta: (chunk: string, full: string) => void,
): Promise<string> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let full = "";
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const raw = trimmed.slice(5).trim();
    if (!raw) continue;
    try {
      const parsed = JSON.parse(raw);
      const chunk = parsed?.data ?? "";
      if (chunk) {
        full += chunk;
        onDelta(chunk, full);
      }
    } catch {
      // ignore non-json keepalive lines
    }
  }
  return full;
}
