import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

BASE_URL = "https://www.investorgain.com"

def deobfuscate_cf_email(encoded_str: str) -> str:
    """Decode Cloudflare email-protection obfuscated strings (e.g. L@112.00)."""
    try:
        r = int(encoded_str[:2], 16)
        return "".join([chr(int(encoded_str[i:i+2], 16) ^ r) for i in range(2, len(encoded_str), 2)])
    except Exception:
        return encoded_str

def safe_float(val: Optional[str]) -> Optional[float]:
    """Convert numeric string to float safely, returning None if empty or invalid."""
    if not val:
        return None
    cleaned = re.sub(r"[^\d.-]", "", val)
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_price_num(price_str: Optional[str]) -> Optional[float]:
    """Extract numeric price (upper cap if range) from price string (e.g. '1,119' -> 1119.0)."""
    if not price_str:
        return None
    cleaned = price_str.replace(",", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if not numbers:
        return None
    try:
        return float(numbers[-1])
    except ValueError:
        return None


def scrape_ipo_subscriptions(url_or_tab: str = "open") -> List[Dict[str, Any]]:
    """
    Scrape IPO Live Subscription table from investorgain.com.
    url_or_tab can be:
      - a tab name like 'open', 'all', 'closing-today', 'sme', 'ipo'
      - or a full URL like 'https://www.investorgain.com/report/ipo-subscription-live/333/open/'
    """
    if url_or_tab.startswith("http://") or url_or_tab.startswith("https://"):
        target_url = url_or_tab
    else:
        tab = url_or_tab.strip("/ ")
        target_url = f"{BASE_URL}/report/ipo-subscription-live/333/{tab}/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(target_url, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id="reportTable")
    if not table:
        raise ValueError(f"Could not find table with id 'reportTable' at {target_url}")

    tbody = table.find("tbody")
    if not tbody:
        return []

    results: List[Dict[str, Any]] = []

    for tr in tbody.find_all("tr"):
        # Skip repeated table header rows
        classes = tr.get("class", [])
        if "tbody-repeated-header" in classes:
            continue

        tds = {td.get("data-label"): td for td in tr.find_all("td")}
        name_td = tds.get("Name")
        if not name_td:
            continue

        # 1. Company Name & Link
        link_el = name_td.find("a")
        name = link_el.get_text(strip=True) if link_el else ""
        rel_link = link_el.get("href", "") if link_el else ""
        full_link = f"{BASE_URL}{rel_link}" if rel_link.startswith("/") else rel_link

        # 2. Badges (Category & Status)
        badges = [b.get_text(strip=True) for b in name_td.find_all("span", class_="badge")]
        category = badges[0] if badges else "IPO"
        status = badges[1] if len(badges) > 1 else ""

        # 3. GMP / Listing Info (check for Cloudflare obfuscated elements)
        gmp_text = ""
        cf_link = name_td.find("a", class_="__cf_email__")
        if cf_link and cf_link.get("data-cfemail"):
            decoded = deobfuscate_cf_email(cf_link["data-cfemail"])
            parent_text = cf_link.parent.get_text(strip=True)
            gmp_text = parent_text.replace(cf_link.get_text(strip=True), decoded)
        else:
            small_tag = name_td.find("small")
            if small_tag:
                gmp_text = small_tag.get_text(separator=" ", strip=True)

        # Extract parsed numeric GMP percentage if present
        gmp_pct_match = re.search(r"\(([+-]?[\d.]+)%\)", gmp_text)
        gmp_pct = float(gmp_pct_match.group(1)) if gmp_pct_match else None

        # 4. Total Subscription & Time
        total_td = tds.get("Total")
        total_raw = ""
        total_time = ""
        if total_td:
            b_tag = total_td.find("b")
            total_raw = b_tag.get_text(strip=True) if b_tag else ""
            small_tag = total_td.find("small")
            total_time = small_tag.get_text(strip=True) if small_tag else ""

        total_num = safe_float(total_raw)

        # 5. Investor Categories Subscriptions
        qib_raw = tds.get("QIB").get_text(strip=True) if tds.get("QIB") else ""
        shni_raw = tds.get("SHNI").get_text(strip=True) if tds.get("SHNI") else ""
        bhni_raw = tds.get("BHNI").get_text(strip=True) if tds.get("BHNI") else ""
        nii_raw = tds.get("NII").get_text(strip=True) if tds.get("NII") else ""
        rii_raw = tds.get("RII").get_text(strip=True) if tds.get("RII") else ""

        # 6. Other details
        anchor = tds.get("Anchor").get_text(strip=True) if tds.get("Anchor") else ""
        size = tds.get("IPO Size").get_text(strip=True) if tds.get("IPO Size") else ""
        price = tds.get("IPO Price").get_text(strip=True) if tds.get("IPO Price") else ""
        pe = tds.get("P/E").get_text(strip=True) if tds.get("P/E") else ""
        closing_date = tds.get("Closing Date").get_text(strip=True) if tds.get("Closing Date") else ""

        # 7. Calculate RII Lot Size & sHNI Lot Size
        # rii_lot_size = (15000 // price) * price (multiple of price just below 15k)
        # shni_lot_size = multiple of rii_lot_size just above 200000
        price_num = extract_price_num(price)
        if price_num and price_num > 0:
            shares_in_rii_lot = int(15000 // price_num)
            if shares_in_rii_lot == 0:
                shares_in_rii_lot = 1
            rii_lot_size = int(shares_in_rii_lot * price_num)
            if rii_lot_size > 0:
                shni_lots = (200000 // rii_lot_size) + 1
                shni_lot_size = int(shni_lots * rii_lot_size)
            else:
                shni_lot_size = None
        else:
            shares_in_rii_lot = None
            rii_lot_size = None
            shni_lot_size = None

        record = {
            "name": name,
            "category": category,
            "is_sme": "SME" in category.upper(),
            "status": status,
            "gmp": gmp_text,
            "gmp_pct": gmp_pct,
            "total": total_num,
            "total_str": f"{total_raw}x" if total_raw else "-",
            "total_time": total_time,
            "qib": safe_float(qib_raw),
            "qib_str": f"{qib_raw}x" if qib_raw else "-",
            "shni": safe_float(shni_raw),
            "shni_str": f"{shni_raw}x" if shni_raw else "-",
            "bhni": safe_float(bhni_raw),
            "bhni_str": f"{bhni_raw}x" if bhni_raw else "-",
            "nii": safe_float(nii_raw),
            "nii_str": f"{nii_raw}x" if nii_raw else "-",
            "rii": safe_float(rii_raw),
            "rii_str": f"{rii_raw}x" if rii_raw else "-",
            "anchor": anchor,
            "size": size,
            "price": price,
            "price_num": price_num,
            "rii_lot_size": rii_lot_size,
            "rii_lot_size_str": f"₹{rii_lot_size:,}" if rii_lot_size else "-",
            "shni_lot_size": shni_lot_size,
            "shni_lot_size_str": f"₹{shni_lot_size:,}" if shni_lot_size else "-",
            "pe": pe,
            "closing_date": closing_date,
            "link": full_link,
        }
        results.append(record)


    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    data = scrape_ipo_subscriptions("open")
    print(f"Scraped {len(data)} items from 'open' tab:")
    for d in data:
        print(f" - {d['name']} [{d['category']}]: Total {d['total_str']}, RII {d['rii_str']}, QIB {d['qib_str']}, GMP {d['gmp']}, Closes {d['closing_date']}")
