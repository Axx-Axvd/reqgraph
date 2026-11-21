"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ProjectTabs } from "@/components/ProjectTabs";
import { Shell } from "@/components/Shell";
import { api, errorText } from "@/lib/api";
import type { ExportFile } from "@/lib/results";
import { supabase } from "@/lib/supabase";

const LINK_SECONDS = 3600;
const LABELS: Record<string, string> = {
  "srs.docx": "SRS по ISO/IEC/IEEE 29148 (Word)",
  "srs.md": "SRS (Markdown)",
  "tz_gost34.docx": "ТЗ по ГОСТ 34.602 (Word)",
  "tz_gost34.md": "ТЗ по ГОСТ 34.602 (Markdown)",
  "tz_gost19.docx": "ТЗ на программу по ГОСТ 19.201 (Word)",
  "tz_gost19.md": "ТЗ на программу по ГОСТ 19.201 (Markdown)",
  "req.reqif": "Требования в ReqIF",
};

export default function ExportsPage() {
  return (
    <Shell>
      <ExportsScreen />
    </Shell>
  );
}

function ExportsScreen() {
  const { id } = useParams<{ id: string }>();
  const [files, setFiles] = useState<ExportFile[] | null>(null);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // links are signed by Storage under the bucket policy: only the owner of the project gets them
  const sign = useCallback(async (list: ExportFile[]) => {
    if (list.length === 0) return;
    const { data, error } = await supabase()
      .storage.from("exports")
      .createSignedUrls(
        list.map((f) => f.path),
        LINK_SECONDS,
        { download: true },
      );
    if (error) {
      setError(`Ссылки не получены: ${error.message}`);
      return;
    }
    const signed: Record<string, string> = {};
    for (const d of data ?? []) if (d.path && d.signedUrl) signed[d.path] = d.signedUrl;
    setLinks(signed);
  }, []);

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/exports", { params: { path: { project_id: id } } })
      .then(({ data, error }) => {
        if (error || !data) return setError(errorText(error));
        setFiles(data);
        void sign(data);
      });
  }, [id, sign]);

  async function make() {
    setBusy(true);
    setError("");
    const { data, error } = await api().POST("/projects/{project_id}/exports", { params: { path: { project_id: id } } });
    setBusy(false);
    if (error || !data) return setError(errorText(error));
    const rest = (files ?? []).filter((f) => f.rev !== data[0]?.rev);
    setFiles([...data, ...rest]);
    void sign(data);
  }

  const revs = [...new Set((files ?? []).map((f) => f.rev))].sort((a, b) => b - a);
  return (
    <>
      <ProjectTabs projectId={id} />
      <h1>Выгрузка</h1>
      <p className="muted">
        Документы последней ревизии: SRS, ТЗ по ГОСТ 34.602 и ГОСТ 19.201 (Word и Markdown), требования в ReqIF и
        картинки схем. Ссылки действуют час.
      </p>
      <div className="row">
        <button type="button" className="button" disabled={busy} onClick={make}>
          {busy ? "Собираем документы…" : "Сделать документы"}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {files && files.length === 0 && <p className="muted">Выгрузок пока нет.</p>}
      {revs.map((rev) => (
        <section key={rev} className="card">
          <h2>Ревизия {rev}</h2>
          <ul className="list" data-testid={`exports-${rev}`}>
            {(files ?? [])
              .filter((f) => f.rev === rev && !f.name.startsWith("img/"))
              .map((f) => (
                <FileLink key={f.id} file={f} href={links[f.path]} />
              ))}
          </ul>
          <details>
            <summary>Картинки схем</summary>
            <ul className="list">
              {(files ?? [])
                .filter((f) => f.rev === rev && f.name.startsWith("img/"))
                .map((f) => (
                  <FileLink key={f.id} file={f} href={links[f.path]} />
                ))}
            </ul>
          </details>
        </section>
      ))}
    </>
  );
}

function FileLink({ file, href }: { file: ExportFile; href?: string }) {
  const label = LABELS[file.name] ?? file.name;
  return <li>{href ? <a href={href}>{label}</a> : <span className="muted">{label}</span>}</li>;
}
