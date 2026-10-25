import { AppShell } from "@/components/shell/AppShell";
import { EarlyScreen } from "@/components/early/EarlyScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function EarlyPage(props: PageProps<"/case/[id]/early">) {
  const { id } = await props.params;
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <EarlyScreen key={id} caseId={decodeURIComponent(id)} />
    </AppShell>
  );
}
