"use client";
// A signed-in page: the session check, the top bar (usage, own key, sign out) and the content.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { api, type Usage } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const { key, setKey } = useOwnKey();

  useEffect(() => {
    let alive = true;
    supabase()
      .auth.getSession()
      .then(({ data }) => {
        if (!alive) return;
        if (!data.session) router.replace("/login");
        else setReady(true);
      });
    return () => {
      alive = false;
    };
  }, [router]);

  useEffect(() => {
    if (!ready) return;
    api()
      .GET("/usage")
      .then(({ data }) => setUsage(data ?? null));
  }, [ready]);

  if (!ready) return <main className="page"><p className="muted">Проверяем вход…</p></main>;

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  const left = usage && usage.runs_limit !== null ? usage.runs_limit - usage.runs_today : null;
  return (
    <>
      <header className="topbar">
        <Link href="/projects" className="brand">reqgraph</Link>
        <span className="usage" data-testid="usage">
          {usage === null
            ? ""
            : usage.unlimited
              ? "без лимита"
              : `осталось прогонов сегодня: ${Math.max(0, left ?? 0)} из ${usage.runs_limit}`}
        </span>
        <label className="own-key">
          <span>Свой ключ OpenRouter</span>
          <input
            type="password"
            autoComplete="off"
            placeholder="необязательно"
            value={key}
            onChange={(e) => setKey(e.target.value.trim())}
            aria-describedby="own-key-hint"
          />
        </label>
        <button type="button" className="link" onClick={signOut}>Выйти</button>
      </header>
      <p id="own-key-hint" className="hint">
        Ключ хранится только в этой вкладке и уходит с запуском и ответами; со своим ключом лимиты
        демо не действуют, платите вы.
      </p>
      <main className="page">{children}</main>
    </>
  );
}
