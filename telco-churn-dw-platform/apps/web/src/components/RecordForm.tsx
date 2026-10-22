"use client";

import { useMemo, useState } from "react";

import type { RowError } from "@/lib/db";
import { ENUMS, INTERNET_ADDONS, normaliseDependencies, validateRecord, type TelcoRecord } from "@/lib/validation";

export const EMPTY_RECORD: Partial<TelcoRecord> = {
  customer_id: "", gender: "Female", senior_citizen: 0, partner: "No", dependents: "No",
  tenure_months: 0, phone_service: "Yes", multiple_lines: "No", internet_service: "DSL",
  online_security: "No", online_backup: "No", device_protection: "No", tech_support: "No", streaming_tv: "No",
  streaming_movies: "No", contract_type: "Month-to-month", paperless_billing: "Yes", payment_method: "Electronic check",
  monthly_charges: 0, total_charges: null, churned: false,
};

interface Props {
  value: Partial<TelcoRecord>;
  onChange: (rec: Partial<TelcoRecord>) => void;
  hints?: Record<string, string>;
  showErrors: boolean;
  lockId?: boolean;
}

type Opt = readonly (string | number)[];

export function RecordForm({ value, onChange, hints = {}, showErrors, lockId }: Props) {
  const errors = useMemo(() => validateRecord(value), [value]);
  const byField = useMemo(() => {
    const m: Record<string, RowError> = {};
    for (const e of errors) m[e.field] ??= e;
    return m;
  }, [errors]);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const set = (field: keyof TelcoRecord, v: unknown) => {
    setTouched((t) => ({ ...t, [field]: true }));
    onChange(normaliseDependencies({ ...value, [field]: v }));
  };
  const err = (f: string) => (showErrors || touched[f] ? byField[f] : undefined);
  const wrap = (f: keyof TelcoRecord, labelText: string, control: React.ReactNode) => {
    const e = err(f);
    return (
      <div className={`field${e ? " invalid" : ""}`} key={f}>
        <label htmlFor={`f-${f}`}>{labelText}</label>
        {control}
        {e ? <span className="error" id={`e-${f}`}>{e.message}</span> : hints[f] ? <span className="hint">{hints[f]}</span> : null}
      </div>
    );
  };
  const select = (f: keyof TelcoRecord, labelText: string, options: Opt, disabled = false, numeric = false) =>
    wrap(f, labelText,
      <select id={`f-${f}`} value={String(value[f] ?? "")} disabled={disabled} aria-invalid={!!err(f)} aria-describedby={err(f) ? `e-${f}` : undefined}
              onChange={(e) => set(f, numeric ? Number(e.target.value) : e.target.value)}>
        {options.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
      </select>);
  const number = (f: keyof TelcoRecord, labelText: string, step: number, nullable = false) =>
    wrap(f, labelText,
      <input id={`f-${f}`} type="number" inputMode="decimal" min={0} step={step} aria-invalid={!!err(f)}
             value={value[f] === null || value[f] === undefined ? "" : String(value[f])}
             onChange={(e) => set(f, e.target.value === "" ? (nullable ? null : 0) : Number(e.target.value))} />);

  const noInternet = value.internet_service === "No";
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <fieldset>
        <legend>Customer</legend>
        <div className="form-grid">
          {wrap("customer_id", "Customer ID",
            <input id="f-customer_id" value={value.customer_id ?? ""} readOnly={lockId} placeholder="e.g. 7590-VHVEG" autoComplete="off"
                   aria-invalid={!!err("customer_id")} onChange={(e) => set("customer_id", e.target.value.trim())} />)}
          {select("gender", "Gender", ENUMS.gender)}
          {select("senior_citizen", "Senior citizen (65+)", [0, 1], false, true)}
          {select("partner", "Partner", ENUMS.yesNo)}
          {select("dependents", "Dependents", ENUMS.yesNo)}
        </div>
      </fieldset>
      <fieldset>
        <legend>Subscription</legend>
        <div className="form-grid">
          {select("contract_type", "Contract", ENUMS.contract_type)}
          {select("payment_method", "Payment method", ENUMS.payment_method)}
          {select("paperless_billing", "Paperless billing", ENUMS.yesNo)}
          {number("tenure_months", "Tenure (months)", 1)}
          {number("monthly_charges", "Monthly charges ($)", 0.01)}
          {number("total_charges", "Total charges ($)", 0.01, true)}
          {wrap("churned", "Churned",
            <select id="f-churned" value={value.churned ? "Yes" : "No"} onChange={(e) => set("churned", e.target.value === "Yes")}>
              <option>No</option><option>Yes</option>
            </select>)}
        </div>
      </fieldset>
      <fieldset>
        <legend>Services</legend>
        <div className="form-grid">
          {select("phone_service", "Phone service", ENUMS.yesNo)}
          {select("multiple_lines", "Multiple lines", ENUMS.multiple_lines, value.phone_service === "No")}
          {select("internet_service", "Internet service", ENUMS.internet_service)}
          {INTERNET_ADDONS.map((f) => select(f, f.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()), noInternet ? ["No internet service"] : ENUMS.yesNo, noInternet))}
        </div>
      </fieldset>
      {showErrors && errors.length > 0 && (
        <div className="notice bad" role="alert">
          Fix {errors.length} {errors.length === 1 ? "field" : "fields"} before saving: {errors.map((e) => e.field).join(", ")}.
        </div>
      )}
    </div>
  );
}
