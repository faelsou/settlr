import { LoadingText } from "@/components/loading";

export default function Home() {
  return (
    <main className="grid min-h-screen place-items-center bg-paper-50">
      <LoadingText text="load.panel" />
      <script
        dangerouslySetInnerHTML={{
          __html: `location.replace(localStorage.getItem("cobranca.token") ? "/inicio" : "/login")`,
        }}
      />
    </main>
  );
}
