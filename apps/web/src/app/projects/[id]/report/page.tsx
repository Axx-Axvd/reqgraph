"use client";
// Проверки (T-511): remarks one card at a time, a ring «разобрано N из M», the check groups aside,
// and «Показать на схеме» opens the node. What was read is kept in this browser only.
import { ChevronLeft, ChevronRight, CircleCheck } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText } from "@/lib/api";
import { SEVERITY, nodeHref, plainMessage, type Finding, type Graph, type Report } from "@/lib/results";
import { cn } from "@/lib/utils";

const GROUPS: Record<string, string> = {
  iso: "Формулировки требований",
  snd: "Процессы",
  sch: "Схемы",
  trc: "Откуда что взялось",
  tpl: "Разделы документов",
};
const ORDER: Record<Finding["severity"], number> = { error: 0, warning: 1, info: 2 };
const TONE = { error: "coral", warning: "amber", info: "neutral" } as const;

const keyOf = (f: Finding) => `${f.check_id}|${f.node_ids.join(",")}|${f.message}`;

function readSeen(storageKey: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(storageKey) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

export default function ReportPage() {
  return (
    <Shell>
      <ReportScreen />
    </Shell>
  );
}

function ReportScreen() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState("");
  const [group, setGroup] = useState("");
  const [at, setAt] = useState(0);
  const storageKey = `sg-seen:${id}`;
  // read before the report arrives: nothing on screen depends on it until then, so no hydration mismatch
  const [seen, setSeen] = useState<Set<string>>(() => readSeen(storageKey));

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/report", { params: { path: { project_id: id } } })
      .then(({ data, error }) => (error || !data ? setError(errorText(error)) : setReport(data)));
    api()
      .GET("/projects/{project_id}/graph", { params: { path: { project_id: id } } })
      .then(({ data }) => data && setGraph(data.graph as unknown as Graph));
  }, [id]);

  const groupOf = useMemo(() => new Map(report?.checks.map((c) => [c.id, c.group]) ?? []), [report]);
  const all = useMemo(
    () => [...(report?.findings ?? [])].sort((a, b) => ORDER[a.severity] - ORDER[b.severity]),
    [report],
  );
  const list = all.filter((f) => !group || groupOf.get(f.check_id) === group);
  const index = Math.min(at, Math.max(list.length - 1, 0));
  const current = list[index];
  const done = all.filter((f) => seen.has(keyOf(f))).length;

  function markAndNext() {
    if (!current) return;
    const next = new Set(seen).add(keyOf(current));
    setSeen(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify([...next]));
    } catch {
      // private mode: the progress lives until the page is closed
    }
    if (index < list.length - 1) setAt(index + 1);
  }

  const groups = [...new Set(report?.checks.map((c) => c.group) ?? [])];
  return (
    <>
      <ProjectTabs projectId={id} />
      <div className="flex flex-col gap-5">
        <h1 className="m-0">Проверки</h1>
        {error && <p className="error">{error}</p>}
        {!report && !error && <Loading />}
        {report && (
          <>
            <p data-testid="report-summary" className="m-0 text-muted">
              Ошибок: <b className="text-fg">{report.summary.errors}</b> · предупреждений:{" "}
              <b className="text-fg">{report.summary.warnings}</b> · замечаний: <b className="text-fg">{report.summary.infos}</b>{" "}
              · проверок: {report.checks.length}. Проверяет код, а не нейросеть: при каждом запуске результат тот же.
            </p>
            {all.length === 0 ? (
              <Card className="flex items-center gap-3 p-6">
                <CircleCheck aria-hidden="true" className="size-8 text-mint" />
                <p className="m-0 text-lg">Все проверки пройдены.</p>
              </Card>
            ) : (
              <div className="grid gap-5 md:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="flex flex-col gap-4 max-md:order-last">
                  <Ring done={done} total={all.length} />
                  <nav aria-label="Группы проверок" className="flex flex-col gap-1">
                    {["", ...groups].map((g) => {
                      const count = all.filter((f) => !g || groupOf.get(f.check_id) === g).length;
                      return (
                        <button
                          key={g || "all"}
                          type="button"
                          aria-pressed={group === g}
                          onClick={() => {
                            setGroup(g);
                            setAt(0);
                          }}
                          className={cn(
                            "flex min-h-10 items-center justify-between gap-3 rounded-control px-3 py-2 text-left text-sm text-muted hover:bg-raised hover:text-fg",
                            group === g && "bg-raised font-medium text-fg",
                          )}
                        >
                          <span>{g ? (GROUPS[g] ?? g) : "Все"}</span>
                          {count === 0 ? (
                            <CircleCheck aria-label="пройдено" className="size-4 text-mint" />
                          ) : (
                            <span className="text-xs text-dim">{count}</span>
                          )}
                        </button>
                      );
                    })}
                  </nav>
                </aside>
                {current ? (
                  <Card className="flex flex-col gap-4 p-6" data-testid="finding" aria-live="polite">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm text-dim">
                        {index + 1} из {list.length}
                      </span>
                      <span className="flex items-center gap-2">
                        {seen.has(keyOf(current)) && <Badge tone="mint">разобрано</Badge>}
                        <Badge tone={TONE[current.severity]}>{SEVERITY[current.severity]}</Badge>
                      </span>
                    </div>
                    <h2 className="m-0 font-sans text-xl leading-snug font-medium">
                      {plainMessage(current.message, graph)}
                    </h2>
                    {current.hint && (
                      <p className="m-0 text-muted">
                        <span className="text-fg">Как исправить:</span> {current.hint}
                      </p>
                    )}
                    <p className="m-0 text-xs text-dim">
                      Проверка {current.check_id} · {GROUPS[groupOf.get(current.check_id) ?? ""] ?? ""}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Button onClick={markAndNext}>{index < list.length - 1 ? "Понятно, дальше" : "Понятно"}</Button>
                      {current.node_ids[0] && (
                        <Button variant="secondary" onClick={() => router.push(nodeHref(id, current.node_ids[0]))}>
                          Показать на схеме
                        </Button>
                      )}
                      <span className="ml-auto flex gap-1">
                        <Button variant="quiet" size="icon" aria-label="Предыдущее" disabled={index === 0} onClick={() => setAt(index - 1)}>
                          <ChevronLeft aria-hidden="true" />
                        </Button>
                        <Button
                          variant="quiet"
                          size="icon"
                          aria-label="Следующее"
                          disabled={index >= list.length - 1}
                          onClick={() => setAt(index + 1)}
                        >
                          <ChevronRight aria-hidden="true" />
                        </Button>
                      </span>
                    </div>
                  </Card>
                ) : (
                  <Card className="p-6">
                    <p className="m-0">В этой группе замечаний нет.</p>
                  </Card>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

function Ring({ done, total }: { done: number; total: number }) {
  const r = 30;
  const length = 2 * Math.PI * r;
  const share = total > 0 ? done / total : 1;
  return (
    <div className="flex items-center gap-3" data-testid="ring">
      <svg viewBox="0 0 72 72" className="size-[72px] -rotate-90" aria-hidden="true">
        <circle cx="36" cy="36" r={r} fill="none" stroke="var(--line-2)" strokeWidth="7" />
        <circle
          cx="36"
          cy="36"
          r={r}
          fill="none"
          stroke="var(--mint)"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={length}
          strokeDashoffset={length * (1 - share)}
          className="transition-[stroke-dashoffset] duration-500 ease-out-soft"
        />
      </svg>
      <p className="m-0 text-sm text-muted">
        Разобрано <b className="text-fg">{done}</b> из {total}
      </p>
    </div>
  );
}
