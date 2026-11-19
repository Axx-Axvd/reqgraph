"use client";
// A BPMN scheme (T-505): bpmn-js in view mode, the XML compiled by the API from the process DSL.
// `focus` (?el=PRC-01.T03) gets the marker is-focused and is scrolled into view.
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";

import { useEffect, useRef, useState } from "react";

type Canvas = {
  zoom: (level: "fit-viewport" | number, center?: "auto") => void;
  addMarker: (id: string, marker: string) => void;
  scrollToElement: (element: unknown) => void;
};
type Registry = { get: (id: string) => unknown };

export function BpmnView({ xml, focus }: { xml: string; focus: string | null }) {
  const box = useRef<HTMLDivElement>(null);
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
      viewer?.destroy();
    };
  }, [xml, focus]);

  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {missing && (
        <p className="error" role="alert">
          Шага {focus} нет на этой схеме.
        </p>
      )}
      <div ref={box} className="bpmn-canvas" data-testid="bpmn" />
    </>
  );
}
