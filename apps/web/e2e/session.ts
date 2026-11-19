// A signed-in browser: supabase-js keeps its session in localStorage under sb-<host>-auth-token;
// the test puts one there before the page loads (the login page itself sends mail or goes to GitHub).
import type { Page } from "@playwright/test";

export type Session = {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  expires_in: number;
  token_type: "bearer";
  user: { id: string; email: string; aud: string; role: string };
};

export function storageKey(supabaseUrl: string): string {
  return `sb-${new URL(supabaseUrl).hostname.split(".")[0]}-auth-token`;
}

export async function signIn(page: Page, supabaseUrl: string, session: Session): Promise<void> {
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [storageKey(supabaseUrl), JSON.stringify(session)],
  );
}

export function fakeSession(): Session {
  const now = Math.floor(Date.now() / 1000);
  return {
    access_token: "test-access-token",
    refresh_token: "test-refresh-token",
    expires_at: now + 3600,
    expires_in: 3600,
    token_type: "bearer",
    user: { id: "00000000-0000-4000-8000-0000000000e2", email: "e2e@example.invalid", aud: "authenticated", role: "authenticated" },
  };
}
