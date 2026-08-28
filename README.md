# Redbubble Pinterest Auto-Bot

Automatska Python skripta koja povlači proizvode sa Redbubble RSS feed-a, generiše SEO opise pomoću Google Gemini AI modela i objavljuje ih na Pinterestu preko GitHub Actions automatizacije.

## Potrebni GitHub Secrets:
- `REDBUBBLE_USERNAME` - Vaše Redbubble korisničko ime
- `GEMINI_API_KEY` - API ključ sa Google AI Studio-a
- `PINTEREST_ACCESS_TOKEN` - Access token sa Pinterest Developer portala
- `PINTEREST_BOARD_ID` - ID Pinterest table na koju bot kači slike
