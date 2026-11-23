// The header of the public pages (landing, sign-in): the logo, «how it works», GitHub, the theme, sign-in.
import Link from "next/link";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";

export const REPO_URL = "https://github.com/Axx-Axvd/reqgraph";

export function SiteHeader({ signIn = true }: { signIn?: boolean }) {
  return (
    <header className="mx-auto flex max-w-[1240px] items-center gap-6 px-5 py-5 sm:px-6">
      <Link href="/" aria-label="reqgraph — на главную" className="inline-flex min-h-11 items-center text-fg no-underline">
        <Logo />
      </Link>
      <nav aria-label="Разделы" className="flex gap-5 max-sm:hidden">
        <Link href="/#how" className="text-muted no-underline hover:text-fg">Как это работает</Link>
        <a href={REPO_URL} className="text-muted no-underline hover:text-fg">GitHub</a>
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        {signIn && (
          <Button asChild variant="secondary">
            <Link href="/login">Войти</Link>
          </Button>
        )}
      </div>
    </header>
  );
}
