"use client";
// Схемы (T-511): by default «Как это будет работать» — the processes in plain words; the requirements
// graph is «Схема для разработчиков» (?view=dev), and a link to a node (?node=) opens it there.
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { OtherSchemes } from "@/components/results/OtherSchemes";
import { ProcessStory } from "@/components/results/ProcessStory";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText } from "@/lib/api";
import type { Graph } from "@/lib/results";
import { cn } from "@/lib/utils";

// React Flow and dagre are only for «Схема для разработчиков»: loaded when it opens
const GraphView = dynamic(() => import("@/components/GraphView").then((m) => m.GraphView), {
  ssr: false,
  loading: () => <Loading label="Загружаем схему…" />,
});

export default function GraphPage() {
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <GraphScreen />
      </Suspense>
    </Shell>
  );
}

function GraphScreen() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const focus = params.get("node");
  const dev = params.get("view") === "dev" || focus !== null;
  const [graph, setGraph] = useState<{ rev: number; graph: Graph } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/graph", { params: { path: { project_id: id } } })
      .then(({ data, error }) =>
        error || !data ? setError(errorText(error)) : setGraph({ rev: data.rev, graph: data.graph as unknown as Graph }),
      );
  }, [id]);

  const empty = graph && Object.keys(graph.graph.nodes).length === 0;
  const views = [
    { href: `/projects/${id}/graph`, label: "Как это будет работать", current: !dev },
    { href: `/projects/${id}/graph?view=dev`, label: "Схема для разработчиков", current: dev },
  ];
  return (
    <>
      <ProjectTabs projectId={id} />
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="m-0">Схемы</h1>
          <nav aria-label="Вид схем" className="grid w-full grid-cols-2 gap-1 rounded-control border border-line p-1 sm:w-auto">
            {views.map((v) => (
              <Link
                key={v.href}
                href={v.href}
                aria-current={v.current ? "page" : undefined}
                className={cn(
                  "flex min-h-10 items-center justify-center rounded-[8px] px-3 py-1.5 text-center text-sm text-muted no-underline hover:text-fg",
                  v.current && "bg-raised font-medium text-fg",
                )}
              >
                {v.label}
              </Link>
            ))}
          </nav>
        </div>
        {error && <p className="error">{error}</p>}
        {!graph && !error && <Loading />}
        {empty && <p className="text-muted">Схем пока нет: начните интервью или прогон по брифу.</p>}
        {graph && !empty && !dev && (
          <>
            <p className="m-0 text-muted">Кто что делает и в каком порядке — так, как вы рассказали.</p>
            <ProcessStory graph={graph.graph} projectId={id} />
            <OtherSchemes projectId={id} />
          </>
        )}
        {graph && !empty && dev && (
          <>
            <p className="m-0 text-muted">
              Все требования и их связи, ревизия {graph.rev}. Нажмите на узел, чтобы увидеть его текст и связи.
            </p>
            <GraphView key={focus ?? ""} graph={graph.graph} projectId={id} focus={focus} />
          </>
        )}
      </div>
    </>
  );
}
