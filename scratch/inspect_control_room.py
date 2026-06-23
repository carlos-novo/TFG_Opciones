import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Open local Streamlit
        print("Opening localhost...")
        await page.goto("http://localhost:8502")
        await page.wait_for_timeout(3000)
        
        # Check login
        if await page.locator("text=Consola").count() == 0:
            print("Logging in...")
            await page.locator("input").first.fill("admin")
            await page.locator("input[type='password']").fill("admin2026")
            await page.locator("button:has-text('Iniciar Sesión')").click()
            await page.wait_for_timeout(4000)
            
        print("Logged in. Navigating to Control Room...")
        tabs = page.locator("button[data-baseweb='tab']")
        count = await tabs.count()
        for i in range(count):
            text = await tabs.nth(i).inner_text()
            if "Control Room" in text:
                print(f"Clicking Tab {i}: {text}")
                await tabs.nth(i).click()
                await page.wait_for_timeout(3000)
                break
                
        # Find Cierre Forzado Manual buttons
        buttons = page.locator("button:has-text('Cierre Forzado Manual')")
        btn_count = await buttons.count()
        print(f"Found {btn_count} manual close buttons.")
        
        for idx in range(btn_count):
            btn = buttons.nth(idx)
            # Traverse up to find parent containers
            parent_html = await btn.evaluate("""el => {
                let p = el;
                let trace = [];
                for(let i=0; i<6; i++) {
                    if(!p) break;
                    trace.push({
                        tagName: p.tagName,
                        className: p.className,
                        id: p.id,
                        attributes: Array.from(p.attributes).map(a => `${a.name}=${a.value}`)
                    });
                    p = p.parentElement;
                }
                return trace;
            }""")
            print(f"\n--- Button {idx} parent trace ---")
            for depth, p_info in enumerate(parent_html):
                print(f"Depth {depth}: <{p_info['tagName']}> class='{p_info['className']}' id='{p_info['id']}' attributes={p_info['attributes']}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
