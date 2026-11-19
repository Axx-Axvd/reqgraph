// The reqgraph API (apps/api) with the types generated from its OpenAPI description
// (src/lib/api-types.ts): if the API changes and this file does not, the build fails.
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./api-types";
import { accessToken } from "./supabase";

export type Project = components["schemas"]["ProjectOut"];
export type Run = components["schemas"]["RunOut"];
export type RunEvent = components["schemas"]["EventOut"];
export type Usage = components["schemas"]["UsageOut"];

export const OWN_KEY_HEADER = "X-OpenRouter-Key";

export function api(ownKey = "") {
  const client = createClient<paths>({
    baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
  });
  const auth: Middleware = {
    async onRequest({ request }) {
      const token = await accessToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      if (ownKey) request.headers.set(OWN_KEY_HEADER, ownKey);
      return request;
    },
  };
  client.use(auth);
  return client;
}

/** The text of an API error: FastAPI puts it in `detail` (a string, or a list for 422). */
export function errorText(error: unknown, fallback = "Не получилось. Попробуйте ещё раз."): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first.msg) return first.msg;
    }
  }
  return fallback;
}

export const STATUS: Record<Run["status"], string> = {
  queued: "в очереди",
  running: "агенты работают",
  waiting_input: "ждёт вашего ответа",
  succeeded: "завершён",
  failed: "ошибка",
  cancelled: "отменён",
};

export const AREAS: Record<string, string> = {
  goals: "цели",
  stakeholders: "участники",
  scenarios: "сценарии",
  exceptions: "исключения",
  data: "данные",
  rules: "правила",
  integrations: "интеграции",
  nfr: "качество",
  constraints: "ограничения",
};
