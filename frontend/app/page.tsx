import { AppShell } from "@/components/shell/AppShell";
import { DuesScreen } from "@/components/dues/DuesScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function DuesPage(props: PageProps<"/">) {
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <DuesScreen />
    </AppShell>
  );
}
