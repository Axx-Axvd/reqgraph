"use client";
// The light / dark switch (T-508): the choice is kept in localStorage and set on <html> before paint
// by THEME_SCRIPT, so the page never flashes the other theme.
import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

export const THEME_KEY = "sg-theme";
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");document.documentElement.dataset.theme=t==="light"?"light":"dark"}catch(e){document.documentElement.dataset.theme="dark"}`;

type Theme = "light" | "dark";

// The theme lives on <html data-theme>; the toggle subscribes to that attribute.
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
const current = (): Theme => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
const onServer = (): Theme => "dark";

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, current, onServer);

  function toggle() {
    const next: Theme = theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // private mode: the choice lives until the tab closes
    }
  }

  const light = theme === "light";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={light ? "Тёмная тема" : "Светлая тема"}
      title={light ? "Тёмная тема" : "Светлая тема"}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl border border-line-2 text-fg transition-transform duration-300 ease-spring hover:-rotate-12 active:scale-90"
    >
      {light ? <Moon aria-hidden="true" className="size-[18px]" /> : <Sun aria-hidden="true" className="size-[18px]" />}
    </button>
  );
}
