// k6 load test for the analytics and ingestion endpoints through APISIX.
//   TOKEN=$(...) k6 run tests/load/k6-analytics-ingest.js
// Get a token with the dev-only telco-cli client (see docs/runbook.md).
import http from "k6/http";
import { check, sleep } from "k6";
import crypto from "k6/crypto";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE = __ENV.GATEWAY_URL || "http://localhost:9080";
const AUTH = { Authorization: `Bearer ${__ENV.TOKEN}` };

export const options = {
  scenarios: {
    analytics: { executor: "constant-arrival-rate", rate: 20, timeUnit: "1s", duration: "2m", preAllocatedVUs: 20, exec: "analytics" },
    ingest: { executor: "constant-arrival-rate", rate: 2, timeUnit: "1s", duration: "2m", preAllocatedVUs: 5, exec: "ingest" },
  },
  thresholds: {
    "http_req_failed{scenario:analytics}": ["rate<0.01"],
    "http_req_duration{scenario:analytics}": ["p(95)<500"],
    "http_req_duration{scenario:ingest}": ["p(95)<1500"],
  },
};

const OLAP = [
  { rows: ["contract_type"], measures: ["customer_count", "churned_count", "churn_rate_pct"] },
  { rows: ["contract_type", "payment_method"], operation: "rollup" },
  { rows: ["contract_type"], columns: ["internet_service"], operation: "pivot" },
  { rows: ["payment_method"], filters: { contract_type: ["Month-to-month"] }, operation: "slice" },
];

export function analytics() {
  const r1 = http.get(`${BASE}/api/v1/analytics/kpis`, { headers: AUTH });
  check(r1, { "kpis 200": (r) => r.status === 200 });
  const q = OLAP[Math.floor(Math.random() * OLAP.length)];
  const r2 = http.post(`${BASE}/api/v1/analytics/olap/query`, JSON.stringify(q), { headers: { ...AUTH, "Content-Type": "application/json" } });
  check(r2, { "olap 200": (r) => r.status === 200 });
  const r3 = http.get(`${BASE}/api/v1/analytics/predictions?risk=high&limit=50`, { headers: AUTH });
  check(r3, { "predictions 200": (r) => r.status === 200 });
}

export function ingest() {
  const records = Array.from({ length: 50 }, (_, i) => ({
    customer_id: `K6${String(__VU).padStart(2, "0")}-${String(__ITER * 50 + i).padStart(6, "0")}`.slice(0, 20),
    gender: "Female", senior_citizen: 0, partner: "No", dependents: "No", tenure_months: 2, phone_service: "Yes",
    multiple_lines: "No", internet_service: "DSL", online_security: "No", online_backup: "No", device_protection: "No",
    tech_support: "No", streaming_tv: "No", streaming_movies: "No", contract_type: "Month-to-month", paperless_billing: "Yes",
    payment_method: "Mailed check", monthly_charges: 45, total_charges: 90, churned: false,
  }));
  const body = JSON.stringify({ batch_id: uuidv4(), client_id: "k6", created_at: new Date().toISOString(), source: "form", records });
  const res = http.post(`${BASE}/api/v1/ingest/batches`, body, {
    headers: { ...AUTH, "Content-Type": "application/json", "Idempotency-Key": uuidv4(), "X-Checksum-SHA256": crypto.sha256(body, "hex") },
  });
  check(res, { "batch accepted": (r) => r.status === 200 && JSON.parse(r.body).accepted_count === 50 });
  sleep(0.1);
}
