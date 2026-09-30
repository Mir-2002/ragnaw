"use client";

import { Dialog } from "@base-ui/react/dialog";
import { useTheme } from "next-themes";
import { useRef } from "react";
import { Frame } from "@/components/retro";
import { FRAMES } from "@/components/theme";
import { TEXT_SPEEDS, useTextSpeed } from "@/hooks/use-text-speed";
import { cn } from "@/lib/utils";

type DialogProps = { open: boolean; onOpenChange: (open: boolean) => void };

function Shell({ open, onOpenChange, title, children }: DialogProps & { title: string; children: React.ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/35" />
        <Dialog.Popup className="fixed top-1/2 left-1/2 z-50 w-[28rem] max-w-[calc(100vw-1.5rem)] -translate-x-1/2 -translate-y-1/2 outline-none">
          <Frame fillClassName="px-text flex flex-col gap-4">
            <Dialog.Title className="px-label text-sm text-[var(--frame-band)]">{title}</Dialog.Title>
            {children}
            <Dialog.Close className="px-button px-label self-end text-xs">
              <span className="px-key">B</span> Close
            </Dialog.Close>
          </Frame>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * OPTION: text speed and frame, like the handheld options screen. ↑/↓ picks a row,
 * ←/→ changes it, and changes apply immediately.
 */
export function OptionDialog(props: DialogProps) {
  const [speed, setSpeed] = useTextSpeed();
  const { theme = "system", setTheme } = useTheme();
  const rows = useRef<(HTMLDivElement | null)[]>([]);

  const settings = [
    {
      label: "Text speed",
      options: TEXT_SPEEDS.map((s) => ({ value: s.id as string, label: s.label })),
      value: speed as string,
      set: (v: string) => setSpeed(v as typeof speed),
    },
    {
      label: "Frame",
      options: FRAMES.map((f) => ({ value: f.theme as string, label: f.label })),
      value: theme,
      set: setTheme,
    },
  ];

  function onKeyDown(event: React.KeyboardEvent, row: number) {
    const setting = settings[row];
    const at = setting.options.findIndex((o) => o.value === setting.value);
    const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (step) {
      event.preventDefault();
      const next = (at + step + setting.options.length) % setting.options.length;
      setting.set(setting.options[next].value);
    }
    const move = { ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (move) {
      event.preventDefault();
      rows.current[(row + move + settings.length) % settings.length]?.focus();
    }
  }

  return (
    <Shell {...props} title="Option">
      <div className="flex flex-col gap-3">
        {settings.map((setting, row) => (
          <div
            key={setting.label}
            ref={(el) => {
              rows.current[row] = el;
            }}
            role="radiogroup"
            aria-label={setting.label}
            tabIndex={0}
            onKeyDown={(e) => onKeyDown(e, row)}
            // The ▶ cursor marks the focused row, so no outline is needed.
            className="px-cursor flex flex-col gap-1 outline-none focus-visible:outline-none sm:flex-row sm:items-baseline sm:gap-4"
          >
            <span className="px-label w-28 shrink-0 text-xs">{setting.label}</span>
            <span className="flex flex-wrap gap-x-3 gap-y-1">
              {setting.options.map((option) => {
                const selected = option.value === setting.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    tabIndex={-1}
                    onClick={() => setting.set(option.value)}
                    className={cn(
                      "px-label cursor-pointer text-xs",
                      // Selected options turn red, as on the handheld options screen.
                      selected ? "text-[var(--accent)]" : "text-[var(--ink-soft)]",
                    )}
                  >
                    {option.label}
                  </button>
                );
              })}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[var(--ink-soft)]">↑↓ choose a setting · ←→ change it</p>
    </Shell>
  );
}

export function AboutDialog(props: DialogProps) {
  return (
    <Shell {...props} title="About RAGNaw">
      <div className="flex flex-col gap-3 leading-snug">
        <p>
          RAGNaw answers Pokémon questions from a snapshot of PokeAPI’s data: stats, types,
          matchups, evolutions, moves, abilities and Pokédex entries, as of the latest games.
        </p>
        <p>
          For each question, an LLM looks things up with a set of tools and search, then writes
          the answer from what it found. The sources under each answer show what it used.
        </p>
        <p className="text-[var(--ink-soft)]">
          Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data and sprites
          from{" "}
          <a href="https://pokeapi.co" target="_blank" rel="noreferrer" className="underline underline-offset-2">
            PokeAPI
          </a>
          .
        </p>
      </div>
    </Shell>
  );
}
