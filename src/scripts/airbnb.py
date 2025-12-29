from src.core.airbnb import search_airbnb

MOVE_IN_DATE = "19-01-2026"
MOVE_OUT_DATE = "19-04-2026"
LOCATION = "Dubai"
MAX_PRICE = "12000" # AED
MAX_PAGES = 1


if __name__ == "__main__":
    listings = search_airbnb(LOCATION, MOVE_IN_DATE, MOVE_OUT_DATE, MAX_PRICE, MAX_PAGES)
    print(listings)
