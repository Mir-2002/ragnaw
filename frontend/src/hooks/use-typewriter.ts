"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Reveal `text` a few characters at a time, like handheld dialogue. The text may keep
 * growing while it streams in; the reveal just keeps catching up.
 */
export function useTypewriter(text: string, charsPerSecond: number) {
  const [shown, setShown] = useState(0);
  const progress = useRef(0);
  const instant = !Number.isFinite(charsPerSecond);
  const behind = !instant && shown < text.length;

  useEffect(() => {
    if (!behind) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      progress.current = Math.min(
        text.length,
        progress.current + ((now - last) / 1000) * charsPerSecond,
      );
      last = now;
      setShown(Math.floor(progress.current));
      if (progress.current < text.length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [behind, text.length, charsPerSecond]);

  const visible = instant ? text.length : shown;
  return { text: text.slice(0, visible), done: visible >= text.length };
}
