"use client";
// Something broke in the page itself (T-512): say so plainly and offer to try again.
import Link from "next/link";

import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";

export default function PageError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-[80vh] max-w-[560px] flex-col items-start justify-center gap-5 px-5">
      <Logo />
      <h1 className="m-0">Что-то сломалось на странице</h1>
      <p className="m-0 text-muted">
        Ваши ответы и проекты сохранены на сервере — страница просто не смогла их показать. Попробуйте ещё раз.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={reset}>Попробовать ещё раз</Button>
        <Button asChild variant="secondary">
          <Link href="/projects">К проектам</Link>
        </Button>
      </div>
    </main>
  );
}
