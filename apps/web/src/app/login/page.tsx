"use client";

import { FormEvent, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, Bot, Boxes, GitBranch, LoaderCircle, Network } from "lucide-react";

import { useTheme } from "../../components/app-shell";
import { apiFetch, readApiError } from "../../lib/api";
import { hasSupabaseConfig, supabase } from "../../lib/supabase";

const features = [
  { label: "Agents", icon: Bot },
  { label: "Knowledge", icon: Boxes },
  { label: "Workflows", icon: GitBranch },
  { label: "MCP tools", icon: Network },
];

export default function LoginPage() {
  useTheme();
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace("/");
    });
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!supabase || !hasSupabaseConfig) {
      setError("Supabase is not configured. Add the frontend environment variables first.");
      return;
    }

    setSubmitting(true);
    const result = mode === "signin"
      ? await supabase.auth.signInWithPassword({ email, password })
      : await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
      });

    if (result.error) {
      setError(result.error.message);
      setSubmitting(false);
      return;
    }

    if (mode === "signup" && !result.data.session) {
      setMessage("Account created. Check your email to confirm the account before signing in.");
      setSubmitting(false);
      return;
    }

    const apiResponse = await apiFetch("/v1/me");
    if (!apiResponse.ok) {
      setError(await readApiError(apiResponse));
      setSubmitting(false);
      return;
    }
    router.replace("/");
  }

  return (
    <main className="login-page">
      <div className="login-orbit orbit-one" />
      <div className="login-orbit orbit-two" />
      <section className="login-shell">
        <div className="login-brand">
          <div className="login-logo-frame"><Image src="/assets/images/VibesFactory-logo.png" alt="VibesFactory" fill priority sizes="360px" className="brand-logo" /></div>
          <span>Build. Orchestrate. Deploy.</span>
        </div>
        <div className="login-layout">
          <div className="login-intro">
            <p className="eyebrow">AI-native control plane</p>
            <h1>From idea to impact.</h1>
            <p className="login-lede">Build, run, and scale production-inspired AI agents from one focused workspace.</p>
            <div className="feature-pills">{features.map((feature) => { const Icon = feature.icon; return <span key={feature.label}><Icon size={15} aria-hidden="true" />{feature.label}</span>; })}</div>
          </div>
          <div className="login-card">
            <div className="login-card-heading"><span className="favicon-frame"><Image src="/assets/images/VibesFactory-favicon.png" alt="" width={32} height={32} /></span><span className="status-badge info"><span />Local environment</span></div>
            <p className="eyebrow">{mode === "signin" ? "Welcome back" : "Create identity"}</p>
            <h2>{mode === "signin" ? "Sign in to VibesFactory" : "Create your VibesFactory account"}</h2>
            <p className="muted">Use your Supabase Auth identity to access your workspaces.</p>
            <form className="login-form" onSubmit={submit}>
              <label htmlFor="email">Email</label>
              <input id="email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              <label htmlFor="password">Password</label>
              <input id="password" name="password" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} required />
              {error ? <p className="form-error" role="alert">{error}</p> : null}
              {message ? <p className="form-success" role="status">{message}</p> : null}
              <button className="button primary-button login-button" type="submit" disabled={submitting}>
                {submitting ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
                {mode === "signin" ? "Continue with Supabase Auth" : "Create account"}
              </button>
            </form>
            <button className="login-mode-toggle" type="button" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); setMessage(null); }}>
              {mode === "signin" ? "Need an account? Create one" : "Already have an account? Sign in"}
            </button>
            <p className="login-footnote">Your workspace, agent versions and traces stay under your control.</p>
          </div>
        </div>
        <footer className="login-footer"><span>VibesFactory · Production-inspired Agentic AI Platform</span><span>v0.1.0 foundation</span></footer>
      </section>
    </main>
  );
}
