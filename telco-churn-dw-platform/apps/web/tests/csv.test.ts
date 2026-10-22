import { describe, expect, it } from "vitest";

import { detectLayout, rowToRecord } from "@/lib/csv";
import { validateRecord } from "@/lib/validation";

const IBM_ROW = {
  customerID: "7590-VHVEG", gender: "Female", SeniorCitizen: "0", Partner: "Yes", Dependents: "No", tenure: "1",
  PhoneService: "No", MultipleLines: "No phone service", InternetService: "DSL", OnlineSecurity: "No", OnlineBackup: "Yes",
  DeviceProtection: "No", TechSupport: "No", StreamingTV: "No", StreamingMovies: "No", Contract: "Month-to-month",
  PaperlessBilling: "Yes", PaymentMethod: "Electronic check", MonthlyCharges: "29.85", TotalCharges: "29.85", Churn: "No",
};

describe("CSV mapping", () => {
  it("detects the IBM layout and converts types", () => {
    expect(detectLayout(Object.keys(IBM_ROW))).toBe("ibm");
    const rec = rowToRecord(IBM_ROW, "ibm");
    expect(rec).toMatchObject({ customer_id: "7590-VHVEG", senior_citizen: 0, tenure_months: 1, monthly_charges: 29.85, churned: false });
    expect(validateRecord(rec)).toEqual([]);
  });

  it("turns a blank TotalCharges into null (tenure 0 customers)", () => {
    const rec = rowToRecord({ ...IBM_ROW, tenure: "0", TotalCharges: " " }, "ibm");
    expect(rec.total_charges).toBeNull();
    expect(validateRecord(rec)).toEqual([]);
  });

  it("keeps unparseable values so validation can report them", () => {
    const rec = rowToRecord({ ...IBM_ROW, tenure: "twelve" }, "ibm");
    expect(validateRecord(rec)).toContainEqual(expect.objectContaining({ field: "tenure_months", code: "type" }));
  });

  it("rejects unknown headers", () => expect(detectLayout(["a", "b"])).toBe("unknown"));
});
