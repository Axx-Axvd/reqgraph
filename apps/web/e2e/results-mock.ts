// The mock mode of T-505: a project with a graph, a CI report and exports, answered in the test.
// Registered after installMock, so these routes win; anything else falls back to installMock.
import type { Page, Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const PROJECT = "00000000-0000-4000-8000-0000000000b1";
const BPMN = join(__dirname, "../../../packages/core/tests/dsl/golden/PRC-01_booking.bpmn");
const DSL = JSON.parse(readFileSync(join(__dirname, "../../../examples/garage61/models/processes/PRC-01_booking.process.json"), "utf-8"));

const graph = {
  schema_version: 1,
  nodes: {
    "BR-001": { id: "BR-001", kind: "BR", status: "draft", title: "Меньше звонков администратору" },
    "UR-001": { id: "UR-001", kind: "UR", status: "draft", title: "Клиент записывается сам" },
    "FR-001": { id: "FR-001", kind: "FR", status: "draft", title: "Каталог услуг", statement: "Система должна показывать список услуг." },
    "FR-002": { id: "FR-002", kind: "FR", status: "draft", title: "Выбор времени", statement: "Система должна показывать свободное время." },
    "ACT-01": { id: "ACT-01", kind: "ACT", status: "draft", name: "Клиент" },
    "PRC-01": { id: "PRC-01", kind: "PRC", status: "draft", name: "Онлайн-запись", dsl: DSL },
    "TURN-0001": { id: "TURN-0001", kind: "TURN", status: "draft", role: "agent", text: "Как сейчас записываются?" },
    "TURN-0002": { id: "TURN-0002", kind: "TURN", status: "draft", role: "client", text: "Хочу, чтобы клиент сам видел свободные окна" },
  },
  edges: [
    { from: "UR-001", rel: "refines", to: "BR-001" },
    { from: "FR-001", rel: "refines", to: "UR-001" },
    { from: "FR-002", rel: "refines", to: "UR-001" },
    { from: "FR-001", rel: "realized_by", to: "PRC-01.T01" },
    { from: "UR-001", rel: "derived_from", to: "TURN-0001" },
    { from: "FR-002", rel: "derived_from", to: "TURN-0002" },
  ],
  high_water: {},
};

const report = {
  schema_version: 1,
  project: "e2e",
  checks: [
    { id: "ISO-001", title: "Однозначность", group: "iso", status: "failed", errors: 1, warnings: 0, infos: 0 },
    { id: "SND-001", title: "Процесс", group: "snd", status: "warning", errors: 0, warnings: 1, infos: 0 },
  ],
  findings: [
    { check_id: "ISO-001", severity: "error", node_ids: ["FR-002"], message: "FR-002: размытое слово «быстро»", hint: "Укажите число.", owner: "analyst" },
    { check_id: "SND-001", severity: "warning", node_ids: ["PRC-01.T01"], message: "PRC-01.T01: шаг без исполнителя", hint: null, owner: "modeler" },
  ],
  summary: { errors: 1, warnings: 1, infos: 0, passed: 0, failed: 1, warned: 1, skipped: 0, status: "fail" },
};

export async function installResults(page: Page): Promise<void> {
  const now = new Date().toISOString();
  const exported: Record<string, unknown>[] = [];
  const json = (route: Route, body: unknown, code = 200) =>
    route.fulfill({ status: code, contentType: "application/json", body: JSON.stringify(body), headers: { "access-control-allow-origin": "*" } });
  const project = { id: PROJECT, name: "Автосервис e2e", head_rev: 1, standards: [], created_at: now };

  await page.route("http://api.test/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "OPTIONS") return route.fallback();
    if (path === `/projects/${PROJECT}`) return json(route, project);
    if (path === `/projects/${PROJECT}/graph`) {
      return json(route, { project_id: PROJECT, rev: 1, graph, ci_summary: null, author: "agent", created_at: now });
    }
    if (path === `/projects/${PROJECT}/report`) return json(route, report);
    if (path === `/projects/${PROJECT}/processes/PRC-01/bpmn`) {
      return route.fulfill({ status: 200, contentType: "application/xml", body: readFileSync(BPMN, "utf-8"), headers: { "access-control-allow-origin": "*" } });
    }
    if (path === `/projects/${PROJECT}/exports`) {
      if (req.method() === "POST" && exported.length === 0) {
        for (const name of ["tz_gost34.docx", "srs.docx", "srs.md", "req.reqif", "img/PRC-01.svg", "img/plantuml-use_cases.svg"]) {
          exported.push({ id: `00000000-0000-4000-8000-00000000f00${exported.length}`, rev: 1, format: name.split(".").pop(), path: `${PROJECT}/1/${name}`, name, created_at: now });
        }
      }
      return json(route, exported);
    }
    return route.fallback();
  });

  await page.route("http://sb.test/storage/v1/object/sign/exports/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/storage/v1/object/sign/exports/", "");
    return json(route, { signedURL: `/object/sign/exports/${path}?token=week` });
  });

  await page.route("http://sb.test/storage/v1/object/sign/exports", async (route) => {
    const { paths } = route.request().postDataJSON() as { paths: string[] };
    return json(route, paths.map((p) => ({ path: p, signedURL: `/object/sign/exports/${p}?token=t`, error: null })));
  });
}
