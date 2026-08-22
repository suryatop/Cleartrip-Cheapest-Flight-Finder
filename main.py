#from here the code starts

from datetime import date

from cleartrip_flight_search import CleartripFlightPriceExplorer, build_chrome_driver


def main() -> None:
    origin = "BLR"
    destinations = ["DEL", "CCU", "Chennai", "HYD"]
    departure_date = date(2026, 8, 24)
    return_date = date(2026, 8, 25)

    driver = build_chrome_driver()
    try:
        explorer = CleartripFlightPriceExplorer(driver, origin)
        report = explorer.run(destinations, departure_date, return_date)
        report.print_report()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
