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
            
        safe_print("Logged in. Navigating to Acciones tab...")
        tabs = page.locator("button[data-baseweb='tab']")
        count = await tabs.count()
        for i in range(count):
            text = await tabs.nth(i).inner_text()
            if "Acciones" in text:
                await tabs.nth(i).click()
                await page.wait_for_timeout(2000)
                break
                
        # Find the Toggle "Filtro Volatilidad (VIX)" or "Filtro Tendencia (SMA)"
        # We can find it by its text
        toggle_label = page.locator("label:has-text('Filtro Tendencia (SMA)')")
        if await toggle_label.count() > 0:
            safe_print("Found Filtro Tendencia (SMA) toggle. Inspecting before check:")
            html_before = await toggle_label.evaluate("el => el.outerHTML")
            safe_print(html_before)
            
            # Click it to activate
            safe_print("Clicking the toggle...")
            await toggle_label.click()
            await page.wait_for_timeout(1000)
            
            safe_print("Inspecting after check:")
            html_after = await toggle_label.evaluate("el => el.outerHTML")
            safe_print(html_after)
            
            # Let's see what style is applied or what class changes
            # We can also execute JS to print computed style of the track and knob
            track_style = await toggle_label.locator("div").first.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    backgroundColor: style.backgroundColor,
                    borderColor: style.borderColor,
                    color: style.color
                };
            }""")
            safe_print(f"Track style: {track_style}")
            
            inner_div_style = await toggle_label.locator("div >> div").first.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    backgroundColor: style.backgroundColor,
                    transform: style.transform,
                    width: style.width,
                    height: style.height
                };
            }""")
            safe_print(f"Inner div style: {inner_div_style}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
