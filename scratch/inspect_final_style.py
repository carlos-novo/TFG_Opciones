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
                
                # Check the tab-highlight element style
                highlight = page.locator("div[data-baseweb='tab-highlight-bar']")
                if await highlight.count() > 0:
                    hl_style = await highlight.first.evaluate("""el => {
                        const style = window.getComputedStyle(el);
                        return style.backgroundColor;
                    }""")
                    safe_print(f"Tab highlight bar background color: {hl_style}")
                break
                
        # Find the Toggle "Filtro Tendencia (SMA)"
        toggle_label = page.locator("label:has-text('Filtro Tendencia (SMA)')")
        if await toggle_label.count() > 0:
            # Click it to activate
            safe_print("Clicking the toggle...")
            await toggle_label.click()
            await page.wait_for_timeout(1000)
            
            # Print styles
            track_style = await toggle_label.locator("div").first.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    backgroundColor: style.backgroundColor,
                    borderColor: style.borderColor
                };
            }""")
            safe_print(f"Track style: {track_style}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
