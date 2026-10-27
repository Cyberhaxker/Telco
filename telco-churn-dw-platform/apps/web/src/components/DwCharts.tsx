"use client";

// The five dashboard plots. They all draw from the single /analytics/charts
// payload (read from the warehouse and pushed live over /analytics/stream).
import { BarChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, PieChart, HeatmapChart, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

export interface Breakdown {
  label: string;
  customers: number;
  churned: number;
  churn_rate_pct: number;
}
export interface ChartsPayload {
  generated_at: string;
  contract_internet: {
    rows: string[];
    columns: string[];
    cells: { row: number; column: number; customers: number; churned: number; churn_rate_pct: number }[];
  };
  tenure: Breakdown[];
  payment: Breakdown[];
  charges: { bin_width: number; bins: { from: number; to: number; retained: number; churned: number }[] };
  risk: { band: "low" | "medium" | "high"; customers: number; avg_probability: number | null }[];
}

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = new Intl.NumberFormat("en-US");

interface Theme {
  ink: string;
  muted: string;
  line: string;
  surface: string;
  primary: string;
  signal: string;
  signalSoft: string;
  ok: string;
  warn: string;
  bad: string;
}
const readTheme = (): Theme => ({
  ink: cssVar("--ink"), muted: cssVar("--muted"), line: cssVar("--line"), surface: cssVar("--surface"),
  primary: cssVar("--primary"), signal: cssVar("--signal"), signalSoft: cssVar("--signal-soft"),
  ok: cssVar("--ok"), warn: cssVar("--warn"), bad: cssVar("--bad"),
});

/** Mounts an ECharts instance, redraws on data/theme change and resizes with its container. */
function Plot({ label, tall, data, option }: { label: string; tall?: boolean; data: unknown; option: (t: Theme) => echarts.EChartsCoreOption }) {
  const ref = useRef<HTMLDivElement>(null);
  const optionRef = useRef(option);
  optionRef.current = option;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    const draw = () => {
      const t = readTheme();
      chart.setOption(
        {
          textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: t.ink },
          aria: { enabled: true, label: { description: label } },
          animationDuration: 400,
          ...optionRef.current(t),
        },
        true,
      );
    };
    draw();
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(el);
    const themeObserver = new MutationObserver(draw);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", draw);
    return () => {
      resize.disconnect();
      themeObserver.disconnect();
      mq.removeEventListener("change", draw);
      chart.dispose();
    };
  }, [data, label]);
  return <div ref={ref} className={`chart${tall ? " tall" : ""}`} role="img" aria-label={label} />;
}

const axisCommon = (t: Theme) => ({
  axisLabel: { color: t.muted },
  axisLine: { lineStyle: { color: t.line } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: t.line } },
});

/** 1. Heatmap: churn rate for every contract x internet-service segment. */
export function ContractInternetHeatmap({ data }: { data: ChartsPayload["contract_internet"] }) {
  const max = Math.max(10, ...data.cells.map((c) => c.churn_rate_pct));
  return (
    <Plot
      tall
      data={data}
      label="Heatmap of churn rate by contract type and internet service"
      option={(t) => ({
        grid: { left: 8, right: 16, top: 8, bottom: 56, containLabel: true },
        tooltip: {
          formatter: (p: { value: number[] }) =>
            `<b>${data.rows[p.value[1]!]} · ${data.columns[p.value[0]!]}</b><br/>Churn rate ${p.value[2]}%<br/>${fmt.format(p.value[4]!)} of ${fmt.format(p.value[3]!)} customers`,
        },
        xAxis: { type: "category", data: data.columns, name: "Internet service", nameLocation: "middle", nameGap: 28, nameTextStyle: { color: t.muted }, ...axisCommon(t), splitLine: { show: false } },
        yAxis: { type: "category", data: data.rows, inverse: true, ...axisCommon(t), splitLine: { show: false } },
        visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 12, itemHeight: 120, textStyle: { color: t.muted }, text: ["High", "Low"], inRange: { color: [t.signalSoft, t.signal] } },
        series: [
          {
            type: "heatmap",
            data: data.cells.map((c) => ({
              value: [c.column, c.row, c.churn_rate_pct, c.customers, c.churned],
              label: { color: c.churn_rate_pct / max > 0.12 ? "#0f2329" : t.ink },
            })),
            itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 },
            label: { show: true, formatter: (p: { value: number[] }) => `${p.value[2]}%`, fontWeight: 600 },
            emphasis: { itemStyle: { borderColor: t.ink } },
          },
        ],
      })}
    />
  );
}

/** 2. Line: churn rate falls as tenure grows. */
export function TenureLine({ data }: { data: Breakdown[] }) {
  return (
    <Plot
      data={data}
      label="Line chart of churn rate by tenure band in months"
      option={(t) => ({
        grid: { left: 8, right: 24, top: 16, bottom: 24, containLabel: true },
        tooltip: {
          trigger: "axis",
          formatter: (p: { dataIndex: number }[]) => {
            const r = data[p[0]!.dataIndex]!;
            return `<b>${r.label} months</b><br/>Churn rate ${r.churn_rate_pct}%<br/>${fmt.format(r.churned)} of ${fmt.format(r.customers)} customers`;
          },
        },
        xAxis: { type: "category", data: data.map((d) => d.label), boundaryGap: true, ...axisCommon(t), splitLine: { show: false } },
        yAxis: { type: "value", min: 0, max: (v: { max: number }) => Math.ceil((v.max + 8) / 10) * 10, axisLabel: { color: t.muted, formatter: "{value}%" }, splitLine: { lineStyle: { color: t.line } } },
        series: [
          {
            type: "line", data: data.map((d) => d.churn_rate_pct), symbolSize: 9, lineStyle: { width: 2, color: t.signal },
            itemStyle: { color: t.signal, borderColor: t.surface, borderWidth: 2 }, areaStyle: { color: t.signal, opacity: 0.12 },
            label: { show: true, position: "top", formatter: "{c}%", color: t.ink },
          },
        ],
      })}
    />
  );
}

/** 3. Horizontal bars: churn rate per payment method. */
export function PaymentBars({ data }: { data: Breakdown[] }) {
  return (
    <Plot
      data={data}
      label="Bar chart of churn rate by payment method"
      option={(t) => ({
        grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
        tooltip: {
          trigger: "axis", axisPointer: { type: "none" },
          formatter: (p: { dataIndex: number }[]) => {
            const r = data[p[0]!.dataIndex]!;
            return `<b>${r.label}</b><br/>Churn rate ${r.churn_rate_pct}%<br/>${fmt.format(r.churned)} of ${fmt.format(r.customers)} customers`;
          },
        },
        xAxis: { type: "value", axisLabel: { color: t.muted, formatter: "{value}%" }, splitLine: { lineStyle: { color: t.line } } },
        yAxis: { type: "category", inverse: true, data: data.map((d) => d.label), ...axisCommon(t), splitLine: { show: false } },
        series: [
          {
            type: "bar", data: data.map((d) => d.churn_rate_pct), barMaxWidth: 28,
            itemStyle: { color: t.signal, borderRadius: [0, 4, 4, 0] },
            label: { show: true, position: "right", formatter: "{c}%", color: t.ink },
          },
        ],
      })}
    />
  );
}

/** 4. Stacked histogram: monthly charges, retained vs churned. */
export function ChargesHistogram({ data }: { data: ChartsPayload["charges"] }) {
  const cats = data.bins.map((b) => `$${b.from}`);
  const series = (name: string, key: "retained" | "churned", color: (t: Theme) => string) => (t: Theme) => ({
    name, type: "bar", stack: "customers", data: data.bins.map((b) => b[key]), barCategoryGap: "12%",
    itemStyle: { color: color(t), borderColor: t.surface, borderWidth: 1 }, emphasis: { focus: "series" },
  });
  return (
    <Plot
      data={data}
      label="Stacked histogram of monthly charges for retained and churned customers"
      option={(t) => ({
        grid: { left: 8, right: 16, top: 36, bottom: 28, containLabel: true },
        legend: { top: 0, textStyle: { color: t.muted } },
        tooltip: {
          trigger: "axis",
          formatter: (p: { dataIndex: number }[]) => {
            const b = data.bins[p[0]!.dataIndex]!;
            const total = b.retained + b.churned;
            return `<b>$${b.from}–$${b.to} per month</b><br/>Retained ${fmt.format(b.retained)}<br/>Churned ${fmt.format(b.churned)} (${total ? ((100 * b.churned) / total).toFixed(1) : 0}%)`;
          },
        },
        xAxis: { type: "category", data: cats, name: "Monthly charges", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: t.muted }, ...axisCommon(t), splitLine: { show: false }, axisLabel: { color: t.muted, interval: 1 } },
        yAxis: { type: "value", axisLabel: { color: t.muted }, splitLine: { lineStyle: { color: t.line } } },
        series: [series("Retained", "retained", (x) => x.primary)(t), series("Churned", "churned", (x) => x.signal)(t)],
      })}
    />
  );
}

const RISK_LABEL = { low: "Low", medium: "Medium", high: "High" } as const;

/** 5. Donut: active customers by predicted churn-risk band. */
export function RiskDonut({ data }: { data: ChartsPayload["risk"] }) {
  const total = data.reduce((a, r) => a + r.customers, 0);
  return (
    <Plot
      data={data}
      label="Donut chart of active customers by churn risk band"
      option={(t) => {
        const color = { low: t.ok, medium: t.warn, high: t.bad };
        return {
          tooltip: {
            formatter: (p: { dataIndex: number }) => {
              const r = data[p.dataIndex]!;
              return `<b>${RISK_LABEL[r.band]} risk</b><br/>${fmt.format(r.customers)} customers (${total ? ((100 * r.customers) / total).toFixed(1) : 0}%)<br/>Average probability ${r.avg_probability === null ? "—" : (r.avg_probability * 100).toFixed(1) + "%"}`;
            },
          },
          legend: { bottom: 0, textStyle: { color: t.muted } },
          series: [
            {
              type: "pie", radius: ["50%", "72%"], center: ["50%", "46%"],
              itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
              label: { show: true, color: t.ink, formatter: (p: { dataIndex: number; percent: number }) => `${RISK_LABEL[data[p.dataIndex]!.band]}\n${p.percent}%` },
              data: data.map((r) => ({ name: `${RISK_LABEL[r.band]} risk`, value: r.customers, itemStyle: { color: color[r.band] } })),
            },
          ],
        };
      }}
    />
  );
}
