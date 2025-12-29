from src.core.airbnb import filter_listings, search_listings, verify_listings

MOVE_IN_DATE = "19-01-2026"
MOVE_OUT_DATE = "19-04-2026"
LOCATION = "Business Bay"
MAX_PRICE = "13000" # AED
MAX_PAGES = 30


if __name__ == "__main__":
    from src.core.telegram import send_message
    from dotenv import load_dotenv
    
    load_dotenv()

    listings = search_listings(LOCATION, MOVE_IN_DATE, MOVE_OUT_DATE, MAX_PRICE, MAX_PAGES)
    print(f"Found {len(listings)} listings before filtering.")
    
    filtered = filter_listings(listings)
    print(f"Found {len(filtered)} listings after filtering.")
    
    verified = verify_listings(filtered, LOCATION)
    print(f"Found {len(verified)} listings after verification.")
    
    if verified:
        send_message(f"Found {len(verified)} verified listings for {LOCATION}:")
        for listing in verified:
            send_message(listing.to_telegram_format())
    else:
        send_message(f"No verified listings found for {LOCATION}.")
