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
                await page.wait_for_timeout(2000)
                break
                
        # Let's inspect the active BUY segmented control button style
        # In the options page, there is a segmented control for BUY/SELL
        # Let's find active BUY button
        # The selector is div[data-testid="stHorizontalBlock"] > div:nth-child(1) button[data-testid="stBaseButton-segmented_controlActive"]
        active_pills = page.locator("button[data-testid='stBaseButton-segmented_controlActive']")
        p_count = await active_pills.count()
        safe_print(f"Found {p_count} active segmented control pills.")
        
        for idx in range(p_count):
            text = await active_pills.nth(idx).inner_text()
            style = await active_pills.nth(idx).evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    backgroundColor: style.backgroundColor,
                    color: style.color
                };
            }""")
            safe_print(f"Active pill {idx} ({text}): {style}")
            
        # Let's inspect the delete button in the 7th column of stHorizontalBlock
        del_btn = page.locator("div[data-testid='stHorizontalBlock'] > div:nth-child(7) button")
        d_count = await del_btn.count()
        safe_print(f"Found {d_count} delete buttons.")
        for idx in range(d_count):
            style = await del_btn.nth(idx).evaluate("""el => {
                const style = window.getComputedStyle(el);
                return {
                    color: style.color,
                    borderColor: style.borderColor,
                    backgroundColor: style.backgroundColor
                };
            }""")
            safe_print(f"Delete button {idx} style: {style}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
