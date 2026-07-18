"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthProvider";
import { LoadingCard } from "@/components/ui/Primitives";

export default function Home() {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(session ? "/dashboard" : "/welcome");
  }, [loading, session, router]);

  return (
    <main className="public-page">
      <LoadingCard message="Redirecting…" />
    </main>
  );
}
