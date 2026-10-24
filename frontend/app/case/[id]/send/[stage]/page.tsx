import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { SendScreen } from "@/components/send/SendScreen";
import { urlStateFrom } from "@/lib/pageState";
import type { Stage } from "@/lib/types";

export default async function SendPage(props: PageProps<"/case/[id]/send/[stage]">) {
  const { id, stage } = await props.params;
  const n = Number(stage);
  if (![1, 2, 3, 4].includes(n)) notFound();
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <SendScreen key={`${id}-${n}`} caseId={decodeURIComponent(id)} stage={n as Stage} />
    </AppShell>
  );
}
