import { AppShell } from "@/components/app-shell";

// One static page. Django answers every /app/** path with this shell and the client reads its own path (see views_app.py).
export function generateStaticParams() {
  return [{ slug: [] }];
}

export const dynamicParams = false;

export default function Page() {
  return <AppShell />;
}
