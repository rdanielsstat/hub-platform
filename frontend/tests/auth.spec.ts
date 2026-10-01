import { test, expect } from '@playwright/test'

test('signs up a new user and lands on the dashboard', async ({ page }) => {
  // Unique per run so POST /auth/register never 409s on a reused DB.
  const email = `e2e-${crypto.randomUUID()}@example.com`
  const displayName = 'E2E User'

  // Logged out, every path renders the login page; its footer links to /signup.
  await page.goto('/login')
  await page.getByRole('link', { name: 'Sign up' }).click()
  await expect(page).toHaveURL('/signup')

  // Ids, not labels: the URL changes before React swaps routes, so a bare
  // "Email" label can still match the outgoing login form's input.
  await page.locator('#signup-email').fill(email)
  await page.locator('#signup-name').fill(displayName)
  await page.locator('#signup-password').fill('e2e-password-123')

  const registered = page.waitForResponse(
    (res) =>
      res.url().endsWith('/auth/register') && res.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Sign up' }).click()
  expect((await registered).status()).toBe(201)

  // The dashboard is the authenticated "/" route.
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  await expect(page.getByText(displayName)).toBeVisible()
  await expect(page.getByText('Nothing captured yet')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
})
