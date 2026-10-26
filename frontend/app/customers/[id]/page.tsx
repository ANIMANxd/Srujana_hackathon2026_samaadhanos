import { AppShell } from "@/components/shell/AppShell";
import { CustomerProfileScreen } from "@/components/customers/CustomerProfileScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function CustomerPage(props: PageProps<"/customers/[id]">) {
  const { id } = await props.params;
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <CustomerProfileScreen key={id} customerId={decodeURIComponent(id)} />
    </AppShell>
  );
}
