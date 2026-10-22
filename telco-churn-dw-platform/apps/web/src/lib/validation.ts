// Browser-side validation with the same JSON Schema as ingestion-api, plus the
// cross-field rules JSON Schema cannot express (mirrors telco_common/records.py).
import type { ErrorObject } from "ajv";

import type { RowError } from "./db";
// Precompiled at build time (scripts/compile-validators.mjs): no runtime code
// generation, so the Content-Security-Policy can forbid 'unsafe-eval'.
import validateSchema from "./generated/record-validator";

export type YesNo = "Yes" | "No";
export type Addon = "Yes" | "No" | "No internet service";

export interface TelcoRecord {
  customer_id: string;
  gender: "Female" | "Male";
  senior_citizen: 0 | 1;
  partner: YesNo;
  dependents: YesNo;
  tenure_months: number;
  phone_service: YesNo;
  multiple_lines: "Yes" | "No" | "No phone service";
  internet_service: "DSL" | "Fiber optic" | "No";
  online_security: Addon;
  online_backup: Addon;
  device_protection: Addon;
  tech_support: Addon;
  streaming_tv: Addon;
  streaming_movies: Addon;
  contract_type: "Month-to-month" | "One year" | "Two year";
  paperless_billing: YesNo;
  payment_method: "Electronic check" | "Mailed check" | "Bank transfer (automatic)" | "Credit card (automatic)";
  monthly_charges: number;
  total_charges: number | null;
  churned: boolean;
  version?: number;
}

export const ENUMS = {
  gender: ["Female", "Male"],
  yesNo: ["Yes", "No"],
  multiple_lines: ["Yes", "No", "No phone service"],
  internet_service: ["DSL", "Fiber optic", "No"],
  addon: ["Yes", "No", "No internet service"],
  contract_type: ["Month-to-month", "One year", "Two year"],
  payment_method: ["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"],
} as const;

export const INTERNET_ADDONS = [
  "online_security", "online_backup", "device_protection", "tech_support", "streaming_tv", "streaming_movies",
] as const;

function fieldOf(e: ErrorObject): string {
  if (e.keyword === "required") return String((e.params as { missingProperty: string }).missingProperty);
  if (e.keyword === "additionalProperties") return "record";
  return e.instancePath.replace(/^\//, "").replace(/\//g, ".") || "record";
}

function messageOf(e: ErrorObject): string {
  if (e.keyword === "enum") return `must be one of: ${(e.params as { allowedValues: unknown[] }).allowedValues.join(", ")}`;
  if (e.keyword === "const") return `must be "${(e.params as { allowedValue: unknown }).allowedValue}"`;
  if (e.keyword === "additionalProperties")
    return `unexpected field ${(e.params as { additionalProperty: string }).additionalProperty}`;
  return e.message ?? "is invalid";
}

export function businessRuleErrors(rec: Partial<TelcoRecord>, row: number): RowError[] {
  const errors: RowError[] = [];
  const { tenure_months: tenure, monthly_charges: monthly, total_charges: total } = rec;
  if (typeof tenure === "number" && typeof monthly === "number") {
    if (tenure > 0 && (total === null || total === undefined))
      errors.push({ row, field: "total_charges", code: "required_when_tenure", message: "total_charges is required when tenure_months > 0" });
    if (tenure > 0 && typeof total === "number" && total + 1e-9 < monthly)
      errors.push({ row, field: "total_charges", code: "lt_monthly", message: "total_charges must be >= monthly_charges when tenure_months > 0" });
  }
  return errors;
}

/** Errors for one record (empty when valid). Combinator branches are reported once per field. */
export function validateRecord(rec: unknown, row = 0): RowError[] {
  if (!validateSchema(rec)) {
    const seen = new Set<string>();
    const out: RowError[] = [];
    for (const e of validateSchema.errors ?? []) {
      if (e.keyword === "if" || e.keyword === "allOf") continue;
      const field = fieldOf(e);
      const key = `${field}:${e.keyword}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ row, field, code: e.keyword, message: messageOf(e) });
    }
    return out;
  }
  return businessRuleErrors(rec as unknown as TelcoRecord, row);
}

/** Make dependent fields consistent (used by the form when service choices change). */
export function normaliseDependencies(rec: Partial<TelcoRecord>): Partial<TelcoRecord> {
  const out = { ...rec };
  if (out.phone_service === "No") out.multiple_lines = "No phone service";
  else if (out.multiple_lines === "No phone service") out.multiple_lines = "No";
  for (const f of INTERNET_ADDONS) {
    if (out.internet_service === "No") out[f] = "No internet service";
    else if (out[f] === "No internet service") out[f] = "No";
  }
  return out;
}
