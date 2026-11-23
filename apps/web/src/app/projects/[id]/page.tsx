"use client";
import { MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { OFFLINE, Problem } from "@/components/Problem";
import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, errorText, STATUS, type Project, type Run } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";

const TONE: Record<Run["status"], "coral" | "mint" | "amber" | "neutral"> = {
  queued: "coral",
  running: "coral",
  waiting_input: "coral",
  succeeded: "mint",
  failed: "amber",
  cancelled: "neutral",
};

export default function ProjectPage() {
  return (
    <Shell>
      <ProjectView />
    </Shell>
  );
}

function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { key, ask } = useOwnKey();
  const [project, setProject] = useState<Project | null>(null);
  const [brief, setBrief] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [limited, setLimited] = useState(false);

  useEffect(() => {
    api()
      .GET("/projects/{project_id}", { params: { path: { project_id: id } } })
      .then(({ data, error }) => (error ? setError(errorText(error)) : setProject(data ?? null)));
    supabase()
      .from("graph_revisions")
      .select("files")
      .eq("project_id", id)
      .eq("rev", 0)
      .maybeSingle()
      .then(({ data }) => setBrief((data?.files as Record<string, string> | null)?.["brief.md"] ?? ""));
    supabase()
      .from("runs")
      .select("*")
      .eq("project_id", id)
      .order("created_at", { ascending: false })
      .limit(5)
      .then(({ data }) => setRuns((data as Run[] | null) ?? []));
  }, [id]);

  async function start(kind: "interview" | "brief") {
    if (busy) return;
    setBusy(true);
    setError("");
    setLimited(false);
    try {
      const { data, error, response } = await api(key).POST("/projects/{project_id}/runs", {
        params: { path: { project_id: id } },
        body: { kind },
      });
      if (response.status === 429) return setLimited(true);
      if (error || !data) return setError(errorText(error));
      router.push(`/projects/${id}/interview?run=${data.run.id}`);
    } catch {
      setError(OFFLINE);
    } finally {
      setBusy(false);
    }
  }

  if (project === null) return error ? <p className="error">{error}</p> : <Loading />;
  return (
    <>
      <ProjectTabs projectId={id} />
      <h1 className="[overflow-wrap:anywhere]">{project.name}</h1>
      <section className="card">
        <h2>Чем вы занимаетесь</h2>
        {brief ? <p className="brief">{brief}</p> : <p className="muted m-0">Брифа нет: аналитик начнёт с вопросов.</p>}
      </section>
      <div className="row">
        <Button size="lg" disabled={busy} onClick={() => start("interview")}>
          <MessageSquareText aria-hidden="true" />
          Начать интервью
        </Button>
        <Button variant="secondary" size="lg" disabled={busy || !brief} onClick={() => start("brief")}>
          Прогон по брифу
        </Button>
      </div>
      <p className="hint">Интервью — аналитик задаёт вопросы по одному. Прогон по брифу — сразу собрать черновик ТЗ по тексту выше.</p>
      {limited && (
        <Problem
          kind="limit"
          title="На сегодня бесплатные прогоны закончились"
          actions={
            <Button variant="secondary" size="sm" onClick={() => ask(true)}>
              Ввести свой ключ
            </Button>
          }
        >
          Новые появятся в полночь по Москве. Продолжить сейчас можно со своим ключом OpenRouter — тогда
          лимита нет, а запросы оплачиваете вы.
        </Problem>
      )}
      {error && <Problem kind={error === OFFLINE ? "offline" : "error"} title={error} />}
      {runs.length > 0 && (
        <section className="mt-8">
          <h2>Прогоны</h2>
          <ul className="list">
            {runs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3">
                <Link href={`/projects/${id}/interview?run=${r.id}`}>
                  {r.kind === "interview" ? "Интервью" : "По брифу"} · {new Date(r.created_at).toLocaleString("ru-RU")}
                </Link>
                <Badge tone={TONE[r.status]} className="ml-auto">
                  {STATUS[r.status]}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
