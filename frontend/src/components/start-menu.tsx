"use client";

import { Menu } from "@base-ui/react/menu";
import { useState } from "react";
import { Frame } from "@/components/retro";

const ITEM =
  "px-cursor px-label block w-full cursor-pointer py-1 pr-2 text-left outline-none data-disabled:cursor-default data-disabled:opacity-40";

const HINTS = {
  examples: "Pick a sample question to ask.",
  newChat: "Clear this conversation and start over.",
  option: "Change text speed and the frame style.",
  about: "Where the answers come from.",
  exit: "Close this menu.",
};

type Props = {
  examples: string[];
  canAsk: boolean;
  canClear: boolean;
  onAsk: (question: string) => void;
  onNewChat: () => void;
  onOption: () => void;
  onAbout: () => void;
};

/** The START menu: a right-hand overlay with a ▶ cursor, like the handheld games. */
export function StartMenu({ examples, canAsk, canClear, onAsk, onNewChat, onOption, onAbout }: Props) {
  const [hint, setHint] = useState(HINTS.examples);
  const describe = (text: string) => ({
    onFocus: () => setHint(text),
    onPointerEnter: () => setHint(text),
  });

  return (
    <Menu.Root>
      <Menu.Trigger className="px-button px-label text-xs">Start</Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={10} className="z-50 outline-none">
          <Menu.Popup className="flex w-60 flex-col gap-2 outline-none">
            <Frame fillClassName="px-text flex flex-col py-3">
              <Menu.SubmenuRoot>
                <Menu.SubmenuTrigger className={ITEM} {...describe(HINTS.examples)}>
                  Examples
                </Menu.SubmenuTrigger>
                <Menu.Portal>
                  <Menu.Positioner side="left" align="start" sideOffset={10} className="z-50 outline-none">
                    <Menu.Popup className="w-80 max-w-[calc(100vw-1.5rem)] outline-none">
                      <Frame fillClassName="px-text flex flex-col gap-1 py-3">
                        {examples.map((question) => (
                          <Menu.Item
                            key={question}
                            className={ITEM.replace("px-label ", "")}
                            disabled={!canAsk}
                            onClick={() => onAsk(question)}
                          >
                            {question}
                          </Menu.Item>
                        ))}
                      </Frame>
                    </Menu.Popup>
                  </Menu.Positioner>
                </Menu.Portal>
              </Menu.SubmenuRoot>
              <Menu.Item className={ITEM} disabled={!canClear} onClick={onNewChat} {...describe(HINTS.newChat)}>
                New chat
              </Menu.Item>
              <Menu.Item className={ITEM} onClick={onOption} {...describe(HINTS.option)}>
                Option
              </Menu.Item>
              <Menu.Item className={ITEM} onClick={onAbout} {...describe(HINTS.about)}>
                About
              </Menu.Item>
              <Menu.Item className={ITEM} {...describe(HINTS.exit)}>
                Exit
              </Menu.Item>
            </Frame>
            {/* Like the handheld menus, the highlighted item is explained below. */}
            <Frame fillClassName="px-text py-3 leading-snug" aria-live="polite">
              {hint}
            </Frame>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
