"use client";
// The tabs of a project page (T-505): overview, graph, checks, exports.
import Link from "next/link";
import { usePathname } from "next/navigation";

export function ProjectTabs({ projectId }: { projectId: string }) {
  const path = usePathname();
  const base = `/projects/${projectId}`;
  const tabs = [
    { href: base, label: "Проект" },
    { href: `${base}/graph`, label: "Граф" },
    { href: `${base}/report`, label: "Проверки" },
    { href: `${base}/exports`, label: "Выгрузка" },
  ];
  return (
    <nav className="tabs" aria-label="Разделы проекта">
      {tabs.map((t) => {
        const current = t.href === base ? path === base : path.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href} aria-current={current ? "page" : undefined}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
