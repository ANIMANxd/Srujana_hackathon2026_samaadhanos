import { AppShell } from "@/components/shell/AppShell";
import { NotFoundState } from "@/components/common/States";

export default function NotFound() {
  return (
    <AppShell state={{ lang: "en", view: "supplier", judge: false, demo: false, send: null, tab: "overview", step: null }}>
      <NotFoundState />
    </AppShell>
  );
}
