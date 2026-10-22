import { expect, type Page } from "@playwright/test";

export const PASSWORD = process.env.DEMO_USER_PASSWORD ?? "";

/** Log in through the real Keycloak login form (Authorization Code + PKCE). */
export async function login(page: Page, username: string, path = "/dashboard"): Promise<void> {
  await page.goto(path);
  const usernameInput = page.locator("#username");
  if (!await usernameInput.isVisible().catch(() => false)) {
    const signIn = page.getByRole("button", { name: /sign in/i });
    if (await signIn.waitFor({ timeout: 12000 }).then(() => true).catch(() => false)) {
      await signIn.click();
    }
  }
  await usernameInput.waitFor({ timeout: 10000 });
  await usernameInput.fill(username);
  await page.locator("#password").fill(PASSWORD);
  await page.locator("#kc-login").click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

/** Query the warehouse through the analytics API with the page's session. */
export async function warehouseHasCustomer(page: Page, customerId: string): Promise<boolean> {
  const status = await page.evaluate(async (id) => {
    const res = await fetch(`/api/v1/analytics/predictions/${id}`);
    return res.status;
  }, customerId);
  return status === 200;
}
