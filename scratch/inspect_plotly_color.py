import asyncio
from playwright.async_api import async_playwright

def safe_print(msg):
    print(msg.encode('ascii', 'replace').decode('ascii'))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Open local Streamlit
        await page.goto("http://localhost:8501")
        await page.wait_for_timeout(2000)
        
        # Check if login is needed
        if await page.locator("text=Acceso Restringido").count() > 0 or await page.locator("text=Consola Algorítmica").count() > 0:
            safe_print("Logging in...")
            await page.locator("input[type='text']").first.fill("admin")
            await page.locator("input[type='password']").fill("admin2026")
            await page.locator("button:has-text('Iniciar Sesión')").click()
            await page.wait_for_timeout(3000)
            
        safe_print("Logged in. Navigating to Opciones tab...")
        tabs = page.locator("button[data-baseweb='tab']")
        count = await tabs.count()
        for i in range(count):
            text = await tabs.nth(i).inner_text()
            if "Opciones" in text:
                await tabs.nth(i).click()
                await page.wait_for_timeout(2500)
                break
                
        # Inspect Greeks metric values
        metrics = page.locator("div[data-testid='stMetricValue']")
        m_count = await metrics.count()
        safe_print(f"Found {m_count} metric values on page.")
        for idx in range(m_count):
            text = await metrics.nth(idx).inner_text()
            style = await metrics.nth(idx).evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    color: style.color
                };
            }""")
            safe_print(f"Metric value {idx} ({text}): {style}")
            
        # Inspect Plotly graph temporal line
        # Plotly lines are rendered as svg path elements.
        # We can find paths with stroke attribute containing #6366f1 or rgb(99, 102, 241)
        paths = page.locator("svg.main-svg path.js-line")
        p_count = await paths.count()
        safe_print(f"Found {p_count} Plotly paths.")
        for idx in range(p_count):
            stroke = await paths.nth(idx).evaluate("el => el.style.stroke || el.getAttribute('stroke')")
            safe_print(f"Path {idx} stroke: {stroke}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
