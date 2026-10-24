import { AppShell } from "@/components/shell/AppShell";
import { UploadScreen } from "@/components/upload/UploadScreen";
import { urlStateFrom } from "@/lib/pageState";

export default async function UploadPage(props: PageProps<"/upload">) {
  const state = await urlStateFrom(props.searchParams);
  return (
    <AppShell state={state}>
      <UploadScreen />
    </AppShell>
  );
}
