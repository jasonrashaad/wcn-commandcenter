# WCN Command Center Changelog

## 2026-09-16: v2 — rebuilt on the Raspberry Pi

Seventeen months after v1, rebuilt from nothing in one evening, on the same mood, with the same
name. v1 lived in a browser tab; v2 lives on `wcn-raspberrypi` and owns the office TV.

- Chromium kiosk at 1080p60 on the Samsung facing the desk; a stdlib Python state server
  behind it. Entirely user-space on the Pi — no root, nothing under `/etc`.
- Brand cards for the family: What Comes Next?, Evolutions, The Spark, Coach's Clipboard.
- **Gallery reel** from the MediaCMS studio's curated ILBTYD playlist (public manifest fallback).
- **PhotoPrism is back** (v1.2 below removed it) — random geotagged batch, thumbnails proxied.
- **Pulse** — fleet reachability, studio count, Pi vitals, Jellyfin now-playing / recently added.
- Samsung remote over HDMI-CEC drives the loop; the ticker did not survive.
- `deploy.sh`, dry-run by default, like the rest of the fleet.

v1 (below) is kept as history. It was right about the watermark, the clock and the date.

---


## 2024-03-19: Major Refactor and UI Enhancements

### Initial Refactor - Ticker-Focused Interface
- Removed PhotoPrism integration and gallery
- Removed video container
- Removed news feed section
- Cleaned up unused animations and styles
- Added configurable multi-source ticker system

### Visual Enhancements
#### Background Watermark (v1.2)
- Added centered WCN logo watermark
- Implemented subtle opacity animation (5-15%)
- Added smooth pulse effect
- Ensured content visibility with proper z-indexing

#### Header Redesign (v1.3)
- Updated tagline to "Transformation Begins With a Question..."
- Enhanced clock display with larger size and decorative elements
- Added full date display with day of week
- Improved header styling and spacing
- Added clock pulse animation effect

### Content Layout Restructure (v1.4)
#### Main Layout
- Implemented three-column grid layout
- Semi-transparent section backgrounds
- Maintained watermark visibility throughout

#### Video Overlay
- Repositioned to bottom-left above ticker
- Added semi-transparent overlay (0.7 opacity)
- Implemented hover effects (scale and opacity)
- Added minimize/maximize toggle
- Smooth transition animations

#### Weather Section
- Dedicated weather section with 5-day forecast
- Large current temperature display
- Detailed current conditions
- Daily forecast cards
- 30-minute auto-update interval
- OpenWeatherMap API integration (requires API key)

#### News Section
- Image-based news cards
- Article summaries included
- Hover effects for interactivity
- 15-minute auto-update interval
- NewsAPI integration (requires API key)
- Fallback placeholder for missing images

#### Market Overview Section
- Dedicated section for market data
- Prepared for future stock market integration

### Technical Details
#### API Integrations
- OpenWeatherMap API for weather data
  - 5-day forecast support
  - Imperial units
  - Location-based weather
- NewsAPI for news with images
  - Top headlines support
  - Image thumbnails
  - Article descriptions
- RSS2JSON API for additional news sources
  - No API key required
  - Multiple feed support

#### Configuration Options
- Stock symbols (comma-separated list)
- Weather location (city, state format)
- News feed URLs (one per line)
- Update intervals (10-300 seconds)
- Individual toggle switches for each data source

### Next Steps
1. **API Integration**
   - Sign up for OpenWeatherMap API key
   - Sign up for NewsAPI key
   - Replace placeholder API keys in code

2. **Content Setup**
   - Add news placeholder image
   - Configure desired news sources
   - Set preferred weather location

3. **Potential Enhancements**
   - Additional data sources
   - Custom styling options
   - More ticker customization
   - Additional news feed formats

### Version Tag
```bash
git tag -a v1.4-layout -m "Implemented full layout with weather, news, and video sections"
``` 