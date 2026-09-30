"use client";

import { useSyncExternalStore } from "react";

export const TEXT_SPEEDS = [
  { id: "slow", label: "Slow", charsPerSecond: 30 },
  { id: "mid", label: "Mid", charsPerSecond: 70 },
  { id: "fast", label: "Fast", charsPerSecond: 180 },
  { id: "instant", label: "Instant", charsPerSecond: Infinity },
] as const;

export type TextSpeed = (typeof TEXT_SPEEDS)[number]["id"];

const KEY = "ragnaw:text-speed";
const listeners = new Set<() => void>();
// The choice lives in memory; localStorage only carries it across visits.
let current: TextSpeed | null = null;

function read(): TextSpeed {
  if (current) return current;
  try {
    const stored = localStorage.getItem(KEY);
    if (TEXT_SPEEDS.some((s) => s.id === stored)) return (current = stored as TextSpeed);
  } catch {
    // Storage can be blocked (private windows, strict settings).
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (current = reduced ? "instant" : "fast");
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setSpeed(next: TextSpeed) {
  current = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // Still applies for this visit.
  }
  listeners.forEach((listener) => listener());
}

export function useTextSpeed() {
  const speed = useSyncExternalStore(subscribe, read, () => "fast" as TextSpeed);
  return [speed, setSpeed] as const;
}

export function charsPerSecond(speed: TextSpeed): number {
  return TEXT_SPEEDS.find((s) => s.id === speed)!.charsPerSecond;
}
