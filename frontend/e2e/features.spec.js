/**
 * Walks the Scan Bhav desks and the public APIs behind them.
 *
 * Run from frontend/:
 *   npm install
 *   npx playwright install chromium
 *   npm run test:e2e
 *
 * Reuses an API already on :8000 and a Vite server on :5173 when they are up.
 * Set PLAYWRIGHT_LIVE=1 to also click Analyze and the history backtest (slow, uses market data).
 */
import { test, expect } from '@playwright/test'

const API = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8000'

const PAGES = [
  { path: '/', name: 'Analyze', text: 'Top stocks by horizon' },
  { path: '/multi', name: 'Screener', text: 'Run screen' },
  { path: '/swing', name: 'Swing', text: 'SWING' },
  { path: '/autopilot', name: 'Autopilot', text: 'DECISION DESK' },
  { path: '/markets', name: 'Markets', text: 'Markets' },
  { path: '/coach', name: 'Coach', text: 'SIP calculator' },
  { path: '/method', name: 'Reference', text: 'Indicators' },
  { path: '/about', name: 'About', text: 'Scan Bhav' },
]

test.describe('API features', () => {
  test('health, integrations, decision desk, and learning gaps respond', async ({ request }) => {
    const health = await request.get(`${API}/health`)
    expect(health.ok()).toBeTruthy()

    const integrations = await request.get(`${API}/api/integrations`)
    expect(integrations.ok()).toBeTruthy()
    const body = await integrations.json()
    expect(body.catalog.keyed.map(row => row.id)).toEqual(
      expect.arrayContaining(['alphavantage', 'finnhub', 'openai', 'anthropic', 'cursor']),
    )
    expect(body.catalog.free.map(row => row.id)).toEqual(expect.arrayContaining(['yahoo', 'nse']))

    const decision = await request.get(`${API}/api/quant/decision`)
    expect(decision.ok()).toBeTruthy()
    const desk = await decision.json()
    expect(desk.auto_execute).toBe(false)
    expect(desk.human_checkpoint).toBe(true)

    const gaps = await request.get(`${API}/api/learning/gaps`)
    expect(gaps.ok()).toBeTruthy()
    expect(Array.isArray((await gaps.json()).gaps)).toBeTruthy()

    const backtest = await request.get(`${API}/api/trading/backtest-agent/status`)
    expect(backtest.ok()).toBeTruthy()
  })

  test('saving an API key returns a hint, not the secret', async ({ request }) => {
    const saved = await request.post(`${API}/api/integrations/key`, {
      data: { provider_id: 'playwright_probe', api_key: 'secret-value-1234' },
    })
    expect(saved.ok()).toBeTruthy()
    const payload = await saved.json()
    expect(payload.configured).toBe(true)
    expect(payload.hint).toContain('1234')
    expect(JSON.stringify(payload)).not.toContain('secret-value')

    await request.post(`${API}/api/integrations/key`, {
      data: { provider_id: 'playwright_probe', api_key: '' },
    })
  })
})

test.describe('Desks', () => {
  for (const pageInfo of PAGES) {
    test(`${pageInfo.name} opens`, async ({ page }) => {
      await page.goto(pageInfo.path)
      await expect(page.getByText(pageInfo.text, { exact: false }).first()).toBeVisible()
    })
  }

  test('portfolio and accounts ask you to sign in', async ({ page }) => {
    await page.goto('/portfolio')
    await expect(page.getByText('Sign in', { exact: false }).first()).toBeVisible()
    await page.goto('/accounts')
    await expect(page.getByText('Broker accounts', { exact: false }).first()).toBeVisible()
  })

  test('settings exposes beginner mode and API keys', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Website settings' }).click()
    const dialog = page.getByRole('dialog', { name: 'Website settings' })
    await expect(dialog.getByText('Beginner mode', { exact: false })).toBeVisible()
    await expect(dialog.getByText('Your API keys')).toBeVisible()
    await expect(dialog.getByText('Alpha Vantage')).toBeVisible()
    await expect(dialog.getByText('Cursor')).toBeVisible()
    await dialog.getByRole('button', { name: 'Coach' }).click()
    await expect(page.getByText('SIP calculator')).toBeVisible()
  })

  test('autopilot shows the review list and the simple backtest', async ({ page }) => {
    await page.goto('/autopilot')
    await expect(page.getByText('DECISION DESK')).toBeVisible()
    await expect(page.getByText('Nothing here places an order', { exact: false })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Check a rule on past prices' })).toBeVisible()
    await expect(page.getByLabel('How to choose history')).toBeVisible()
    await page.getByLabel('How to choose history').selectOption('random')
    await expect(page.getByRole('button', { name: 'Run check' })).toBeEnabled()
  })

  test('analyze form accepts a symbol', async ({ page }) => {
    await page.goto('/')
    const input = page.getByPlaceholder('Search name or code, e.g. Adani or RELIANCE.NSE')
    await input.fill('RELIANCE.NSE')
    await expect(page.getByRole('button', { name: 'Analyze' })).toBeEnabled()
  })

  test('screener shows the run control', async ({ page }) => {
    await page.goto('/multi')
    await expect(page.getByRole('button', { name: 'Run screen' })).toBeVisible()
    await expect(page.getByLabel('Rank horizon')).toBeVisible()
  })
})

test.describe('Dummy fixture', () => {
  test('recommendation from the fixed JSON is the same every time', async ({ request }) => {
    const first = await request.get(`${API}/api/fixtures/playwright`)
    const second = await request.get(`${API}/api/fixtures/playwright`)
    expect(first.ok()).toBeTruthy()
    expect(second.ok()).toBeTruthy()
    const a = await first.json()
    const b = await second.json()
    expect(b).toEqual(a)

    const rec = a.recommendation
    expect(rec.deterministic).toBe(true)
    expect(rec.top).toBe('RELIANCE.NSE')
    expect(rec.recommendations.map(row => row.symbol)).toEqual([
      'RELIANCE.NSE',
      'TCS.NSE',
      'TINY.NSE',
    ])
    expect(rec.recommendations[0]).toMatchObject({
      rank: 1,
      score: 79.4,
      decision: 'review',
      news_score: 78,
      headline: 'Reliance wins a firm export order',
    })
    expect(rec.recommendations[2]).toMatchObject({
      symbol: 'TINY.NSE',
      score: 42.5,
      decision: 'skip',
      headline: 'No headlines',
    })
    expect(a.world.news['RELIANCE.NSE'].headlines).toHaveLength(1)
    expect(a.world.backtest.results).toHaveLength(3)
    expect(a.world.prices['RELIANCE.NSE'][2].close).toBe(2950.5)
  })
})

test.describe('Live market actions', () => {
  test.skip(!process.env.PLAYWRIGHT_LIVE, 'Set PLAYWRIGHT_LIVE=1 to hit Yahoo/NSE')

  test('analyze RELIANCE returns a rating', async ({ page }) => {
    test.setTimeout(180_000)
    await page.goto('/')
    await page.getByPlaceholder('Search name or code, e.g. Adani or RELIANCE.NSE').fill('RELIANCE.NSE')
    await page.getByRole('button', { name: 'Analyze' }).click()
    await expect(page.getByText(/composite|stance|RSI/i).first()).toBeVisible({ timeout: 150_000 })
  })
})
