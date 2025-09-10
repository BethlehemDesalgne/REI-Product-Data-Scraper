# REI Product Data Scraper

This project is a robust web scraping pipeline designed to collect, normalize, and export product data from [REI.com](https://www.rei.com). It demonstrates skills in large-scale scraping, data cleaning, and structured output generation for downstream analytics.

## 🔍 Problem Statement
Retailers like REI present product data in dynamic, inconsistent formats, making it difficult to extract clean, structured information for analysis or integration. The challenge is to:
- Reliably collect product IDs from category pages.
- Handle dynamic product detail pages (PDPs) that embed JSON (`modelData`) inside HTML.
- Normalize extracted attributes (brand, price, colors, sizes, ratings, availability, features, specs, media, etc.).
- Save results into a clean JSON format ready for analysis.

## 📈 Scalability Plan
This repo also includes a **[Scalability Plan](REI%20Full%20Catalog%20Scraping%20Scalability%20Plan.docx)** that outlines how to extend the scraper to REI’s *entire catalog*:
1. **Category Discovery** – Build a full category hierarchy by parsing `/categories` endpoint responses.
2. **Product ID Collection** – Traverse each category’s paginated JSON API, storing unique product IDs while handling rate limits.
3. **Product Detail Extraction** – Fetch detailed product data for every unique ID and export into JSON/CSV.
4. **Concurrency & Resilience** – Use multi-threading, retries with exponential backoff, rotating proxies, and checkpointing to handle large-scale scraping at production level:contentReference[oaicite:0]{index=0}.

This ensures the solution can scale from a single category (like Women’s T-Shirts) to the **full REI catalog** with complete SKU coverage.

## ⚙️ Features
- **Concurrent Scraping** with retry logic for efficiency.
- **Browser Automation** via `DrissionPage` (Chromium) for dynamic rendering.
- **Data Normalization** for attributes:
  - Product details (name, description, brand, categories, specs, features).
  - Pricing & sale ranges.
  - Colors & sizes.
  - Ratings & reviews.
  - Media (images, videos).
  - Availability and shipping flags.
- **Clean Output** into structured JSON.

## 📂 Output
- `product_ids.json` – list of collected product IDs.
- `extracted_product_data.json` – normalized product dataset.
- `REI Full Catalog Scraping Scalability Plan.docx` – outlines full end-to-end scaling approach.

## 🛠️ Tech Stack
- **Python** (`requests`, `BeautifulSoup`, `DrissionPage`, `concurrent.futures`)
- **Concurrency & Retry Handling** with `urllib3` and `HTTPAdapter`
- **JSON Data Normalization** with custom helper functions
