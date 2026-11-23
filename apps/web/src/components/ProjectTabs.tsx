"use client";
// The tabs of a project (T-508): one row; on a phone it scrolls instead of wrapping.
import Link from "next/link";
import { usePathname } from "next/navigation";

export function ProjectTabs({ projectId }: { projectId: string }) {
  const path = usePathname();
  const base = `/projects/${projectId}`;
  const tabs = [
    { href: base, label: "Интервью" },
    { href: `${base}/graph`, label: "Схемы" },
    { href: `${base}/report`, label: "Проверки" },
    { href: `${base}/exports`, label: "Документы" },
  ];
  return (
    <nav className="tabs" aria-label="Разделы проекта">
      {tabs.map((t) => {
        const current =
          t.href === base
            ? path === base || path.startsWith(`${base}/interview`)
            : path.startsWith(t.href) || (t.label === "Схемы" && path.startsWith(`${base}/processes`));
        return (
          <Link key={t.href} href={t.href} aria-current={current ? "page" : undefined}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
