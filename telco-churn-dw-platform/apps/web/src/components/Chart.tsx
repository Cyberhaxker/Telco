"use client";

import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

export interface Series {
  name: string;
  values: (number | null)[];
  /** "signal" draws the series in the churn colour; otherwise the categorical palette is used. */
  tone?: "signal" | "primary" | "muted";
}

interface ChartProps {
  categories: string[];
  series: Series[];
  kind?: "bar" | "line";
  horizontal?: boolean;
  unit?: string;
  label: string;
  tall?: boolean;
  stacked?: boolean;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Bar/line chart themed from CSS tokens; re-renders when the theme changes. */
export function Chart({ categories, series, kind = "bar", horizontal = false, unit = "", label, tall, stacked }: ChartProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    const draw = () => {
      const ink = cssVar("--ink");
      const muted = cssVar("--muted");
      const line = cssVar("--line");
      const palette = [cssVar("--primary"), cssVar("--signal"), "#7a8f95", "#5b7fbd", "#8d6cab", "#4c9a6a"];
      const toneColor = (t?: Series["tone"]) =>
        t === "signal" ? cssVar("--signal") : t === "primary" ? cssVar("--primary") : t === "muted" ? muted : undefined;
      const valueAxis = {
        type: "value" as const,
        axisLabel: { color: muted, formatter: (v: number) => `${v}${unit}` },
        splitLine: { lineStyle: { color: line } },
      };
      const catAxis = {
        type: "category" as const, data: categories,
        axisLabel: { color: muted, interval: 0, hideOverlap: true }, axisLine: { lineStyle: { color: line } }, axisTick: { show: false },
      };
      chart.setOption(
        {
          color: palette,
          textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: ink },
          grid: { left: 8, right: 16, top: series.length > 1 ? 36 : 16, bottom: 8, containLabel: true },
          legend: series.length > 1 ? { top: 0, textStyle: { color: muted } } : undefined,
          tooltip: { trigger: "axis", valueFormatter: (v: unknown) => (v === null || v === undefined ? "—" : `${v}${unit}`) },
          xAxis: horizontal ? valueAxis : catAxis,
          yAxis: horizontal ? { ...catAxis, inverse: true } : valueAxis,
          series: series.map((s) => ({
            name: s.name, type: kind, data: s.values, stack: stacked ? "total" : undefined,
            itemStyle: { color: toneColor(s.tone), borderRadius: kind === "bar" ? (horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]) : 0 },
            barMaxWidth: 36, smooth: false, symbolSize: 6,
            emphasis: { focus: "series" },
          })),
          aria: { enabled: true, label: { description: label } },
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
  }, [categories, series, kind, horizontal, unit, label, stacked]);

  return <div ref={ref} className={`chart${tall ? " tall" : ""}`} role="img" aria-label={label} />;
}
