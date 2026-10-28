import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), request: vi.fn() }));

import { request } from "@/lib/api";
import { money, seconds } from "@/features/account/usage";
import type { Notice } from "./api";
import { NotificationBell } from "./bell";
import { announcement, badgeText, dayLabel, groupByDay, unreadText } from "./logic";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const note = (id: number, created_at: string): Notice => ({ id, kind: "search", title: `n${id}`, text: "", link: "", created_at, read: false });

describe("notification logic", () => {
  it("says the unread count in words", () => {
    expect(unreadText(0)).toBe("No unread notifications");
    expect(unreadText(1)).toBe("1 unread notification");
    expect(unreadText(4)).toBe("4 unread notifications");
  });

  it("only a rise in the count is announced, and never the first reading", () => {
    expect(announcement(null, 3)).toBeNull();
    expect(announcement(3, 3)).toBeNull();
    expect(announcement(3, 1)).toBeNull();
    expect(announcement(1, 2)).toBe("1 new notification");
    expect(announcement(0, 3)).toBe("3 new notifications");
  });

  it("caps the badge", () => {
    expect(badgeText(9)).toBe("9");
    expect(badgeText(10)).toBe("9+");
  });

  it("groups by day, newest first, with plain labels", () => {
    const now = new Date(2026, 9, 29, 15, 0);
    const items = [note(1, new Date(2026, 9, 29, 9, 0).toISOString()), note(2, new Date(2026, 9, 29, 8, 0).toISOString()), note(3, new Date(2026, 9, 28, 20, 0).toISOString()), note(4, new Date(2026, 9, 20, 20, 0).toISOString())];
    const groups = groupByDay(items, now);
    expect(groups.map((g) => [g.label === dayLabel(g.items[0].created_at, now) ? g.label : "?", g.items.length])).toEqual([["Today", 2], ["Yesterday", 1], [groups[2].label, 1]]);
    expect(groups[0].label).toBe("Today");
    expect(groups[1].label).toBe("Yesterday");
  });
});

describe("usage formatting", () => {
  it("shows times and money plainly", () => {
    expect(seconds(null)).toBe("not recorded");
    expect(seconds(420)).toBe("420 ms");
    expect(seconds(2500)).toBe("2.5 s");
    expect(money(0.0123, "USD")).toBe("$0.0123");
    expect(money(12.5, "USD")).toBe("$12.50");
  });
});

describe("the bell", () => {
  const show = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <NotificationBell />
      </QueryClientProvider>,
    );

  it("names the unread count for screen readers and shows a short badge", async () => {
    vi.mocked(request).mockResolvedValue({ unread: 3 });
    show();
    const button = await screen.findByRole("button", { name: "Notifications. 3 unread notifications" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("bell-count").textContent).toBe("3");
  });

  it("has no badge when nothing is unread", async () => {
    vi.mocked(request).mockResolvedValue({ unread: 0 });
    show();
    await screen.findByRole("button", { name: "Notifications. No unread notifications" });
    expect(screen.queryByTestId("bell-count")).toBeNull();
  });
});
