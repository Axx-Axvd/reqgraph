"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { api, errorText } from "@/lib/api";

// bpmn-js works with the DOM only: no server rendering
const BpmnView = dynamic(() => import("@/components/BpmnView").then((m) => m.BpmnView), {
  ssr: false,
  loading: () => <p className="muted">Загружаем схему…</p>,
});

export default function ProcessPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="muted">Загружаем…</p>}>
        <ProcessScreen />
      </Suspense>
    </Shell>
  );
}

function ProcessScreen() {
  const { id, pid } = useParams<{ id: string; pid: string }>();
  const focus = useSearchParams().get("el");
  const [xml, setXml] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/processes/{process_id}/bpmn", {
        params: { path: { project_id: id, process_id: pid } },
        parseAs: "text",
      })
      .then(({ data, error }) => (error || !data ? setError(errorText(error)) : setXml(data as unknown as string)));
  }, [id, pid]);

  return (
    <>
      <ProjectTabs projectId={id} />
      <h1>Процесс {pid}</h1>
      <p>
        <Link href={`/projects/${id}/graph?node=${pid}`}>← Узел на графе</Link>
      </p>
      {error && <p className="error">{error}</p>}
      {!xml && !error && <p className="muted">Загружаем…</p>}
      {xml && <BpmnView xml={xml} focus={focus} />}
    </>
  );
}
