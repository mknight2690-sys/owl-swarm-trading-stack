"""Test SeleniumBase UC Mode to bypass Cloudflare Turnstile."""
try:
    from seleniumbase import SB
    print("SeleniumBase available")

    with SB(uc=True, headless=True, incognito=True) as sb:
        url = "https://api.blofin.com/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP"
        sb.uc_open_with_reconnect(url, 4)
        sb.sleep(8)
        page_text = sb.get_page_text()
        print(f"Page text length: {len(page_text)}")
        print(f"Page text: {page_text[:500]}")
except ImportError:
    print("SeleniumBase not installed")
except Exception as e:
    print(f"Error: {e}")
