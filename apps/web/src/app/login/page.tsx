"use client";
import { useState, type FormEvent } from "react";

import { Disclaimer } from "@/components/Disclaimer";
import { supabase } from "@/lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const callback = () => `${window.location.origin}/auth/callback`;

  async function byEmail(e: FormEvent) {
    e.preventDefault();
    setError("");
    const { error } = await supabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: callback() },
    });
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
    <main className="page narrow">
      <h1>Вход</h1>
      <Disclaimer />
      <button type="button" className="button" onClick={byGithub}>Войти через GitHub</button>
      <form onSubmit={byEmail} className="stack">
        <label>
          Почта
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <button type="submit" className="button secondary">Прислать ссылку для входа</button>
      </form>
      {sent && <p className="ok">Ссылка отправлена на {email}. Откройте её в этом браузере.</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}
