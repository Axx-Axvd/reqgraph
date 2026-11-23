"use client";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Disclaimer } from "@/components/Disclaimer";
import { InterviewChat } from "@/components/InterviewChat";
import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";

export default function InterviewPage() {
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <Interview />
      </Suspense>
    </Shell>
  );
}

function Interview() {
  const { id } = useParams<{ id: string }>();
  const run = useSearchParams().get("run");
  return (
    <>
      <ProjectTabs projectId={id} />
      <h1 className="sr-only">Интервью</h1>
      <Disclaimer />
      {run ? <InterviewChat runId={run} projectId={id} /> : <p className="error">Не указан прогон.</p>}
    </>
  );
}
