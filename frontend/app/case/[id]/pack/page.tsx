import { AppShell } from "@/components/shell/AppShell";
import { PackScreen } from "@/components/pack/PackScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function PackPage(props: PageProps<"/case/[id]/pack">) {
  const { id } = await props.params;
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <PackScreen key={id} caseId={decodeURIComponent(id)} />
    </AppShell>
  );
}
