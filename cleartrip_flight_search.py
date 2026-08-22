#this is the page contain the logic of the code

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from typing import List

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

CLEARTRIP_URL = "https://www.cleartrip.com"
DEFAULT_TIMEOUT = 15
RESULTS_TIMEOUT = 25
PAGE_LOAD_TIMEOUT = 30
TOP_N_FLIGHTS = 5

_EXTRACT_ONWARD_FLIGHTS_JS = r"""
const maxCount = arguments[0];

function isFlightLegRow(text) {
  const times = text.match(/\d{1,2}:\d{2}/g) || [];
  const durations = text.match(/\d{1,2}h\s?\d{1,2}m/g) || [];
  const prices = text.match(/₹[\d,]+/g) || [];
  return times.length === 2 && durations.length === 1 && prices.length === 1;
}

function rowPrice(text) {
  const match = text.match(/₹[\d,]+/);
  return match ? parseInt(match[0].replace(/[^\d]/g, ''), 10) : Infinity;
}

const priceLeaves = Array.from(document.querySelectorAll('body *')).filter(
  el => el.children.length === 0 && /^₹[\d,]+$/.test((el.textContent || '').trim())
);

const seenRows = new Set();
const rows = [];
for (const leaf of priceLeaves) {
  let node = leaf;
  let matchedRow = null;
  for (let depth = 0; depth < 12 && node.parentElement; depth++) {
    node = node.parentElement;
    if (isFlightLegRow(node.textContent || '')) {
      matchedRow = node;
      break;
    }
  }
  if (matchedRow && !seenRows.has(matchedRow)) {
    seenRows.add(matchedRow);
    rows.push(matchedRow);
  }
}

if (rows.length === 0) {
  return [];
}

const xPositions = rows.map(row => row.getBoundingClientRect().x);
const midX = (Math.min(...xPositions) + Math.max(...xPositions)) / 2;
const onwardRows = rows
  .filter((row, i) => xPositions[i] < midX)
  .sort((a, b) => rowPrice(a.textContent || '') - rowPrice(b.textContent || ''))
  .slice(0, maxCount);

return onwardRows.map(row => {
  const fields = row.innerText.split('\n').map(s => s.trim()).filter(Boolean);
  return {
    airline: fields[0] || '',
    flightNumber: fields[1] || '',
    departureTime: fields[2] || '',
    duration: fields[3] || '',
    stops: fields[4] || '',
    arrivalTime: fields[5] || '',
    price: fields[6] || '',
  };
});
"""


def robust_click(driver: WebDriver, element: WebElement) -> None:
    try:
        element.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", element)


@dataclass(frozen=True)
class FlightSearchRequest:
    origin: str
    destination: str
    departure_date: date
    return_date: date


@dataclass(frozen=True)
class FlightOffer:
    airline: str
    flight_number: str
    departure_time: str
    arrival_time: str
    duration: str
    stops: str
    price_inr: int

    @property
    def price_display(self) -> str:
        return f"₹{self.price_inr:,}"


class PopupHandler:
    """Dismisses the modals Cleartrip shows on a fresh visit."""

    _CLOSE_ICON = (By.CSS_SELECTOR, "svg[data-testid='closeIcon']")
    _LOGIN_PROMO_CLOSE = (By.XPATH, "//div[@class='pb-1 px-1 flex flex-middle nmx-1']")

    def __init__(self, driver: WebDriver, timeout: int = 6):
        self.driver = driver
        self.timeout = timeout

    def dismiss_close_icon_popup(self) -> None:
        self._dismiss(self._CLOSE_ICON)

    def dismiss_login_promo(self) -> None:
        self._dismiss(self._LOGIN_PROMO_CLOSE)

    def _dismiss(self, locator: tuple) -> None:
        try:
            close_button = WebDriverWait(self.driver, self.timeout).until(
                EC.element_to_be_clickable(locator)
            )
            robust_click(self.driver, close_button)
        except TimeoutException:
            pass  


class CleartripHomePage:
    """Page object for the flight-search widget on the Cleartrip home page."""

    _ROUND_TRIP_LABEL = (By.XPATH, "//p[normalize-space(text())='Round trip']")
    _FROM_INPUT = (By.XPATH, "//input[@placeholder='Where from?']")
    _TO_INPUT = (By.XPATH, "//input[@placeholder='Where to?']")
    _AIRPORT_SUGGESTIONS = (By.CSS_SELECTOR, "ul.airportList li")
    _DEPARTURE_TRIGGER = (By.CSS_SELECTOR, "div[data-testid='dateSelectOnward']")
    _SEARCH_BUTTON = (By.XPATH, "//button[normalize-space(.)='Search Flights']")

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    def open(self) -> "CleartripHomePage":
        self.driver.get(CLEARTRIP_URL)
        popups = PopupHandler(self.driver)
        popups.dismiss_close_icon_popup()
        popups.dismiss_login_promo()
        self._ensure_round_trip_selected()
        return self

    def _ensure_round_trip_selected(self) -> None:
        # Cleartrip's trip-type default (One way vs. Round trip) varies by
        # session, and selecting it resets the From/To fields - so this must
        # run before set_origin/set_destination, not just once at page load.
        label = self.wait.until(EC.element_to_be_clickable(self._ROUND_TRIP_LABEL))
        robust_click(self.driver, label)

    def set_origin(self, city_or_code: str) -> "CleartripHomePage":
        self._pick_airport(self._FROM_INPUT, city_or_code)
        return self

    def set_destination(self, city_or_code: str) -> "CleartripHomePage":
        self._pick_airport(self._TO_INPUT, city_or_code)
        return self

    def _pick_airport(self, input_locator: tuple, query: str) -> None:
        field = self.wait.until(EC.element_to_be_clickable(input_locator))
        robust_click(self.driver, field)
        self.driver.execute_script("arguments[0].select();", field)
        field.send_keys(query)
        time.sleep(1)  # the suggestion list is debounced (~600ms) before it filters
        suggestion = self.wait.until(EC.element_to_be_clickable(self._AIRPORT_SUGGESTIONS))
        robust_click(self.driver, suggestion)

    def select_travel_dates(self, departure: date, return_date: date) -> "CleartripHomePage":
        trigger = self.wait.until(EC.element_to_be_clickable(self._DEPARTURE_TRIGGER))
        robust_click(self.driver, trigger)
        self._click_calendar_day(departure)
        self._click_calendar_day(return_date)  # same calendar stays open for the return pick
        return self

    def _click_calendar_day(self, day: date) -> None:
        aria_label = day.strftime("%a %b %d %Y")
        locator = (By.XPATH, f"//div[@aria-label='{aria_label}']")
        cell = self.wait.until(EC.element_to_be_clickable(locator))
        robust_click(self.driver, cell)

    def submit_search(self) -> "CleartripResultsPage":
        button = self.wait.until(EC.element_to_be_clickable(self._SEARCH_BUTTON))
        robust_click(self.driver, button)
        return CleartripResultsPage(self.driver)


class CleartripResultsPage:
    """Page object for the onward/return split flight-results page."""

    _ANY_PRICE = (By.XPATH, "//*[contains(text(), '₹')]")

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, RESULTS_TIMEOUT)

    def wait_until_loaded(self) -> "CleartripResultsPage":
        self.wait.until(EC.url_contains("flights/results"))
        self.wait.until(EC.presence_of_element_located(self._ANY_PRICE))
        assert "flights/results" in self.driver.current_url, "Search did not reach the results page"
        return self

    def top_cheapest_onward_flights(self, limit: int = TOP_N_FLIGHTS) -> List[FlightOffer]:
        deadline = time.monotonic() + RESULTS_TIMEOUT
        raw_rows: list = []
        while time.monotonic() < deadline:
            raw_rows = self.driver.execute_script(_EXTRACT_ONWARD_FLIGHTS_JS, limit)
            if raw_rows:
                break
            time.sleep(1)
        return [self._to_flight_offer(row) for row in raw_rows]

    @staticmethod
    def _to_flight_offer(row: dict) -> FlightOffer:
        price_inr = int(re.sub(r"[^\d]", "", row["price"]))
        return FlightOffer(
            airline=row["airline"],
            flight_number=row["flightNumber"],
            departure_time=row["departureTime"],
            arrival_time=row["arrivalTime"],
            duration=row["duration"],
            stops=row["stops"],
            price_inr=price_inr,
        )


class FlightPriceReport:
    """Collects per-destination results and prints them as console tables."""

    def __init__(self, origin: str):
        self.origin = origin
        self._entries: List[tuple] = []

    def add_destination_result(self, destination: str, offers: List[FlightOffer]) -> None:
        self._entries.append((destination, offers))

    def print_report(self) -> None:
        for destination, offers in self._entries:
            self._print_destination_table(destination, offers)

    def _print_destination_table(self, destination: str, offers: List[FlightOffer]) -> None:
        title = f"Top {TOP_N_FLIGHTS} cheapest flights: {self.origin} -> {destination}"
        print()
        print(title)

        if not offers:
            print("  No flights found.")
            return

        headers = ["#", "Airline", "Flight No.", "Departure", "Arrival", "Duration", "Stops", "Price"]
        rows = [
            [
                str(rank),
                offer.airline,
                offer.flight_number,
                offer.departure_time,
                offer.arrival_time,
                offer.duration,
                offer.stops,
                offer.price_display,
            ]
            for rank, offer in enumerate(offers, start=1)
        ]
        self._print_table(headers, rows)

    @staticmethod
    def _print_table(headers: List[str], rows: List[List[str]]) -> None:
        widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]

        def format_row(cells: List[str]) -> str:
            return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths))

        print(format_row(headers))
        for row in rows:
            print(format_row(row))


class CleartripFlightPriceExplorer:
    """Drives the end-to-end search across every destination."""

    def __init__(self, driver: WebDriver, origin: str):
        self.driver = driver
        self.origin = origin
        self.report = FlightPriceReport(origin)

    def run(self, destinations: List[str], departure: date, return_date: date) -> FlightPriceReport:
        assert destinations, "At least one destination is required"
        requests = [
            FlightSearchRequest(self.origin, destination, departure, return_date)
            for destination in destinations
        ]
        for request in requests:
            print(f"Searching {request.origin} -> {request.destination} ...")
            offers = self._search_one(request)
            self.report.add_destination_result(request.destination, offers)
        return self.report

    def _search_one(self, request: FlightSearchRequest) -> List[FlightOffer]:
        try:
            home = CleartripHomePage(self.driver).open()
            home.set_origin(request.origin).set_destination(request.destination)
            home.select_travel_dates(request.departure_date, request.return_date)
            results = home.submit_search()
            results.wait_until_loaded()
            offers = results.top_cheapest_onward_flights(TOP_N_FLIGHTS)
            assert offers, f"No onward flights were parsed for {request.origin} -> {request.destination}"
            time.sleep(3)
            self.driver.get(CLEARTRIP_URL)
            return offers
        except (WebDriverException, AssertionError) as exc:
            print(f"  Could not fetch flights for {request.destination}: {exc}")
            return []


def build_chrome_driver() -> WebDriver:
    options = Options()
    options.page_load_strategy = "eager"
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.maximize_window()
    return driver
