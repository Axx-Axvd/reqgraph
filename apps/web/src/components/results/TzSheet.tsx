"use client";
// The ТЗ sheet (T-511): the requirements of the last revision on paper, by section, with contents.
// A click on an item shows «Откуда это в ТЗ»: the client's words and what the checks said.
// It is a preview: the full document by ГОСТ 34.602 with every section and scheme is the Word file.
import { CircleCheck, Quote, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import { nodeHref, nodeTitle, plainMessage, quoteOf, type Finding, type Graph, type GraphNode } from "@/lib/results";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { kind: "BR", title: "Цели и назначение системы" },
  { kind: "UR", title: "Что нужно пользователям" },
  { kind: "FR", title: "Требования к функциям" },
  { kind: "NFR", title: "Требования к качеству" },
  { kind: "CON", title: "Ограничения" },
];

function textOf(node: GraphNode): string {
  return typeof node.statement === "string" && node.statement ? node.statement : nodeTitle(node);
}

export function TzSheet({
  graph,
  findings,
  projectId,
  projectName,
}: {
  graph: Graph;
  findings: Finding[];
  projectId: string;
  projectName: string;
}) {
  const sections = SECTIONS.map((s) => ({
    ...s,
    items: Object.values(graph.nodes)
      .filter((n) => n.kind === s.kind)
      .sort((a, b) => a.id.localeCompare(b.id)),
  })).filter((s) => s.items.length > 0);
  const [selected, setSelected] = useState<string | null>(null);

  if (sections.length === 0) {
    return <p className="m-0 text-muted">Требований пока нет: они появятся после интервью.</p>;
  }
  const node = selected ? graph.nodes[selected] : undefined;
  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <article
        aria-label="Лист ТЗ"
        className="rounded-panel bg-paper px-5 py-7 font-serif text-[16px] leading-relaxed text-paper-fg shadow-[var(--shadow)] sm:px-10"
      >
        <p className="m-0 mb-1 font-sans text-xs tracking-[0.08em] text-[#55596a]">ТЕХНИЧЕСКОЕ ЗАДАНИЕ · ГОСТ 34.602-2020</p>
        <h2 className="m-0 mb-5 font-serif text-2xl font-bold [overflow-wrap:anywhere]">{projectName}</h2>
        <nav aria-label="Содержание" className="mb-6 font-sans text-sm">
          <p className="m-0 mb-1 font-semibold">Содержание</p>
          <ol className="m-0 list-none p-0">
            {sections.map((s, i) => (
              <li key={s.kind}>
                <a href={`#tz-${s.kind}`} className="text-[#a8401c]">
                  {i + 1}. {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        {sections.map((s, i) => (
          <section key={s.kind} id={`tz-${s.kind}`} className="mb-6 scroll-mt-24">
            <h3 className="m-0 mb-3 font-serif text-lg font-bold">
              {i + 1}. {s.title}
            </h3>
            <ol className="m-0 flex list-none flex-col gap-1 p-0">
              {s.items.map((item, j) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-pressed={selected === item.id}
                    onClick={() => setSelected(item.id)}
                    className={cn(
                      "w-full rounded-md px-2 py-1.5 text-left font-serif leading-relaxed text-paper-fg hover:bg-[#f1ece2]",
                      selected === item.id && "bg-[#fde3d6]",
                    )}
                  >
                    <span className="font-sans text-sm text-[#55596a]">
                      {i + 1}.{j + 1}.
                    </span>{" "}
                    {textOf(item)}
                  </button>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </article>
      <aside aria-label="Откуда это в ТЗ" className="lg:sticky lg:top-20">
        {node ? (
          <Origin node={node} graph={graph} findings={findings} projectId={projectId} />
        ) : (
          <Card className="p-5 text-muted">Нажмите на пункт ТЗ — покажем, из каких ваших слов он получился и что сказали проверки.</Card>
        )}
      </aside>
    </div>
  );
}

function Origin({ node, graph, findings, projectId }: { node: GraphNode; graph: Graph; findings: Finding[]; projectId: string }) {
  const said = quoteOf(graph, node.id);
  const mine = findings.filter((f) => f.node_ids.includes(node.id));
  return (
    <Card className="flex flex-col gap-4 p-5" data-testid="origin">
      <h2 className="m-0 text-base">Откуда это в ТЗ</h2>
      <div className="flex flex-col gap-1.5">
        <p className="m-0 text-xs font-semibold tracking-wide text-dim uppercase">Ваши слова</p>
        {said ? (
          <p className="m-0 flex gap-2 text-client">
            <Quote aria-hidden="true" className="mt-1 size-4 shrink-0 text-coral" />
            <span>«{said}»</span>
          </p>
        ) : (
          <p className="m-0 text-muted">Сформулировано аналитиком из брифа и соседних требований.</p>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <p className="m-0 text-xs font-semibold tracking-wide text-dim uppercase">Проверки</p>
        {mine.length === 0 ? (
          <p className="m-0 flex items-center gap-2 text-mint-text">
            <CircleCheck aria-hidden="true" className="size-4" />
            Замечаний нет
          </p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {mine.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-amber" />
                <span>
                  {plainMessage(f.message, graph)}
                  {f.hint && <span className="block text-muted">{f.hint}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Link href={nodeHref(projectId, node.id)} className="text-sm">
        Показать на схеме
      </Link>
    </Card>
  );
}
