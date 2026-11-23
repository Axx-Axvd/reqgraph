"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText } from "@/lib/api";
import { SEVERITY, nodeHref, type Finding, type Report } from "@/lib/results";

export default function ReportPage() {
  return (
    <Shell>
      <ReportScreen />
    </Shell>
  );
}

function ReportScreen() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [only, setOnly] = useState<Finding["severity"] | "">("");

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/report", { params: { path: { project_id: id } } })
      .then(({ data, error }) => (error || !data ? setError(errorText(error)) : setReport(data)));
  }, [id]);

  const findings = report?.findings.filter((f) => !only || f.severity === only) ?? [];
  return (
    <>
      <ProjectTabs projectId={id} />
      <h1>Проверки</h1>
      {error && <p className="error">{error}</p>}
      {!report && !error && <Loading />}
      {report && (
        <>
          <p data-testid="report-summary">
            Ошибок: <b>{report.summary.errors}</b> · предупреждений: <b>{report.summary.warnings}</b> · замечаний:{" "}
            <b>{report.summary.infos}</b> · проверок: {report.checks.length}
          </p>
          <div className="row" role="group" aria-label="Фильтр">
            {(["", "error", "warning", "info"] as const).map((s) => (
              <button
                key={s || "all"}
                type="button"
                className={`button secondary${only === s ? " active" : ""}`}
                aria-pressed={only === s}
                onClick={() => setOnly(s)}
              >
                {s ? SEVERITY[s] : "все"}
              </button>
            ))}
          </div>
          {findings.length === 0 ? (
            <p className="ok">{report.findings.length === 0 ? "Все проверки пройдены." : "Нет находок этого вида."}</p>
          ) : (
            <ul className="findings">
              {findings.map((f, i) => (
                <FindingRow key={`${f.check_id}-${i}`} finding={f} projectId={id} />
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}

function FindingRow({ finding, projectId }: { finding: Finding; projectId: string }) {
  const router = useRouter();
  const first = finding.node_ids[0];
  const open = () => first && router.push(nodeHref(projectId, first));
  return (
    <li className={`finding ${finding.severity}`}>
      <button type="button" className="finding-main" onClick={open} disabled={!first} data-testid="finding">
        <span className="badge">{SEVERITY[finding.severity]}</span>
        <code>{finding.check_id}</code> {finding.message}
      </button>
      {finding.hint && <p className="muted">{finding.hint}</p>}
      {finding.node_ids.length > 1 && (
        <p className="nodes">
          {finding.node_ids.map((n) => (
            <Link key={n} href={nodeHref(projectId, n)}>
              {n}
            </Link>
          ))}
        </p>
      )}
    </li>
  );
}
