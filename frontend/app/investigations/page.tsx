"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { LoadingCard } from "@/components/ui/Primitives";

export default function InvestigationsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/incidents");
  }, [router]);

  return (
    <main className="public-page">
      <LoadingCard message="Redirecting to incidents…" />
    </main>
  );
}
