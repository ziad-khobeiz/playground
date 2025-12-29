from datetime import datetime, timedelta
from src.core.airbnb import search_listings, verify_listing

def test_verification():
    print("Step 1: finding a listing to test...")
    
    # Calculate dynamic dates: 1 month from now
    now = datetime.now()
    check_in = now + timedelta(days=60)
    check_out = check_in + timedelta(days=10)
    
    move_in_str = check_in.strftime("%d-%m-%Y")
    move_out_str = check_out.strftime("%d-%m-%Y")
    
    print(f"Testing with dates: {move_in_str} to {move_out_str}")

    # Search for a listings in Dubai
    listings = search_listings(
        location="Dubai",
        move_in_date=move_in_str, 
        move_out_date=move_out_str,
        max_price=10000,
        max_pages=1
    )
    
    if not listings:
        print("No listings found to test.")
        return

    test_listing = listings[0]
    print(f"Testing with listing: {test_listing.title}\nLink: {test_listing.link}")

    # Test 1: Should match location
    print("\n--- Test 1: Verify correctly matches Dubai ---")
    result_match = verify_listing(test_listing, "Dubai")
    print(f"Result (Expect True for Location check): {result_match}")

    # Test 2: Should fail location
    print("\n--- Test 2: Verify correctly FAILS Paris ---")
    result_fail = verify_listing(test_listing, "Paris")
    print(f"Result (Expect False): {result_fail}")

if __name__ == "__main__":
    test_verification()
