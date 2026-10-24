import { AppShell } from "@/components/shell/AppShell";
import { CaseScreen } from "@/components/case/CaseScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function CasePage(props: PageProps<"/case/[id]">) {
  const { id } = await props.params;
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <CaseScreen key={id} caseId={decodeURIComponent(id)} />
    </AppShell>
  );
}
