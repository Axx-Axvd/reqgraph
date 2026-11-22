// The mock mode: the API and Supabase REST answered in the test, with an interview that asks
// numbered questions until «done» — the same shape the stub models give in the stack mode.
import type { Page, Route } from "@playwright/test";

type Turn = { id: number; role: "agent" | "client"; content: string };

export async function installMock(page: Page): Promise<void> {
  const projects: Record<string, unknown>[] = [];
  const turns: Turn[] = [];
  let status = "queued";
  let asked = 0;
  const runId = "00000000-0000-4000-8000-0000000000r1".replace("r", "a");
  const now = () => new Date().toISOString();
  const json = (route: Route, body: unknown, code = 200) =>
    route.fulfill({ status: code, contentType: "application/json", body: JSON.stringify(body), headers: { "access-control-allow-origin": "*" } });
  const ask = () => {
    asked += 1;
    turns.push({ id: turns.length + 1, role: "agent", content: `Вопрос ${asked}: как это устроено у вас сейчас?` });
    status = "waiting_input";
  };
  const run = (projectId: string) => ({
    id: runId, project_id: projectId, kind: "interview", status, iteration: 0, cost_usd: 0,
    error: null, byok: false, created_at: now(), started_at: now(), finished_at: status === "succeeded" ? now() : null,
  });

  await page.route("http://api.test/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    }
    if (path === "/usage") return json(route, { runs_today: 0, runs_limit: 3, cost_today_usd: 0, unlimited: false });
    if (path === "/projects" && req.method() === "GET") return json(route, projects);
    if (path === "/projects" && req.method() === "POST") {
      const body = req.postDataJSON() as { name: string };
      const project = { id: "00000000-0000-4000-8000-0000000000b1", name: body.name, head_rev: 0, standards: [], created_at: now() };
      projects.push(project);
      return json(route, project, 201);
    }
    const projectRuns = path.match(/^\/projects\/([^/]+)\/runs$/);
    if (projectRuns) {
      setTimeout(ask, 300); // the worker asks a moment later
      return json(route, { run: run(projectRuns[1]), job: { id: 1, run_id: runId, kind: "start", status: "queued", created_at: now() } }, 201);
    }
    if (/^\/projects\/[^/]+$/.test(path)) return json(route, projects[0]);
    if (path.endsWith("/events")) return json(route, []);
    if (path.endsWith("/answer")) {
      const body = req.postDataJSON() as { text?: string; done?: boolean; simpler?: boolean };
      if (body.text) turns.push({ id: turns.length + 1, role: "client", content: body.text });
      status = "running";
      if (body.simpler) {
        // T-320: the worker's «проще» turn, then the same question in plainer words
        turns.push({ id: turns.length + 1, role: "client", content: "Слишком сложно — можно проще?" });
        setTimeout(() => {
          turns.push({ id: turns.length + 1, role: "agent", content: `Вопрос ${asked}, проще: как вы это делаете сейчас?` });
          status = "waiting_input";
        }, 300);
      } else setTimeout(() => (body.done ? (status = "succeeded") : ask()), 300);
      return json(route, { id: 2, run_id: runId, kind: "resume", status: "queued", created_at: now() }, 202);
    }
    if (path.startsWith("/runs/")) return json(route, run(String(projects[0]?.id ?? "")));
    return json(route, { detail: `нет заглушки для ${path}` }, 404);
  });

  await page.route("http://sb.test/rest/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const object = (route.request().headers()["accept"] ?? "").includes("vnd.pgrst.object");
    if (url.pathname.endsWith("/interview_turns")) return json(route, turns);
    if (url.pathname.endsWith("/graph_revisions")) {
      const row = { files: { "brief.md": "Стоматология, 3 кресла." } };
      return json(route, object ? row : [row]);
    }
    if (url.pathname.endsWith("/runs")) return json(route, []);
    return json(route, []);
  });
  await page.route("http://sb.test/auth/v1/**", (route) => json(route, {}));
}
