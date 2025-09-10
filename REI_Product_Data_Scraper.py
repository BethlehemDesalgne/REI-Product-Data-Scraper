from __future__ import annotations

# ========== Imports ==========
import json
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry



# ========== Constants & Headers ==========
LISTING_URL_TMPL = "https://www.rei.com/c/womens-t-shirts?json=true&page={}"
BASE_URL = "https://www.rei.com"

PRODUCT_IPS = "product_ids.json"
OUTPUT_PRODUCT_DATA = 'extracted_product_data.json'

TARGET_COUNT = 90         
MAX_WORKERS  = 8          
MAX_EMPTY_PAGES = 3        
REQUEST_TIMEOUT = (5, 20)  

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139 Safari/537.36",
}

# ========== Small Utilities ==========
def random_sleep(min_seconds=5, max_seconds=8):
    sleep_duration = random.uniform(min_seconds, max_seconds)
    print(f"Sleeping for {sleep_duration:.2f} seconds...")
    time.sleep(sleep_duration)

def make_session(pool_size: int) -> requests.Session:
    """Create a pooled session with retries/backoff."""
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(HEADERS)
    return s

# ========== Product-ID Collection ==========
def parse_prod_ids(payload: dict) -> List[str]:
    """Extract prodId strings from a search JSON payload."""
    results = payload.get("searchResults", {}).get("results", []) or []
    ids = []
    for item in results:
        pid = item.get("prodId")
        if pid:
            ids.append(str(pid))
    return ids

def fetch_page(session: requests.Session, page_number: int) -> List[str]:
    """Fetch one page and return the prodIds found."""
    # Tiny jitter helps avoid thundering herd patterns
    time.sleep(random.uniform(0.02, 0.12))
    url = LISTING_URL_TMPL .format(page_number)
    r = session.get(url, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    return parse_prod_ids(data)

def collect_prod_ids(
    target_count: int = TARGET_COUNT,
    start_page: int = 1,
    max_workers: int = MAX_WORKERS,
    max_empty: int = MAX_EMPTY_PAGES,
) -> List[str]:
    session = make_session(pool_size=max_workers + 4)
    collected, seen = [], set()
    next_page = start_page
    empty_streak = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        # warm up the queue
        futures = {ex.submit(fetch_page, session, p): p for p in range(next_page, next_page + max_workers)}
        next_page += max_workers

        while futures and len(collected) < target_count and empty_streak < max_empty:
            for future in as_completed(list(futures.keys())):
                page_num = futures.pop(future)
                try:
                    ids = future.result()
                except Exception:
                    ids = []

                if not ids:
                    empty_streak += 1
                else:
                    empty_streak = 0
                    for pid in ids:
                        if pid not in seen:
                            seen.add(pid)
                            collected.append(pid)
                            if len(collected) >= target_count:
                                break

                # keep the pipeline full
                if len(collected) < target_count and empty_streak < max_empty:
                    futures[ex.submit(fetch_page, session, next_page)] = next_page
                    next_page += 1

                if len(collected) >= target_count or empty_streak >= max_empty:
                    break

        # Best-effort cancel any not-yet-started tasks (Python 3.9+)
        ex.shutdown(cancel_futures=True)

    return collected[:target_count]


# ========== Normalization Helpers (PDP modelData) ==========
def deep_get(d: Any, path: List[Any], default=None):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur

def to_abs_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    if url.startswith(("media/", "product/", "c/")):
        return f"{BASE_URL}/{url.lstrip('/')}"
    return url

def extract_name(data: Dict[str, Any]) -> Optional[str]:
    full_title = deep_get(data, ["title"])
    if isinstance(full_title, str) and " | " in full_title:
        return full_title.split(" | ", 1)[0].strip()
    brand = deep_get(data, ["pageData", "product", "brand", "name"]) or "REI Co-op"
    prod_title = deep_get(data, ["pageData", "product", "title"])
    if prod_title:
        return f"{brand} {prod_title}".strip()
    return None

def extract_product_id(data: Dict[str, Any]) -> Optional[str]:
    return deep_get(data, ["pageData", "product", "styleId"])

def extract_description(data: Dict[str, Any]) -> Optional[str]:
    desc = data.get("description")
    if isinstance(desc, str):
        return desc.strip()
    meta_desc = deep_get(data, ["openGraphProperties", "og:description"])
    if isinstance(meta_desc, str):
        return meta_desc.strip()
    return None

def extract_canonical_url(data: Dict[str, Any]) -> Optional[str]:
    og_url = deep_get(data, ["openGraphProperties", "og:url"])
    if isinstance(og_url, str):
        return to_abs_url(og_url)
    can = deep_get(data, ["pageData", "product", "canonicalUrl"])
    if isinstance(can, str):
        return to_abs_url(can)
    return None

def extract_breadcrumbs(data: Dict[str, Any]):
    crumbs = deep_get(data, ["pageData", "product", "breadcrumbs"], default=[]) or []
    out = []
    for c in crumbs:
        item = c.get("item") if isinstance(c, dict) else None
        if isinstance(item, dict):
            name = item.get("name")
            url = to_abs_url(item.get("url"))
            canonical = item.get("canonical")
            if name:
                out.append({"name": name, "url": url, "canonical": canonical})
    return out

def extract_categories(data: Dict[str, Any]) -> List[str]:
    return [b["name"] for b in extract_breadcrumbs(data)]

def extract_taxonomy(data: Dict[str, Any]):
    taxCat = deep_get(data, ["pageData", "product", "taxCat"])
    taxCatRoot = deep_get(data, ["pageData", "product", "taxCatRoot"])
    return taxCat, taxCatRoot

def extract_brand(data: Dict[str, Any]):
    b = deep_get(data, ["pageData", "product", "brand"]) or {}
    if not isinstance(b, dict):
        return None
    out = dict(b)  # shallow copy
    # Normalize URLs
    for key in ("link", "logoUrl"):
        if key in out and isinstance(out[key], str):
            out[key] = to_abs_url(out[key])
    return out

def extract_colors(data: Dict[str, Any]) -> List[str]:
    colors = deep_get(data, ["pageData", "product", "colors"], default=[]) or []
    labels = []
    for c in colors:
        label = c.get("displayLabel") or c.get("name")
        if isinstance(label, str):
            labels.append(label.strip().title() if label.isupper() else label.strip())
    seen, uniq = set(), []
    for v in labels:
        if v not in seen:
            seen.add(v); uniq.append(v)
    return uniq

def extract_sizes(data: Dict[str, Any]) -> List[str]:
    sizes = deep_get(data, ["pageData", "product", "sizesV2"]) or deep_get(data, ["pageData", "product", "sizes"]) or []
    return [str(s) for s in sizes] if isinstance(sizes, list) else []

def extract_price_info(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[Tuple[float, float]], bool, List[int]]:
    skus = deep_get(data, ["pageData", "product", "skus"], default=[]) or []
    regulars, sale_vals, savings_pct = [], [], set()
    is_on_sale = False
    for sku in skus:
        cmp_val = deep_get(sku, ["price", "compareAt", "value"])
        price_val = deep_get(sku, ["price", "price", "value"])
        offer_type = deep_get(sku, ["price", "price", "offerType"])
        sale_flag = deep_get(sku, ["price", "price", "sale"]) or (offer_type in {"sale", "clearance"})
        if isinstance(cmp_val, (int, float)): regulars.append(float(cmp_val))
        if sale_flag and isinstance(price_val, (int, float)):
            sale_vals.append(float(price_val)); is_on_sale = True
        sp = deep_get(sku, ["price", "savingsPercentage"])
        if isinstance(sp, (int, float)):
            try: savings_pct.add(int(round(float(sp))))
            except Exception: pass
    regular_price = max(regulars) if regulars else (max(sale_vals) if sale_vals else None)
    sale_range = (min(sale_vals), max(sale_vals)) if sale_vals else None
    return regular_price, sale_range, is_on_sale, sorted(savings_pct)

def summarize_availability(data: Dict[str, Any]) -> Optional[str]:
    skus = deep_get(data, ["pageData", "product", "skus"], default=[]) or []
    if not skus: return None
    total = len(skus)
    unavailable = sum(1 for s in skus if s.get("unavailable") or (s.get("status") == "UNAVAILABLE"))
    sellable = sum(1 for s in skus if s.get("sellable"))
    if sellable == 0: return "Unavailable — All SKUs are currently unavailable."
    ratio = unavailable / total if total else 0
    if ratio >= 0.5: return "Limited — Many SKUs are unavailable; some colors/sizes may be on clearance or backorder."
    if 0 < ratio < 0.5: return "Partially available — Some sizes or colors are out of stock."
    return "In stock — Most options available."

def extract_features(data: Dict[str, Any]) -> List[str]:
    for c in (deep_get(data, ["pageData", "product", "features"]),
              deep_get(data, ["pageData", "product", "bullets"]),
              deep_get(data, ["pageData", "product", "highlights"])):
        if isinstance(c, list) and c:
            return [str(x).strip() for x in c if str(x).strip()]
    long_desc = deep_get(data, ["pageData", "product", "longDescription"])
    if isinstance(long_desc, str) and long_desc.strip():
        return [p.strip("•- \n\r\t") for p in long_desc.split("\n") if p.strip()][:15]
    return []

def extract_specs(data: Dict[str, Any]) -> Dict[str, str]:
    specs = deep_get(data, ["pageData", "product", "specs"])
    if isinstance(specs, dict):
        return {str(k).strip(): str(v).strip() for k, v in specs.items()}
    if isinstance(specs, list):
        out = {}
        for row in specs:
            k, v = row.get("name"), row.get("value")
            if k and v: out[str(k).strip()] = str(v).strip()
        if out: return out
    attrs = deep_get(data, ["pageData", "product", "attributes"])
    if isinstance(attrs, list):
        out = {}
        for a in attrs:
            k = a.get("name") or a.get("label")
            v = a.get("value") or a.get("text")
            if k and v: out[str(k).strip()] = str(v).strip()
        if out: return out
    return {}

def extract_ratings(data: Dict[str, Any]):
    def coerce_summary(rs: Dict[str, Any]):
        avg = rs.get("averageRating"); cnt = rs.get("count", rs.get("reviewCount"))
        hist = rs.get("ratingHistogram"); top = rs.get("topRated")
        try: avg = float(avg) if avg is not None else None
        except Exception: avg = None
        try: cnt = int(cnt) if cnt is not None else None
        except Exception: cnt = None
        if isinstance(hist, dict):
            try: hist = {str(k): int(v) for k, v in hist.items()}
            except Exception: hist = None
        else: hist = None
        if not isinstance(top, bool): top = None
        return avg, cnt, hist, top

    for path in (["pageData","product","reviews","reviewSummary"],
                 ["pageData","product","reviewSummary"],
                 ["reviews","reviewSummary"],
                 ["reviewSummary"]):
        rs = deep_get(data, path)
        if isinstance(rs, dict): return coerce_summary(rs)

    candidates: List[Dict[str, Any]] = []
    def walk(o: Any):
        if isinstance(o, dict):
            inner = o.get("reviewSummary")
            if isinstance(inner, dict): candidates.append(inner)
            if ("averageRating" in o) and ("count" in o or "reviewCount" in o): candidates.append(o)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(data)

    best, best_cnt = None, -1
    for rs in candidates:
        try_cnt = rs.get("count", rs.get("reviewCount"))
        try:
            try_cnt = int(try_cnt) if try_cnt is not None else -1
        except Exception:
            try_cnt = -1
        if try_cnt > best_cnt: best_cnt, best = try_cnt, rs
    if best: return coerce_summary(best)

    avg = deep_get(data, ["pageData","product","reviews","averageRating"]) or deep_get(data, ["pageData","product","averageRating"])
    cnt = deep_get(data, ["pageData","product","reviews","reviewCount"]) or deep_get(data, ["pageData","product","reviewCount"])
    try: avg = float(avg) if avg is not None else None
    except Exception: avg = None
    try: cnt = int(cnt) if cnt is not None else None
    except Exception: cnt = None
    return avg, cnt, None, None

def extract_featured_image(data: Dict[str, Any]) -> Optional[str]:
    featured = deep_get(data, ["pageData","product","displayOptions","featuredImage","heroImageUrl"])
    return to_abs_url(featured)

def extract_images_full(data: Dict[str, Any]):
    images = deep_get(data, ["pageData","product","images"])
    return images if isinstance(images, list) else None

def extract_videos(data: Dict[str, Any]):
    vids = deep_get(data, ["pageData","product","videos"])
    return vids if isinstance(vids, list) else None

def build_output(data: Dict[str, Any]) -> Dict[str, Any]:
    product_name = extract_name(data)
    product_id = extract_product_id(data)
    description = extract_description(data)
    canonical_url = extract_canonical_url(data)
    breadcrumbs = extract_breadcrumbs(data)
    categories = [b["name"] for b in breadcrumbs]
    taxCat, taxCatRoot = extract_taxonomy(data)
    brand = extract_brand(data)
    colors = extract_colors(data)
    sizes = extract_sizes(data)
    regular_price, sale_range, is_on_sale, savings_pct = extract_price_info(data)
    availability = summarize_availability(data)
    features = extract_features(data)
    specs = extract_specs(data)
    avg_rating, review_count, rating_histogram, top_rated = extract_ratings(data)
    featured_img = extract_featured_image(data)
    images_full = extract_images_full(data)
    videos = extract_videos(data)

    # Flags straight from product
    sapGender = deep_get(data, ["pageData","product","sapGender"])
    eligibleForShipping = deep_get(data, ["pageData","product","eligibleForShipping"])
    allSkusAreBopusOnly = deep_get(data, ["pageData","product","allSkusAreBopusOnly"])
    anyOversizeCharges = deep_get(data, ["pageData","product","anyOversizeCharges"])
    anySkuShippingRestrictions = deep_get(data, ["pageData","product","anySkuShippingRestrictions"])
    anySkusAreMembersOnly = deep_get(data, ["pageData","product","anySkusAreMembersOnly"])
    allDisplayableSkusArePreorder = deep_get(data, ["pageData","product","allDisplayableSkusArePreorder"])
    allDisplayableSkusAreBackorder = deep_get(data, ["pageData","product","allDisplayableSkusAreBackorder"])

    skus_raw = deep_get(data, ["pageData", "product", "skus"])

    out_core = {
        "productId": str(product_id) if product_id is not None else None,
        "productName": product_name,
        "brand": brand,
        "description": description,

        "media": {
            "featuredImage": featured_img,
            "allImages": images_full,
            "videos": videos,
        },

       "price": {
            "regularPrice": regular_price,
            "salePriceRange": list(sale_range) if sale_range else None,
            "isOnSale": bool(is_on_sale),
            "savingsPercentage": savings_pct or None,
        },

        "colors": colors,
        "sizes": sizes,

        "availability": availability,
        "features": features,
        "specs": specs,

        "ratings": {
            "averageRating": avg_rating,
            "reviewCount": review_count,
            "ratingHistogram": rating_histogram,
            "topRated": top_rated,
        },

        "metadata": {
            "canonicalUrl": canonical_url,
            "breadcrumbs": breadcrumbs,
            "categories": categories,
            "taxCat": taxCat,
            "taxCatRoot": taxCatRoot,
        },

        "shippingAndEligibility": {
            "sapGender": sapGender,
            "eligibleForShipping": eligibleForShipping,
            "allSkusAreBopusOnly": allSkusAreBopusOnly,
            "anyOversizeCharges": anyOversizeCharges,
            "anySkuShippingRestrictions": anySkuShippingRestrictions,
            "anySkusAreMembersOnly": anySkusAreMembersOnly,
            "allDisplayableSkusArePreorder": allDisplayableSkusArePreorder,
            "allDisplayableSkusAreBackorder": allDisplayableSkusAreBackorder,
        }
    }

    def prune(obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                pv = prune(v)
                if pv not in (None, [], {}, ""):
                    cleaned[k] = pv
            return cleaned
        if isinstance(obj, list):
            cleaned_list = []
            for v in obj:
                pv = prune(v)
                if pv not in (None, [], {}, ""):
                    cleaned_list.append(pv)
            return cleaned_list
        return obj

    pruned = prune(out_core)
    if skus_raw is not None:
        pruned["skus"] = skus_raw  # append raw, unpruned, at the end
    return pruned

# ========== Main Orchestration ==========
def main() -> None:
    prod_ids = collect_prod_ids()
    print(f"✅ Collected {len(prod_ids)} prodIds")
    # Save the list
    with open(PRODUCT_IPS, "w", encoding="utf-8") as f:
        json.dump(prod_ids, f, indent=2)
    print("💾 Saved to prod_ids.json and prod_ids.txt")

    time.sleep(2)

    # Load product IDs from JSON file
    with open(PRODUCT_IPS, "r", encoding="utf-8") as f:
        prod_ids = json.load(f)

    # Initialize the browser page
    page = ChromiumPage()

    # List to store all product data (now: normalized dicts from build_output)
    all_products_data = []

    for idx, prod_id in enumerate(prod_ids, 1):
        try:
            # Navigate to the product URL
            url = f'https://www.rei.com/product/{prod_id}'
            random_sleep(5, 8)
            page.get(url)
            
            # Print the page title to confirm
            print(f"Processing product {idx}/{len(prod_ids)}: {prod_id} - {page.title}")
            random_sleep(5, 8)

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(page.html, 'html.parser')

            # Find the script tag with id="modelData"
            model_data_script = soup.find('script', id='modelData')
            if model_data_script:
                json_text = model_data_script.string
                try:
                    # Parse the JSON text
                    product_data = json.loads(json_text)

                    normalized = build_output(product_data)
                    all_products_data.append(normalized)

                except json.JSONDecodeError:
                    print(f"Product {prod_id}: Error parsing JSON from modelData script tag.")
                except Exception as e:
                    print(f"Product {prod_id}: Error processing data - {str(e)}")
            else:
                print(f"Product {prod_id}: modelData script tag not found on the page.")
            
        except Exception as e:
            print(f"Product {prod_id}: Failed to process - {str(e)}")

    with open(OUTPUT_PRODUCT_DATA, 'w', encoding='utf-8') as json_file:
        json.dump(all_products_data, json_file, indent=4)
    print("All product data saved to 'extracted_product_info_all.json'")

    # Close the browser when done
    page.quit()
    print("Processing complete.")

if __name__ == "__main__":
    main()