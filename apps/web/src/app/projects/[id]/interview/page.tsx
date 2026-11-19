"use client";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Disclaimer } from "@/components/Disclaimer";
import { InterviewChat } from "@/components/InterviewChat";
import { Shell } from "@/components/Shell";

export default function InterviewPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="muted">Загружаем…</p>}>
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
      <p><Link href={`/projects/${id}`}>← Проект</Link></p>
      <h1>Интервью</h1>
      <Disclaimer />
      {run ? <InterviewChat runId={run} projectId={id} /> : <p className="error">Не указан прогон.</p>}
    </>
  );
}
