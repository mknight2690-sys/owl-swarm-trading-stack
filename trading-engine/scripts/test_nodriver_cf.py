"""Use nodriver (real Chrome) to solve Cloudflare and extract cookies."""
import asyncio

async def main():
    try:
        import nodriver as uc
    except ImportError:
        print("nodriver not installed")
        return

    print("Starting headless Chrome to solve Cloudflare challenge...")
    browser = await uc.Chrome(headless=True)
    
    # Navigate to BloFin API
    await browser.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP")
    await browser.sleep(8)  # Wait for Cloudflare challenge to resolve
    
    # Get page content
    content = await browser.get_content()
    print(f"Content length: {len(content)}")
    print(f"Content preview: {content[:300]}")
    
    # Get cookies
    cookies = await browser.send(cdp.network.get_cookies())
    print(f"\nCookies: {cookies}")
    
    await browser.quit()

asyncio.run(main())
