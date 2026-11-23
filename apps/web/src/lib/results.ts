// Types and helpers of the project results (T-505): the graph, the CI report, the exports.
import type { components } from "./api-types";

export type Report = components["schemas"]["CIReport"];
export type Finding = components["schemas"]["Finding"];
export type ExportFile = components["schemas"]["ExportOut"];

export type GraphNode = { id: string; kind: string; [field: string]: unknown };
export type GraphEdge = { from: string; rel: string; to: string };
export type Graph = { nodes: Record<string, GraphNode>; edges: GraphEdge[] };

export const KINDS: Record<string, string> = {
  BR: "бизнес-требования",
  UR: "пользовательские",
  FR: "функциональные",
  NFR: "нефункциональные",
  CON: "ограничения",
  ACT: "роли",
  PRC: "процессы",
  ENT: "сущности",
  UC: "сценарии использования",
  C4: "элементы C4",
  TURN: "реплики интервью",
  SEC: "разделы документов",
};

/** Kinds hidden at first: there are many of them and they are context, not the model. */
export const HIDDEN_AT_FIRST = ["TURN", "SEC"];

export const RELS: Record<string, string> = {
  refines: "уточняет",
  realized_by: "реализуется в",
  derived_from: "выведено из",
  rendered_in: "в разделе",
  conflicts_with: "противоречит",
  depends_on: "зависит от",
};

export const SEVERITY: Record<Finding["severity"], string> = {
  error: "ошибка",
  warning: "предупреждение",
  info: "замечание",
};

/** A process step (PRC-01.T03, PRC-01.G01) is shown on the BPMN scheme of its process. */
const STEP = /^(PRC-\d+)\.[A-Za-z]\w*$/;

export function processOf(id: string): string | null {
  return STEP.exec(id)?.[1] ?? null;
}

/** Where a node of a finding is shown: the step on its BPMN scheme, anything else on the graph. */
export function nodeHref(projectId: string, id: string): string {
  const process = processOf(id);
  return process
    ? `/projects/${projectId}/processes/${process}?el=${encodeURIComponent(id)}`
    : `/projects/${projectId}/graph?node=${encodeURIComponent(id)}`;
}

/** A short label of a node: its title, name or statement. */
export function nodeTitle(node: GraphNode): string {
  for (const field of ["title", "name", "statement", "text", "heading"]) {
    const value = node[field];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

/** The client's words a node came from: its own derived_from turn, else the nearest one up the
 * refines / realized_by chain (a FR refines a UR that was said in the interview). */
export function quoteOf(graph: Graph, id: string): string | null {
  const seen = new Set<string>();
  let level = [id];
  while (level.length > 0) {
    const next: string[] = [];
    for (const current of level) {
      if (seen.has(current)) continue;
      seen.add(current);
      for (const e of graph.edges) {
        if (e.from !== current) continue;
        const to = graph.nodes[e.to];
        if (e.rel === "derived_from" && to?.kind === "TURN" && to.role === "client" && typeof to.text === "string") {
          return to.text;
        }
        if (e.rel === "refines") next.push(e.to);
      }
    }
    level = next;
  }
  return null;
}

/** Requirements realized by a process step (PRC-01.T03): `realizes` of the DSL and realized_by edges. */
export function realizersOf(graph: Graph, stepRef: string, realizes: string[] = []): string[] {
  const ids = new Set(realizes);
  for (const e of graph.edges) if (e.rel === "realized_by" && e.to === stepRef) ids.add(e.from);
  return [...ids].filter((id) => graph.nodes[id]).sort();
}

export type DslElement = { id: string; type: string; name?: string; lane?: string | null; realizes?: string[] };
export type ProcessDsl = { id: string; name: string; lanes?: string[]; nodes: DslElement[]; flows?: (string[])[] };

/** `via` — the label of the gateway branch that leads to the step («нет»), when there is one. */
export type Step = { element: DslElement; branches: { label: string; to: string }[]; via: string };

/** The steps of a process in reading order: depth-first from the start events along the flows,
 * each element once; a gateway keeps the labels of its branches. */
export function stepsOf(dsl: ProcessDsl): Step[] {
  const byId = new Map(dsl.nodes.map((n) => [n.id, n]));
  const out = new Map<string, { label: string; to: string }[]>();
  for (const [src, dst, label] of dsl.flows ?? []) {
    if (!out.has(src)) out.set(src, []);
    out.get(src)!.push({ label: label ?? "", to: dst });
  }
  const steps: Step[] = [];
  const seen = new Set<string>();
  const visit = (id: string, via: string) => {
    const element = byId.get(id);
    if (!element || seen.has(id)) return;
    seen.add(id);
    steps.push({ element, branches: out.get(id) ?? [], via });
    for (const b of out.get(id) ?? []) visit(b.to, b.label);
  };
  for (const n of dsl.nodes) if (n.type === "start") visit(n.id, "");
  for (const n of dsl.nodes) visit(n.id, ""); // anything not reachable from a start
  return steps;
}

/** A remark of a check for a person: the leading «FR-002: » becomes the requirement's own words. */
export function plainMessage(message: string, graph: Graph | null): string {
  const m = /^([A-Z][A-Z0-9]*-\d+(?:\.[A-Za-z]\w*)?):\s*([\s\S]*)$/.exec(message);
  if (!m) return message;
  const title = graph ? titleOf(graph, m[1]) : "";
  return title ? `«${title}»: ${m[2]}` : m[2];
}

/** The words of a node or of a process step, without its id. */
export function titleOf(graph: Graph, id: string): string {
  const process = processOf(id);
  if (process) {
    const dsl = graph.nodes[process]?.dsl as ProcessDsl | undefined;
    const local = id.slice(process.length + 1);
    return dsl?.nodes.find((n) => n.id === local)?.name || (graph.nodes[process] ? nodeTitle(graph.nodes[process]) : "");
  }
  return graph.nodes[id] ? nodeTitle(graph.nodes[id]) : "";
}
