from playwright.sync_api import sync_playwright

MOVE_IN_DATE = "19-01-2026"
MOVE_OUT_DATE = "19-04-2026"
LOCATION = "Dubai"
MAX_PRICE = "12000" # AED
MAX_PAGES = 10

import re

def extract_listings(page):
    listings = []
    # Wait for at least one card to be present
    page.wait_for_selector('[data-testid="card-container"]')
    
    cards = page.locator('[data-testid="card-container"]').all()
    print(f"Found {len(cards)} listings.")

    for i, card in enumerate(cards):
        try:
            # 1. Extract Title (The main listing name)
            # Try specific test id for name, fallback to title
            title_loc = card.get_by_test_id("listing-card-name") # often the user facing title
            if title_loc.count() == 0:
                 title_loc = card.get_by_test_id("listing-card-title")
            title = title_loc.first.inner_text().strip() if title_loc.count() > 0 else "N/A"

            # 2. Extract Description (Combination of property type and subtitles)
            description_parts = []
            
            # Add property type (e.g., "Apartment in Dubai") if it's different/available
            # Sometimes listing-card-title is the type, listing-card-name is the specific name "Lovely 1 Bd"
            type_loc = card.get_by_test_id("listing-card-title")
            if type_loc.count() > 0:
                text = type_loc.first.inner_text().strip()
                if text and text != title:
                     description_parts.append(text)
            
            # Collect and clean subtitles (e.g., "1 bedroom", "Dec 19-24")
            # We use .all() to get all subtitle elements
            subtitle_locs = card.get_by_test_id("listing-card-subtitle").all()
            for loc in subtitle_locs:
                raw_text = loc.inner_text().strip()
                if not raw_text:
                    continue
                
                # Split by newline or dot to handle internal duplication or multi-line text
                pieces = re.split(r'[\n·]', raw_text)
                for piece in pieces:
                    p = piece.strip()
                    # Filter out empty pieces, the title itself, or duplicates
                    if p and p != title and p not in description_parts:
                        description_parts.append(p)
            
            full_description = " · ".join(description_parts)
            if not full_description:
                 full_description = "N/A"

            # 3. Extract Link
            # The card itself is usually wrapped in a link or has a main link
            link_el = card.locator("a").first
            link = link_el.get_attribute("href") if link_el.count() > 0 else "N/A"
            if link != "N/A" and not link.startswith("http"):
                link = "https://www.airbnb.ae" + link

            # 4. Extract Price
            price_el = card.locator('[data-testid="price-availability-row"]')
            price = price_el.inner_text() if price_el.count() > 0 else "N/A"
            # Clean up price text (remove newlines, "night", etc for cleaner output)
            # Usually "1,200 AED\nnight"
            price = price.split('\n')[0].strip()

            # 5. Extract Rating
            rating = "N/A"
            # Try aria-label first which is most reliable "Rated 4.86 out of 5..."
            rating_lo = card.locator('span[aria-label*="rating"], span[aria-label*="average rating"]')
            if rating_lo.count() > 0:
                rating = rating_lo.first.get_attribute("aria-label")
            else:
                 # Fallback: look for text pattern like "4.86 (120)"
                 # We scan all spans in the card for this pattern
                 spans = card.locator("span").all()
                 for span in spans:
                     txt = span.inner_text().strip()
                     # Regex for "4.x (123)" or "4.x"
                     if re.match(r'^\d+\.\d+(\s*\(\d+\))?$', txt):
                         rating = txt
                         break

            # 6. Extract Picture
            img_el = card.locator("img").first
            picture = img_el.get_attribute("src") if img_el.count() > 0 else "N/A"

            listings.append({
                "Title": title,
                "Description": full_description,
                "Link": link,
                "Price": price,
                "Rating": rating,
                "Picture": picture
            })
            
        except Exception as e:
            print(f"Error extracting card {i}: {e}")
            continue

    return listings

with sync_playwright() as playwright:
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir="./playwright_user_data",
        headless=False,
        no_viewport=True,
    )
    page = browser.new_page()
    page.goto("https://www.airbnb.ae/")

    # 1. Type LOCATION into the destination field
    page.get_by_test_id("structured-search-input-field-query").fill(LOCATION)

    # 2. Click the suggestion for "LOCATION, United Arab Emirates"
    page.get_by_test_id("option-0").click()

    # 3. Open the date picker/check-in field if not already open (usually typing location opens it, but clicking suggestion might auto-advance)
    # The logic above clicks the option which usually advances to dates.
    
    # 4. Navigate to Jan 2026 for Check-in
    # We need to find the "Next" button and click until we see "January 2026"
    # Using a while loop is safer than hardcoding clicks.
    
    # Wait for the date picker to be visible just in case
    # Ideally we'd look for the calendar container, but looking for the next button is a good proxy.
    next_month_button = page.locator('button[aria-label="Move forward to switch to the next month."]')
    
    # We might need to ensure the calendar is open.
    # If the previous step worked, we are likely in the "Check in" tab.
    
    while not page.get_by_role("heading", name="January 2026").is_visible():
        next_month_button.click()
    
    # Select Jan 19, 2026
    # Locator matching partial label for robustness. Element is a button.
    page.locator('button[aria-label*="19,"][aria-label*="January 2026"]').click()

    # 5. Navigate to April 2026 for Check-out
    while not page.get_by_role("heading", name="April 2026").is_visible():
        next_month_button.click()

    # Select April 19, 2026
    page.locator('button[aria-label*="19,"][aria-label*="April 2026"]').click()

    # 6. Click Search
    page.get_by_test_id("structured-search-input-search-button").click()

    # Wait for results to load
    page.wait_for_selector('[data-testid="category-bar-filter-button"]')

    # 7. Open Filters
    page.get_by_test_id("category-bar-filter-button").click()

    # 8. Select "Entire home"
    # Using specific role ensures we get the actionable element
    page.get_by_role("radio", name="Entire home").click()

    # 9. Select 1 Bedroom (click increase button once)
    # Using the specific test-id for the stepper increase button
    page.get_by_test_id("stepper-filter-item-min_bedrooms-stepper-increase-button").click()

    # 10. Set Max Price
    # We need to clear it first or just fill it.
    price_input = page.locator("#price_filter_max")
    price_input.fill(MAX_PRICE)

    # 11. Click "Show ... homes"
    # This button text is dynamic (e.g. "Show 123 homes"), so we match partially
    page.locator("a").filter(has_text="Show").click()

    # Wait for results to update/reload
    page.wait_for_timeout(3000)

    MAX_PAGES = 10
    
    # 12. Extract Listings with Pagination
    all_listings = []
    
    for page_num in range(1, MAX_PAGES + 1):
        print(f"Scraping page {page_num}...")
        
        # Extract from current page
        current_listings = extract_listings(page)
        all_listings.extend(current_listings)
        print(f"Extracted {len(current_listings)} listings from page {page_num}.")
        
        # Check for Next button
        next_button = page.locator('a[aria-label="Next"]')
        
        if next_button.is_visible():
            next_button.click()
            # Wait for the next page to load. 
            # Ideally wait for the page number or listings to update.
            # A simple timeout is robust enough for this demo, or we can wait for net idle
            page.wait_for_timeout(3000) 
        else:
            print("No next page found or reached end.")
            break

    print(f"Total listings extracted: {len(all_listings)}")
    for listing in all_listings:
        print(listing)
    
    # breakpoint() # Removed as requested

