import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { DuesScreen } from "@/components/dues/DuesScreen";
import { buildHref } from "@/lib/params-parse";
import { urlStateFrom } from "@/lib/pageState";

export default async function DuesPage(props: PageProps<"/">) {
  const state = await urlStateFrom(props.searchParams);
  // ?demo=1 always starts the scripted run on CASE-01. Every later step is a
  // normal case URL that keeps demo=1, so this redirect fires only at the start.
  if (state.demo) redirect(buildHref("/case/case_01", state));
  return (
    <AppShell state={state}>
      <DuesScreen />
    </AppShell>
  );
}
