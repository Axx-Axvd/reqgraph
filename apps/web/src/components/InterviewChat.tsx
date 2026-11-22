"use client";
// The interview chat (T-504): questions and answers come from interview_turns, the progress from
// run_events. Supabase Realtime pushes new rows; a 2-second poll of the API is the fallback
// (07_deploy), so the chat works whether Realtime is up or not.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { AREAS, api, errorText, STATUS, type Run, type RunEvent } from "@/lib/api";
import { useOwnKey } from "@/lib/own-key";
import { supabase } from "@/lib/supabase";

type Turn = { id: number; role: "agent" | "client"; content: string };
type Coverage = { got: Record<string, number>; need: Record<string, number> };

const NODES: Record<string, string> = {
  intake: "читаем бриф",
  analyst: "аналитик записывает требования",
  coverage: "считаем, какие темы уже раскрыты",
  interviewer: "интервьюер готовит вопрос",
  modeler: "строим модели процессов и данных",
  modeler_views: "строим сценарии использования и C4",
  standards: "собираем SRS",
  ci_check: "проверяем модели и требования",
  reviewer: "разбираем замечания проверок",
  export: "готовим документы",
};
const POLL_MS = 2000;

export function InterviewChat({ runId, projectId }: { runId: string; projectId: string }) {
  const { key } = useOwnKey();
  const [run, setRun] = useState<Run | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activity, setActivity] = useState("");
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const lastEvent = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const client = api();
    const [runRes, eventsRes, turnsRes] = await Promise.all([
      client.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }),
      client.GET("/runs/{run_id}/events", {
        params: { path: { run_id: runId }, query: { after: lastEvent.current } },
      }),
      supabase()
        .from("interview_turns")
        .select("id, role, content")
        .eq("run_id", runId)
        .order("id"),
    ]);
    if (runRes.data) setRun(runRes.data);
    const events: RunEvent[] = eventsRes.data ?? [];
    if (events.length > 0) {
      lastEvent.current = events[events.length - 1].id;
      for (const e of events) {
        if (e.type === "node_start" && typeof e.payload.node === "string") {
          setActivity(NODES[e.payload.node] ?? "");
        }
        if (e.type === "coverage") setCoverage(e.payload as unknown as Coverage);
      }
    }
    if (turnsRes.data) setTurns(turnsRes.data as Turn[]);
  }, [runId]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    const channel = supabase()
      .channel(`run-${runId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "interview_turns", filter: `run_id=eq.${runId}` },
        () => refresh(),
      )
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "run_events", filter: `run_id=eq.${runId}` },
        () => refresh(),
      )
      .subscribe();
    return () => {
      clearInterval(timer);
      supabase().removeChannel(channel);
    };
  }, [runId, refresh]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [turns.length]);

  async function send(reply: { text?: string; done?: boolean; simpler?: boolean }) {
    const body = { text: reply.text ?? null, done: reply.done ?? false, simpler: reply.simpler ?? false };
    setSending(true);
    setError("");
    const { error } = await api(key).POST("/runs/{run_id}/answer", {
      params: { path: { run_id: runId } },
      body,
    });
    setSending(false);
    if (error) setError(errorText(error));
    else {
      setAnswer("");
      refresh();
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (answer.trim()) send({ text: answer.trim() });
  }

  async function cancel() {
    const { error } = await api().POST("/runs/{run_id}/cancel", { params: { path: { run_id: runId } } });
    if (error) setError(errorText(error));
    else refresh();
  }

  const waiting = run?.status === "waiting_input";
  const finished = run && ["succeeded", "failed", "cancelled"].includes(run.status);
  return (
    <div className="chat-layout">
      <section className="chat" aria-label="Интервью" aria-live="polite">
        {turns.length === 0 && <p className="muted">Агенты читают бриф и готовят первый вопрос…</p>}
        {turns.map((t) => (
          <div key={t.id} className={`bubble ${t.role}`} data-role={t.role}>
            <span className="who">{t.role === "agent" ? "Аналитик" : "Вы"}</span>
            <p>{t.content}</p>
          </div>
        ))}
        <div ref={bottom} />
      </section>
      <aside className="side">
        <p data-testid="run-status">
          Статус: <strong>{run ? STATUS[run.status] : "…"}</strong>
        </p>
        {run && !waiting && !finished && activity && <p className="muted">Сейчас: {activity}…</p>}
        {run?.error && <p className="error">{run.error}</p>}
        {coverage && (
          <ul className="coverage" aria-label="Покрытие тем">
            {Object.entries(coverage.need).map(([area, need]) => (
              <li key={area} className={(coverage.got[area] ?? 0) >= need ? "done" : ""}>
                {AREAS[area] ?? area}: {coverage.got[area] ?? 0} из {need}
              </li>
            ))}
          </ul>
        )}
        {finished && (
          <p>
            <Link href={`/projects/${projectId}`}>Результат появится на странице проекта</Link>
          </p>
        )}
        {run && !finished && (
          <button type="button" className="link" onClick={cancel}>Отменить прогон</button>
        )}
      </aside>
      {waiting && (
        <form className="answer" onSubmit={submit}>
          <label htmlFor="answer">Ваш ответ</label>
          <textarea
            id="answer"
            rows={3}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={sending}
          />
          <div className="row">
            <button type="submit" className="button" disabled={sending || !answer.trim()}>Ответить</button>
            <button type="button" className="button secondary" disabled={sending} onClick={() => send({ simpler: true })}>
              Слишком сложно — проще
            </button>
            <button type="button" className="button secondary" disabled={sending} onClick={() => send({ done: true })}>
              Готово, вопросов хватит
            </button>
          </div>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
