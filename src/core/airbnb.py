from playwright.sync_api import sync_playwright
from datetime import datetime
import re
import time

def extract_page_listings(page):
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


def search_airbnb(location: str, move_in_date: str, move_out_date: str, max_price: int, max_pages: int, retries: int = 3):
    last_exception = None
    
    for attempt in range(1, retries + 1):
        print(f"Details collection attempt {attempt}/{retries}")
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir="./playwright_user_data",
                    headless=False,
                    no_viewport=True,
                )
                page = browser.new_page()
                page.goto("https://www.airbnb.ae/")

                # 1. Type LOCATION into the destination field
                page.get_by_test_id("structured-search-input-field-query").fill(location)

                # 2. Click the suggestion for "LOCATION, United Arab Emirates"
                page.get_by_test_id("option-0").click()

                # 3. Open the date picker/check-in field if not already open (usually typing location opens it, but clicking suggestion might auto-advance)
                # The logic above clicks the option which usually advances to dates.
                
                # Parse Dates
                # Format: DD-MM-YYYY
                move_in_dt = datetime.strptime(move_in_date, "%d-%m-%Y")
                move_out_dt = datetime.strptime(move_out_date, "%d-%m-%Y")

                # Format for UI matching
                # Heading style for month: "January 2026" (%B %Y)
                check_in_month_str = move_in_dt.strftime("%B %Y")
                check_out_month_str = move_out_dt.strftime("%B %Y")
                
                # Day for aria-label: "19,"
                check_in_day_str = f"{move_in_dt.day},"
                check_out_day_str = f"{move_out_dt.day},"

                # 4. Navigate to Check-in Month
                # We need to find the "Next" button and click until we see the target month/year
                # Using a while loop is safer than hardcoding clicks.
                
                # Wait for the date picker to be visible just in case
                # Ideally we'd look for the calendar container, but looking for the next button is a good proxy.
                next_month_button = page.locator('button[aria-label="Move forward to switch to the next month."]')
                
                # We might need to ensure the calendar is open.
                # If the previous step worked, we are likely in the "Check in" tab.
                
                while not page.get_by_role("heading", name=check_in_month_str).is_visible():
                    next_month_button.click()
                
                # Select Check-in Day
                # Locator matching partial label for robustness. Element is a button.
                # e.g. aria-label="19, ... January 2026"
                page.locator(f'button[aria-label*="{check_in_day_str}"][aria-label*="{check_in_month_str}"]').click()

                # 5. Navigate to Check-out Month
                while not page.get_by_role("heading", name=check_out_month_str).is_visible():
                    next_month_button.click()

                # Select Check-out Day
                page.locator(f'button[aria-label*="{check_out_day_str}"][aria-label*="{check_out_month_str}"]').click()

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
                # Ensure existing text is cleared or just use fill which usually overwrites
                price_input.fill(max_price)

                # 11. Click "Show ... homes"
                # This button text is dynamic (e.g. "Show 123 homes"), so we match partially
                page.locator("a").filter(has_text="Show").click()

                # Wait for results to update/reload
                page.wait_for_timeout(3000)
                
                # 12. Extract Listings with Pagination
                all_listings = []
                
                for page_num in range(1, max_pages + 1):
                    print(f"Scraping page {page_num}...")
                    
                    # Extract from current page
                    current_listings = extract_page_listings(page)
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
                
                return all_listings

        except Exception as e:
            print(f"Error encountered during search attempt {attempt}: {e}")
            last_exception = e
            if attempt < retries:
                print("Retrying in 2 seconds...")
                time.sleep(2)
            else:
                print("Max retries reached.")

    # If we fall through the loop, raise the last exception
    if last_exception:
        raise last_exception
    return []
