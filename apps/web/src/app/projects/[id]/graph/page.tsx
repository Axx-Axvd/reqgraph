"use client";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { GraphView } from "@/components/GraphView";
import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { api, errorText } from "@/lib/api";
import type { Graph } from "@/lib/results";

export default function GraphPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="muted">Загружаем…</p>}>
        <GraphScreen />
      </Suspense>
    </Shell>
  );
}

function GraphScreen() {
  const { id } = useParams<{ id: string }>();
  const focus = useSearchParams().get("node");
  const [graph, setGraph] = useState<{ rev: number; graph: Graph } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/graph", { params: { path: { project_id: id } } })
      .then(({ data, error }) =>
        error || !data ? setError(errorText(error)) : setGraph({ rev: data.rev, graph: data.graph as unknown as Graph }),
      );
  }, [id]);

  return (
    <>
      <ProjectTabs projectId={id} />
      <h1>Граф требований</h1>
      {error && <p className="error">{error}</p>}
      {!graph && !error && <p className="muted">Загружаем…</p>}
      {graph && Object.keys(graph.graph.nodes).length === 0 && (
        <p className="muted">Граф пока пуст: начните интервью или прогон по брифу.</p>
      )}
      {graph && Object.keys(graph.graph.nodes).length > 0 && (
        <>
          <p className="muted">Ревизия {graph.rev}. Нажмите на узел, чтобы увидеть его текст и связи.</p>
          <GraphView key={focus ?? ""} graph={graph.graph} projectId={id} focus={focus} />
        </>
      )}
    </>
  );
}
