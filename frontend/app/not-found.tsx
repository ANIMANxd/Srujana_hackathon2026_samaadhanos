import { AppShell } from "@/components/shell/AppShell";
import { NotFoundState } from "@/components/common/States";

export default function NotFound() {
  return (
    <AppShell state={{ lang: "en", view: "supplier", judge: false, send: null }}>
      <NotFoundState />
    </AppShell>
  );
}
