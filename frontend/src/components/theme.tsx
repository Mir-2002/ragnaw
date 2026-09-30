"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

// Frames are next-themes themes stored as data-frame on <html>. "light" and "dark" are
// next-themes' names for what "system" resolves to, so AUTO picks blue or night.
// Blue (the daytime grass look) is the default; AUTO and NIGHT stay available in OPTION.
export const FRAMES = [
  { theme: "system", label: "Auto" },
  { theme: "light", label: "Blue" },
  { theme: "red", label: "Red" },
  { theme: "green", label: "Green" },
  { theme: "dark", label: "Night" },
] as const;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="data-frame"
      themes={["light", "red", "green", "dark"]}
      value={{ light: "blue", red: "red", green: "green", dark: "night" }}
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
