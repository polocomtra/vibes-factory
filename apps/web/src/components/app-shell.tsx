"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  Boxes,
  BrainCircuit,
  ChevronDown,
  CircleHelp,
  Cloud,
  Code2,
  FlaskConical,
  GitBranch,
  Globe2,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Settings,
  Sun,
  X,
  Zap,
} from "lucide-react";

export type ThemePreference = "system" | "dark" | "light";

type NavItem = {
  label: string;
  icon: LucideIcon;
  group?: string;
};

const navItems: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Agents", icon: Bot, group: "Build" },
  { label: "Playground", icon: Code2 },
  { label: "Workflows", icon: GitBranch },
  { label: "Knowledge", icon: Boxes, group: "Connect" },
  { label: "Tools", icon: Zap },
  { label: "MCP Servers", icon: Network },
  { label: "Evaluations", icon: FlaskConical, group: "Operate" },
  { label: "Deployments", icon: Cloud },
  { label: "Traces", icon: Radio },
  { label: "Monitoring", icon: Activity },
  { label: "Settings", icon: Settings, group: "Workspace" },
];

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>("dark");
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem("vf-theme") as ThemePreference | null;
    const nextPreference = stored === "light" || stored === "system" ? stored : "dark";
    setPreference(nextPreference);

    const media = window.matchMedia("(prefers-color-scheme: light)");
    const syncTheme = () => {
      const nextTheme = nextPreference === "system" ? (media.matches ? "light" : "dark") : nextPreference;
      setResolvedTheme(nextTheme);
      document.documentElement.dataset.theme = nextTheme;
    };

    syncTheme();
    media.addEventListener("change", syncTheme);
    return () => media.removeEventListener("change", syncTheme);
  }, []);

  const updatePreference = (nextPreference: ThemePreference) => {
    setPreference(nextPreference);
    window.localStorage.setItem("vf-theme", nextPreference);
    const nextTheme = nextPreference === "system"
      ? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
      : nextPreference;
    setResolvedTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
  };

  return { preference, resolvedTheme, updatePreference };
}

function BrandLockup({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className={collapsed ? "brand-lockup brand-lockup-collapsed" : "brand-lockup"}>
      <div className="brand-image-frame">
        <Image
          src="/assets/images/VibesFactory-logo.png"
          alt="VibesFactory"
          fill
          priority
          sizes="190px"
          className="brand-logo"
        />
      </div>
      {collapsed ? null : <span className="brand-version">CONTROL PLANE</span>}
    </div>
  );
}

function ThemeMenu({
  preference,
  resolvedTheme,
  onChange,
}: {
  preference: ThemePreference;
  resolvedTheme: "dark" | "light";
  onChange: (theme: ThemePreference) => void;
}) {
  const [open, setOpen] = useState(false);
  const themeIcon = resolvedTheme === "dark" ? Moon : Sun;
  const ThemeIcon = themeIcon;

  return (
    <div className="theme-menu">
      <button
        className="icon-button"
        type="button"
        aria-label="Change appearance"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <ThemeIcon aria-hidden="true" size={17} />
      </button>
      {open ? (
        <div className="theme-popover" role="menu" aria-label="Appearance">
          <div className="popover-heading">Appearance</div>
          {(["system", "dark", "light"] as ThemePreference[]).map((theme) => (
            <button
              className={preference === theme ? "theme-option selected" : "theme-option"}
              key={theme}
              type="button"
              role="menuitemradio"
              aria-checked={preference === theme}
              onClick={() => {
                onChange(theme);
                setOpen(false);
              }}
            >
              {theme === "system" ? <CircleHelp size={15} aria-hidden="true" /> : null}
              {theme === "dark" ? <Moon size={15} aria-hidden="true" /> : null}
              {theme === "light" ? <Sun size={15} aria-hidden="true" /> : null}
              <span>{theme[0].toUpperCase() + theme.slice(1)}</span>
              {preference === theme ? <span className="theme-check" aria-hidden="true">✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { preference, resolvedTheme, updatePreference } = useTheme();
  const [activeItem, setActiveItem] = useState("Dashboard");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const activeDescription = useMemo(() => {
    if (activeItem === "Dashboard") return "Here’s what’s happening in your workspace.";
    return `${activeItem} is ready for the next milestone.`;
  }, [activeItem]);

  return (
    <div className="app-shell">
      <div className={mobileOpen ? "sidebar-overlay visible" : "sidebar-overlay"} onClick={() => setMobileOpen(false)} />
      <aside className={sidebarCollapsed ? "sidebar collapsed" : "sidebar"} data-mobile-open={mobileOpen}>
        <div className="sidebar-topline">
          <BrandLockup collapsed={sidebarCollapsed} />
          <button
            className="sidebar-close mobile-only icon-button"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="workspace-switcher">
          <div className="workspace-avatar">A</div>
          <div className="workspace-copy">
            <strong>Acme Corp</strong>
            <span>Pro workspace</span>
          </div>
          <ChevronDown className="workspace-chevron" size={15} aria-hidden="true" />
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <div className="nav-entry" key={item.label}>
                {item.group ? <div className="nav-group-label">{sidebarCollapsed ? null : item.group}</div> : null}
                <button
                  className={activeItem === item.label ? "nav-item active" : "nav-item"}
                  type="button"
                  aria-current={activeItem === item.label ? "page" : undefined}
                  title={sidebarCollapsed ? item.label : undefined}
                  onClick={() => {
                    setActiveItem(item.label);
                    setMobileOpen(false);
                  }}
                >
                  <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                  <span>{item.label}</span>
                  {item.label === "Monitoring" && !sidebarCollapsed ? <span className="nav-live-dot" /> : null}
                </button>
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="runtime-status">
            <span className="status-pulse" />
            <span>{sidebarCollapsed ? "" : "All systems operational"}</span>
          </div>
          <button
            className="collapse-button"
            type="button"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed((current) => !current)}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={16} aria-hidden="true" /> : <PanelLeftClose size={16} aria-hidden="true" />}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="mobile-only icon-button" type="button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>
            <Menu size={19} aria-hidden="true" />
          </button>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{activeItem}</strong>
          </div>
          <div className="topbar-actions">
            <span className="topbar-status"><span className="status-pulse" /> API online</span>
            <ThemeMenu preference={preference} resolvedTheme={resolvedTheme} onChange={updatePreference} />
            <button className="avatar-button" type="button" aria-label="Open profile menu">WK</button>
          </div>
        </header>

        <div className="content-frame">
          <div className="sr-only">{activeDescription}</div>
          {children}
        </div>
      </main>
    </div>
  );
}
