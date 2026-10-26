import { AppShell } from "@/components/shell/AppShell";
import { SuggestionsReviewScreen } from "@/components/customers/SuggestionsReviewScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function ReviewPage(props: PageProps<"/customers/review">) {
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <SuggestionsReviewScreen />
    </AppShell>
  );
}
