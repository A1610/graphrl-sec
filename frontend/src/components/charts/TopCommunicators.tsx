"use client";

/**
 * TopCommunicators — horizontal bar chart of the top hosts by outbound connections.
 *
 * Uses Recharts BarChart with a custom YAxis tick renderer.
 * Falls back to a visually-hidden table for accessibility / screen readers.
 */

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type YAxisProps,
} from "recharts";
import type { ValueType, NameType } from "recharts/types/component/DefaultTooltipContent";
import type { Formatter } from "recharts/types/component/DefaultTooltipContent";

import type { CommunicatorResponse } from "@/types/api";
import { formatNumber, truncate } from "@/lib/utils";

interface TopCommunicatorsProps {
  communicators: CommunicatorResponse[];
}

interface ChartRow {
  name: string;
  outbound: number;
  destinations: number;
  label: string;
}

// Custom YAxis tick — renders the entity_key label truncated to 14 chars.
// We type `x` and `y` as `number | string` to match Recharts' TickProps,
// then coerce them to numbers before passing to SVG attributes.
function CustomYTick(props: {
  x?: number | string;
  y?: number | string;
  payload?: { value: string };
}): React.ReactElement | null {
  const { x, y, payload } = props;
  if (payload == null) return null;
  const xNum = typeof x === "string" ? parseFloat(x) : (x ?? 0);
  const yNum = typeof y === "string" ? parseFloat(y) : (y ?? 0);

  return (
    <text
      x={xNum}
      y={yNum}
      dy={4}
      textAnchor="end"
      fill="#8b949e"
      fontSize={11}
    >
      {truncate(payload.value, 14)}
    </text>
  );
}

// Tooltip formatter — matches Recharts' Formatter<ValueType, NameType> signature.
const tooltipFormatter: Formatter<ValueType, NameType> = (
  value,
  _name,
  item,
) => {
  const numVal = typeof value === "number" ? value : Number(value ?? 0);
  const payload = item.payload as ChartRow | undefined;
  const destinations = payload?.destinations ?? 0;
  const nodeLabel = payload?.label ?? "";
  return [
    `${formatNumber(numVal)} connections · ${formatNumber(destinations)} destinations`,
    nodeLabel,
  ];
};

const tooltipLabelFormatter = (label: unknown): string =>
  typeof label === "string" ? label : String(label ?? "");

// YAxis tick prop — cast through unknown to satisfy Recharts' overloaded TickProp type
const yAxisTick = CustomYTick as unknown as YAxisProps["tick"];

export default function TopCommunicators({
  communicators,
}: TopCommunicatorsProps): React.ReactElement {
  const data: ChartRow[] = communicators.slice(0, 10).map((c) => ({
    name: c.entity_key,
    outbound: c.outbound_count,
    destinations: c.unique_destinations,
    label: c.node_label,
  }));

  const maxVal = Math.max(...data.map((d) => d.outbound), 1);

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
        Top Communicators (outbound connections)
      </h2>

      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
        >
          <XAxis
            type="number"
            domain={[0, maxVal]}
            tick={{ fill: "#8b949e", fontSize: 11 }}
            axisLine={{ stroke: "#30363d" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={110}
            tick={yAxisTick}
            axisLine={{ stroke: "#30363d" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#161b22",
              border: "1px solid #30363d",
              borderRadius: "6px",
              color: "#e6edf3",
              fontSize: "12px",
            }}
            formatter={tooltipFormatter}
            labelFormatter={tooltipLabelFormatter}
          />
          <Bar dataKey="outbound" radius={[0, 3, 3, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={
                  entry.label === "ExternalIP"
                    ? "#f85149"
                    : entry.label === "Host"
                    ? "#58a6ff"
                    : "#3fb950"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Accessible table for screen readers */}
      <table className="sr-only" aria-label="Top communicators data table">
        <thead>
          <tr>
            <th scope="col">IP</th>
            <th scope="col">Type</th>
            <th scope="col">Outbound</th>
            <th scope="col">Destinations</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td>{row.label}</td>
              <td>{row.outbound}</td>
              <td>{row.destinations}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
