"use client";
// The exported files of a project (T-505, T-511): the list from the API and links signed by Storage.
// Storage signs under the bucket policy, so only the owner of the project gets the links.
import { useCallback, useEffect, useState } from "react";

import { api, errorText } from "@/lib/api";
import type { ExportFile } from "@/lib/results";
import { supabase } from "@/lib/supabase";

export const LINK_SECONDS = 3600;
export const SHARE_SECONDS = 7 * 24 * 3600;

/** A scheme picture of the export (img/<kind>-<stem>.svg or img/PRC-01.svg) by what it shows. */
export function schemeLabel(name: string): string {
  const stem = name.replace(/^img\//, "").replace(/\.svg$/, "");
  if (stem.startsWith("dbml-")) return "Данные";
  if (stem.startsWith("plantuml-")) return stem.includes("seq") ? "Порядок действий (UML)" : "Сценарии использования (UML)";
  if (stem.startsWith("structurizr-")) return "Архитектура (C4)";
  return `Процесс ${stem}`;
}

export function useExports(projectId: string) {
  const [files, setFiles] = useState<ExportFile[] | null>(null);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const sign = useCallback(async (list: ExportFile[]) => {
    if (list.length === 0) return;
    const { data, error } = await supabase()
      .storage.from("exports")
      .createSignedUrls(
        list.map((f) => f.path),
        LINK_SECONDS,
      );
    if (error) {
      setError(`Ссылки не получены: ${error.message}`);
      return;
    }
    const signed: Record<string, string> = {};
    for (const d of data ?? []) if (d.path && d.signedUrl) signed[d.path] = d.signedUrl;
    setLinks((old) => ({ ...old, ...signed }));
  }, []);

  useEffect(() => {
    api()
      .GET("/projects/{project_id}/exports", { params: { path: { project_id: projectId } } })
      .then(({ data, error }) => {
        if (error || !data) return setError(errorText(error));
        setFiles(data);
        void sign(data);
      });
  }, [projectId, sign]);

  const make = useCallback(async () => {
    setError("");
    const { data, error } = await api().POST("/projects/{project_id}/exports", {
      params: { path: { project_id: projectId } },
    });
    if (error || !data) return setError(errorText(error));
    setFiles((old) => [...data, ...(old ?? []).filter((f) => f.rev !== data[0]?.rev)]);
    void sign(data);
  }, [projectId, sign]);

  const rev = files && files.length > 0 ? Math.max(...files.map((f) => f.rev)) : null;
  const latest = (files ?? []).filter((f) => f.rev === rev);
  return { files, latest, rev, links, error, make };
}

/** A link to one file for a week: for the contractor, who has no account here. */
export async function shareLink(path: string): Promise<{ url?: string; error?: string }> {
  const { data, error } = await supabase().storage.from("exports").createSignedUrl(path, SHARE_SECONDS);
  return error || !data ? { error: error?.message ?? "нет ссылки" } : { url: data.signedUrl };
}
