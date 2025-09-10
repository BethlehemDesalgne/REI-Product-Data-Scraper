# REI Product Data Scraper

This project is a robust web scraping pipeline designed to collect, normalize, and export product data from [REI.com](https://www.rei.com). It demonstrates skills in large-scale scraping, data cleaning, and structured output generation for downstream analytics.

## 🔍 Problem Statement
Retailers like REI present product data in dynamic, inconsistent formats, making it difficult to extract clean, structured information for analysis or integration. The challenge is to:
- Reliably collect product IDs from category pages.
- Handle dynamic product detail pages (PDPs) that embed JSON (`modelData`) inside HTML.
- Normalize extracted attributes (brand, price, colors, sizes, ratings, availability, features, specs, media, etc.).
- Save results into a clean JSON format ready for analysis.

## ⚙️ Features
- **Concurrent Scraping**: Uses `ThreadPoolExecutor` with retry logic for efficient collection of product IDs.
- **Browser Automation**: Leverages `DrissionPage` (Chromium) to handle dynamic PDP rendering.
- **Data Normalization**: Extracts and standardizes product attributes such as:
  - Product details (name, description, brand, categories, specs, features).
  - Pricing & sale ranges.
  - Colors & sizes.
  - Ratings & reviews.
  - Media (images, videos).
  - Availability and shipping flags.
- **Clean Output**: Exports structured product data into `extracted_product_data.json`.

## 📂 Output
- `product_ids.json` – list of collected product IDs.
- `extracted_product_data.json` – normalized product dataset.

## 🛠️ Tech Stack
- **Python** (`requests`, `BeautifulSoup`, `DrissionPage`, `concurrent.futures`)
- **Concurrency & Retry Handling** with `urllib3` and `HTTPAdapter`
- **JSON Data Normalization** with custom helper functions
