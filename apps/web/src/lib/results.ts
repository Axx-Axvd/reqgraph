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
