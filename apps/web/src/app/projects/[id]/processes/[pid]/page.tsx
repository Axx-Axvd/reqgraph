"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText } from "@/lib/api";
import { nodeTitle, type Graph } from "@/lib/results";

// bpmn-js works with the DOM only: no server rendering
const BpmnView = dynamic(() => import("@/components/BpmnView").then((m) => m.BpmnView), {
  ssr: false,
  loading: () => <p className="muted">Загружаем схему…</p>,
});

export default function ProcessPage() {
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <ProcessScreen />
      </Suspense>
    </Shell>
  );
}

function ProcessScreen() {
  const { id, pid } = useParams<{ id: string; pid: string }>();
  const focus = useSearchParams().get("el");
  const [xml, setXml] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/processes/{process_id}/bpmn", {
        params: { path: { project_id: id, process_id: pid } },
        parseAs: "text",
      })
      .then(({ data, error }) => (error || !data ? setError(errorText(error)) : setXml(data as unknown as string)));
    api()
      .GET("/projects/{project_id}/graph", { params: { path: { project_id: id } } })
      .then(({ data }) => {
        const node = (data?.graph as unknown as Graph | undefined)?.nodes[pid];
        if (node) setName(nodeTitle(node));
      });
  }, [id, pid]);

  return (
    <>
      <ProjectTabs projectId={id} />
      <div className="flex flex-col gap-5">
        <h1 className="m-0">{name || "Схема процесса"}</h1>
        <p className="m-0 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <Link href={`/projects/${id}/graph`}>Как это будет работать</Link>
          <Link href={`/projects/${id}/graph?node=${pid}`}>Этот процесс на схеме для разработчиков</Link>
        </p>
        {error && <p className="error">{error}</p>}
        {!xml && !error && <Loading />}
        {xml && <BpmnView xml={xml} focus={focus} />}
      </div>
    </>
  );
}
