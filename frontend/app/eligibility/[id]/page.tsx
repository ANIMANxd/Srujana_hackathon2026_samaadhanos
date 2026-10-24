import { AppShell } from "@/components/shell/AppShell";
import { EligibilityScreen } from "@/components/case/EligibilityScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function EligibilityPage(props: PageProps<"/eligibility/[id]">) {
  const { id } = await props.params;
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <EligibilityScreen key={id} caseId={decodeURIComponent(id)} />
    </AppShell>
  );
}
