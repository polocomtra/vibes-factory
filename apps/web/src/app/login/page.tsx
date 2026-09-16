"use client";

import Image from "next/image";
import { ArrowRight, Bot, Boxes, GitBranch, Network } from "lucide-react";

import { useTheme } from "../../components/app-shell";

const features = [
  { label: "Agents", icon: Bot },
  { label: "Knowledge", icon: Boxes },
  { label: "Workflows", icon: GitBranch },
  { label: "MCP tools", icon: Network },
];

export default function LoginPage() {
  useTheme();

  return (
    <main className="login-page">
      <div className="login-orbit orbit-one" />
      <div className="login-orbit orbit-two" />
      <section className="login-shell">
        <div className="login-brand">
          <div className="login-logo-frame">
            <Image src="/assets/images/VibesFactory-logo.png" alt="VibesFactory" fill priority sizes="360px" className="brand-logo" />
          </div>
          <span>Build. Orchestrate. Deploy.</span>
        </div>
        <div className="login-layout">
          <div className="login-intro">
            <p className="eyebrow">AI-native control plane</p>
            <h1>From idea to impact.</h1>
            <p className="login-lede">Build, run, and scale production-inspired AI agents from one focused workspace.</p>
            <div className="feature-pills">
              {features.map((feature) => { const Icon = feature.icon; return <span key={feature.label}><Icon size={15} aria-hidden="true" />{feature.label}</span>; })}
            </div>
          </div>
          <div className="login-card">
            <div className="login-card-heading"><span className="favicon-frame"><Image src="/assets/images/VibesFactory-favicon.png" alt="" width={32} height={32} /></span><span className="status-badge info"><span />Local environment</span></div>
            <p className="eyebrow">Welcome back</p>
            <h2>Sign in to VibesFactory</h2>
            <p className="muted">Authentication is being connected in Phase 1.</p>
            <button className="button primary-button login-button" type="button" disabled>Continue with Supabase Auth <ArrowRight size={16} aria-hidden="true" /></button>
            <p className="login-footnote">Your workspace, agent versions and traces stay under your control.</p>
          </div>
        </div>
        <footer className="login-footer"><span>VibesFactory · Production-inspired Agentic AI Platform</span><span>v0.1.0 foundation</span></footer>
      </section>
    </main>
  );
}
