"use client";
// After the magic link or GitHub: supabase-js exchanges the code in the URL for a session (PKCE).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { supabase } from "@/lib/supabase";

export default function Callback() {
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    const { data } = supabase().auth.onAuthStateChange((_event, session) => {
      if (session) router.replace("/projects");
    });
    supabase()
      .auth.getSession()
      .then(({ data: got, error }) => {
        if (error) setError(error.message);
        else if (got.session) router.replace("/projects");
      });
    return () => data.subscription.unsubscribe();
  }, [router]);
  return (
    <main className="page narrow">
      {error ? <p className="error">{error}</p> : <p className="muted">Входим…</p>}
    </main>
  );
}
