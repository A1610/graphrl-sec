# 21 — Module: Next.js SOC Dashboard

## Phase 6, Module 6.2

---

## 1. What We Are Building

A real-time SOC (Security Operations Center) dashboard built with Next.js that provides analysts with alert monitoring, network graph visualization, attack campaign timelines, and triage feedback interfaces.

**In Simple Terms:** The control center screen where the SOC analyst sees everything — live alerts, network maps with suspicious connections highlighted, attack timelines, and buttons to confirm or reject AI decisions.

---

## 2. Why We Are Building It

- Analysts need visual context, not just scores
- Graph visualization reveals attack patterns invisible in tables
- Campaign timelines tell the attack story
- Feedback interface enables DRL agent learning loop
- Demonstrates the complete end-to-end system for dissertation

---

## 3. How It Works

### Dashboard Pages

```
/                        → Dashboard overview (KPIs + recent alerts)
/alerts                  → Alert list with filtering/sorting
/alerts/[id]             → Alert detail with graph neighborhood
/campaigns               → Active campaigns list
/campaigns/[id]          → Campaign detail with timeline
/graph                   → Interactive network graph explorer
/analytics               → Detection & triage performance metrics
/settings                → User settings, system config
```

---

## 4. Implementation Plan

### Task 4.1: Dashboard Layout & Navigation

```
frontend/src/
├── app/
│   ├── layout.tsx           # Root layout with sidebar navigation
│   ├── page.tsx             # Dashboard overview
│   ├── alerts/
│   │   ├── page.tsx         # Alert list
│   │   └── [id]/page.tsx    # Alert detail
│   ├── campaigns/
│   │   ├── page.tsx         # Campaign list
│   │   └── [id]/page.tsx    # Campaign detail + timeline
│   ├── graph/
│   │   └── page.tsx         # Network graph explorer
│   └── analytics/
│       └── page.tsx         # Performance metrics
```

### Task 4.2: Dashboard Overview Page

Key Performance Indicators (KPIs):
- Total alerts today
- Critical alerts pending
- False positive rate (last 24h)
- Active campaigns
- Autonomous triage rate (% handled by AI)
- Detection latency (avg time to alert)

Charts:
- Alert volume over time (line chart)
- Alert severity distribution (donut chart)
- Triage action breakdown (bar chart)

### Task 4.3: Alert List & Detail Pages

Alert List:
- Sortable/filterable table
- Columns: timestamp, source IP, dest IP, anomaly score, triage decision, campaign
- Real-time updates via WebSocket
- Color coding by severity (critical=red, high=orange, medium=yellow, low=green)

Alert Detail:
- Full alert metadata
- Graph neighborhood visualization (vis.js or D3.js force graph)
- T-HetGAT anomaly explanation (attention weights on neighbors)
- Analyst feedback buttons: Confirm / Override (with dropdown for correct action)

### Task 4.4: Network Graph Visualization

Interactive graph using `vis-network` or D3.js:
- Nodes colored by type (Host=blue, ExternalIP=red, Service=green, User=purple)
- Node size = anomaly score
- Edge thickness = traffic volume
- Edge color = anomaly score (green → red gradient)
- Click node to see details
- Zoom, pan, search by IP
- Time slider to view graph at different points in time

### Task 4.5: Campaign Timeline

Campaign detail page:
- Horizontal timeline visualization (D3.js timeline)
- Events plotted chronologically
- Involved hosts shown as "swim lanes"
- Color coding by severity
- Click event for details

### Task 4.6: Real-Time Updates (WebSocket)

```typescript
// frontend/src/hooks/useAlertStream.ts
const useAlertStream = () => {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    
    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/alerts');
        ws.onmessage = (event) => {
            const alert = JSON.parse(event.data);
            setAlerts(prev => [alert, ...prev].slice(0, 100));
        };
        return () => ws.close();
    }, []);
    
    return alerts;
};
```

### Task 4.7: Analyst Feedback Interface

On each alert detail page:
- "AI Decision: ESCALATE (94% confidence)"
- [Confirm] [Override ▼]
  - Override options: Dismiss, Investigate, Escalate, Correlate
  - Text field for notes
- Feedback sent to API → stored in DB → used for DRL retraining

---

## 5. Folder Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── alerts/
│   │   ├── campaigns/
│   │   ├── graph/
│   │   └── analytics/
│   │
│   ├── components/             # Reusable components
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── KPICard.tsx
│   │   ├── alerts/
│   │   │   ├── AlertTable.tsx
│   │   │   ├── AlertDetail.tsx
│   │   │   └── FeedbackForm.tsx
│   │   ├── graph/
│   │   │   ├── NetworkGraph.tsx
│   │   │   └── GraphControls.tsx
│   │   ├── campaigns/
│   │   │   ├── CampaignList.tsx
│   │   │   └── CampaignTimeline.tsx
│   │   └── charts/
│   │       ├── AlertVolumeChart.tsx
│   │       ├── SeverityDonut.tsx
│   │       └── TriageBreakdown.tsx
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAlertStream.ts
│   │   ├── useGraphData.ts
│   │   └── useApi.ts
│   │
│   ├── lib/                    # Utility functions
│   │   ├── api.ts              # API client (axios)
│   │   └── websocket.ts        # WebSocket manager
│   │
│   └── types/                  # TypeScript types
│       ├── alert.ts
│       ├── campaign.ts
│       └── graph.ts
│
├── public/
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

---

## 6. Dependencies

```json
{
    "dependencies": {
        "next": "latest",
        "react": "^18",
        "d3": "^7",
        "vis-network": "^9",
        "axios": "^1.6",
        "socket.io-client": "^4.7",
        "recharts": "^2.10",
        "@tailwindcss/forms": "latest",
        "date-fns": "^3",
        "lucide-react": "latest"
    }
}
```

---

## 7. Expected Output

### Dashboard Overview:
```
┌─────────────────────────────────────────────────────────┐
│  GraphRL-Sec SOC Dashboard                    [Prince]  │
├────────┬────────────────────────────────────────────────┤
│        │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────┐ │
│ Alerts │  │12,450│ │  23  │ │ 3.2% │ │ 82% auto     │ │
│        │  │alerts│ │crit. │ │ FPR  │ │ triaged      │ │
│ Camp.  │  └──────┘ └──────┘ └──────┘ └──────────────┘ │
│        │                                                │
│ Graph  │  [Alert Volume Chart ~~~~~~~~~~~~]             │
│        │                                                │
│ Analyt │  [Recent Alerts Table]                         │
│        │  14:32 | 192.168.10.50 → ext | Score: 0.97 ▲  │
│ Config │  14:31 | 10.0.0.5 → ext     | Score: 0.42 ─   │
│        │  14:30 | 192.168.1.1 → int  | Score: 0.12 ▼   │
└────────┴────────────────────────────────────────────────┘
```

---

## 8. Testing Strategy

- Component tests with React Testing Library
- E2E tests with Playwright (optional, time permitting)
- API mock for frontend-only testing
- WebSocket mock for real-time testing

---

## 9. Definition of Done

- [ ] Dashboard overview shows KPIs and charts
- [ ] Alert list with real-time WebSocket updates
- [ ] Alert detail with graph neighborhood visualization
- [ ] Campaign list and timeline visualization
- [ ] Interactive network graph explorer
- [ ] Analyst feedback form works and reaches API
- [ ] Responsive design (works on 1920×1080 and larger)
- [ ] Dark theme (SOC analysts work in dark rooms)
- [ ] No console errors
- [ ] Frontend builds without errors
