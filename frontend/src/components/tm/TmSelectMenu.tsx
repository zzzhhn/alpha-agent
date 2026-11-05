"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import clsx from "clsx";

export interface TmSelectMenuOption {
  readonly value: string;
  readonly label: ReactNode;
  readonly meta?: ReactNode;
  readonly disabled?: boolean;
}

interface TmSelectMenuProps {
  readonly value: string;
  readonly options: readonly TmSelectMenuOption[];
  readonly onChange: (next: string) => void;
  readonly ariaLabel: string;
  readonly placeholder?: ReactNode;
  readonly size?: "xs" | "sm" | "md";
  readonly align?: "start" | "end";
  readonly menuMinWidth?: number;
  readonly disabled?: boolean;
  readonly className?: string;
  readonly buttonClassName?: string;
  readonly menuClassName?: string;
}

const SIZE_CLASSES = {
  xs: "h-6 text-xs",
  sm: "h-7 text-xs",
  md: "h-8 text-xs",
};

const VIEWPORT_GAP = 8;
const MENU_MAX_HEIGHT = 288;

export function tmMenuVerticalPosition(top: number, bottom: number, viewportHeight: number, contentHeight: number) {
  const below = Math.max(0, viewportHeight - bottom - VIEWPORT_GAP - 4);
  const above = Math.max(0, top - VIEWPORT_GAP - 4);
  const desired = Math.min(MENU_MAX_HEIGHT, contentHeight);
  const openAbove = below < desired && above > below;
  const maxHeight = Math.min(MENU_MAX_HEIGHT, openAbove ? above : below);
  return {
    top: openAbove ? Math.max(VIEWPORT_GAP, top - 4 - Math.min(desired, maxHeight)) : bottom + 4,
    maxHeight,
  };
}

/** Portal-backed listbox for styled selection when native Safari controls fail. */
export function TmSelectMenu({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = "Select",
  size = "sm",
  align = "start",
  menuMinWidth,
  disabled,
  className,
  buttonClassName,
  menuClassName,
}: TmSelectMenuProps) {
  const buttonId = useId();
  const listboxId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: MENU_MAX_HEIGHT });

  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const selected = options.find((option) => option.value === value);

  const enabledIndex = useCallback((start: number, direction: 1 | -1) => {
    if (options.length === 0) return -1;
    for (let step = 0; step < options.length; step += 1) {
      const index = (start + direction * step + options.length) % options.length;
      if (!options[index]?.disabled) return index;
    }
    return -1;
  }, [options]);

  const place = useCallback(() => {
    const trigger = buttonRef.current;
    const list = listRef.current;
    if (!trigger || !list || typeof window === "undefined") return;
    const rect = trigger.getBoundingClientRect();
    const availableWidth = Math.max(0, window.innerWidth - VIEWPORT_GAP * 2);
    const width = Math.min(
      Math.max(rect.width, menuMinWidth ?? rect.width),
      availableWidth,
    );
    const preferredLeft = align === "end" ? rect.right - width : rect.left;
    // Measure at the final width so wrapped labels determine the real height.
    // A short upward menu must stay attached to its trigger, not reserve 288px.
    list.style.width = `${width}px`;
    const vertical = tmMenuVerticalPosition(rect.top, rect.bottom, window.innerHeight, list.scrollHeight + 2);
    setPosition({
      ...vertical,
      left: Math.min(
        Math.max(preferredLeft, VIEWPORT_GAP),
        window.innerWidth - width - VIEWPORT_GAP,
      ),
      width,
    });
  }, [align, menuMinWidth]);

  const openMenu = useCallback((index = selectedIndex) => {
    if (disabled || options.length === 0) return;
    const next = enabledIndex(index, 1);
    setActiveIndex(next < 0 ? 0 : next);
    setOpen(true);
  }, [disabled, enabledIndex, options.length, selectedIndex]);

  const closeMenu = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) buttonRef.current?.focus();
  }, []);

  const choose = useCallback((index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    closeMenu(true);
  }, [closeMenu, onChange, options]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
    listRef.current?.focus();
  }, [open, place]);

  useLayoutEffect(() => {
    if (!open) return;
    const list = listRef.current;
    const option = list?.children[activeIndex] as HTMLElement | undefined;
    if (!list || !option) return;
    const top = option.offsetTop;
    const bottom = top + option.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }, [activeIndex, open, position.maxHeight]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || listRef.current?.contains(target)) return;
      closeMenu();
    }
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [closeMenu, open, place]);

  function move(direction: 1 | -1) {
    const next = enabledIndex(activeIndex + direction, direction);
    if (next >= 0) setActiveIndex(next);
  }

  return (
    <span className={clsx("inline-flex min-w-0", className)}>
      <button
        ref={buttonRef}
        id={buttonId}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            openMenu(event.key === "ArrowDown" ? selectedIndex : options.length - 1);
          } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            openMenu(event.key === "Home" ? 0 : options.length - 1);
          }
        }}
        className={clsx(
          "flex min-w-0 items-center justify-between gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-tm-fg outline-none transition-colors hover:border-tm-rule-2 focus-visible:border-tm-accent disabled:cursor-not-allowed disabled:text-tm-muted",
          SIZE_CLASSES[size],
          buttonClassName,
        )}
      >
        <span className="min-w-0 truncate text-left">{selected?.label ?? placeholder}</span>
        <ChevronDown
          aria-hidden="true"
          className={clsx("h-3 w-3 shrink-0 text-tm-muted transition-transform", open && "rotate-180")}
          strokeWidth={1.75}
        />
      </button>
      {open && typeof document !== "undefined"
        ? createPortal(
            <ul
              ref={listRef}
              id={listboxId}
              role="listbox"
              tabIndex={0}
              aria-labelledby={buttonId}
              aria-activedescendant={`${listboxId}-option-${activeIndex}`}
              style={{
                position: "fixed",
                top: position.top,
                left: position.left,
                width: position.width,
                maxHeight: position.maxHeight,
                maxWidth: `calc(100vw - ${VIEWPORT_GAP * 2}px)`,
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  move(1);
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  move(-1);
                } else if (event.key === "Home" || event.key === "End") {
                  event.preventDefault();
                  const next = enabledIndex(event.key === "Home" ? 0 : options.length - 1, event.key === "Home" ? 1 : -1);
                  if (next >= 0) setActiveIndex(next);
                } else if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  choose(activeIndex);
                } else if (event.key === "Escape") {
                  event.preventDefault();
                  event.stopPropagation();
                  closeMenu(true);
                } else if (event.key === "Tab") {
                  // Continue the normal tab order from the trigger, not the
                  // portal appended at the end of document.body.
                  closeMenu(true);
                }
              }}
              className={clsx(
                "relative z-[80] overflow-y-auto border border-tm-rule-2 bg-tm-bg-2 py-0.5 font-tm-mono text-xs text-tm-fg shadow-[var(--tm-shadow-floating)] outline-none focus-visible:ring-1 focus-visible:ring-tm-accent",
                menuClassName,
              )}
            >
              {options.map((option, index) => (
                <li
                  key={option.value}
                  id={`${listboxId}-option-${index}`}
                  role="option"
                  aria-selected={option.value === value}
                  aria-disabled={option.disabled || undefined}
                  onMouseMove={() => !option.disabled && setActiveIndex(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(index)}
                  className={clsx(
                    "flex min-h-7 cursor-pointer items-center gap-2 px-2 py-1.5",
                    index === activeIndex && "bg-tm-bg-3",
                    option.value === value ? "text-tm-accent" : "text-tm-fg",
                    option.disabled && "cursor-not-allowed opacity-45",
                  )}
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="break-words">{option.label}</span>
                    {option.meta !== undefined && option.meta !== null ? (
                      <span className="break-words text-xs text-tm-muted">{option.meta}</span>
                    ) : null}
                  </span>
                  <Check
                    aria-hidden="true"
                    className={clsx("h-3 w-3 shrink-0", option.value !== value && "invisible")}
                    strokeWidth={1.75}
                  />
                </li>
              ))}
            </ul>,
            document.body,
          )
        : null}
    </span>
  );
}
