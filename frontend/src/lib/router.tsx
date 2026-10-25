"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Navigation inside the app. Django answers every /app/** path with the same page, so routing is done here from the address bar.
 * `history.pushState` is understood by the Next.js router (usePathname updates), and a reload on any path still lands on the right screen.
 */
export function navigate(to: string, { replace = false }: { replace?: boolean } = {}) {
  const url = `/app${to === "/" ? "/" : to}`;
  if (replace) window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
  window.scrollTo({ top: 0 });
}

export function Link({ to, children, className, ...rest }: { to: string; children: React.ReactNode; className?: string } & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return (
    <a
      {...rest}
      href={`/app${to === "/" ? "/" : to}`}
      className={className}
      onClick={(event) => {
        rest.onClick?.(event);
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || rest.target === "_blank") return;
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

/** The path inside the app ("/prep/3"), or null until the page has loaded in the browser (the build-time render has no address). */
export function useAppPath(): string | null {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  const path = pathname.replace(/\/+$/, "");
  return path === "" ? "/" : path;
}

export type Route = { pattern: RegExp; render: (params: string[]) => React.ReactNode };

export function matchRoute(routes: Route[], path: string): React.ReactNode | undefined {
  for (const route of routes) {
    const m = route.pattern.exec(path);
    if (m) return route.render(m.slice(1));
  }
  return undefined;
}
