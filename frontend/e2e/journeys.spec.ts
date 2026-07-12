import { expect, test } from "@playwright/test";

// Sign in via the demo (full-access admin) path.
async function enterDemo(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /continue as demo/i }).click();
  await expect(page.getByText(/Case Queue/i)).toBeVisible();
}

test("landing shows the login with demo entry", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ComplianceAgent" })).toBeVisible();
  await expect(page.getByRole("button", { name: /continue as demo/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /create organization/i })).toBeVisible();
});

test("demo login loads the case queue from the backend", async ({ page }) => {
  await enterDemo(page);
  await expect(page.getByText(/\d+ cases · \d+ pending review/i)).toBeVisible();
  // Real backend data — a case card renders.
  await expect(page.getByText(/CASE-\d+/).first()).toBeVisible();
});

test("navigation between views works", async ({ page }, testInfo) => {
  await enterDemo(page);
  // Desktop uses the top nav; mobile uses the bottom nav — both are role=button by label.
  const isMobile = testInfo.project.name === "mobile";
  const nav = isMobile ? page.locator("nav[aria-label='Primary']").last() : page;

  await nav.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByText(/Portfolio Analytics/i)).toBeVisible();

  await nav.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/Import transactions/i)).toBeVisible();
});

test("opening a case shows the investigation panel", async ({ page }) => {
  await enterDemo(page);
  await page.getByText(/CASE-\d+/).first().click();
  await expect(page.getByRole("button", { name: /run investigation/i })).toBeVisible();
});

test("command palette opens and navigates (desktop)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "palette shortcut is keyboard-only");
  await enterDemo(page);
  await page.keyboard.press("Meta+k");
  const dialog = page.getByRole("dialog", { name: /command palette/i });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("option", { name: "Dashboard" }).click();
  await expect(page.getByText(/Portfolio Analytics/i)).toBeVisible();
});

test("language toggle switches the document to RTL Arabic", async ({ page }) => {
  await enterDemo(page);
  await page.getByRole("button", { name: /switch language/i }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
});

test("mobile shows the floating bottom navigation", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only");
  await enterDemo(page);
  const bottomNav = page.locator("nav[aria-label='Primary']").last();
  await expect(bottomNav.getByRole("button", { name: "Dashboard" })).toBeVisible();
  await expect(bottomNav.getByRole("button", { name: "Cases" })).toBeVisible();
});
