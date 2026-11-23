"use client";
// A BPMN scheme (T-505): bpmn-js in view mode, the XML compiled by the API from the process DSL.
// `focus` (?el=PRC-01.T03) gets the marker is-focused and is scrolled into view.
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";

import { Maximize, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

type Canvas = {
  zoom: ((level: "fit-viewport" | number, center?: "auto") => void) & (() => number);
  addMarker: (id: string, marker: string) => void;
  scrollToElement: (element: unknown) => void;
};
type Registry = { get: (id: string) => unknown };

export function BpmnView({ xml, focus }: { xml: string; focus: string | null }) {
  const box = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<Canvas | null>(null);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let viewer: { importXML: (xml: string) => Promise<unknown>; get: (name: string) => unknown; destroy: () => void } | null = null;
    let alive = true;
    import("bpmn-js/lib/NavigatedViewer").then(async ({ default: NavigatedViewer }) => {
      if (!alive || !box.current) return;
      viewer = new NavigatedViewer({ container: box.current }) as unknown as typeof viewer;
      try {
        await viewer!.importXML(xml);
      } catch (exc) {
        setError(`Схема не открылась: ${exc instanceof Error ? exc.message : String(exc)}`);
        return;
      }
      const canvas = viewer!.get("canvas") as Canvas;
      canvas.zoom("fit-viewport", "auto");
      canvasRef.current = canvas;
      if (focus) {
        const element = (viewer!.get("elementRegistry") as Registry).get(focus);
        if (element) {
          canvas.addMarker(focus, "is-focused");
          canvas.scrollToElement(element);
        } else {
          setMissing(true);
        }
      }
    });
    return () => {
      alive = false;
      canvasRef.current = null;
      viewer?.destroy();
    };
  }, [xml, focus]);

  function zoomBy(factor: number) {
    const canvas = canvasRef.current;
    if (canvas) canvas.zoom(Math.min(4, Math.max(0.2, canvas.zoom() * factor)));
  }

  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {missing && (
        <p className="error" role="alert">
          Шага {focus} нет на этой схеме.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Масштаб схемы">
        <Button variant="secondary" size="icon" aria-label="Уменьшить" onClick={() => zoomBy(1 / 1.25)}>
          <Minus aria-hidden="true" />
        </Button>
        <Button variant="secondary" size="icon" aria-label="Увеличить" onClick={() => zoomBy(1.25)}>
          <Plus aria-hidden="true" />
        </Button>
        <Button variant="secondary" size="sm" onClick={() => canvasRef.current?.zoom("fit-viewport", "auto")}>
          <Maximize aria-hidden="true" />
          Вписать
        </Button>
        <span className="text-sm text-dim">или колесо мыши и перетаскивание</span>
      </div>
      <div ref={box} className="bpmn-canvas" data-testid="bpmn" />
    </>
  );
}
