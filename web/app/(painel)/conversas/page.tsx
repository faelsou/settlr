import { LoadingText } from "@/components/loading";
import { Suspense } from "react";
import { ConversasInbox } from "./inbox-page";

export default function ConversasPage() {
  return (
    <Suspense fallback={<LoadingText text="inbox.loadingList" />}>
      <ConversasInbox />
    </Suspense>
  );
}
