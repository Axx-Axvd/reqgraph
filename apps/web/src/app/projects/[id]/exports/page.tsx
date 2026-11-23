"use client";
// Документы (T-511): the ТЗ sheet with «Откуда это в ТЗ», then the files of the last export by
// document — ТЗ · SRS · Схемы · ReqIF — and a week-long link to the ТЗ for the contractor.
import { Copy, Download, Link2, RefreshCw } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { TzSheet } from "@/components/results/TzSheet";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { schemeLabel, shareLink, useExports } from "@/lib/exports";
import type { ExportFile, Finding, Graph } from "@/lib/results";

type Tab = "tz" | "srs" | "schemes" | "reqif";
const TABS: { value: Tab; label: string }[] = [
  { value: "tz", label: "ТЗ" },
  { value: "srs", label: "SRS" },
  { value: "schemes", label: "Схемы" },
  { value: "reqif", label: "ReqIF" },
];
const LABELS: Record<string, string> = {
  "tz_gost34.docx": "ТЗ по ГОСТ 34.602 (Word)",
  "tz_gost34.md": "ТЗ по ГОСТ 34.602 (Markdown)",
  "tz_gost19.docx": "ТЗ на программу по ГОСТ 19.201 (Word)",
  "tz_gost19.md": "ТЗ на программу по ГОСТ 19.201 (Markdown)",
  "srs.docx": "SRS по ISO/IEC/IEEE 29148 (Word)",
  "srs.md": "SRS (Markdown)",
  "req.reqif": "Требования в ReqIF",
};
const FILES: Record<Exclude<Tab, "schemes">, string[]> = {
  tz: ["tz_gost34.docx", "tz_gost34.md", "tz_gost19.docx", "tz_gost19.md"],
  srs: ["srs.docx", "srs.md"],
  reqif: ["req.reqif"],
};
const ABOUT: Record<Exclude<Tab, "tz">, string> = {
  srs: "Спецификация требований по ISO/IEC/IEEE 29148 — для команды разработки и международных заказчиков.",
  schemes: "Схемы процессов, данных и устройства системы — те же, что в документах, по одной на лист.",
  reqif: "Требования в формате ReqIF — чтобы загрузить их в систему управления требованиями (Polarion, DOORS, StrictDoc).",
};

/** A signed link that saves the file instead of opening it (Storage reads ?download). */
function downloadHref(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}download=`;
}

export default function ExportsPage() {
  return (
    <Shell>
      <ExportsScreen />
    </Shell>
  );
}

function ExportsScreen() {
  const { id } = useParams<{ id: string }>();
  const { files, latest, rev, links, error, make } = useExports(id);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("tz");
  const [graph, setGraph] = useState<Graph | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [name, setName] = useState("");

  useEffect(() => {
    const path = { params: { path: { project_id: id } } };
    api()
      .GET("/projects/{project_id}/graph", path)
      .then(({ data }) => setGraph(data ? (data.graph as unknown as Graph) : { nodes: {}, edges: [] }));
    api()
      .GET("/projects/{project_id}/report", path)
      .then(({ data }) => data && setFindings(data.findings));
    api()
      .GET("/projects/{project_id}", path)
      .then(({ data }) => data && setName(data.name));
  }, [id]);

  async function build() {
    setBusy(true);
    await make();
    setBusy(false);
  }

  const byName = new Map(latest.map((f) => [f.name, f]));
  const pictures = latest.filter((f) => f.name.startsWith("img/"));
  return (
    <>
      <ProjectTabs projectId={id} />
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="m-0">Документы</h1>
            <p className="m-0 mt-1 text-muted">
              {rev === null
                ? "Соберите документы — получится ТЗ по ГОСТ, SRS, схемы и файл для систем управления требованиями."
                : `Собраны по ревизии ${rev}. Ссылки на файлы действуют час.`}
            </p>
          </div>
          <Button variant={rev === null ? "primary" : "secondary"} disabled={busy} onClick={build}>
            <RefreshCw aria-hidden="true" className={busy ? "animate-spin motion-reduce:animate-none" : undefined} />
            {busy ? "Собираем документы…" : rev === null ? "Сделать документы" : "Собрать заново"}
          </Button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {files && files.length === 0 && <p className="m-0 text-muted">Выгрузок пока нет.</p>}
        <Tabs label="Документы" tabs={TABS} value={tab} onChange={setTab}>
          {tab === "tz" && (
            <div className="flex flex-col gap-5">
              <div className="flex flex-wrap items-center gap-2">
                <FileRow names={FILES.tz} byName={byName} links={links} primary />
                {byName.get("tz_gost34.docx") && <ShareLink file={byName.get("tz_gost34.docx")!} />}
              </div>
              {graph ? (
                <TzSheet graph={graph} findings={findings} projectId={id} projectName={name || "Проект"} />
              ) : (
                <Loading />
              )}
            </div>
          )}
          {tab !== "tz" && (
            <div className="flex flex-col gap-4">
              <p className="m-0 max-w-[68ch] text-muted">{ABOUT[tab]}</p>
              {rev === null && <p className="m-0">Сначала соберите документы.</p>}
              {tab !== "schemes" && <FileRow names={FILES[tab]} byName={byName} links={links} />}
              {tab === "schemes" && (
                <div className="grid gap-4 md:grid-cols-2" data-testid="export-schemes">
                  {pictures.map((f) => (
                    <Card key={f.id} className="flex flex-col gap-3 p-4">
                      <h2 className="m-0 text-base">{schemeLabel(f.name)}</h2>
                      {links[f.path] && (
                        <>
                          {/* eslint-disable-next-line @next/next/no-img-element -- a signed Storage link */}
                          <img src={links[f.path]} alt={schemeLabel(f.name)} className="max-h-72 w-full rounded-control bg-paper object-contain p-2" />
                          <a href={downloadHref(links[f.path])} className="text-sm">
                            Скачать SVG
                          </a>
                        </>
                      )}
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </Tabs>
      </div>
    </>
  );
}

function FileRow({
  names,
  byName,
  links,
  primary = false,
}: {
  names: string[];
  byName: Map<string, ExportFile>;
  links: Record<string, string>;
  primary?: boolean;
}) {
  const present = names.map((n) => byName.get(n)).filter((f): f is ExportFile => Boolean(f));
  if (present.length === 0) return null;
  return (
    <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
      {present.map((f, i) => {
        const href = links[f.path];
        const label = LABELS[f.name] ?? f.name;
        return (
          <li key={f.id}>
            {href ? (
              <Button asChild variant={primary && i === 0 ? "primary" : "secondary"} size="sm">
                <a href={downloadHref(href)}>
                  <Download aria-hidden="true" />
                  {label}
                </a>
              </Button>
            ) : (
              <span className="text-muted">{label}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ShareLink({ file }: { file: ExportFile }) {
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  async function create() {
    const { url, error } = await shareLink(file.path);
    if (!url) return setNote(`Ссылка не получена: ${error}`);
    setUrl(url);
    try {
      await navigator.clipboard.writeText(url);
      setNote("Скопировано. Ссылка действует 7 дней, входить на сайт не нужно.");
    } catch {
      setNote("Ссылка действует 7 дней, входить на сайт не нужно.");
    }
  }
  return (
    <div className={url ? "flex basis-full flex-col gap-2" : "flex flex-col gap-2"}>
      {url ? (
        <div className="flex flex-wrap items-center gap-2">
          <Input readOnly value={url} aria-label="Ссылка для подрядчика" className="min-w-0 flex-1" onFocus={(e) => e.currentTarget.select()} />
          <Button variant="secondary" size="sm" onClick={() => void navigator.clipboard?.writeText(url)}>
            <Copy aria-hidden="true" />
            Скопировать
          </Button>
        </div>
      ) : (
        <Button variant="quiet" size="sm" className="self-start" onClick={create}>
          <Link2 aria-hidden="true" />
          Ссылка для подрядчика
        </Button>
      )}
      {note && (
        <p className="m-0 text-sm text-muted" role="status">
          {note}
        </p>
      )}
    </div>
  );
}
