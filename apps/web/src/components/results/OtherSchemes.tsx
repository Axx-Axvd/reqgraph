"use client";
// Data, UML and C4 schemes (T-511): the pictures drawn by Kroki for the last export. The site does
// not draw them itself — the export already has them, and the API stays light (Render Free).
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { schemeLabel, useExports } from "@/lib/exports";

export function OtherSchemes({ projectId }: { projectId: string }) {
  const { latest, files, links, error } = useExports(projectId);
  const pictures = latest.filter((f) => f.name.startsWith("img/") && !/^img\/PRC-/.test(f.name));
  return (
    <section aria-labelledby="other-schemes" className="flex flex-col gap-3">
      <h2 id="other-schemes" className="m-0 text-lg">
        Данные и устройство системы
      </h2>
      {error && <p className="error">{error}</p>}
      {files && pictures.length === 0 && (
        <p className="m-0 text-muted">
          Схемы данных, сценариев и архитектуры рисуются вместе с документами.{" "}
          <Link href={`/projects/${projectId}/exports`}>Сделать документы</Link>
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {pictures.map((f) => (
          <Card key={f.id} className="flex flex-col gap-3 p-4">
            <h3 className="m-0 text-base">{schemeLabel(f.name)}</h3>
            {links[f.path] ? (
              <a href={links[f.path]} target="_blank" rel="noreferrer" className="block rounded-control bg-paper p-3">
                {/* eslint-disable-next-line @next/next/no-img-element -- a signed Storage link, not a static asset */}
                <img src={links[f.path]} alt={schemeLabel(f.name)} className="mx-auto max-h-80 w-full object-contain" />
              </a>
            ) : (
              <p className="m-0 text-muted">Получаем ссылку…</p>
            )}
          </Card>
        ))}
      </div>
    </section>
  );
}
