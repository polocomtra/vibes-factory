"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { hasSupabaseConfig, supabase } from "../../../lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    if (!supabase || !hasSupabaseConfig) return;
    void supabase.auth.getSession().then(() => router.replace("/"));
  }, [router]);

  return <main className="callback-page"><p>Completing authentication…</p></main>;
}
