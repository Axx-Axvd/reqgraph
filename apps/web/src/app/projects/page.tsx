"use client";
// Projects (T-510, board «Проекты и новый проект»): where you stopped, all projects as cards with the next
// step, a new project in a dialog.
import { ArrowRight, MessageSquareText, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { NewProjectDialog } from "@/components/projects/NewProjectDialog";
import { Shell } from "@/components/Shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText, type Project, type Run } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function Projects() {
  return (
    <Shell>
      <ProjectList />
    </Shell>
  );
}

type RunRow = Pick<Run, "id" | "project_id" | "kind" | "status" | "created_at">;
type Resume = { run: RunRow; project: Project; question: string; asked: number };

const STATE: Record<RunRow["status"], { label: string; tone: "coral" | "mint" | "amber" | "neutral" }> = {
  waiting_input: { label: "идёт разговор", tone: "coral" },
  queued: { label: "агенты работают", tone: "coral" },
  running: { label: "агенты работают", tone: "coral" },
  succeeded: { label: "ТЗ собрано", tone: "mint" },
  failed: { label: "прогон не удался", tone: "amber" },
  cancelled: { label: "прогон отменён", tone: "neutral" },
};

function next(project: Project, run: RunRow | undefined): { label: string; href: string } {
  const base = `/projects/${project.id}`;
  if (run?.status === "waiting_input") return { label: "Продолжить разговор", href: `${base}/interview?run=${run.id}` };
  if (run && (run.status === "queued" || run.status === "running"))
    return { label: "Посмотреть, как идёт", href: `${base}/interview?run=${run.id}` };
  if (run?.status === "succeeded") return { label: "Открыть документы", href: `${base}/exports` };
  return { label: "Начать разговор", href: base };
}

function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [resume, setResume] = useState<Resume | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      const [list, recent] = await Promise.all([
        api().GET("/projects"),
        supabase().from("runs").select("id, project_id, kind, status, created_at").order("created_at", { ascending: false }).limit(50),
      ]);
      if (!alive) return;
      if (!list.data) {
        setError(errorText((list as { error?: unknown }).error));
        return;
      }
      const all = list.data;
      const rows = (recent.data as RunRow[] | null) ?? [];
      setProjects(all);
      setRuns(rows);
      const waiting = rows.find((r) => r.status === "waiting_input");
      const project = waiting && all.find((p) => p.id === waiting.project_id);
      if (!waiting || !project) return;
      const turns = await supabase()
        .from("interview_turns")
        .select("role, content")
        .eq("run_id", waiting.id)
        .eq("role", "agent")
        .order("id", { ascending: false });
      const asked = (turns.data as { content: string }[] | null) ?? [];
      if (alive && asked.length > 0) setResume({ run: waiting, project, question: asked[0].content, asked: asked.length });
    })();
    return () => {
      alive = false;
    };
  }, []);

  const lastRun = (p: Project) => runs.find((r) => r.project_id === p.id);
  return (
    <>
      <div className="mb-7 flex flex-wrap items-end gap-4">
        <h1 className="m-0 font-display text-[clamp(28px,7.4vw,38px)] font-extrabold tracking-[-0.03em]">
          {resume ? "С возвращением" : "Проекты"}
        </h1>
        <div className="ml-auto">
          <NewProjectDialog autoOpen />
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {resume && (
        <section
          aria-label="Продолжить разговор"
          className="mb-8 flex flex-col gap-4 rounded-[26px] border border-coral bg-surface p-6 sm:p-7"
        >
          <span className="inline-flex items-center gap-2 text-[13px] text-coral-text">
            <span className="size-2 animate-pulse rounded-full bg-coral" aria-hidden="true" />
            {resume.project.name}
          </span>
          <h2 className="m-0 font-display text-[clamp(20px,4vw,26px)] font-bold">Вы остановились на {resume.asked}-м вопросе</h2>
          <p className="m-0 max-w-[640px] rounded-[20px_20px_20px_6px] bg-raised px-4 py-3.5 text-[17px] leading-normal">{resume.question}</p>
          <Button asChild size="lg" className="self-start">
            <Link href={`/projects/${resume.project.id}/interview?run=${resume.run.id}`}>
              <MessageSquareText aria-hidden="true" />
              Ответить
            </Link>
          </Button>
        </section>
      )}

      {projects === null && !error ? (
        <Loading />
      ) : projects && projects.length === 0 ? (
        <section className="flex flex-col items-start gap-3 rounded-[24px] border border-line bg-surface p-8">
          <h2 className="m-0 font-display text-2xl font-bold">Здесь появится ваше первое ТЗ</h2>
          <p className="m-0 max-w-[420px] text-muted">Расскажите, чем занимаетесь, — остальное спросит аналитик.</p>
          <NewProjectDialog
            trigger={
              <Button size="lg" className="mt-2">
                Начать разговор
              </Button>
            }
          />
        </section>
      ) : (
        projects && (
          <>
            {resume && <h2 className="mb-3 text-[18px] font-semibold text-muted">Все проекты</h2>}
            <ul className="m-0 grid list-none gap-4 p-0 [grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr))]">
              {projects.map((p) => {
                const run = lastRun(p);
                const state = run ? STATE[run.status] : { label: "черновик", tone: "neutral" as const };
                const step = next(p, run);
                return (
                  <li key={p.id}>
                    <Link
                      href={step.href}
                      className="flex h-full flex-col gap-4 rounded-[20px] border border-line bg-surface p-5 text-fg no-underline transition-[transform,border-color] duration-200 hover:-translate-y-0.5 hover:border-line-2"
                    >
                      <div className="flex items-center gap-2">
                        <Badge tone={state.tone}>{state.label}</Badge>
                        <span className="ml-auto text-xs text-dim">
                          {new Date(run?.created_at ?? p.created_at).toLocaleDateString("ru-RU")}
                        </span>
                      </div>
                      <h3 className="m-0 text-xl font-semibold [overflow-wrap:anywhere]">{p.name}</h3>
                      <span className="mt-auto flex items-center gap-2 border-t border-line pt-3 text-sm text-coral-text">
                        {step.label}
                        <ArrowRight aria-hidden="true" className="size-4" />
                      </span>
                    </Link>
                  </li>
                );
              })}
              <li>
                <NewProjectDialog
                  trigger={
                    <button
                      type="button"
                      className="flex h-full min-h-[170px] w-full flex-col items-center justify-center gap-2.5 rounded-[20px] border border-dashed border-line-2 bg-transparent text-muted"
                    >
                      <span className="inline-flex size-11 items-center justify-center rounded-full border border-line-2">
                        <Plus aria-hidden="true" className="size-5" />
                      </span>
                      Новый проект
                    </button>
                  }
                />
              </li>
            </ul>
          </>
        )
      )}
    </>
  );
}
