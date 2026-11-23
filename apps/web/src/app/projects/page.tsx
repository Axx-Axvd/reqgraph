"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText, type Project } from "@/lib/api";
import { START_KEY } from "@/lib/example";

export default function Projects() {
  return (
    <Shell>
      <ProjectList />
    </Shell>
  );
}

function ProjectList() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");

  // what the visitor typed on the landing page waits in sessionStorage across the sign-in
  const [started] = useState(() => {
    try {
      return (typeof window === "undefined" ? null : sessionStorage.getItem(START_KEY)) ?? "";
    } catch {
      return "";
    }
  });
  const [name, setName] = useState(() => started.split(/[,.;]/)[0].slice(0, 80));
  const [brief, setBrief] = useState(started);

  useEffect(() => {
    api()
      .GET("/projects")
      .then(({ data, error }) => (error ? setError(errorText(error)) : setProjects(data ?? [])));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    const { data, error } = await api().POST("/projects", {
      body: { name, brief: brief.trim() || null },
    });
    if (error || !data) {
      setError(errorText(error));
      return;
    }
    try {
      sessionStorage.removeItem(START_KEY);
    } catch {
      // nothing kept
    }
    router.push(`/projects/${data.id}`);
  }

  return (
    <>
      <h1>Проекты</h1>
      <form onSubmit={create} className="card stack" aria-label="Новый проект">
        <h2>Новый проект</h2>
        <label>
          Название
          <input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Бриф: что за дело и что нужно автоматизировать
          <textarea rows={6} value={brief} onChange={(e) => setBrief(e.target.value)} />
        </label>
        <button type="submit" className="button">Создать</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {projects === null ? (
        <Loading />
      ) : projects.length === 0 ? (
        <p className="muted">Проектов пока нет.</p>
      ) : (
        <ul className="list">
          {projects.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`}>{p.name}</Link>
              <span className="muted"> · версия графа {p.head_rev}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
