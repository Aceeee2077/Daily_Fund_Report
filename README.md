# Daily Fund Report

This repository generates a daily Chinese fund movement report as an HTML page.

The GitHub Actions workflow runs at 08:00 Beijing time on weekdays, updates fund
data from Eastmoney/Tiantian Fund, appends the latest record to `data/history.json`,
regenerates `report.html`, and publishes `docs/index.html` to GitHub Pages.

## Files

- `data/funds.json`: fund codes to track.
- `scripts/update_fund_report.py`: fetches fund data and renders the HTML report.
- `report.html`: local report page.
- `docs/index.html`: GitHub Pages entry point.
- `.github/workflows/daily-fund-report.yml`: scheduled automation.

## Customize Funds

Edit `data/funds.json` and add or remove six-digit fund codes:

```json
{ "code": "161725", "label": "招商中证白酒指数A" }
```

## Run Locally

```bash
python scripts/update_fund_report.py
```
