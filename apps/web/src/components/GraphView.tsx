"use client";
// The requirements graph (T-505): React Flow draws, dagre lays the nodes out in layers.
// `focus` (a node id from ?node=) is selected, centred and marked with the class is-focused.
import "@xyflow/react/dist/style.css";

import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  HIDDEN_AT_FIRST,
  KINDS,
  RELS,
  nodeTitle,
  processOf,
  type Graph,
  type GraphNode,
} from "@/lib/results";

const WIDTH = 190;
const HEIGHT = 64;
const SKIP = new Set(["id", "kind", "status", "assumption", "dsl"]);

/** The colour of a kind: the left border of its nodes, its swatch in the legend, its dot on the mini map. */
const KIND_COLOR: Record<string, string> = {
  BR: "var(--coral)",
  UR: "var(--coral)",
  FR: "#8fc7ff",
  NFR: "#8fc7ff",
  CON: "#8fc7ff",
  ACT: "var(--mint)",
  UC: "var(--mint)",
  PRC: "var(--amber)",
  ENT: "var(--amber)",
  C4: "var(--amber)",
  TURN: "var(--dim)",
  SEC: "var(--dim)",
};

/** An edge to a process step (PRC-01.T03) goes to its process node. */
function target(id: string): string {
  return processOf(id) ?? id;
}

function layout(graph: Graph, shown: Set<string>, focus: string | null, selected: string | null) {
  const ids = Object.values(graph.nodes)
    .filter((n) => shown.has(n.kind))
    .map((n) => n.id);
  const visible = new Set(ids);
  const edges = graph.edges
    .map((e) => ({ ...e, to: target(e.to) }))
    .filter((e) => visible.has(e.from) && visible.has(e.to));
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 56 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const id of ids) g.setNode(id, { width: WIDTH, height: HEIGHT });
  // refines and realized_by point from the detail to the whole: draw the whole above
  for (const e of edges) g.setEdge(e.to, e.from);
  dagre.layout(g);
  const nodes: Node[] = ids.map((id) => {
    const node = graph.nodes[id];
    const at = g.node(id);
    const classes = [`kind-${node.kind}`];
    if (id === focus) classes.push("is-focused");
    return {
      id,
      position: { x: at.x - WIDTH / 2, y: at.y - HEIGHT / 2 },
      data: {
        label: (
          <span className="graph-node">
            <b>{id}</b>
            <span>{nodeTitle(node)}</span>
          </span>
        ),
      },
      className: classes.join(" "),
      selected: id === selected,
      style: { width: WIDTH },
    };
  });
  const flow: Edge[] = edges.map((e, i) => ({
    id: `${e.from}-${e.rel}-${e.to}-${i}`,
    source: e.to,
    target: e.from,
    label: RELS[e.rel] ?? e.rel,
    className: `rel-${e.rel}`,
  }));
  return { nodes, edges: flow };
}

export function GraphView(props: { graph: Graph; projectId: string; focus: string | null }) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}

function GraphCanvas({ graph, projectId, focus }: { graph: Graph; projectId: string; focus: string | null }) {
  const present = useMemo(() => {
    const kinds = new Set(Object.values(graph.nodes).map((n) => n.kind));
    return Object.keys(KINDS).filter((k) => kinds.has(k));
  }, [graph]);
  const focusKind = focus ? graph.nodes[focus]?.kind : undefined;
  const [shown, setShown] = useState<Set<string>>(() => {
    const first = present.filter((k) => !HIDDEN_AT_FIRST.includes(k) || k === focusKind);
    return new Set(first.length > 0 ? first : present); // only interview turns so far: show them
  });
  const [selected, setSelected] = useState<string | null>(focus);
  const { nodes, edges } = useMemo(() => layout(graph, shown, focus, selected), [graph, shown, focus, selected]);
  const flow = useReactFlow();

  useEffect(() => {
    if (!focus || !graph.nodes[focus]) return;
    const timer = setTimeout(() => flow.fitView({ nodes: [{ id: focus }], maxZoom: 1.2, duration: 300 }), 50);
    return () => clearTimeout(timer);
  }, [flow, focus, graph]);

  function toggle(kind: string) {
    setShown((old) => {
      const next = new Set(old);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  const current = selected ? graph.nodes[selected] : undefined;
  return (
    <>
      {focus && !graph.nodes[focus] && (
        <p className="error" role="alert">
          Узла {focus} нет в этой ревизии графа.
        </p>
      )}
      <fieldset className="filters">
        <legend>Показывать · цвет полосы — вид узла</legend>
        {present.map((kind) => (
          <label key={kind} className="check">
            <input type="checkbox" checked={shown.has(kind)} onChange={() => toggle(kind)} />
            <span aria-hidden="true" className="inline-block h-3 w-1 rounded-sm" style={{ background: KIND_COLOR[kind] }} />
            {KINDS[kind]}
          </label>
        ))}
      </fieldset>
      <div className="graph-layout">
        <div className="graph-canvas" data-testid="graph">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            minZoom={0.1}
            onlyRenderVisibleElements
            nodesDraggable={false}
            nodesConnectable={false}
            onNodeClick={(_, node) => setSelected(node.id)}
          >
            <Background />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              ariaLabel="Мини-карта графа"
              nodeColor={(n) => KIND_COLOR[graph.nodes[n.id]?.kind ?? ""] ?? "var(--dim)"}
              bgColor="var(--bg)"
              maskColor="color-mix(in srgb, var(--bg) 60%, transparent)"
            />
          </ReactFlow>
        </div>
        {current && <NodePanel node={current} graph={graph} projectId={projectId} />}
      </div>
    </>
  );
}

function NodePanel({ node, graph, projectId }: { node: GraphNode; graph: Graph; projectId: string }) {
  const out = graph.edges.filter((e) => e.from === node.id);
  const into = graph.edges.filter((e) => target(e.to) === node.id);
  const link = (id: string) => `/projects/${projectId}/graph?node=${encodeURIComponent(target(id))}`;
  return (
    <aside className="card node-panel" aria-label={`Узел ${node.id}`}>
      <h2>
        {node.id} <span className="muted">· {KINDS[node.kind] ?? node.kind}</span>
      </h2>
      <dl>
        {Object.entries(node)
          .filter(([k, v]) => !SKIP.has(k) && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join("; ") : typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
      </dl>
      {node.kind === "PRC" && (
        <p>
          <Link href={`/projects/${projectId}/processes/${node.id}`}>Схема BPMN</Link>
        </p>
      )}
      {out.length + into.length > 0 && (
        <ul className="list">
          {out.map((e, i) => (
            <li key={`o${i}`}>
              {RELS[e.rel] ?? e.rel} <Link href={link(e.to)}>{e.to}</Link>
            </li>
          ))}
          {into.map((e, i) => (
            <li key={`i${i}`}>
              <Link href={link(e.from)}>{e.from}</Link> {RELS[e.rel] ?? e.rel} {e.to !== node.id ? e.to : "этот узел"}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
