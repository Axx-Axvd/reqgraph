"use client";
// A signed-in page: the session check, the header (usage, own key, theme, sign out) and the content.
import { KeyRound, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Loading } from "@/components/ui/skeleton";
import { api, type Usage } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const { key, setKey, asking, ask } = useOwnKey();

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

  if (!ready)
    return (
      <main className="page">
        <Loading label="Проверяем вход…" />
      </main>
    );

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  const left = usage && usage.runs_limit !== null ? usage.runs_limit - usage.runs_today : null;
  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex min-h-[60px] max-w-[1100px] flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2">
          <Link href="/projects" aria-label="reqgraph — к проектам" className="inline-flex min-h-11 items-center text-fg no-underline">
            <Logo />
          </Link>
          <span className="ml-auto text-[13px] text-muted max-sm:order-last max-sm:ml-0 max-sm:basis-full" data-testid="usage">
            {usage === null
              ? ""
              : usage.unlimited
                ? "без лимита"
                : `осталось прогонов сегодня: ${Math.max(0, left ?? 0)} из ${usage.runs_limit}`}
          </span>
          <span className="flex-1 sm:hidden" aria-hidden="true" />
          <Dialog open={asking} onOpenChange={ask}>
            <DialogTrigger asChild>
              <Button variant="quiet" size="sm" aria-label="Свой ключ OpenRouter">
                <KeyRound aria-hidden="true" />
                <span className="max-sm:sr-only">{key ? "Свой ключ задан" : "Свой ключ"}</span>
              </Button>
            </DialogTrigger>
            <DialogContent
              title="Свой ключ OpenRouter"
              description="Необязательно. Ключ хранится только в этой вкладке и уходит с запуском и ответами; со своим ключом лимиты демо не действуют, платите вы."
            >
              <label>
                Ключ
                <input
                  type="password"
                  autoComplete="off"
                  placeholder="sk-or-…"
                  value={key}
                  onChange={(e) => setKey(e.target.value.trim())}
                />
              </label>
            </DialogContent>
          </Dialog>
          <ThemeToggle />
          <Button variant="quiet" size="sm" onClick={signOut}>
            <LogOut aria-hidden="true" />
            <span className="max-sm:sr-only">Выйти</span>
          </Button>
        </div>
      </header>
      <main className="page sg-rise">{children}</main>
    </>
  );
}
