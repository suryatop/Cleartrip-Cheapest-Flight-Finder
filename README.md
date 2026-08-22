# Cleartrip Cheapest-Flight Finder

This is a Python + Selenium script that goes to [cleartrip.com](https://www.cleartrip.com)
and searches round-trip flights from **BLR** to **DEL, CCU, Chennai, HYD**. For each
destination it grabs the top 5 cheapest flights and prints them to the console.

## What it does

For each destination, one by one:

1. Opens `https://www.cleartrip.com` and closes the popups that show up (login/promo
   popup, and a close-icon overlay).
2. Types the origin (`BLR`) into the "Where from?" box.
3. Types the destination (`DEL` / `CCU` / `Chennai` / `HYD`) into the "Where to?" box.
4. Clicks the departure date and the return date on the calendar.
5. Clicks **Search Flights** and waits for the results to show up.
6. Reads the 5 cheapest flights (airline, flight number, times, duration, stops,
   price) off the results page.
7. Waits a few seconds, then goes back to the home page before starting the next
   destination.

Once every destination is done, it prints one table per destination, like this:

```
Top 5 cheapest flights: BLR -> HYD
#  Airline             Flight No.  Departure  Arrival  Duration  Stops      Price
1  Alliance Air        9I-517      20:50      22:35    1h 45m    Non-stop   ₹4,109
2  Air India Express   IX-1723     22:25      23:35    1h 10m    Non-stop   ₹4,427
3  IndiGo              6E-6178     06:25      07:35    1h 10m    Non-stop   ₹4,428
4  IndiGo              6E-484      08:15      09:30    1h 15m    Non-stop   ₹4,428
5  IndiGo              6E-6067     16:30      17:45    1h 15m    Non-stop   ₹4,428
```

The departure and return dates are currently set as fixed values in `main.py`
(`date(2026, 8, 24)` / `date(2026, 8, 25)`), not calculated from today's date. If you
need different dates, just change those two lines.

## Requirements

- Python 3.9+
- Google Chrome installed
- Selenium 4.6+ (it comes with Selenium Manager, so you don't need to download
  ChromeDriver separately)

```bash
pip install selenium
```

## Running it

```bash
python3 main.py
```

This opens a real Chrome window and runs the searches in it. Don't close the window
while it's running. Results print to the terminal after all four destinations are
done.

## Files

- `main.py` — the entry point. Just sets the origin/destinations/dates, starts the
  browser, runs the search, and prints the report.
- `cleartrip_flight_search.py` — all the actual logic, split into classes:

| Class | What it's for |
|---|---|
| `FlightSearchRequest` | Holds one origin/destination/date search |
| `FlightOffer` | Holds one flight result after it's been extracted |
| `PopupHandler` | Closes the popups Cleartrip shows on a fresh page load |
| `CleartripHomePage` | Handles the search form (cities, dates, submit button) |
| `CleartripResultsPage` | Waits for results and pulls the flight data out |
| `FlightPriceReport` | Prints the console tables |
| `CleartripFlightPriceExplorer` | Runs the search loop for every destination |

**Why the flight data isn't read using class/XPath selectors:** Cleartrip's results
page classnames change every time they redeploy the site (stuff like `sc-bdfDLd
hHGXKc`), so any selector based on those breaks sooner or later. Instead, the script
looks at the text inside each DOM node and picks out the smallest one that has
exactly one price (`₹4,109`), one duration (`1h 45m`), and two times (`20:50`,
`22:35`) — that's one flight row. It tells onward flights apart from return flights
just by which side of the page they're on. This is slower to write but it doesn't
break every time Cleartrip changes their frontend.

## Known limitations

- Only shows flights Cleartrip already displays by default (its "Non-stop" filter is
  already applied by the site) — doesn't clear filters to also check 1-stop/2-stop
  flights.
- If Cleartrip changes the page so much that nothing matches the price/duration/time
  pattern anymore, that destination will just come back with no flights. The script
  prints a message and moves on to the next destination instead of crashing.
- The departure/return dates are hardcoded (see above). Once those dates are in the
  past, the calendar won't have a matching day to click and the search for every
  destination will fail.
