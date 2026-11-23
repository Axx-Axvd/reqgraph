// No such page (T-512).
import Link from "next/link";

import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[80vh] max-w-[560px] flex-col items-start justify-center gap-5 px-5">
      <Logo />
      <h1 className="m-0">Такой страницы нет</h1>
      <p className="m-0 text-muted">Возможно, ссылка устарела или в адресе опечатка. Ваши проекты на месте.</p>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link href="/projects">К проектам</Link>
        </Button>
        <Button asChild variant="secondary">
          <Link href="/">На главную</Link>
        </Button>
      </div>
    </main>
  );
}
