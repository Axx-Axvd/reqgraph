"use client";
// «Как это будет работать» (T-511): each process as steps in plain words, who does what, with the
// client's words each step came from. Built from the process DSL kept on the PRC node.
import { ArrowRight, Clock, GitFork, Quote } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  nodeTitle,
  quoteOf,
  realizersOf,
  stepsOf,
  type Graph,
  type ProcessDsl,
  type Step,
} from "@/lib/results";
import { cn } from "@/lib/utils";

const WAITS = new Set(["timer", "message"]);
const TASKS = new Set(["task", "user_task", "service_task"]);

export function ProcessStory({ graph, projectId }: { graph: Graph; projectId: string }) {
  const processes = Object.values(graph.nodes)
    .filter((n) => n.kind === "PRC")
    .sort((a, b) => a.id.localeCompare(b.id));
  if (processes.length === 0) {
    return (
      <Card className="p-6">
        <h2 className="m-0 text-lg">Процессов пока нет</h2>
        <p className="m-0 mt-2 text-muted">
          Они появятся, когда аналитик соберёт требования из интервью: кто что делает и в каком порядке.
        </p>
      </Card>
    );
  }
  return (
    <div className="flex flex-col gap-5">
      {processes.map((p) => {
        const dsl = p.dsl as ProcessDsl | undefined;
        return (
          <Card key={p.id} className="p-5 sm:p-6" data-testid="process-story">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
              <h2 className="m-0 text-lg">{nodeTitle(p)}</h2>
              <Link className="text-sm" href={`/projects/${projectId}/processes/${p.id}`}>
                Схема процесса
              </Link>
            </div>
            {dsl?.lanes && dsl.lanes.length > 0 && (
              <p className="m-0 mt-1 text-sm text-muted">Участники: {dsl.lanes.join(", ")}</p>
            )}
            {dsl ? (
              <ol className="m-0 mt-4 flex list-none flex-col gap-3 p-0">
                {stepsOf(dsl).map((step) => (
                  <StepItem key={step.element.id} step={step} dsl={dsl} graph={graph} />
                ))}
              </ol>
            ) : (
              <p className="m-0 mt-3 text-muted">Шаги этого процесса ещё не описаны.</p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function StepItem({ step, dsl, graph }: { step: Step; dsl: ProcessDsl; graph: Graph }) {
  const { element, branches } = step;
  const via = step.via ? `если «${step.via}»: ` : "";
  const name = element.name?.trim() ?? "";
  const nameOf = (id: string) => dsl.nodes.find((n) => n.id === id)?.name || "дальше";

  if (element.type === "start") {
    return <li className="text-sm font-semibold tracking-wide text-dim uppercase">Начало: {name || "старт"}</li>;
  }
  if (element.type === "end") {
    return (
      <li className="flex items-center gap-2 text-sm text-muted">
        <ArrowRight aria-hidden="true" className="size-4 text-mint" />
        {via}Итог: {name || "процесс завершён"}
      </li>
    );
  }
  if (WAITS.has(element.type)) {
    return (
      <li className="flex items-center gap-2 text-sm text-muted">
        <Clock aria-hidden="true" className="size-4 text-amber" />
        {via}Ждём: {name}
      </li>
    );
  }
  if (!TASKS.has(element.type)) {
    // a gateway: a question with labelled branches is worth reading; a bare split is not
    const labelled = branches.filter((b) => b.label);
    if (!name && labelled.length === 0) return null;
    return (
      <li className="rounded-control border border-dashed border-line-2 px-4 py-3">
        <p className="m-0 flex items-center gap-2 font-medium">
          <GitFork aria-hidden="true" className="size-4 text-amber" />
          {name || "Развилка"}
        </p>
        {labelled.length > 0 && (
          <ul className="m-0 mt-2 flex list-none flex-col gap-1 p-0 text-sm text-muted">
            {labelled.map((b) => (
              <li key={`${b.label}-${b.to}`}>
                {b.label} → {nameOf(b.to)}
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  }
  const said = realizersOf(graph, `${dsl.id}.${element.id}`, element.realizes)
    .map((id) => quoteOf(graph, id))
    .find((q) => q);
  return (
    <li className="flex flex-col gap-1.5 rounded-control bg-raised px-4 py-3">
      <p className="m-0 flex flex-wrap items-center gap-2">
        {step.via && <span className="text-sm text-amber-text">если «{step.via}»:</span>}
        {element.lane && (
          <Badge tone={element.type === "user_task" ? "coral" : "neutral"} className={cn("ring-1 ring-inset", element.type === "user_task" ? "bg-transparent ring-coral-line" : "ring-line-2")}>
            {element.lane}
          </Badge>
        )}
        <span>{name}</span>
      </p>
      {said && (
        <p className="m-0 flex gap-1.5 text-[13px] text-coral-text">
          <Quote aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span>со слов: «{said}»</span>
        </p>
      )}
    </li>
  );
}
