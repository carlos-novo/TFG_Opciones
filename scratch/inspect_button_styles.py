import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        print("Connecting to http://localhost:8502...")
        await page.goto("http://localhost:8502")
        await page.wait_for_timeout(3000)
        
        if await page.locator("text=Consola").count() == 0:
            print("Logging in...")
            await page.locator("input").first.fill("admin")
            await page.locator("input[type='password']").fill("admin2026")
            await page.locator("button:has-text('Iniciar Sesión')").click()
            await page.wait_for_timeout(4000)
            
        print("Navigating to Control Room...")
        tabs = page.locator("button[data-baseweb='tab']")
        count = await tabs.count()
        for i in range(count):
            text = await tabs.nth(i).inner_text()
            if "Control Room" in text:
                await tabs.nth(i).click()
                await page.wait_for_timeout(3000)
                break
                
        buttons = page.locator("button:has-text('Cierre Forzado Manual')")
        btn_count = await buttons.count()
        print(f"Found {btn_count} manual close buttons.")
        
        if btn_count > 0:
            btn = buttons.first
            parent_styles = await btn.evaluate("""el => {
                let p = el;
                let trace = [];
                for(let i=0; i<6; i++) {
                    if(!p) break;
                    let style = window.getComputedStyle(p);
                    let rect = p.getBoundingClientRect();
                    trace.push({
                        tagName: p.tagName,
                        className: p.className,
                        width: style.width,
                        display: style.display,
                        justifyContent: style.justifyContent,
                        alignItems: style.alignItems,
                        rect: {left: rect.left, right: rect.right, width: rect.width, top: rect.top, height: rect.height}
                    });
                    p = p.parentElement;
                }
                return trace;
            }""")
            for depth, info in enumerate(parent_styles):
                print(f"\nDepth {depth}: <{info['tagName']}> class='{info['className']}'")
                print(f"  Width: {info['width']}, Display: {info['display']}, JustifyContent: {info['justifyContent']}, AlignItems: {info['alignItems']}")
                print(f"  Rect: {info['rect']}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
