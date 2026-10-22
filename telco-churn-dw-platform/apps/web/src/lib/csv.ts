// CSV -> TelcoRecord conversion, mirroring telco_common.records.from_ibm_csv_row.
import type { TelcoRecord } from "./validation";

export const IBM_COLUMN_MAP: Record<string, keyof TelcoRecord> = {
  customerID: "customer_id", gender: "gender", SeniorCitizen: "senior_citizen", Partner: "partner",
  Dependents: "dependents", tenure: "tenure_months", PhoneService: "phone_service", MultipleLines: "multiple_lines",
  InternetService: "internet_service", OnlineSecurity: "online_security", OnlineBackup: "online_backup",
  DeviceProtection: "device_protection", TechSupport: "tech_support", StreamingTV: "streaming_tv",
  StreamingMovies: "streaming_movies", Contract: "contract_type", PaperlessBilling: "paperless_billing",
  PaymentMethod: "payment_method", MonthlyCharges: "monthly_charges", TotalCharges: "total_charges", Churn: "churned",
};
export const RECORD_FIELDS = Object.values(IBM_COLUMN_MAP);

export type CsvLayout = "ibm" | "record" | "unknown";

export function detectLayout(header: string[]): CsvLayout {
  const h = new Set(header.map((x) => x.trim()));
  if (Object.keys(IBM_COLUMN_MAP).every((c) => h.has(c))) return "ibm";
  if (RECORD_FIELDS.every((c) => h.has(c))) return "record";
  return "unknown";
}

const toInt = (v: string): number | string => (/^-?\d+$/.test(v) ? Number(v) : v);
const toNum = (v: string): number | string => (v !== "" && !Number.isNaN(Number(v)) ? Math.round(Number(v) * 100) / 100 : v);

export function rowToRecord(row: Record<string, string>, layout: Exclude<CsvLayout, "unknown">): Record<string, unknown> {
  const get = (ibm: string, field: string) => String((layout === "ibm" ? row[ibm] : row[field]) ?? "").trim();
  const rec: Record<string, unknown> = {};
  for (const [ibm, field] of Object.entries(IBM_COLUMN_MAP)) {
    const v = get(ibm, field);
    if (field === "senior_citizen" || field === "tenure_months") rec[field] = toInt(v);
    else if (field === "monthly_charges") rec[field] = toNum(v);
    else if (field === "total_charges") rec[field] = v === "" ? null : toNum(v);
    else if (field === "churned")
      rec[field] = ({ yes: true, no: false, true: true, false: false, "1": true, "0": false } as Record<string, boolean>)[v.toLowerCase()] ?? v;
    else rec[field] = v;
  }
  if (layout === "record" && /^\d+$/.test(String(row.version ?? ""))) rec.version = Number(row.version);
  return rec;
}
