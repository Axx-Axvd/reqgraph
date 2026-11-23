"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import { Loading } from "@/components/ui/skeleton";
import { api, errorText, type Project } from "@/lib/api";

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
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [error, setError] = useState("");

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
