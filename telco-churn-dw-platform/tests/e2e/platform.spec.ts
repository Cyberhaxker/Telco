import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test.describe("dashboard and analytics", () => {
  test("viewer sees KPIs but not the OLAP explorer", async ({ page }) => {
    await login(page, "viewer");
    await expect(page.getByText("Churn rate", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("26.54%")).toBeVisible();
    await expect(page.getByRole("link", { name: "OLAP explorer" })).toHaveCount(0);
  });

  test("analyst reproduces the acceptance figures in the OLAP explorer", async ({ page }) => {
    await login(page, "analyst", "/olap");
    await page.getByRole("button", { name: "Churn by contract" }).click();
    const table = page.getByRole("table", { name: /OLAP result/i });
    await expect(table.getByRole("row", { name: /Month-to-month\s+3,?875\s+1,?655\s+42\.71/ })).toBeVisible();
    await expect(table.getByRole("row", { name: /One year\s+1,?473\s+166\s+11\.27/ })).toBeVisible();
    await expect(table.getByRole("row", { name: /Two year\s+1,?695\s+48\s+2\.83/ })).toBeVisible();
    await page.getByRole("button", { name: "Tenure bands" }).click();
    await expect(table.getByRole("row", { name: /0-12\s+2,?186\s+1,?037\s+47\.44/ })).toBeVisible();
    await page.getByRole("button", { name: "Pivot" }).click();
    await expect(page.getByText(/pivot/).first()).toBeVisible();
  });

  test("app shell is installable", async ({ page }) => {
    await page.goto("/login");
    const manifest = await page.evaluate(async () => (await fetch("/manifest.webmanifest")).json());
    expect(manifest.display).toBe("standalone");
    expect(manifest.icons.some((i: { sizes: string }) => i.sizes === "512x512")).toBe(true);
    const sw = await page.evaluate(async () => (await navigator.serviceWorker.ready).active?.scriptURL);
    expect(sw).toContain("/sw.js");
  });
});
