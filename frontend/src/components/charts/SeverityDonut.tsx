"use client";

/**
 * SeverityDonut — Recharts pie/donut chart showing node-type distribution.
 *
 * Slices:
 *   Host          → #58a6ff (blue)
 *   ExternalIP    → #f85149 (red)
 *   Service       → #3fb950 (green)
 *   Domain        → #d29922 (orange)
 *   User          → #bc8cff (purple)
 */

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  type PieLabelRenderProps,
} from "recharts";

import type { GraphStatsResponse } from "@/types/api";
import { formatNumber } from "@/lib/utils";

interface SeverityDonutProps {
  stats: GraphStatsResponse;
}

interface DonutEntry {
  name: string;
  value: number;
  color: string;
}

const RADIAN = Math.PI / 180;

function renderCustomLabel(props: PieLabelRenderProps): React.ReactElement | null {
  const {
    cx, cy, midAngle, innerRadius, outerRadius, percent,
  } = props;

  // All of these can be undefined per the Recharts type signature; guard them
  if (
    cx == null || cy == null || midAngle == null ||
    innerRadius == null || outerRadius == null || percent == null
  ) {
    return null;
  }

  const cxNum = typeof cx === "string" ? parseFloat(cx) : cx;
  const cyNum = typeof cy === "string" ? parseFloat(cy) : cy;
  const irNum = typeof innerRadius === "string" ? parseFloat(innerRadius) : innerRadius;
  const orNum = typeof outerRadius === "string" ? parseFloat(outerRadius) : outerRadius;
  const pct = typeof percent === "string" ? parseFloat(percent) : percent;

  if (pct < 0.04) return null;

  const radius = irNum + (orNum - irNum) * 0.5;
  const x = cxNum + radius * Math.cos(-midAngle * RADIAN);
  const y = cyNum + radius * Math.sin(-midAngle * RADIAN);

  return (
    <text
      x={x}
      y={y}
      fill="#e6edf3"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
    >
      {`${(pct * 100).toFixed(0)}%`}
    </text>
  );
}

export default function SeverityDonut({
  stats,
}: SeverityDonutProps): React.ReactElement {
  const data: DonutEntry[] = [
    { name: "Host", value: stats.host_count, color: "#58a6ff" },
    { name: "ExternalIP", value: stats.external_ip_count, color: "#f85149" },
    { name: "Service", value: stats.service_count, color: "#3fb950" },
    { name: "Domain", value: stats.domain_count, color: "#d29922" },
    { name: "User", value: stats.user_count, color: "#bc8cff" },
  ].filter((d) => d.value > 0);

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
        Node Type Distribution
      </h2>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
            dataKey="value"
            labelLine={false}
            label={renderCustomLabel}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} stroke="none" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: "#161b22",
              border: "1px solid #30363d",
              borderRadius: "6px",
              color: "#e6edf3",
              fontSize: "12px",
            }}
            formatter={(value) => {
              const numVal = typeof value === "number" ? value : Number(value ?? 0);
              return [formatNumber(numVal), "Nodes"] as [string, string];
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value) => (
              <span style={{ color: "#8b949e", fontSize: "11px" }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
