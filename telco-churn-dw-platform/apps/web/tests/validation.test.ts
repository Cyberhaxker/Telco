import { describe, expect, it } from "vitest";

import { normaliseDependencies, validateRecord, type TelcoRecord } from "@/lib/validation";

const GOOD: TelcoRecord = {
  customer_id: "1234-ABCDE", gender: "Female", senior_citizen: 0, partner: "Yes", dependents: "No", tenure_months: 5,
  phone_service: "Yes", multiple_lines: "No", internet_service: "Fiber optic", online_security: "No", online_backup: "Yes",
  device_protection: "No", tech_support: "No", streaming_tv: "Yes", streaming_movies: "No", contract_type: "Month-to-month",
  paperless_billing: "Yes", payment_method: "Electronic check", monthly_charges: 80.5, total_charges: 402.5, churned: false,
};

describe("validateRecord (same cases as telco_common tests)", () => {
  it("accepts a valid record", () => expect(validateRecord(GOOD)).toEqual([]));

  it.each([
    [{ gender: "X" }, "gender", "enum"],
    [{ tenure_months: -1 }, "tenure_months", "minimum"],
    [{ monthly_charges: 0 }, "monthly_charges", "exclusiveMinimum"],
    [{ total_charges: 10 }, "total_charges", "lt_monthly"],
    [{ total_charges: null }, "total_charges", "required_when_tenure"],
    [{ internet_service: "No" }, "online_security", "const"],
    [{ phone_service: "No" }, "multiple_lines", "const"],
    [{ unexpected: 1 }, "record", "additionalProperties"],
  ])("rejects %j on %s (%s)", (patch, field, code) => {
    const errors = validateRecord({ ...GOOD, ...patch }, 3);
    expect(errors).toContainEqual(expect.objectContaining({ row: 3, field, code }));
  });

  it("reports a missing field by name", () => {
    const rest: Partial<TelcoRecord> = { ...GOOD };
    delete rest.gender;
    expect(validateRecord(rest)).toContainEqual(expect.objectContaining({ field: "gender", code: "required" }));
  });

  it("allows null total when tenure is 0", () => {
    expect(validateRecord({ ...GOOD, tenure_months: 0, total_charges: null })).toEqual([]);
  });
});

describe("normaliseDependencies", () => {
  it("sets add-ons to 'No internet service' when internet is removed, and back", () => {
    const off = normaliseDependencies({ ...GOOD, internet_service: "No" });
    expect(off.online_security).toBe("No internet service");
    expect(validateRecord(off)).toEqual([]);
    const on = normaliseDependencies({ ...off, internet_service: "DSL" });
    expect(on.online_security).toBe("No");
  });
  it("keeps multiple_lines consistent with phone service", () => {
    expect(normaliseDependencies({ ...GOOD, phone_service: "No" }).multiple_lines).toBe("No phone service");
  });
});
