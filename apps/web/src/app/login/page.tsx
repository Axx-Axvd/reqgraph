"use client";
// Sign-in (T-509, board «Вход»): GitHub or a link by e-mail; on the left — the promise and how the words
// become a ТЗ (a graph that assembles once; with «reduce motion» it is drawn at once).
import { useState, type FormEvent } from "react";

import { Disclaimer } from "@/components/Disclaimer";
import { SiteHeader } from "@/components/SiteHeader";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const callback = () => `${window.location.origin}/auth/callback`;

  async function byEmail(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const { error } = await supabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: callback() },
    });
    setBusy(false);
    if (error) setError(error.message);
    else setSent(true);
  }

  async function byGithub() {
    setError("");
    const { error } = await supabase().auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: callback() },
    });
    if (error) setError(error.message);
  }

  return (
    <>
      <SiteHeader signIn={false} />
      <main className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-12 px-5 pt-6 pb-16 sm:px-6">
        <section className="flex min-w-0 flex-[1_1_480px] flex-col gap-6 max-sm:hidden">
          <h2 className="m-0 font-display text-[clamp(30px,6vw,46px)] leading-[1.06] font-extrabold tracking-[-0.035em]">
            Расскажите о своём деле. <span className="text-coral">Техническое задание</span> мы напишем сами.
          </h2>
          <svg viewBox="0 0 560 220" className="login-graph w-full max-w-[560px]" aria-hidden="true">
            {[
              "M38 128 C 90 120, 100 62, 143 58",
              "M39 130 C 95 130, 120 120, 161 120",
              "M38 133 C 90 145, 100 180, 139 180",
              "M157 58 C 205 58, 215 79, 258 79",
              "M175 120 C 215 120, 222 141, 258 141",
              "M153 180 C 210 180, 222 148, 258 145",
              "M322 79 C 372 79, 392 108, 440 108",
              "M322 141 C 372 141, 392 116, 440 116",
            ].map((d, i) => (
              <path key={d} d={d} pathLength={1} fill="none" stroke="var(--line-2)" strokeWidth="1.6" style={{ animationDelay: `${0.2 + i * 0.12}s` }} />
            ))}
            <circle cx="30" cy="130" r="9" fill="var(--coral)" />
            {[
              [150, 58],
              [168, 120],
              [146, 180],
            ].map(([x, y], i) => (
              <circle key={x} cx={x} cy={y} r="7" fill="var(--surface)" stroke="var(--mint)" strokeWidth="1.8" style={{ animationDelay: `${0.6 + i * 0.1}s` }} />
            ))}
            <rect x="258" y="64" width="64" height="30" rx="8" fill="var(--raised)" stroke="var(--line-2)" />
            <rect x="258" y="126" width="64" height="30" rx="8" fill="var(--raised)" stroke="var(--line-2)" />
            <path d="M440 50 H 520 L 536 66 V 174 H 440 Z" fill="var(--paper)" />
            {[72, 88, 98, 108, 124, 134, 144].map((y, i) => (
              <rect key={y} x="452" y={y} width={[50, 70, 62, 72, 44, 66, 58][i]} height={i === 0 ? 6 : 4} rx="2" fill={i === 0 ? "#1b1d26" : "#b9b2a5"} />
            ))}
            <circle cx="532" cy="54" r="12" fill="var(--mint)" />
            <path d="M526 54 l4 4 8-9" fill="none" stroke="#16302a" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="m-0 text-sm text-muted">Каждый пункт ТЗ связан с вашими словами и проверен кодом.</p>
        </section>

        <section className="flex min-w-0 flex-[1_1_min(380px,100%)] justify-center">
          <div className="sg-rise flex w-full max-w-[420px] flex-col gap-4 rounded-[22px] border border-line bg-surface p-7 shadow-(--shadow)">
            <h1 className="m-0 font-display text-2xl font-bold tracking-tight sm:text-[24px]">Вход</h1>
            <Button type="button" size="lg" className="bg-fg text-bg" onClick={byGithub}>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5z" />
              </svg>
              Войти через GitHub
            </Button>
            <div className="flex items-center gap-3 text-[13px] text-dim">
              <span className="h-px flex-1 bg-line" />
              или ссылкой на почту
              <span className="h-px flex-1 bg-line" />
            </div>
            <form onSubmit={byEmail} className="flex flex-col gap-3">
              <label>
                Почта
                <input type="email" required autoComplete="email" placeholder="name@example.ru" value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <Button type="submit" size="lg" disabled={busy}>
                {busy ? "Отправляем…" : "Прислать ссылку для входа"}
              </Button>
            </form>
            {sent && (
              <p className="ok m-0" role="status">
                Ссылка отправлена на {email}. Откройте её в этом браузере.
              </p>
            )}
            {error && (
              <p className="error m-0" role="alert">
                {error}
              </p>
            )}
            <Disclaimer />
          </div>
        </section>
      </main>
    </>
  );
}
