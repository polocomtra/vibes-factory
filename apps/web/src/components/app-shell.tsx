"use client";

import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
    // Temporarily hidden navigation icons; uncomment with their nav item:
    // Activity,
    Bot,
    // Boxes,
    BrainCircuit,
    ChevronDown,
    CircleHelp,
    Code2,
    // Cloud,
    // FlaskConical,
    // GitBranch,
    Globe2,
    // LayoutDashboard,
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

export type ThemePreference = "system" | "dark" | "light";

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
};

const navItems: NavItem[] = [
    // Temporarily hidden until the feature is implemented:
    // { label: "Dashboard", icon: LayoutDashboard },
    { label: "Agents", icon: Bot, group: "Build" },
    { label: "Playground", icon: Code2 },
    // { label: "Workflows", icon: GitBranch },
    // { label: "Knowledge", icon: Boxes, group: "Connect" },
    { label: "Tools", icon: Zap, group: "Connect" },
    { label: "MCP Servers", icon: Network },
    // { label: "Evaluations", icon: FlaskConical, group: "Operate" },
    // { label: "Deployments", icon: Cloud },
    { label: "Traces", icon: Radio, group: "Operate" },
    // { label: "Monitoring", icon: Activity },
    { label: "Settings", icon: Settings, group: "Workspace" },
];

export function useTheme() {
    const [preference, setPreference] = useState<ThemePreference>("dark");
    const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">(
        "dark",
    );

    useEffect(() => {
        const stored = window.localStorage.getItem(
            "vf-theme",
        ) as ThemePreference | null;
        const nextPreference =
            stored === "light" || stored === "system" ? stored : "dark";
        setPreference(nextPreference);

        const media = window.matchMedia("(prefers-color-scheme: light)");
        const syncTheme = () => {
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
        if (path.startsWith("/agents")) return "Agents";
        if (path === "/tools" || path.startsWith("/tools/")) return "Tools";
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

    useEffect(() => {
        setActiveItem(getActiveItem(pathname));
    }, [pathname]);

    useEffect(() => {
        let cancelled = false;
        async function loadIdentity() {
            if (!supabase) {
                router.replace("/login");
                return;
            }
            const meResponse = await apiFetch("/v1/me");
            if (meResponse.status === 401) {
                router.replace("/login");
                return;
            }
            if (!meResponse.ok) return;
            const me = (await meResponse.json()) as { email: string };
            const workspaceResponse = await apiFetch("/v1/workspaces");
            if (!workspaceResponse.ok || cancelled) return;
            const body = (await workspaceResponse.json()) as {
                data: WorkspaceSummary[];
            };
            const saved = window.localStorage.getItem("vf-workspace-id");
            const selected = body.data.some(
                (workspace) => workspace.id === saved,
            )
                ? saved
                : (body.data[0]?.id ?? null);
            setEmail(me.email);
            setWorkspaces(body.data);
            setSelectedWorkspaceId(selected);
            if (selected)
                window.localStorage.setItem("vf-workspace-id", selected);
        }
        void loadIdentity();
        return () => {
            cancelled = true;
        };
    }, [router]);

    const navigate = (label: string) => {
        setActiveItem(label);
        setMobileOpen(false);
        if (label === "Dashboard") router.push("/");
        if (label === "Agents") router.push("/agents");
        if (label === "Tools") router.push("/tools");
        if (label === "MCP Servers") router.push("/mcp-servers");
        if (label === "Playground") router.push("/playground");
        if (label === "Traces") router.push("/traces");
        if (label === "Settings") router.push("/settings");
    };

    const activeDescription = useMemo(() => {
        if (activeItem === "Dashboard")
            return "Here’s what’s happening in your workspace.";
        return `${activeItem} is ready for the next milestone.`;
    }, [activeItem]);

    const runtimeLayout = pathname.includes("/playground");
    const shellClass = [
        "app-shell",
        sidebarCollapsed ? "sidebar-collapsed" : "",
        runtimeLayout ? "runtime-shell" : "",
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <div className={shellClass}>
            <div
                className={
                    mobileOpen ? "sidebar-overlay visible" : "sidebar-overlay"
                }
                onClick={() => setMobileOpen(false)}
            />
            <aside
                className={sidebarCollapsed ? "sidebar collapsed" : "sidebar"}
                data-mobile-open={mobileOpen}
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
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        return (
                            <div className="nav-entry" key={item.label}>
                                {item.group ? (
                                    <div className="nav-group-label">
                                        {sidebarCollapsed ? null : item.group}
                                    </div>
                                ) : null}
                                <button
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
                                    onClick={() => {
                                        navigate(item.label);
                                    }}
                                >
                                    <Icon
                                        size={17}
                                        strokeWidth={1.8}
                                        aria-hidden="true"
                                    />
                                    <span>{item.label}</span>
                                    {item.label === "Monitoring" &&
                                    !sidebarCollapsed ? (
                                        <span className="nav-live-dot" />
                                    ) : null}
                                </button>
                            </div>
                        );
                    })}
                </nav>

                <div className="sidebar-footer">
                    <div className="runtime-status">
                        <span className="status-pulse" />
                        <span>
                            {sidebarCollapsed ? "" : "All systems operational"}
                        </span>
                    </div>
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
                        <span className="topbar-status">
                            <span className="status-pulse" /> API online
                        </span>
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

                <div
                    className={
                        runtimeLayout
                            ? "content-frame runtime-content-frame"
                            : "content-frame"
                    }
                >
                    <div className="sr-only">{activeDescription}</div>
                    {children}
                </div>
            </main>
        </div>
    );
}
