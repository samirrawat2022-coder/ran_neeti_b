# RAN-NEETI — Full Feature Build (Free-tier compatible)

This build preserves the original Streamlit workflows and removes paid Google Search grounding from Gemini requests.

## Included features
- Home Dashboard
- Real Sports Lab with sport, format, venue, two competitors, competition/date, context and advanced instructions
- Anime & Fictional Battles with matchup type, universe, character versions/story arcs and scenario rules
- TheSportsDB public team/player metadata lookup (optional; uses public test key `3` unless configured)
- Jikan character lookup with MediaWiki fallback
- MediaWiki general entity lookup
- Gemini text generation without the `google_search` tool
- Structured matchup reports: evidence, outcome estimates, strengths/weaknesses, major moves, counters, turning points, win conditions, outcome paths and uncertainty
- Recent Reports session history
- Markdown report downloads
- About RAN-NEETI page
- API connection test and clearer API error handling

## Deploy
1. Extract this ZIP.
2. Upload the contents of `RAN_NEETI_Full_Build` to the root of a GitHub repository.
3. On Streamlit Community Cloud, create an app from that repository and set the main file path to `app.py`.
4. In App settings → Secrets, add:

```toml
GEMINI_API_KEY = "YOUR_PRIVATE_GEMINI_API_KEY"
GEMINI_MODEL = "gemini-3.8-flash"
```

Optional:
```toml
SPORTSDB_API_KEY = "3"
```

5. Save, reboot the app, then use **TEST API CONNECTION** in the sidebar.

Never put API keys in source code, GitHub, screenshots, or chat. Gemini requests use text generation only; they do not attach Google Search grounding. Text generation remains subject to the model's free-tier rate limits and availability. Removing grounding cannot eliminate 429 errors caused by exhausted text-generation quota, request-rate limits, disabled API access, or an invalid key.

## Data freshness and limitations
- SportsDB/Jikan/MediaWiki are public entity metadata sources, not a guaranteed live official sports-data feed.
- Google Search grounding is disabled. Recent scores, injuries, lineups, weather and breaking news must be supplied by the user or verified independently.
- The app includes no trained sport-specific ML models, historical training pipeline, calibrated probability forecasts or validated accuracy metrics. Sports percentages are qualitative AI estimates; fictional matchup percentages are subjective scenario interpretations.
- Report history is stored in Streamlit session state and may disappear when the session resets.

## Verification
The Python source is syntax-checked. A live end-to-end test still requires a valid Gemini API key, available free-tier quota, internet access and a deployed Streamlit runtime. API providers can change rate limits and availability.
