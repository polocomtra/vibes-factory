# VibesFactory — Brand & UI Design System

**Document Version:** 1.0  
**Status:** Approved Baseline  
**Project:** VibesFactory  
**Document Type:** Brand / Product UI / Design System Specification

Related documents:

- `BRD.md`
- `ARCHITECTURE.md`
- `IMPLEMENTATION_PLAN.md`
- `API.md`

---

# 1. Purpose

This document defines the visual language and UI system for VibesFactory.

It is the source of truth for:

- Brand identity
- Color palette
- Dark and light themes
- Typography
- Layout
- Spacing
- Borders
- Radius
- Shadows
- Navigation
- Forms
- Tables
- Cards
- Charts
- Agent UI
- Workflow UI
- Trace UI
- Status colors
- Component behavior
- Responsive behavior
- Accessibility
- Design tokens

The objective is for every VibesFactory screen to feel like part of one cohesive product.

The UI should communicate:

> **Technical sophistication, AI-native infrastructure, production readiness, clarity, and speed.**

---

# 2. Brand Direction

VibesFactory should visually feel like:

```text
AI-native
+
Developer-focused
+
Production infrastructure
+
Modern SaaS
+
Technical
+
Precise
+
Premium
```

It should not feel like:

```text
Consumer social app

Gaming dashboard

Crypto product

Generic admin template

Bright playful productivity software

Corporate banking software
```

The product should feel closer to:

```text
AI infrastructure
developer platform
observability platform
cloud console
modern IDE
```

than a conventional CRUD dashboard.

---

# 3. Brand Personality

VibesFactory brand personality:

### Technical

The product should look appropriate for engineers working with:

```text
Agents
Models
Tools
MCP
Workflows
Traces
Evaluations
Deployments
```

### Intelligent

The interface should feel AI-native without excessive futuristic decoration.

### Production-Oriented

Metrics, status, traces, versions, cost, latency, and deployments should feel first-class.

### Confident

Use strong typography and restrained visual hierarchy.

### Minimal

Avoid decorative elements that compete with operational information.

---

# 4. Brand Tagline

Primary tagline:

> **Build. Orchestrate. Deploy. Turn ideas into impact.**

Secondary brand statement:

> **From idea to impact.**

Supporting product description:

> A production-inspired platform for building, running, and scaling AI agents.

---

# 5. Logo Direction

Primary VibesFactory logo uses:

```text
V-shaped geometric mark
+
VibesFactory wordmark
```

The mark should visually suggest:

```text
V

velocity

layers

agent flow

orchestration

forward movement
```

Primary logo gradient:

```text
Electric Blue
→
Electric Purple
```

The logo mark may glow subtly in Dark Theme.

Do not use strong glow around the full wordmark.

---

# 6. Approved Themes

VibesFactory supports exactly two primary application themes.

## Theme 1 — Obsidian

Dark theme.

Visual direction:

```text
Black
+
Deep Ocean Blue
+
Purple
+
Electric Blue
```

Primary usage:

- Developer preference
- Trace inspection
- Workflow building
- Long sessions
- Agent operations

---

## Theme 2 — Frost

Light theme.

Visual direction:

```text
White
+
Soft Ice
+
Deep Ocean Typography
+
Purple
+
Electric Blue
```

Light theme must remain unmistakably VibesFactory.

It must NOT become:

```text
black text
+
gray borders
+
generic white dashboard
```

Purple and deep blue remain core visual identity.

---

# 7. Theme Switching

Theme options:

```text
System

Dark

Light
```

Recommended setting:

```text
Settings
→ Appearance
→ Theme
```

Persist preference locally and optionally at user profile level later.

Implementation should support:

```html
<html data-theme="dark">
```

or equivalent class-based theming.

Core components must never contain hard-coded theme-specific colors.

Use semantic design tokens.

---

# 8. Core Brand Palette

## Brand Purple

### Purple 50

```text
#F4F0FF
```

### Purple 100

```text
#E9E1FF
```

### Purple 200

```text
#D5C5FF
```

### Purple 300

```text
#B79AFF
```

### Purple 400

```text
#936BFF
```

### Purple 500 — Primary

```text
#7047FF
```

Primary VibesFactory action color.

### Purple 600

```text
#5E35F2
```

### Purple 700

```text
#4A27CE
```

### Purple 800

```text
#381FA0
```

### Purple 900

```text
#291878
```

---

# 9. Electric Blue Palette

Used for:

- Secondary accent
- Agent execution
- Trace nodes
- Links
- Charts
- Gradient

### Blue 400

```text
#45A3FF
```

### Blue 500

```text
#247CFF
```

### Blue 600

```text
#1764E8
```

### Blue 700

```text
#1252C2
```

---

# 10. Deep Ocean Palette

Deep Ocean provides the distinctive VibesFactory technical identity.

### Ocean 950

```text
#030711
```

Near-black application background.

### Ocean 900

```text
#06101F
```

### Ocean 850

```text
#081426
```

### Ocean 800

```text
#0B192D
```

### Ocean 750

```text
#10213A
```

### Ocean 700

```text
#162B49
```

### Ocean 600

```text
#253C5C
```

### Ocean 500

```text
#3D5574
```

### Ocean 300

```text
#8EA0B8
```

### Ocean 200

```text
#B9C5D5
```

### Ocean 100

```text
#DCE4ED
```

### Ocean 50

```text
#F2F6FA
```

---

# 11. Brand Gradient

Primary gradient:

```css
linear-gradient(
  135deg,
  #247CFF 0%,
  #7047FF 55%,
  #936BFF 100%
)
```

Alternative horizontal gradient:

```css
linear-gradient(
  90deg,
  #247CFF,
  #7047FF
)
```

Use for:

- Logo mark
- Primary visual accents
- Active navigation highlights
- Selected workflow nodes
- Primary hero visual
- Some primary buttons
- Small chart emphasis

Do not apply gradient to large paragraphs or entire dashboard backgrounds.

---

# 12. Semantic Colors

## Success

Primary:

```text
#16C784
```

Background light:

```text
#EAFBF4
```

Background dark:

```text
#092A20
```

---

## Warning

Primary:

```text
#F5A524
```

Light background:

```text
#FFF7E6
```

Dark background:

```text
#33220A
```

---

## Error

Primary:

```text
#F0445E
```

Light background:

```text
#FFF0F2
```

Dark background:

```text
#351018
```

---

## Information

Primary:

```text
#247CFF
```

---

# 13. Dark Theme — Obsidian

Primary application background:

```text
#030711
```

Secondary background:

```text
#06101F
```

Sidebar:

```text
#050C18
```

Primary surface:

```text
#081426
```

Secondary surface:

```text
#0B192D
```

Elevated surface:

```text
#10213A
```

Hover surface:

```text
#132641
```

Primary border:

```text
#1A2D49
```

Strong border:

```text
#294466
```

Primary text:

```text
#F4F7FC
```

Secondary text:

```text
#A9B7CB
```

Tertiary text:

```text
#71849E
```

Disabled text:

```text
#52637A
```

Primary accent:

```text
#7047FF
```

Accent hover:

```text
#815EFF
```

Link:

```text
#8EA7FF
```

---

# 14. Light Theme — Frost

Application background:

```text
#F8FAFD
```

Primary surface:

```text
#FFFFFF
```

Secondary surface:

```text
#F4F7FC
```

Hover surface:

```text
#EEF2FA
```

Sidebar:

```text
#FBFCFF
```

Primary border:

```text
#DFE6F0
```

Strong border:

```text
#CBD5E3
```

Primary text:

```text
#0B1736
```

This is deep ocean blue.

Do not use pure black as the normal body color.

Secondary text:

```text
#526581
```

Tertiary text:

```text
#8291A8
```

Disabled text:

```text
#A8B3C2
```

Primary accent:

```text
#6240F5
```

Accent hover:

```text
#5332E6
```

Link:

```text
#4B4FE9
```

---

# 15. Semantic Token Model

Coding agents must use semantic tokens.

Do NOT write:

```css
background: #081426;
```

inside individual components.

Use:

```css
background: var(--surface-primary);
```

Recommended tokens:

```text
--background

--background-secondary

--surface-primary

--surface-secondary

--surface-elevated

--surface-hover

--surface-selected

--border-default

--border-strong

--text-primary

--text-secondary

--text-tertiary

--text-disabled

--brand-primary

--brand-secondary

--brand-hover

--link

--success

--warning

--error

--info
```

---

# 16. Suggested CSS Variables

## Dark

```css
[data-theme="dark"] {
  --background: #030711;
  --background-secondary: #06101F;

  --surface-primary: #081426;
  --surface-secondary: #0B192D;
  --surface-elevated: #10213A;
  --surface-hover: #132641;
  --surface-selected: #151D48;

  --border-default: #1A2D49;
  --border-strong: #294466;

  --text-primary: #F4F7FC;
  --text-secondary: #A9B7CB;
  --text-tertiary: #71849E;
  --text-disabled: #52637A;

  --brand-primary: #7047FF;
  --brand-secondary: #247CFF;
  --brand-hover: #815EFF;

  --success: #16C784;
  --warning: #F5A524;
  --error: #F0445E;
  --info: #247CFF;
}
```

---

## Light

```css
[data-theme="light"] {
  --background: #F8FAFD;
  --background-secondary: #F3F6FB;

  --surface-primary: #FFFFFF;
  --surface-secondary: #F4F7FC;
  --surface-elevated: #FFFFFF;
  --surface-hover: #EEF2FA;
  --surface-selected: #F0EDFF;

  --border-default: #DFE6F0;
  --border-strong: #CBD5E3;

  --text-primary: #0B1736;
  --text-secondary: #526581;
  --text-tertiary: #8291A8;
  --text-disabled: #A8B3C2;

  --brand-primary: #6240F5;
  --brand-secondary: #247CFF;
  --brand-hover: #5332E6;

  --success: #0FAE73;
  --warning: #D98A14;
  --error: #DC3852;
  --info: #176FEA;
}
```

---

# 17. Typography

Primary UI font:

> **Inter**

Fallback:

```css
font-family:
  Inter,
  ui-sans-serif,
  system-ui,
  -apple-system,
  BlinkMacSystemFont,
  "Segoe UI",
  sans-serif;
```

Inter should be used for:

```text
navigation
headers
forms
tables
metrics
buttons
body text
```

---

# 18. Technical / Code Font

Use:

> **JetBrains Mono**

Fallback:

```css
font-family:
  "JetBrains Mono",
  "SFMono-Regular",
  Consolas,
  monospace;
```

Use for:

```text
JSON
code
trace payload
API examples
IDs
token values where useful
```

Do not use monospace for ordinary UI labels.

---

# 19. Typography Scale

## Display

```text
40px
48px line height
700 weight
```

Marketing/hero only.

---

## Page Title

```text
28px
34px
700
```

Example:

```text
Dashboard
Customer Support Agent
Monitoring
```

---

## Section Title

```text
20px
28px
650–700
```

---

## Card Title

```text
15px
22px
600
```

---

## Body

```text
14px
21px
400
```

Default product body typography.

---

## Body Small

```text
13px
19px
400
```

---

## Label

```text
12px
17px
500–600
```

---

## Caption

```text
11px
16px
500
```

---

## Metric Large

```text
24–28px
32px
700
```

---

# 20. Typography Rules

Use strong distinction between:

```text
Page title

Section title

Body

Metadata
```

Do not make everything bold.

Use deep ocean/navy rather than black for Light Theme primary typography.

In Dark Theme:

```text
headings
→ near-white

body
→ soft blue-gray
```

Avoid pure white for every text element.

---

# 21. Global Layout

Application shell:

```text
┌───────────┬─────────────────────────────────┐
│ Sidebar   │ Main Content                    │
│           │                                 │
│           │                                 │
│           │                                 │
└───────────┴─────────────────────────────────┘
```

Desktop sidebar width:

```text
220–240px
```

Recommended:

```text
232px
```

Collapsed:

```text
64px
```

---

# 22. Content Width

Normal management pages:

```text
max-width: 1600px
```

Forms:

```text
max-width: 1200px
```

Dense observability views may use the full available width.

Examples:

```text
Trace Viewer

Workflow Editor

Monitoring
```

---

# 23. Page Padding

Desktop:

```text
24px
```

Large screen:

```text
28–32px
```

Tablet:

```text
20px
```

Mobile:

```text
16px
```

---

# 24. Spacing Scale

Base unit:

```text
4px
```

Tokens:

```text
space-1 = 4px
space-2 = 8px
space-3 = 12px
space-4 = 16px
space-5 = 20px
space-6 = 24px
space-8 = 32px
space-10 = 40px
space-12 = 48px
space-16 = 64px
```

Most card layouts should use:

```text
16px
20px
24px
```

rather than arbitrary spacing.

---

# 25. Border Radius

## Small

```text
6px
```

Used for:

```text
small tags
small buttons
```

## Standard

```text
8px
```

Used for:

```text
inputs
buttons
menus
```

## Card

```text
10px
```

or:

```text
12px
```

Default:

```text
10px
```

## Large

```text
16px
```

Used sparingly.

Avoid excessive:

```text
24px
32px
```

consumer-app rounded cards.

VibesFactory should feel technical.

---

# 26. Borders

Default:

```text
1px
```

Do not use thick borders except:

```text
focus
selected workflow nodes
high-priority states
```

Dark Theme should rely on visible deep-blue borders rather than invisible black-on-black surfaces.

---

# 27. Shadows

VibesFactory should use restrained shadows.

## Light Theme Card

```css
box-shadow:
  0 1px 2px rgba(12, 24, 48, 0.04),
  0 4px 12px rgba(12, 24, 48, 0.04);
```

## Light Elevated

```css
box-shadow:
  0 10px 30px rgba(12, 24, 48, 0.10);
```

Dark Theme should rely primarily on:

```text
border
surface contrast
small glow
```

instead of conventional shadows.

---

# 28. Glow

Purple/blue glow is permitted only for important interactive emphasis.

Example:

```css
box-shadow:
  0 0 0 1px rgba(112, 71, 255, 0.45),
  0 0 18px rgba(112, 71, 255, 0.18);
```

Use on:

```text
selected workflow node
active dark navigation item
primary execution indicator
```

Do not glow all cards.

---

# 29. Sidebar

Navigation order:

```text
Dashboard

Agents
Playground

Workflows

Knowledge
Tools
MCP Servers

Evaluations

Deployments

Traces
Monitoring

Settings
```

Group separators may be introduced later.

---

# 30. Sidebar Active State

Dark Theme:

```text
purple/blue gradient tint
purple border/glow
white text
```

Light Theme:

```text
soft purple background
purple icon/text
```

Example Light:

```text
background: #F0EDFF
text: #5332E6
```

---

# 31. Sidebar Icons

Use one icon family consistently.

Recommended:

> **Lucide**

Icon size:

```text
16px
```

Main navigation:

```text
16–18px
```

Stroke:

```text
1.7–2px
```

Do not mix:

```text
Lucide
Heroicons
Material Icons
Font Awesome
```

within the same product.

---

# 32. Page Header

Standard page:

```text
Page Title                    Actions
Description
```

Example:

```text
Customer Support Agent               Test  Save Draft  Publish
Helps customers with product questions...
```

Primary action appears on far right.

---

# 33. Tabs

Used heavily for resource details.

Example:

```text
Overview
Instructions
Model
Tools
Knowledge
Guardrails
Evaluation
Versions
Deployments
```

Active tab:

```text
purple text
+
purple bottom border
```

Do not use large pill tabs for primary resource navigation.

---

# 34. Cards

Default card:

```text
surface-primary
1px border
10px radius
```

Padding:

```text
16–20px
```

Cards must not be excessively elevated.

Dark cards should clearly separate from main background.

---

# 35. Metric Cards

Layout:

```text
Label

Large Metric

Delta / secondary value
```

Example:

```text
Total Runs
1,482
↑ 12%
```

Metric color remains normal primary text.

Only delta uses semantic color.

Avoid making the full metric:

```text
green
red
purple
```

unless specifically meaningful.

---

# 36. Buttons

Button variants:

```text
Primary

Secondary

Ghost

Danger

Icon
```

---

# 37. Primary Button

Use primary gradient or solid Purple 500.

Recommended:

```text
background: #7047FF
```

or subtle:

```text
#247CFF → #7047FF
```

Height:

```text
36px
```

Large:

```text
40px
```

Horizontal padding:

```text
14–16px
```

Font:

```text
13px
600
```

---

# 38. Secondary Button

Surface background with border.

Light:

```text
white
+
border
+
deep blue text
```

Dark:

```text
transparent/deep surface
+
ocean border
+
light text
```

---

# 39. Ghost Button

No border by default.

On hover:

```text
surface-hover
```

Use for:

```text
Share
Copy
More
Rerun
```

---

# 40. Danger Button

Use Red only for destructive operations.

Do not use red as ordinary secondary action.

---

# 41. Inputs

Standard input:

```text
height: 36–40px

border: 1px

radius: 8px
```

Light:

```text
white background
deep blue text
```

Dark:

```text
#071321 background
light text
```

Focus:

```text
purple border
+
subtle purple focus ring
```

Example:

```css
box-shadow: 0 0 0 3px rgba(112, 71, 255, 0.15);
```

---

# 42. Text Areas

Same design as input.

Minimum height:

```text
88px
```

Instructions editor may use:

```text
240px+
```

---

# 43. Form Labels

Label:

```text
12px
600
```

Spacing:

```text
6px below label
```

Optional helper text:

```text
12px
text-secondary
```

---

# 44. Select / Combobox

Must support:

```text
keyboard navigation
search for large collections
selected state
disabled state
```

Model selector and Agent selector should use combobox behavior.

---

# 45. Tags

Tags are compact.

Height:

```text
22–24px
```

Primary resource tag:

```text
soft purple background
purple text
```

Status tags use semantic colors.

---

# 46. Status Badges

## Completed / Healthy / Ready

```text
green
```

## Running / Processing / Deploying

```text
blue
```

## Waiting / Pending

```text
amber
```

## Failed / Error

```text
red
```

## Draft / Disabled

```text
gray/ocean
```

## Published

```text
green
```

Badge design:

```text
soft background
colored text
optional small dot
```

Avoid fully saturated badge backgrounds.

---

# 47. Tables

Tables should be compact and technical.

Header:

```text
12px
600
text-secondary
```

Rows:

```text
40–44px
```

Use subtle separators.

Hover:

```text
surface-hover
```

Selected:

```text
surface-selected
```

Numbers generally right aligned.

Names generally left aligned.

---

# 48. Empty States

Empty state should include:

```text
simple icon

short title

one sentence

primary CTA
```

Example:

```text
No agents yet.

Create your first agent to begin building with VibesFactory.

[ Create Agent ]
```

Avoid large illustrations.

---

# 49. Loading States

Use:

```text
skeletons
spinners
status indicators
```

Prefer skeleton for:

```text
dashboard
lists
cards
```

Spinner for:

```text
small actions
button submission
```

---

# 50. Dashboard

Dashboard should prioritize:

```text
Total Agents

Total Runs

Success Rate

Estimated Cost

Runs Over Time

Recent Runs
```

Grid:

```text
4 metric cards

large chart + recent runs
```

Dark and Light layouts must remain identical.

---

# 51. Agent Detail

Resource header:

```text
Agent Name
Published / Draft status
Description

Test
Save Draft
Publish
```

Primary tabs:

```text
Overview
Instructions
Model
Tools
Knowledge
Memory
Guardrails
Evaluation
Versions
Deployments
```

---

# 52. Agent Overview

Two-column desktop layout:

```text
Main Information             Configuration Summary
```

Recommended ratio:

```text
65 / 35
```

Configuration Summary should surface:

```text
Model

Tools count

Knowledge count

Memory

Guardrails

Latest Version

Last Updated
```

---

# 53. Playground

Layout should resemble a developer agent console rather than consumer messaging app.

Header:

```text
Agent selector

Version selector

Mode / config

New Session
```

Conversation area:

```text
Agent
User
Tool / system execution optional
```

Bottom:

```text
message input
send button
```

---

# 54. Playground Message Style

User:

```text
purple / gradient bubble
white text
```

Agent:

```text
surface-secondary
primary text
```

Do not use giant rounded chat bubbles.

Radius:

```text
8–10px
```

Messages can include expandable:

```text
Tool Calls

Sources

Trace
```

---

# 55. Trace Viewer

Trace Viewer is one of VibesFactory's signature interfaces.

Desktop split view:

```text
┌──────────────────┬─────────────────────────┐
│ Timeline / Tree  │ Span Detail             │
│                  │                         │
└──────────────────┴─────────────────────────┘
```

Left:

```text
User Message

Agent

Retrieval

Tool

Model

Child Agent

Completed
```

Right:

```text
Input

Output

Details

Logs
```

---

# 56. Trace Node Colors

Use consistent semantic category colors.

User:

```text
Blue
```

Model:

```text
Purple
```

Tool:

```text
Cyan / Blue
```

Retrieval:

```text
Indigo
```

Memory:

```text
Violet
```

Workflow:

```text
Blue
```

Guardrail:

```text
Amber
```

Error:

```text
Red
```

Complete:

```text
Green
```

---

# 57. JSON / Trace Payload

Use code typography.

Font:

```text
JetBrains Mono
```

Size:

```text
12–13px
```

Syntax colors should remain readable in both themes.

Example conceptual mapping:

```text
key → purple/blue

string → green/cyan

number → amber

boolean → violet

error → red
```

Do not over-saturate syntax highlighting.

---

# 58. Workflow Editor

Workflow Canvas:

```text
dot-grid background

nodes

edges

zoom controls
```

Dark theme dot grid:

```text
subtle blue dots
```

Light:

```text
soft gray-blue dots
```

---

# 59. Workflow Node Base

Node:

```text
surface-primary

1px border

8–10px radius

32–44px minimum height
```

Selected node:

```text
purple border
+
small blue/purple glow
```

---

# 60. Workflow Node Types

Trigger:

```text
Green
```

Agent:

```text
Blue
```

Tool:

```text
Cyan
```

Condition:

```text
Orange / Amber
```

Human Approval:

```text
Purple
```

Transform:

```text
Indigo
```

End:

```text
Ocean/Neutral
```

Color should mostly appear in:

```text
icon
small header marker
border accent
```

not entire node background.

---

# 61. Workflow Edges

Default:

```text
Ocean muted
```

Selected/executing:

```text
Electric Purple / Blue
```

Successful path:

```text
green
```

Failed:

```text
red
```

---

# 62. Knowledge UI

Knowledge page should use:

```text
table / list

Name

Type

Documents

Status

Actions
```

Prominent CTA:

```text
+ Add Source
```

Document status must be visible.

---

# 63. Tool UI

Tool list should surface:

```text
Name

Type

Version

Risk

Status

Last Updated
```

Risk level:

```text
LOW
MEDIUM
HIGH
```

should use semantic badges.

---

# 64. MCP UI

MCP Server card/list surfaces:

```text
Connection status

Transport

Tool count

Credential

Last discovery
```

Actions:

```text
Test Connection

Discover Tools

Import Tool
```

---

# 65. Deployments UI

Deployment card:

```text
Environment

Health

URL

Agent Version

Last Deployment

Actions
```

Environment icon:

```text
Production → purple/blue

Staging → cyan

Development → ocean
```

Health status remains semantic green/yellow/red.

---

# 66. Monitoring UI

Primary metric cards:

```text
Total Runs

Success Rate

Average Latency

Estimated Cost
```

Charts:

```text
Runs

Success Rate

P95 Latency

Cost
```

VibesFactory charts should primarily use:

```text
Purple
Blue
Cyan
```

with semantic colors only when meaning demands them.

---

# 67. Chart Palette

Recommended sequence:

```text
Series 1: #7047FF
Series 2: #247CFF
Series 3: #38BDF8
Series 4: #9B6CFF
Series 5: #16C784
Series 6: #F5A524
```

Avoid rainbow dashboards.

---

# 68. Chart Grid

Light:

```text
#E8EDF4
```

Dark:

```text
#17263C
```

Grid lines should remain subtle.

---

# 69. Chart Area Fill

Purple chart fill:

```css
linear-gradient(
  180deg,
  rgba(112, 71, 255, 0.22),
  rgba(112, 71, 255, 0)
)
```

---

# 70. Integrations UI

Provider cards should display recognizable provider icon/logo where legally appropriate.

Each card:

```text
Provider

Connection state

Configure
```

Connected:

```text
green indicator
```

Not connected:

```text
neutral
```

Never make provider brand colors dominate VibesFactory branding.

---

# 71. Modal / Dialog

Recommended max width:

```text
480px
```

Large configuration dialogs:

```text
640px
```

Dark backdrop:

```text
rgba(0,0,0,0.55)
```

Light/dark modal surfaces follow semantic theme tokens.

---

# 72. Dropdowns

Radius:

```text
8px
```

Padding:

```text
6px
```

Item:

```text
32–36px
```

Selected:

```text
surface-selected
brand-primary text/icon
```

---

# 73. Tooltips

Compact.

Use:

```text
12px
```

Dark tooltips may remain dark in both themes.

Example:

```text
background: #081426

text: #F4F7FC
```

---

# 74. Toast Notifications

Placement:

```text
top-right
```

or:

```text
bottom-right
```

Choose one and keep consistent.

Recommended:

```text
bottom-right
```

Variants:

```text
Success

Info

Warning

Error
```

---

# 75. Focus States

All interactive controls require visible keyboard focus.

Recommended:

```css
outline: none;

box-shadow:
  0 0 0 2px var(--background),
  0 0 0 4px var(--brand-primary);
```

Never remove focus indication without replacement.

---

# 76. Accessibility

Minimum target:

> WCAG AA

Requirements:

```text
4.5:1 normal text contrast

3:1 large text

keyboard navigability

visible focus

semantic HTML

ARIA for custom controls

non-color status indicators
```

Never communicate:

```text
success
error
status
```

using color alone.

Use:

```text
icon
label
dot
```

as additional indicators.

---

# 77. Responsive Breakpoints

Recommended:

```text
sm  = 640px

md  = 768px

lg  = 1024px

xl  = 1280px

2xl = 1536px
```

---

# 78. Responsive Sidebar

Desktop:

```text
232px
```

Medium:

```text
64px collapsed
```

Mobile:

```text
drawer
```

Do not force desktop sidebar into mobile layout.

---

# 79. Responsive Tables

On smaller screens:

```text
horizontal scroll
```

or carefully selected columns.

Do not transform every technical table into unrelated card layouts.

---

# 80. Mobile Priority

VibesFactory is primarily desktop-first.

Reason:

```text
Trace Viewer

Workflow Builder

Agent Configuration

Monitoring
```

are complex engineering interfaces.

Mobile must remain functional for:

```text
monitoring

runs

simple configuration

approval
```

but does not need full workflow-builder parity initially.

---

# 81. Motion

Animation should be subtle.

Timing:

```text
Fast: 120ms

Normal: 180ms

Slow: 240ms
```

Easing:

```css
cubic-bezier(0.2, 0, 0, 1)
```

Use for:

```text
hover

menu

sidebar

modal

selection
```

Avoid continuous decorative animation.

---

# 82. Agent Execution Animation

Allowed:

```text
small pulsing execution dot

moving trace status

subtle progress animation
```

Avoid:

```text
large glowing AI orbs

constant particles

large animated backgrounds
```

inside operational UI.

---

# 83. Marketing vs Product UI

Marketing surfaces may use:

```text
planet / deep ocean graphic

gradient

subtle glow

large brand statements
```

The application console should remain restrained.

Do not put the planetary header graphic on every product screen.

---

# 84. Header Visual

The approved planetary/deep-space graphic may be used on:

```text
landing page

login

onboarding

documentation cover

empty dashboard state
```

not as a permanent application header occupying substantial vertical space.

---

# 85. Z-Index Scale

Use controlled layers.

```text
base        0

sticky      10

dropdown    30

popover     40

modal       50

toast       60

critical    100
```

Avoid arbitrary values such as:

```text
999999
```

---

# 86. Component Naming

Preferred React component names:

```text
Button

IconButton

Badge

StatusBadge

Card

MetricCard

Input

TextArea

Select

Combobox

Tabs

Table

DropdownMenu

Dialog

Tooltip

Toast

Sidebar

PageHeader

EmptyState

Skeleton

CodeBlock
```

Domain:

```text
AgentStatusBadge

RunStatusBadge

TraceTimeline

TraceSpanInspector

WorkflowNode

KnowledgeTable

DeploymentCard
```

---

# 87. Primitive vs Domain Components

Separate:

```text
UI primitives
```

from:

```text
business/domain UI
```

Example:

```text
components/ui/button.tsx
```

vs:

```text
features/runs/components/run-status-badge.tsx
```

Do not place all product components under one large generic component directory.

---

# 88. Recommended Frontend Structure

```text
apps/web/src/
│
├── app/
│
├── components/
│   ├── ui/
│   └── layout/
│
├── features/
│   ├── agents/
│   ├── playground/
│   ├── workflows/
│   ├── tools/
│   ├── knowledge/
│   ├── memory/
│   ├── traces/
│   ├── evaluations/
│   ├── deployments/
│   └── monitoring/
│
├── design-system/
│   ├── tokens.css
│   ├── themes.css
│   └── typography.css
│
├── lib/
└── types/
```

---

# 89. Tailwind Integration

If Tailwind CSS is used, configure it around semantic CSS variables.

Good:

```text
bg-background

bg-surface-primary

text-text-primary

border-border-default

bg-brand-primary
```

Avoid widespread direct classes such as:

```text
bg-[#081426]

text-[#F4F7FC]
```

Domain components should remain theme-independent.

---

# 90. Example Tailwind Tokens

Conceptual:

```css
@theme {
  --color-background: var(--background);
  --color-surface-primary: var(--surface-primary);
  --color-surface-secondary: var(--surface-secondary);

  --color-text-primary: var(--text-primary);
  --color-text-secondary: var(--text-secondary);

  --color-border: var(--border-default);

  --color-brand: var(--brand-primary);
}
```

Exact syntax may depend on the Tailwind version in use.

---

# 91. Theme Implementation Rule

Component code must never contain logic such as:

```tsx
if (theme === "dark") {
  return darkColor;
}
```

for ordinary styling.

Correct:

```text
semantic token
→ theme definition
→ component
```

Theme differences belong in token definitions.

---

# 92. Dark / Light Visual Parity

The Dark and Light versions must have:

```text
same information hierarchy

same components

same spacing

same dimensions

same interaction patterns
```

Only the semantic visual tokens change.

Do not maintain two separate component implementations.

---

# 93. Theme Examples

## Dark Card

```text
Background:
#081426

Border:
#1A2D49

Title:
#F4F7FC

Body:
#A9B7CB
```

## Light Card

```text
Background:
#FFFFFF

Border:
#DFE6F0

Title:
#0B1736

Body:
#526581
```

The same Card component produces both.

---

# 94. Primary Navigation Example

Dark:

```text
inactive:
transparent
#A9B7CB

active:
purple/blue tinted surface
#FFFFFF
purple glow
```

Light:

```text
inactive:
transparent
#526581

active:
#F0EDFF
#5332E6
```

---

# 95. Logo Theme Handling

Dark Theme wordmark:

```text
#F4F7FC
```

Light Theme wordmark:

```text
#09152F
```

Logo icon keeps brand gradient in both modes.

---

# 96. Icon Color

Default:

```text
currentColor
```

Icons inherit text color whenever possible.

Do not independently hardcode every icon color.

Semantic icons may use:

```text
success

warning

error

brand
```

---

# 97. Dense Information Design

VibesFactory is an engineering product.

Density target:

> **Comfortable compact**

Do not create huge whitespace similar to marketing pages.

Examples:

```text
36px controls

40–44px table rows

16–20px cards

24px page gaps
```

---

# 98. Design Consistency Rule

If a screen requires a new UI pattern, first determine whether it can use:

```text
existing primitive

existing card

existing table

existing status badge

existing detail layout
```

Create new patterns only when necessary.

---

# 99. Avoided UI Patterns

Avoid:

```text
excessive glassmorphism

neumorphism

heavy gradients everywhere

large pill-based navigation

oversized round cards

large hero banners inside application pages

3D icons

cartoon illustrations

rainbow graphs

too many status colors

blurred translucent surfaces on every panel
```

VibesFactory should remain sharp and technical.

---

# 100. Signature Visual Elements

The UI should be recognizable through:

```text
purple + electric blue brand gradient

deep ocean typography

deep ocean dark surfaces

subtle blue borders

technical compact layouts

trace timelines

workflow nodes

status badges

strong metrics
```

rather than decorative visual effects.

---

# 101. Design Token Naming Convention

Use semantic names.

Good:

```text
color.background.default

color.surface.primary

color.text.primary

color.border.default

color.brand.primary

color.status.success
```

Bad:

```text
purple1

darkBlue3

cardGray
```

Semantic names allow theme mapping.

---

# 102. Token Categories

Design tokens should cover:

```text
color

typography

spacing

radius

border

shadow

motion

z-index

breakpoint
```

---

# 103. Recommended Theme Names in Code

```text
light

dark

system
```

Do not expose internal branding theme names such as:

```text
obsidian
frost
```

to core application logic.

These names may be used in design documentation only.

---

# 104. UI Copy Style

Use concise technical language.

Good:

```text
Create Agent

Publish Version

Run Evaluation

Test Connection

View Trace

Deploy
```

Avoid verbose:

```text
Click here to create a new artificial intelligence agent.
```

---

# 105. Sentence Style

Button:

```text
Sentence case
```

Preferred:

```text
Save draft

New deployment

Add source
```

Avoid:

```text
SAVE DRAFT

New Deployment
```

unless a product term requires capitalization.

---

# 106. Product Terminology

Use consistent names:

```text
Agent

Agent version

Run

Session

Tool

Knowledge base

Memory

Workflow

Evaluation

Deployment

Trace

MCP server

Credential
```

Do not arbitrarily alternate:

```text
execution / invocation / process
```

when referring to a `Run`.

---

# 107. Status Terminology

UI may display humanized status:

```text
Completed

Failed

Running

Waiting for approval
```

while backend enum remains:

```text
COMPLETED

FAILED

RUNNING

WAITING_APPROVAL
```

---

# 108. Design QA Checklist

Every new screen must be checked against:

### Theme

```text
Works in Dark

Works in Light
```

### Typography

```text
Correct hierarchy

No arbitrary font sizes
```

### Color

```text
Semantic tokens only

No hard-coded theme colors
```

### Layout

```text
Uses global spacing system

Responsive

Correct content width
```

### Components

```text
Existing primitives reused
```

### Accessibility

```text
Keyboard

Focus

Contrast

Semantic status
```

---

# 109. Coding Agent Rules

Coding agents implementing VibesFactory UI MUST:

1. Read this document before implementing UI.
2. Treat this document as the design-system source of truth.
3. Implement semantic theme tokens before feature styling.
4. Support Light and Dark from the first reusable component.
5. Use one component implementation for both themes.
6. Use Inter for normal UI.
7. Use JetBrains Mono for code/JSON.
8. Use Lucide icons consistently.
9. Use the approved purple, deep ocean, and electric-blue palette.
10. Preserve compact technical SaaS density.
11. Reuse design-system primitives.
12. Avoid hard-coded hex values in feature components.
13. Maintain WCAG AA contrast.
14. Keep trace/workflow visual semantics consistent.
15. Avoid introducing a separate visual style for individual modules.

---

# 110. Coding Agent Anti-Patterns

Do not generate UI that resembles a generic template by default.

Do not replace approved design direction with:

```text
gray-only shadcn defaults

blue-only SaaS colors

random gradients

rounded consumer cards

arbitrary icon libraries
```

If using a component library, restyle it to VibesFactory tokens.

The library is an implementation tool, not the product visual identity.

---

# 111. Recommended Initial UI Foundation Task

Before implementing product screens, build:

```text
ThemeProvider

ThemeToggle

CSS Tokens

Typography

Button

IconButton

Input

TextArea

Select

Badge

StatusBadge

Card

MetricCard

Tabs

Table

DropdownMenu

Dialog

Tooltip

Toast

Skeleton

Sidebar

PageHeader

CodeBlock
```

Then create a dedicated:

```text
/design-system
```

development page or Storybook-like route showing every primitive in:

```text
Dark Theme

Light Theme
```

---

# 112. Initial Layout Foundation

Implement:

```text
AppShell
│
├── Sidebar
│
└── Main
    ├── PageHeader
    └── Content
```

This should become the common application layout.

Do not duplicate sidebar/layout markup on each route.

---

# 113. First Screens for Visual Verification

Before building the entire product, coding agent should implement these screens first:

```text
1. Dashboard

2. Agent Detail

3. Playground

4. Trace Viewer

5. Workflow Editor
```

These five screens exercise most of the design system.

Review both:

```text
Dark

Light
```

before continuing to all remaining pages.

---

# 114. Approved Visual Reference

Two visual directions are approved:

### VibesFactory Dark

```text
black / deep ocean background

near-white typography

purple + electric-blue accents

deep-blue bordered surfaces

subtle neon highlights
```

### VibesFactory Light

```text
white / ice background

deep-ocean typography

purple + electric-blue accents

soft blue-gray borders

minimal shadows
```

The layouts, components, visual hierarchy, and brand identity should remain consistent between both themes.

---

# 115. Final Design Principle

VibesFactory should look like:

> **A production AI infrastructure console that combines the clarity of a modern developer platform with the visual identity of next-generation AI technology.**

The essential visual formula is:

```text
Deep Ocean
+
Black / White Theme Foundation
+
Electric Purple
+
Electric Blue
+
Technical Typography
+
Compact Structured Layout
+
Operational Data
```

The interface must remain functional before decorative.

Every visual decision should improve one or more of:

```text
clarity

hierarchy

debuggability

navigation

confidence

speed
```

rather than simply adding decoration.