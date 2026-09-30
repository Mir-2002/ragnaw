import { cn } from "@/lib/utils";

/** A dialogue-box frame: outline, colored band, light inner edge, stepped corners. */
export function Frame({
  className,
  fillClassName,
  children,
  ...props
}: React.ComponentProps<"div"> & { fillClassName?: string }) {
  return (
    <div className={cn("frame px-notch", className)} {...props}>
      <div className="frame-band px-notch">
        <div className={cn("frame-fill px-notch", fillClassName)}>{children}</div>
      </div>
    </div>
  );
}

/** The blinking ▼ a handheld shows when a line of dialogue is finished. */
export function MoreArrow({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("px-blink select-none text-[var(--accent)]", className)}>
      ▼
    </span>
  );
}
