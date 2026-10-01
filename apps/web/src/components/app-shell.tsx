"use client";

import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
    Activity,
    Bot,
    Boxes,
    BrainCircuit,
    Cloud,
    ShieldCheck,
    ChevronDown,
    CircleHelp,
    Code2,
    GitBranch,
    FlaskConical,
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

import { apiFetch } from "../lib/api";
import { supabase } from "../lib/supabase";
import { RouteFeatureHelp } from "./feature-help";

export type ThemePreference = "system" | "dark" | "light";

const MonitoringWorkspaceContext = createContext<string | null>(null);
export type WorkspaceLoadStatus = "loading" | "ready" | "error";
const WorkspaceStatusContext = createContext<WorkspaceLoadStatus>("loading");

export function useSelectedWorkspaceId() {
    return useContext(MonitoringWorkspaceContext);
}

export function useWorkspaceLoadStatus() {
    return useContext(WorkspaceStatusContext);
}

type WorkspaceSummary = {
    id: string;
    name: string;
    slug: string;
    role: "OWNER" | "MEMBER";
};

type NavItem = {
    label: string;
    icon: LucideIcon;
    group?: string;
    href: string;
};

const navItems: NavItem[] = [
    { label: "Dashboard", icon: LayoutDashboard, href: "/" },
    { label: "Agents", icon: Bot, group: "Build", href: "/agents" },
    { label: "Playground", icon: Code2, group: "Build", href: "/playground" },
    { label: "Workflows", icon: GitBranch, group: "Build", href: "/workflows" },
    { label: "Tools", icon: Zap, group: "Build", href: "/tools" },
    { label: "Knowledge", icon: Boxes, group: "Build", href: "/knowledge" },
    { label: "Memory", icon: BrainCircuit, group: "Build", href: "/memory" },
    { label: "MCP Servers", icon: Network, group: "Platform", href: "/mcp-servers" },
    { label: "Guardrails", icon: ShieldCheck, group: "Platform", href: "/guardrails" },
    { label: "Deployments", icon: Cloud, group: "Operate", href: "/deployments" },
    { label: "Approvals", icon: ShieldCheck, group: "Operate", href: "/approvals" },
    { label: "Traces", icon: Radio, group: "Operate", href: "/traces" },
    { label: "Monitoring", icon: Activity, group: "Operate", href: "/monitoring" },
    { label: "Evaluations", icon: FlaskConical, group: "Evaluate", href: "/evaluations" },
    { label: "Settings", icon: Settings, group: "System", href: "/settings" },
];

export function useTheme() {
    const [preference, setPreference] = useState<ThemePreference>("dark");
    const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">(
        "dark",
    );

    useEffect(() => {
        const stored = window.localStorage.getItem("vf-theme") as ThemePreference | null;
        const initialPreference = stored === "light" || stored === "system" ? stored : "dark";
        setPreference(initialPreference);
        const media = window.matchMedia("(prefers-color-scheme: light)");
        const syncTheme = () => {
            const saved = window.localStorage.getItem("vf-theme") as ThemePreference | null;
            const nextPreference = saved === "light" || saved === "system" ? saved : "dark";
            const nextTheme =
                nextPreference === "system"
                    ? media.matches
                        ? "light"
                        : "dark"
                    : nextPreference;
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
        const nextTheme =
            nextPreference === "system"
                ? window.matchMedia("(prefers-color-scheme: light)").matches
                    ? "light"
                    : "dark"
                : nextPreference;
        setResolvedTheme(nextTheme);
        document.documentElement.dataset.theme = nextTheme;
    };

    return { preference, resolvedTheme, updatePreference };
}

function BrandLockup({ collapsed = false }: { collapsed?: boolean }) {
    return (
        <div
            className={
                collapsed
                    ? "brand-lockup brand-lockup-collapsed"
                    : "brand-lockup"
            }
        >
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
                <div
                    className="theme-popover"
                    role="menu"
                    aria-label="Appearance"
                >
                    <div className="popover-heading">Appearance</div>
                    {(["system", "dark", "light"] as ThemePreference[]).map(
                        (theme) => (
                            <button
                                className={
                                    preference === theme
                                        ? "theme-option selected"
                                        : "theme-option"
                                }
                                key={theme}
                                type="button"
                                role="menuitemradio"
                                aria-checked={preference === theme}
                                onClick={() => {
                                    onChange(theme);
                                    setOpen(false);
                                }}
                            >
                                {theme === "system" ? (
                                    <CircleHelp size={15} aria-hidden="true" />
                                ) : null}
                                {theme === "dark" ? (
                                    <Moon size={15} aria-hidden="true" />
                                ) : null}
                                {theme === "light" ? (
                                    <Sun size={15} aria-hidden="true" />
                                ) : null}
                                <span>
                                    {theme[0].toUpperCase() + theme.slice(1)}
                                </span>
                                {preference === theme ? (
                                    <span
                                        className="theme-check"
                                        aria-hidden="true"
                                    >
                                        ✓
                                    </span>
                                ) : null}
                            </button>
                        ),
                    )}
                </div>
            ) : null}
        </div>
    );
}

function WorkspaceSwitcher({
    workspaces,
    selectedWorkspaceId,
    onChange,
}: {
    workspaces: WorkspaceSummary[];
    selectedWorkspaceId: string | null;
    onChange: (workspaceId: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
    const selectedWorkspace = workspaces.find(
        (workspace) => workspace.id === selectedWorkspaceId,
    );
    const selectedIndex = selectedWorkspace
        ? workspaces.indexOf(selectedWorkspace)
        : 0;

    useEffect(() => {
        if (!open) return;
        const handlePointerDown = (event: MouseEvent) => {
            if (!rootRef.current?.contains(event.target as Node))
                setOpen(false);
        };
        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") setOpen(false);
        };
        document.addEventListener("mousedown", handlePointerDown);
        document.addEventListener("keydown", handleEscape);
        requestAnimationFrame(() => optionRefs.current[selectedIndex]?.focus());
        return () => {
            document.removeEventListener("mousedown", handlePointerDown);
            document.removeEventListener("keydown", handleEscape);
        };
    }, [open, selectedIndex]);

    function focusOption(index: number) {
        if (workspaces.length === 0) return;
        const nextIndex = (index + workspaces.length) % workspaces.length;
        optionRefs.current[nextIndex]?.focus();
    }

    return (
        <div className="workspace-switcher" ref={rootRef}>
            <button
                className="workspace-trigger"
                type="button"
                aria-haspopup="listbox"
                aria-expanded={open}
                onClick={() => setOpen((current) => !current)}
                onKeyDown={(event) => {
                    if (
                        event.key === "ArrowDown" ||
                        event.key === "Enter" ||
                        event.key === " "
                    ) {
                        event.preventDefault();
                        setOpen(true);
                    }
                }}
            >
                <span className="workspace-avatar" aria-hidden="true">
                    {selectedWorkspace?.name.slice(0, 1).toUpperCase() || "A"}
                </span>
                <span className="workspace-trigger-copy">
                    <strong>
                        {selectedWorkspace?.name || "Select workspace"}
                    </strong>
                    <span>
                        {selectedWorkspace
                            ? `${selectedWorkspace.role === "OWNER" ? "Owner" : "Member"} workspace`
                            : "No workspace yet"}
                    </span>
                </span>
                <ChevronDown
                    className="workspace-chevron"
                    size={16}
                    aria-hidden="true"
                />
            </button>
            {open ? (
                <div
                    className="workspace-menu"
                    role="listbox"
                    aria-label="Workspaces"
                >
                    {workspaces.length === 0 ? (
                        <div className="workspace-empty">
                            No workspaces yet. Open Settings to create one.
                        </div>
                    ) : null}
                    {workspaces.map((workspace, index) => (
                        <button
                            className={
                                workspace.id === selectedWorkspaceId
                                    ? "workspace-option selected"
                                    : "workspace-option"
                            }
                            key={workspace.id}
                            type="button"
                            role="option"
                            aria-selected={workspace.id === selectedWorkspaceId}
                            ref={(element) => {
                                optionRefs.current[index] = element;
                            }}
                            onClick={() => {
                                onChange(workspace.id);
                                setOpen(false);
                            }}
                            onKeyDown={(event) => {
                                if (event.key === "ArrowDown") {
                                    event.preventDefault();
                                    focusOption(index + 1);
                                }
                                if (event.key === "ArrowUp") {
                                    event.preventDefault();
                                    focusOption(index - 1);
                                }
                                if (event.key === "Home") {
                                    event.preventDefault();
                                    focusOption(0);
                                }
                                if (event.key === "End") {
                                    event.preventDefault();
                                    focusOption(workspaces.length - 1);
                                }
                                if (event.key === "Escape") setOpen(false);
                            }}
                        >
                            <span
                                className="workspace-option-avatar"
                                aria-hidden="true"
                            >
                                {workspace.name.slice(0, 1).toUpperCase()}
                            </span>
                            <span className="workspace-option-copy">
                                <strong>{workspace.name}</strong>
                                <small>
                                    {workspace.role === "OWNER"
                                        ? "Owner"
                                        : "Member"}
                                </small>
                            </span>
                            {workspace.id === selectedWorkspaceId ? (
                                <span
                                    className="workspace-option-check"
                                    aria-hidden="true"
                                >
                                    ✓
                                </span>
                            ) : null}
                        </button>
                    ))}
                </div>
            ) : null}
        </div>
    );
}

export function AppShell({ children }: { children: React.ReactNode }) {
    const { preference, resolvedTheme, updatePreference } = useTheme();
    const pathname = usePathname();
    const router = useRouter();
    const getActiveItem = (path: string) => {
        if (path === "/playground" || path.includes("/playground"))
            return "Playground";
        if (path === "/traces" || path.includes("/traces")) return "Traces";
        if (path === "/monitoring") return "Monitoring";
        if (path === "/evaluations" || path.startsWith("/evaluations/"))
            return "Evaluations";
        if (path.startsWith("/agents")) return "Agents";
        if (path === "/workflows" || path.startsWith("/workflows/")) return "Workflows";
        if (path === "/tools" || path.startsWith("/tools/")) return "Tools";
        if (path === "/knowledge" || path.startsWith("/knowledge/")) return "Knowledge";
        if (path === "/memory" || path.startsWith("/memory/")) return "Memory";
        if (path === "/guardrails" || path.startsWith("/guardrails/")) return "Guardrails";
        if (path === "/approvals" || path.startsWith("/approvals/")) return "Approvals";
        if (path === "/deployments" || path.startsWith("/deployments/"))
            return "Deployments";
        if (path === "/mcp-servers" || path.startsWith("/mcp-servers/"))
            return "MCP Servers";
        if (path === "/settings") return "Settings";
        return "Dashboard";
    };
    const [activeItem, setActiveItem] = useState(getActiveItem(pathname));
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [mobileOpen, setMobileOpen] = useState(false);
    const [email, setEmail] = useState("");
    const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
    const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<
        string | null
    >(null);
    const [workspaceLoadStatus, setWorkspaceLoadStatus] = useState<WorkspaceLoadStatus>("loading");
    const [workspaceIdentityRetry, setWorkspaceIdentityRetry] = useState(0);
    const [isMobileViewport, setIsMobileViewport] = useState(false);
    const mobileTriggerRef = useRef<HTMLButtonElement>(null);
    const sidebarRef = useRef<HTMLElement>(null);
    const drawerWasOpenRef = useRef(false);

    useEffect(() => {
        const media = window.matchMedia("(max-width: 640px)");
        const sync = () => setIsMobileViewport(media.matches);
        sync();
        media.addEventListener("change", sync);
        return () => media.removeEventListener("change", sync);
    }, []);

    useEffect(() => {
        if (!isMobileViewport) { drawerWasOpenRef.current = false; return; }
        if (mobileOpen) {
            drawerWasOpenRef.current = true;
            requestAnimationFrame(() => sidebarRef.current?.querySelector<HTMLElement>(".sidebar-close")?.focus());
            const onKeyDown = (event: KeyboardEvent) => {
                if (event.key === "Escape") setMobileOpen(false);
                if (event.key !== "Tab" || !sidebarRef.current) return;
                const focusable = Array.from(sidebarRef.current.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)'));
                if (!focusable.length) return;
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            };
            document.addEventListener("keydown", onKeyDown);
            return () => document.removeEventListener("keydown", onKeyDown);
        }
        if (drawerWasOpenRef.current) {
            drawerWasOpenRef.current = false;
            mobileTriggerRef.current?.focus({ preventScroll: true });
        }
    }, [isMobileViewport, mobileOpen]);

    useEffect(() => {
        setActiveItem(getActiveItem(pathname));
    }, [pathname]);

    useEffect(() => {
        let cancelled = false;
        setWorkspaceLoadStatus("loading");
        async function loadIdentity() {
            if (!supabase) {
                router.replace("/login");
                return;
            }
            try {
                const meResponse = await apiFetch("/v1/me");
                if (meResponse.status === 401) { router.replace("/login"); return; }
                if (!meResponse.ok) throw new Error("Your account could not be loaded.");
                const me = (await meResponse.json()) as { email: string };
                const workspaceResponse = await apiFetch("/v1/workspaces");
                if (!workspaceResponse.ok) throw new Error("Workspaces could not be loaded.");
                const body = (await workspaceResponse.json()) as { data: WorkspaceSummary[] };
                if (cancelled) return;
                const saved = window.localStorage.getItem("vf-workspace-id");
                const selected = body.data.some((workspace) => workspace.id === saved) ? saved : (body.data[0]?.id ?? null);
                setEmail(me.email);
                setWorkspaces(body.data);
                setSelectedWorkspaceId(selected);
                setWorkspaceLoadStatus("ready");
                if (selected) window.localStorage.setItem("vf-workspace-id", selected);
            } catch {
                if (!cancelled) setWorkspaceLoadStatus("error");
            }
        }
        void loadIdentity();
        return () => {
            cancelled = true;
        };
    }, [router, workspaceIdentityRetry]);

    const navigate = (href: string) => {
        setMobileOpen(false);
        router.push(href);
    };

    const runtimeLayout = pathname.includes("/playground");
    const workflowLayout = pathname.startsWith("/workflows/") || pathname.startsWith("/workflow-runs/");
    const shellClass = [
        "app-shell",
        sidebarCollapsed ? "sidebar-collapsed" : "",
        runtimeLayout ? "runtime-shell" : "",
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <WorkspaceStatusContext.Provider value={workspaceLoadStatus}>
        <MonitoringWorkspaceContext.Provider value={selectedWorkspaceId}>
        <div className={shellClass}>
            <div
                className={
                    mobileOpen ? "sidebar-overlay visible" : "sidebar-overlay"
                }
                onClick={() => setMobileOpen(false)}
                aria-hidden="true"
            />
            <aside
                ref={sidebarRef}
                className={sidebarCollapsed ? "sidebar collapsed" : "sidebar"}
                data-mobile-open={mobileOpen}
                inert={isMobileViewport && !mobileOpen ? true : undefined}
            >
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

                <WorkspaceSwitcher
                    workspaces={workspaces}
                    selectedWorkspaceId={selectedWorkspaceId}
                    onChange={(workspaceId) => {
                        setSelectedWorkspaceId(workspaceId);
                        window.localStorage.setItem(
                            "vf-workspace-id",
                            workspaceId,
                        );
                    }}
                />

                <nav className="sidebar-nav" aria-label="Primary navigation">
                    {navItems.map((item, index) => {
                        const Icon = item.icon;
                        const previousItem = navItems[index - 1];
                        const showGroupLabel =
                            Boolean(item.group) &&
                            item.group !== previousItem?.group;
                        return (
                            <div className="nav-entry" key={item.label}>
                                {showGroupLabel ? (
                                    <div className="nav-group-label">
                                        {sidebarCollapsed ? null : item.group}
                                    </div>
                                ) : null}
                                <a
                                    href={item.href}
                                    className={
                                        activeItem === item.label
                                            ? "nav-item active"
                                            : "nav-item"
                                    }
                                    type="button"
                                    aria-current={
                                        activeItem === item.label
                                            ? "page"
                                            : undefined
                                    }
                                    title={
                                        sidebarCollapsed
                                            ? item.label
                                            : undefined
                                    }
                                    onClick={(event) => {
                                        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                                        event.preventDefault();
                                        navigate(item.href);
                                    }}
                                >
                                    <Icon
                                        size={17}
                                        strokeWidth={1.8}
                                        aria-hidden="true"
                                    />
                                    <span>{item.label}</span>
                                </a>
                            </div>
                        );
                    })}
                </nav>

                <div className="sidebar-footer">
                    <button
                        className="collapse-button"
                        type="button"
                        aria-label={
                            sidebarCollapsed
                                ? "Expand sidebar"
                                : "Collapse sidebar"
                        }
                        onClick={() =>
                            setSidebarCollapsed((current) => !current)
                        }
                    >
                        {sidebarCollapsed ? (
                            <PanelLeftOpen size={16} aria-hidden="true" />
                        ) : (
                            <PanelLeftClose size={16} aria-hidden="true" />
                        )}
                    </button>
                </div>
            </aside>

            <main className="main-content">
                <header className="topbar">
                    <button
                        className="mobile-only icon-button"
                        type="button"
                        aria-label="Open navigation"
                        ref={mobileTriggerRef}
                        onClick={() => setMobileOpen(true)}
                    >
                        <Menu size={19} aria-hidden="true" />
                    </button>
                    <div className="breadcrumb">
                        <span>Workspace</span>
                        <span className="breadcrumb-separator">/</span>
                        <strong>{activeItem}</strong>
                    </div>
                    <div className="topbar-actions">
                        <ThemeMenu
                            preference={preference}
                            resolvedTheme={resolvedTheme}
                            onChange={updatePreference}
                        />
                        <button
                            className="avatar-button"
                            type="button"
                            aria-label={`Signed in as ${email || "user"}`}
                        >
                            {email ? email.slice(0, 2).toUpperCase() : "VF"}
                        </button>
                    </div>
                </header>
                {workspaceLoadStatus === "error" ? <div className="shell-load-notice" role="alert"><span>Workspace information could not be refreshed.</span><button type="button" className="text-button" onClick={() => setWorkspaceIdentityRetry((retry) => retry + 1)}>Retry</button></div> : null}

                <div
                    className={
                        runtimeLayout
                            ? "content-frame runtime-content-frame"
                            : workflowLayout
                                ? "content-frame workflow-content-frame"
                                : "content-frame"
                    }
                >
                    <RouteFeatureHelp />
                    {children}
                </div>
            </main>
        </div>
        </MonitoringWorkspaceContext.Provider>
        </WorkspaceStatusContext.Provider>
    );
}
