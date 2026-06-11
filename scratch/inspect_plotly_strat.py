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
                break
                
        # Wait for Plotly element to render
        try:
            safe_print("Waiting for Plotly graph...")
            await page.wait_for_selector("div.stPlotlyChart", timeout=15000)
            safe_print("Found stPlotlyChart container!")
        except Exception as e:
            safe_print(f"Plotly container not found: {e}")
            # Let's take screenshot or print body to see what's there
            body = await page.locator("body").inner_text()
            safe_print(body[:1000])
            await browser.close()
            return
            
        # Inspect Plotly graph lines
        paths = page.locator("svg.main-svg path.js-line")
        p_count = await paths.count()
        safe_print(f"Found {p_count} Plotly paths.")
        for idx in range(p_count):
            stroke = await paths.nth(idx).evaluate("el => el.style.stroke || el.getAttribute('stroke')")
            name = await paths.nth(idx).evaluate("el => el.parentElement.getAttribute('data-unformatted') || el.className.baseVal")
            safe_print(f"Path {idx} ({name}): stroke = {stroke}")
            
        # Inspect SVG lines (horizontal and vertical markups)
        shapes = page.locator("svg.main-svg g.shapelayer path")
        s_count = await shapes.count()
        safe_print(f"Found {s_count} Plotly shape paths.")
        for idx in range(s_count):
            stroke = await shapes.nth(idx).evaluate("el => el.style.stroke || el.getAttribute('stroke')")
            d_attr = await shapes.nth(idx).evaluate("el => el.getAttribute('d')")
            safe_print(f"Shape {idx} stroke: {stroke}, path d: {d_attr}")
            
        # Inspect text annotations
        annotations = page.locator("svg.main-svg g.annotation-text text")
        a_count = await annotations.count()
        safe_print(f"Found {a_count} Plotly annotations.")
        for idx in range(a_count):
            txt = await annotations.nth(idx).inner_text()
            fill = await annotations.nth(idx).evaluate("el => el.getAttribute('fill') || el.style.fill")
            safe_print(f"Annotation {idx} text: {txt}, fill: {fill}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
