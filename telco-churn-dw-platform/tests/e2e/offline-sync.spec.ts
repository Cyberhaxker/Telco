import { expect, test } from "@playwright/test";

import { login } from "./helpers";

// Acceptance: go offline, enter a record and queue it, come back online, see it
// synced and validated, and resend without creating duplicates.
test("offline data entry is queued, synced on reconnect, and idempotent", async ({ page, context }) => {
  const id = `${String(Date.now()).slice(-4)}-E2E${String.fromCharCode(65 + Math.floor(Math.random() * 26))}${String.fromCharCode(65 + Math.floor(Math.random() * 26))}`;
  await login(page, "entry", "/data-entry");
  await page.waitForFunction(() => navigator.serviceWorker?.controller !== null);

  await context.setOffline(true);
  await expect(page.getByRole("status").filter({ hasText: "Offline" }).first()).toBeVisible();

  await page.locator("#f-customer_id").fill(id);
  await page.locator("#f-tenure_months").fill("3");
  await page.locator("#f-monthly_charges").fill("70.25");
  await page.locator("#f-total_charges").fill("210.75");
  await page.getByRole("button", { name: "Save record" }).click();
  await expect(page.getByText(/saved .* on this device/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /1 waiting to sync/ })).toBeVisible();

  // The page and its data still work offline.
  await page.goto("/sync");
  await expect(page.getByText(`Record ${id}`)).toBeVisible();
  await expect(page.getByText("Waiting")).toBeVisible();

  await context.setOffline(false);
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByText("Accepted").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("link", { name: "All synced" })).toBeVisible();

  // Resend the stored batch (same Idempotency-Key and bytes): the server must
  // return the original result instead of applying the record twice.
  await page.evaluate(async (customerId) => {
    const req = indexedDB.open("telco-churn");
    const dbh: IDBDatabase = await new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); });
    const store = dbh.transaction("outbox", "readwrite").objectStore("outbox");
    const all: { batch_id: string; status: string; records: { customer_id: string }[] }[] =
      await new Promise((res) => { const r = store.getAll(); r.onsuccess = () => res(r.result); });
    const batch = all.find((b) => b.records.some((r) => r.customer_id === customerId))!;
    await new Promise((res) => { const r = store.put({ ...batch, status: "PENDING", attempts: 0, next_attempt_at: 0 }); r.onsuccess = res; });
  }, id);
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByText("Accepted").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/1 records accepted/)).toBeVisible();

  // Exactly one batch for this customer, accepted once.
  await expect(page.getByText(`Record ${id}`)).toHaveCount(1);
});
