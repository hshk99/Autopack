---
name: site-scraper
description: Deep scrape specific sites for relevant pages
tools: [WebFetch, Read, Write]
model: haiku
---

# Site Scraper Sub-Agent

Scrape target sites for pages related to: {{topic}}

## Input

Target sites: {{target_sites}}
Topic: {{topic}}

## Scraping Process

For each target site:

### Step 1: Fetch Sitemap (if available)
```
WebFetch: {{site}}/sitemap.xml
```

### Step 2: If No Sitemap, Crawl Key Pages
Fetch and extract links from:
- Homepage
- /blog or /articles
- /docs or /documentation
- /resources
- /pricing (for competitor sites)

### Step 3: Identify Relevant Pages
From discovered links, identify pages related to {{topic}} by:
- URL path matching
- Page title matching
- Meta description content

### Step 4: Extract Page Metadata
For each relevant page:
- Title
- URL
- Meta description
- Publication date (if available)
- Page type (blog, docs, product, etc.)

## Output Format

Return JSON to parent agent:
```json
{
  "scraped_sites": [
    {
      "site": "https://example.com",
      "sitemap_found": true,
      "pages_discovered": 45,
      "relevant_pages": [
        {
          "url": "https://example.com/blog/relevant-post",
          "title": "Page Title",
          "description": "Meta description...",
          "page_type": "blog",
          "published_date": "2024-01-10",
          "relevance_score": 0.85
        }
      ]
    }
  ],
  "total_pages_scraped": 120,
  "total_relevant_pages": 35
}
```

## Constraints

- Use haiku model for cost efficiency
- Respect robots.txt (skip disallowed paths)
- Maximum 20 pages per site
- 1 second delay between requests (simulated via sequential fetching)
- Skip non-HTML content (PDFs, images, etc.)
- Prioritize recent content (check dates when available)
