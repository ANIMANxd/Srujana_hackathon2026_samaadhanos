import { AppShell } from "@/components/shell/AppShell";
import { ImportScreen } from "@/components/importer/ImportScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function ImportPage(props: PageProps<"/import">) {
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <ImportScreen />
    </AppShell>
  );
}
