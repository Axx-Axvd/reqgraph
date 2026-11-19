"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Shell } from "@/components/Shell";
import { api, errorText, STATUS, type Project, type Run } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";

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
  const { key } = useOwnKey();
  const [project, setProject] = useState<Project | null>(null);
  const [brief, setBrief] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    setBusy(true);
    setError("");
    const { data, error } = await api(key).POST("/projects/{project_id}/runs", {
      params: { path: { project_id: id } },
      body: { kind },
    });
    setBusy(false);
    if (error || !data) {
      setError(errorText(error));
      return;
    }
    router.push(`/projects/${id}/interview?run=${data.run.id}`);
  }

  if (project === null) return error ? <p className="error">{error}</p> : <p className="muted">Загружаем…</p>;
  return (
    <>
      <p><Link href="/projects">← Проекты</Link></p>
      <h1>{project.name}</h1>
      <section className="card">
        <h2>Бриф</h2>
        {brief ? <pre className="brief">{brief}</pre> : <p className="muted">Брифа нет: агенты начнут с вопросов.</p>}
      </section>
      <div className="row">
        <button type="button" className="button" disabled={busy} onClick={() => start("interview")}>
          Начать интервью
        </button>
        <button type="button" className="button secondary" disabled={busy || !brief} onClick={() => start("brief")}>
          Прогон по брифу
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {runs.length > 0 && (
        <section>
          <h2>Прогоны</h2>
          <ul className="list">
            {runs.map((r) => (
              <li key={r.id}>
                <Link href={`/projects/${id}/interview?run=${r.id}`}>
                  {r.kind === "interview" ? "Интервью" : "По брифу"} · {new Date(r.created_at).toLocaleString("ru-RU")}
                </Link>
                <span className="muted"> · {STATUS[r.status]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
