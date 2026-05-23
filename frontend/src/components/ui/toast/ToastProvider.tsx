"use client";

import { createContext, useCallback, useReducer, type ReactNode } from "react";

export type ToastKind = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: string;
  kind: ToastKind;
  message: string;
  duration: number;
  action?: ToastAction;
}

interface ToastContextValue {
  items: ToastItem[];
  enqueue: (toast: Omit<ToastItem, "id">) => string;
  dismiss: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

type Action =
  | { type: "enqueue"; item: ToastItem }
  | { type: "dismiss"; id: string };

function reducer(state: ToastItem[], action: Action): ToastItem[] {
  if (action.type === "enqueue") return [...state, action.item];
  if (action.type === "dismiss") return state.filter((t) => t.id !== action.id);
  return state;
}

let _id = 0;
const _nextId = () => `t${++_id}_${Date.now()}`;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, dispatch] = useReducer(reducer, []);

  const enqueue = useCallback((t: Omit<ToastItem, "id">) => {
    const id = _nextId();
    dispatch({ type: "enqueue", item: { ...t, id } });
    if (t.duration > 0) {
      setTimeout(() => dispatch({ type: "dismiss", id }), t.duration);
    }
    return id;
  }, []);

  const dismiss = useCallback((id: string) => {
    dispatch({ type: "dismiss", id });
  }, []);

  return (
    <ToastContext.Provider value={{ items, enqueue, dismiss }}>
      {children}
    </ToastContext.Provider>
  );
}
