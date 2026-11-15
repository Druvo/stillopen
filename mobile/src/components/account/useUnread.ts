import { useEffect, useState } from "react";
import { AppState } from "react-native";

import { noticeApi } from "../../api/notifications";

// One shared, cheap poll of GET /notifications/summary for every place that shows the unread count (the More tab and the menu row).
let count = 0;
const listeners = new Set<(n: number) => void>();
let timer: ReturnType<typeof setInterval> | null = null;

async function poll() {
  try {
    const { unread } = await noticeApi.summary();
    if (unread !== count) {
      count = unread;
      listeners.forEach((l) => l(count));
    }
  } catch {
    // a failed poll just keeps the last number
  }
}

/** The number of unread notifications, refreshed every minute while the app is open and whenever it comes back to the front. */
export function useUnread(): number {
  const [n, setN] = useState(count);
  useEffect(() => {
    listeners.add(setN);
    if (listeners.size === 1) {
      void poll();
      timer = setInterval(poll, 60_000);
    } else setN(count);
    const sub = AppState.addEventListener("change", (s) => s === "active" && void poll());
    return () => {
      listeners.delete(setN);
      sub.remove();
      if (listeners.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };
  }, []);
  return n;
}

/** Ask for an immediate refresh (after reading or clearing notices). */
export const refreshUnread = () => void poll();
