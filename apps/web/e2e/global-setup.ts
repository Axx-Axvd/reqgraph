// The stack mode: a test user in the local Supabase (service role of the local CLI, CI only) and
// its session for the browser, written to e2e/.session.json (ignored by git).
import { createClient } from "@supabase/supabase-js";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

export const SESSION_FILE = join(__dirname, ".session.json");

export default async function globalSetup(): Promise<void> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const service = process.env.E2E_SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !anon || !service) throw new Error("нужны NEXT_PUBLIC_SUPABASE_URL, ..._ANON_KEY и E2E_SUPABASE_SERVICE_ROLE_KEY");
  const email = `e2e-${Date.now()}@example.invalid`;
  const password = `e2e-${Math.random().toString(36).slice(2)}-Aa1!`;
  const admin = createClient(url, service, { auth: { persistSession: false } });
  const created = await admin.auth.admin.createUser({ email, password, email_confirm: true });
  if (created.error) throw created.error;
  const client = createClient(url, anon, { auth: { persistSession: false } });
  const signed = await client.auth.signInWithPassword({ email, password });
  if (signed.error || !signed.data.session) throw signed.error ?? new Error("нет сессии");
  writeFileSync(SESSION_FILE, JSON.stringify(signed.data.session));
}
