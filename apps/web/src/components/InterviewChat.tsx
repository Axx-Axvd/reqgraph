"use client";
// The interview (T-504, redesigned in T-510 by the board «Интервью»): questions and answers come from
// interview_turns, the coverage of topics from the coverage kept with each question, the draft
// requirements from «drafts» run events (written by the worker while it waits for the next answer), the
// progress from run_events. Supabase Realtime pushes new rows; a 2-second poll of the API is the fallback
// (07_deploy), so the chat works whether Realtime is up or not. After the interview the same screen shows
// how the ТЗ is being put together (board «После интервью: сборка ТЗ»).
import { ArrowRight, Check, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AREAS, api, errorText, STATUS, type Run, type RunEvent } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";
import { cn } from "@/lib/utils";

type Coverage = { got: Record<string, number>; need: Record<string, number> };
type Turn = { id: number; role: "agent" | "client"; content: string; coverage: Coverage | null };
type Draft = { id: string; kind: string; title: string; statement: string };
type Drafts = { turn: string; answer: string; items: Draft[] };

const KIND: Record<string, { label: string; dot: string }> = {
  BR: { label: "цель", dot: "bg-coral-text" },
  UR: { label: "что нужно людям", dot: "bg-amber" },
  FR: { label: "что делает система", dot: "bg-[#8fc7ff]" },
  NFR: { label: "качество", dot: "bg-mint" },
  CON: { label: "ограничение", dot: "bg-dim" },
};

const NODES: Record<string, string> = {
  intake: "читаем бриф",
  analyst: "записываю требования",
  coverage: "смотрю, какие темы уже раскрыты",
  interviewer: "готовлю следующий вопрос",
  modeler: "строим схемы процессов и данных",
  modeler_views: "строим сценарии использования и C4",
  standards: "собираем SRS",
  ci_check: "проверяем модели и требования",
  reviewer: "разбираем замечания проверок",
  export: "готовим документы",
};

/** The stages of putting the ТЗ together after the interview, by the nodes of the run graph. */
const STAGES: { name: string; nodes: string[] }[] = [
  { name: "Требования из разговора", nodes: ["intake", "analyst", "coverage", "interviewer"] },
  { name: "Схемы процессов и данных", nodes: ["modeler", "modeler_views"] },
  { name: "Проверки кодом", nodes: ["ci_check", "reviewer"] },
  { name: "ТЗ по ГОСТ и SRS", nodes: ["standards", "export"] },
];
const stageOf = (node: string) => STAGES.findIndex((s) => s.nodes.includes(node));

const POLL_MS = 2000;

export function InterviewChat({ runId, projectId }: { runId: string; projectId: string }) {
  const { key } = useOwnKey();
  const [run, setRun] = useState<Run | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const lastEvent = useRef(0);

  const refresh = useCallback(async () => {
    const client = api();
    const [runRes, eventsRes, turnsRes] = await Promise.all([
      client.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }),
      client.GET("/runs/{run_id}/events", { params: { path: { run_id: runId }, query: { after: lastEvent.current } } }),
      supabase().from("interview_turns").select("id, role, content, coverage").eq("run_id", runId).order("id"),
    ]);
    if (runRes.data) setRun(runRes.data);
    const fresh = (eventsRes.data ?? []).filter((e) => e.id > lastEvent.current);
    if (fresh.length > 0) {
      lastEvent.current = fresh[fresh.length - 1].id;
      setEvents((prev) => [...prev, ...fresh]);
    }
    if (turnsRes.data) setTurns(turnsRes.data as Turn[]);
  }, [runId]);

  useEffect(() => {
    // the first load and the fallback poll; Realtime below only speeds it up
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, POLL_MS);
    const channel = supabase()
      .channel(`run-${runId}`)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "interview_turns", filter: `run_id=eq.${runId}` }, () => refresh())
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "run_events", filter: `run_id=eq.${runId}` }, () => refresh())
      .subscribe();
    return () => {
      clearTimeout(first);
      clearInterval(timer);
      supabase().removeChannel(channel);
    };
  }, [runId, refresh]);

  async function send(body: { text: string | null; done: boolean }) {
    if (sending) return;
    setSending(true);
    setError("");
    const { error } = await api(key).POST("/runs/{run_id}/answer", { params: { path: { run_id: runId } }, body });
    setSending(false);
    if (error) setError(errorText(error));
    else {
      setAnswer("");
      refresh();
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = answer.trim();
    if (text) send({ text, done: false });
  }

  async function cancel() {
    const { error } = await api().POST("/runs/{run_id}/cancel", { params: { path: { run_id: runId } } });
    if (error) setError(errorText(error));
    else refresh();
  }

  // ---- what the events say ----
  const drafts = useMemo(
    () => events.filter((e) => e.type === "drafts").map((e) => e.payload as unknown as Drafts),
    [events],
  );
  const activity = useMemo(() => {
    const last = [...events].reverse().find((e) => e.type === "node_start" && typeof e.payload.node === "string");
    return last ? String(last.payload.node) : "";
  }, [events]);
  const interviewOver = run?.kind === "brief" || events.some((e) => e.type === "interview_end");
  const reached = useMemo(
    () =>
      events.reduce((max, e) => (e.type === "node_start" && typeof e.payload.node === "string" ? Math.max(max, stageOf(String(e.payload.node))) : max), 0),
    [events],
  );
  const coverage = [...turns].reverse().find((t) => t.coverage)?.coverage ?? null;

  // drafts go under the answer they came from: the first client bubble with the same text
  const byTurn = useMemo(() => {
    const placed = new Map<number, Draft[]>();
    for (const d of drafts) {
      const bubble = turns.find((t) => t.role === "client" && t.content === d.answer && !placed.has(t.id));
      if (bubble) placed.set(bubble.id, d.items);
    }
    return placed;
  }, [drafts, turns]);
  const allDrafts = drafts.flatMap((d) => d.items).reverse();

  const waiting = run?.status === "waiting_input";
  const finished = !!run && ["succeeded", "failed", "cancelled"].includes(run.status);
  const working = !!run && !waiting && !finished;
  const totals = coverage
    ? Object.entries(coverage.need).reduce(
        (acc, [area, need]) => ({ got: acc.got + Math.min(coverage.got[area] ?? 0, need), need: acc.need + need }),
        { got: 0, need: 0 },
      )
    : null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section aria-label="Разговор" className="flex min-w-0 flex-col rounded-panel border border-line bg-surface lg:h-[calc(100vh-200px)] lg:min-h-[560px]">
        {totals && (
          <div className="flex flex-col gap-2 px-5 pt-5 sm:px-6" role="group" aria-label={`Раскрыто тем: ${totals.got} из ${totals.need}`}>
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-medium">Раскрыто тем</span>
              <span className="ml-auto text-muted tabular-nums">
                {totals.got} из {totals.need}
              </span>
            </div>
            <span className="h-2 overflow-hidden rounded-full bg-raised" aria-hidden="true">
              <span
                className="block h-full rounded-full bg-gradient-to-r from-coral to-mint transition-[width] duration-700 ease-out-soft"
                style={{ width: `${Math.round((100 * totals.got) / Math.max(1, totals.need))}%` }}
              />
            </span>
          </div>
        )}

        <div className="flex min-h-[240px] flex-1 flex-col-reverse overflow-y-auto lg:min-h-0">
          <div className="flex flex-col gap-3 p-5 sm:p-6" aria-live="polite">
            {turns.length === 0 && !finished && (
              <p className="muted m-0">{run?.kind === "brief" ? "Агенты читают бриф…" : "Аналитик готовит первый вопрос…"}</p>
            )}
            {turns.map((t) => (
              <div key={t.id} className={`bubble ${t.role}`} data-role={t.role}>
                <span className="who">{t.role === "agent" ? "Аналитик" : "Вы"}</span>
                <p>{t.content}</p>
                {t.role === "client" && byTurn.get(t.id)?.map((d) => <DraftCard key={d.id} draft={d} />)}
              </div>
            ))}
            {working && !interviewOver && (
              <span role="status" className="inline-flex items-center gap-2 self-start rounded-2xl bg-raised px-4 py-2.5 text-sm text-muted">
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-coral" />
                {NODES[activity] ?? "думаю"}…
              </span>
            )}
          </div>
        </div>

        {waiting && (
          <form className="m-4 mt-0 flex flex-col gap-3 rounded-[18px] border border-line-2 bg-bg p-3 sm:m-5 sm:mt-0" onSubmit={submit}>
            <label htmlFor="answer" className="sr-only">
              Ваш ответ
            </label>
            <textarea
              id="answer"
              rows={2}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e);
              }}
              disabled={sending}
              placeholder="Ответьте своими словами…"
              className="!border-0 !bg-transparent !shadow-none"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="quiet" disabled={sending} onClick={() => send({ text: null, done: true })}>
                Готово, вопросов хватит
              </Button>
              <Button type="submit" className="ml-auto" disabled={sending || !answer.trim()}>
                Ответить
              </Button>
            </div>
          </form>
        )}

        {(interviewOver || finished) && run && <Build run={run} reached={reached} projectId={projectId} />}
        {error && (
          <p className="error mx-5 mb-4" role="alert">
            {error}
          </p>
        )}
      </section>

      <aside className="flex flex-col gap-4 self-start" aria-label="Что уже понятно">
        <section className="flex flex-col gap-2.5 rounded-panel border border-line bg-surface p-5" aria-label="Черновик ТЗ" aria-live="polite">
          <div className="flex items-baseline gap-2">
            <h2 className="m-0 font-sans text-xs font-medium tracking-[0.1em] text-muted">ЧЕРНОВИК ТЗ</h2>
            <span className="ml-auto text-[13px]">{allDrafts.length}</span>
          </div>
          {allDrafts.length === 0 ? (
            <p className="m-0 text-sm text-dim">Требования появятся после ваших ответов.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {allDrafts.slice(0, 8).map((d, i) => (
                <li key={d.id} className={cn("grid grid-cols-[10px_minmax(0,1fr)] items-start gap-2.5 rounded-lg p-2", i === 0 && "sg-rise bg-mint-fill")}>
                  <span className={cn("mt-1.5 size-2 rounded-full", KIND[d.kind]?.dot ?? "bg-dim")} aria-hidden="true" />
                  <span className="text-[13px] leading-snug">{d.title}</span>
                </li>
              ))}
            </ul>
          )}
          <Link href={`/projects/${projectId}/exports`} className="text-[13px] no-underline">
            Открыть документы →
          </Link>
        </section>

        {coverage && (
          <section className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-5" aria-label="Покрытие тем">
            <h2 className="m-0 font-sans text-xs font-medium tracking-[0.1em] text-muted">ПОКРЫТИЕ ТЕМ</h2>
            <ul className="m-0 grid list-none grid-cols-3 gap-2 p-0">
              {Object.entries(coverage.need).map(([area, need]) => {
                const got = coverage.got[area] ?? 0;
                const tone = got >= need ? "done" : got === 0 ? "gap" : "part";
                return (
                  <li
                    key={area}
                    className={cn(
                      "flex min-h-[74px] flex-col justify-between gap-1.5 rounded-xl border p-2.5 text-xs leading-tight",
                      tone === "done" && "border-mint bg-mint-fill",
                      tone === "gap" && "border-amber bg-amber-fill",
                      tone === "part" && "border-line bg-raised",
                    )}
                  >
                    <span className="min-h-[2.4em]">{AREAS[area] ?? area}</span>
                    <span className={cn("text-[13px] tabular-nums", tone === "done" ? "text-mint-text" : tone === "gap" ? "text-amber-text" : "text-muted")}>
                      {Math.min(got, need)}/{need}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <section className="flex flex-col gap-2 rounded-panel border border-line bg-surface p-5 text-sm">
          <p className="m-0" data-testid="run-status">
            Статус: <strong>{run ? STATUS[run.status] : "…"}</strong>
          </p>
          {run?.error && <p className="error m-0">{run.error}</p>}
          {run && !finished && (
            <Button variant="quiet" size="sm" className="self-start" onClick={cancel}>
              Отменить прогон
            </Button>
          )}
        </section>
      </aside>
    </div>
  );
}

function DraftCard({ draft }: { draft: Draft }) {
  const kind = KIND[draft.kind] ?? { label: draft.kind, dot: "bg-dim" };
  return (
    <div className="sg-rise mt-2 flex flex-col gap-1.5 rounded-2xl border border-line-2 bg-raised px-3.5 py-3 text-left">
      <span className="inline-flex items-center gap-2 text-xs text-muted">
        <span className={cn("size-2 rounded-full", kind.dot)} aria-hidden="true" />
        Черновик требования · {kind.label}
      </span>
      <span className="text-[15px] leading-normal text-fg">{draft.statement || draft.title}</span>
    </div>
  );
}

/** After the interview: the stages of putting the ТЗ together, then «ТЗ готово». */
function Build({ run, reached, projectId }: { run: Run; reached: number; projectId: string }) {
  const done = run.status === "succeeded";
  const failed = run.status === "failed" || run.status === "cancelled";
  return (
    <div className="m-4 mt-0 flex flex-col gap-3 rounded-[18px] border border-line bg-bg p-4 sm:m-5 sm:mt-0" aria-live="polite">
      <div className="flex items-center gap-2">
        <h2 className="m-0 font-display text-lg font-bold">{done ? "ТЗ готово" : failed ? "Сборка остановилась" : "Собираем ваше ТЗ"}</h2>
        {!done && !failed && <Badge tone="coral">обычно меньше минуты</Badge>}
      </div>
      <ol className="m-0 flex list-none flex-col gap-1 p-0">
        {STAGES.map((s, i) => {
          const state = done || i < reached ? "done" : i === reached && !failed ? "run" : "wait";
          return (
            <li key={s.name} className={cn("flex min-h-10 items-center gap-3 rounded-xl px-2", state === "run" && "bg-surface", state === "wait" && "opacity-60")}>
              {state === "done" ? (
                <span className="inline-flex size-6 items-center justify-center rounded-full bg-mint text-[#16302a]">
                  <Check aria-hidden="true" className="size-4" />
                </span>
              ) : state === "run" ? (
                <LoaderCircle aria-hidden="true" className="size-6 animate-spin text-coral" />
              ) : (
                <span className="inline-flex size-6 items-center justify-center">
                  <span className="size-2.5 rounded-full border-2 border-line-2" />
                </span>
              )}
              <span className={cn("text-[15px]", state === "run" && "font-semibold")}>{s.name}</span>
            </li>
          );
        })}
      </ol>
      {done && (
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href={`/projects/${projectId}/exports`}>
              Открыть документы
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href={`/projects/${projectId}/report`}>Посмотреть проверки</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
