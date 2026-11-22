import { LoadingText } from "@/components/loading";
import { Suspense } from "react";
import { TitulosScreen } from "./screen";

export default function TitulosPage() {
  return (
    <Suspense fallback={<LoadingText text="load.invoices" />}>
      <TitulosScreen />
    </Suspense>
  );
}
