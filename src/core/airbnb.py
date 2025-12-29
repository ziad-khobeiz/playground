from playwright.sync_api import sync_playwright
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
import re
import time
from src.core.llm import get_response, DEFAULT_FIREWORKS_MODEL

FILTER_PROMPT = """
From the following list of listings, return a list of listing/room IDs that match the following criteria:
The listing could likely be a one bedroom apartment. Exclude any listing that is obviously a studio. Exclude any listing that is obviously a room in a shared housing.

If you are unsure, include the listing.
Be very concise in your reasoning. Do not overthink it.

Listings:
{listings}
"""

class Listing(BaseModel):
    id: str
    title: str
    description: str
    link: str
    price: str
    rating: str
    picture: str

    def to_telegram_format(self) -> str:
        return (
            f"🏠 <b>{self.title}</b>\n"
            f"📍 {self.description}\n"
            f"💰 {self.price}\n"
            f"⭐ {self.rating}\n"
            f"🔗 <a href='{self.link}'>View Listing</a>"
        )


class ListingIdResponse(BaseModel):
    ids: List[str]


def extract_page_listings(page) -> List[Listing]:
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
            
            # Extract ID from link
            listing_id = "N/A"
            if link != "N/A":
                match = re.search(r'/rooms/(\d+)', link)
                if match:
                    listing_id = match.group(1)

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

            listings.append(Listing(
                id=listing_id,
                title=title,
                description=full_description,
                link=link,
                price=price,
                rating=rating,
                picture=picture
            ))
            
        except Exception as e:
            print(f"Error extracting card {i}: {e}")
            continue

    return listings


def search_listings(location: str, move_in_date: str, move_out_date: str, max_price: int, max_pages: int, retries: int = 3) -> List[Listing]:
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
                
                # --- NEW: Handle "One price" disclosure popup ---
                # It usually appears on load. We try to find the "Got it" button.
                try:
                    # Short timeout because it might not be there
                    got_it_btn = page.get_by_role("button", name="Got it")
                    if got_it_btn.is_visible(timeout=5000):
                        got_it_btn.click()
                        print("Closed 'One price' popup.")
                except Exception:
                    pass # verify if this is needed or if is_visible handles it gracefully

                # 1. Type LOCATION into the destination field
                # Click first to ensuring focus, then clear and type
                search_input = page.get_by_test_id("structured-search-input-field-query")
                search_input.click(force=True)
                search_input.fill(location)

                # 2. Click the suggestion for "LOCATION, United Arab Emirates"
                # Wait for suggestion to appear
                suggestion = page.get_by_test_id("option-0")
                suggestion.wait_for(state="visible", timeout=5000)
                suggestion.click()

                # 3. Open the date picker/check-in field if not already open
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
                
                # Wait for the date picker container or header to ensure it's open
                # If clicking suggestion didn't open it, we might need to click "Check in"
                try:
                    page.get_by_test_id("structured-search-input-field-split-dates-0").click(timeout=2000)
                except:
                    pass # It might already be open

                next_month_button = page.locator('button[aria-label="Move forward to switch to the next month."]')
                
                # Loop to find Check-In Month
                # Add a safe breaker to avoid infinite loops
                max_clicks = 24 
                clicks = 0
                while not page.get_by_role("heading", name=check_in_month_str).is_visible():
                    if clicks > max_clicks:
                        raise Exception(f"Could not find check-in month {check_in_month_str}")
                    next_month_button.click()
                    clicks += 1
                
                # Select Check-in Day
                # Use ^= to match start of string "1, ..." avoiding "11," or "21," matches
                page.locator(f'button[aria-label^="{check_in_day_str}"][aria-label*="{check_in_month_str}"]').click()

                # 5. Navigate to Check-out Month
                clicks = 0
                while not page.get_by_role("heading", name=check_out_month_str).is_visible():
                    if clicks > max_clicks:
                        raise Exception(f"Could not find check-out month {check_out_month_str}")
                    next_month_button.click()
                    clicks += 1

                # Select Check-out Day
                page.locator(f'button[aria-label^="{check_out_day_str}"][aria-label*="{check_out_month_str}"]').click()

                # 6. Click Search
                # Ensure we are at the top where the search bar usually is
                page.evaluate("window.scrollTo(0, 0)")
                search_btn = page.get_by_test_id("structured-search-input-search-button").first
                search_btn.wait_for(state="visible", timeout=5000)
                search_btn.click()

                # Wait for results to load
                page.wait_for_selector('[data-testid="category-bar-filter-button"]')

                # --- NEW: Handle "One price" popup after search ---
                try:
                    # Look for the popup and click "Got it" or similar.
                    # Text: "Now you’ll see one price for your trip, all fees included."
                    # Button usually says "Got it" or "OK"
                    popup_btn = page.get_by_role("button", name="Got it")
                    if popup_btn.is_visible(timeout=3000):
                        popup_btn.click()
                        print("Closed 'One price' post-search popup.")
                    else:
                         # Sometimes it might be a different button or just a close X
                         close_btn = page.get_by_label("Close")
                         if close_btn.is_visible(timeout=1000):
                             # Ensure we are closing a modal, not something else. 
                             # This is risky but often necessary. Check if modal is present.
                             if page.locator('[data-testid="modal-container"]').is_visible():
                                 close_btn.first.click()
                                 print("Closed modal via Close button.")
                except Exception:
                    pass

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
                price_input.fill(str(max_price)) # ensure string

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
                        # Use JS click to bypass viewport/overlap issues completely
                        next_button.evaluate("node => node.click()")
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


def filter_listings(listings: List[Listing]) -> List[Listing]:
    # Format listings for the prompt
    listings_text = ""
    for l in listings:
        listings_text += f"\n- ID: {l.id}\n  Title: {l.title}\n  Description: {l.description}\n  Price: {l.price}\n"
        
    prompt = FILTER_PROMPT.format(listings=listings_text)
    
    try:
        response = get_response(prompt, ListingIdResponse)
        
        # Filter the original list based on returned IDs
        filtered_listings = [l for l in listings if l.id in response.ids]
        
        # Log if some IDs were not found (optional, for debugging)
        if len(response.ids) != len(filtered_listings):
            print(f"Note: LLM returned definitions for {len(response.ids)} IDs, but only {len(filtered_listings)} were matched.")

        return filtered_listings
        
    except Exception as e:
        print(f"Error filtering listings: {e}")
        return []

class LocationVerification(BaseModel):
    is_match: bool
    reason: str

class AestheticVerification(BaseModel):
    is_aesthetic: bool
    reason: str

def verify_listing(listing: Listing, required_location: str) -> bool:
    print(f"Verifying listing: {listing.title} ({listing.id})")
    
    # Using the user-preferred alias for Gemini 3
    VISION_MODEL = "accounts/fireworks/models/qwen3-vl-235b-a22b-thinking"
    
    scraped_location = "N/A"
    image_urls = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch_persistent_context(
                user_data_dir="./playwright_user_data",
                headless=False,
                no_viewport=True,
            )
            page = browser.new_page()
            
            print(f"Navigating to {listing.link}...")
            page.goto(listing.link)
            
            # Close "One price" popup if present
            try:
                page.get_by_role("button", name="Got it").click(timeout=3000)
                print("Closed popup.")
            except:
                pass
                
            page.wait_for_load_state("domcontentloaded")
            
            # 1. Scrape Location
            # Attempt to find "Where you'll be" section text
            # This is often under a specific heading
            try:
                # Find the heading "Where you'll be" and get the text following it
                # We can grab the whole text content of the location section if possible
                # Simple approach: Search for the text "Where you'll be" and grab surrounding text
                # Or just grab the main address header often found at the top
                
                # Let's try to get the meta address first
                # <meta property="og:title" content="..."> might contain location
                
                # Let's use the page text but focus on the "Where you'll be" area
                # We can also look for the map container
                
                heading = page.get_by_role("heading", name="Where you'll be")
                if heading.count() > 0:
                    heading.scroll_into_view_if_needed()
                    # Get the text of the container. 
                    # Assuming some structure, but safely just grabbing a chunk of text around it?
                    # Let's grab the 1000 characters after the heading appears in the inner_text?
                    # Getting parent text is better.
                    # locator("..") from heading
                    loc_container = heading.locator("xpath=..")
                    scraped_location = loc_container.inner_text()
                else:
                    # Fallback to body text truncated
                    scraped_location = page.inner_text("body")[:5000]
                    
            except Exception as e:
                print(f"Error scraping precise location: {e}")
                scraped_location = page.inner_text("body")[:5000]

            # 2. Scrape Images
            # Get images from the photo grid
            images = page.locator('[data-testid="photo-grid-picture"] img').all()
            if not images:
                # Fallback to all images
                images = page.locator("img").all()
            
            count = 0
            for img in images:
                src = img.get_attribute("src")
                if src and "im/pictures" in src:
                    if src not in image_urls:
                        image_urls.append(src)
                        count += 1
                if count >= 10: 
                    break
            
            print(f"Scraped {len(image_urls)} images.")
            
    except Exception as e:
        print(f"Error scraping listing: {e}")
        return False

    # 3. Verify Location with LLM
    print("Verifying location...")
    location_prompt = f"""
    The user is looking for a listing in "{required_location}".
    I have scraped the following text from the listing page (specifically looking for 'Where you'll be' or address data):
    
    ---
    {scraped_location[:5000]}
    ---
    
    Does this listing appear to be in {required_location}? 
    Be strict about the city/area. If the text says "Dubai" and user wants "Dubai", it's a match.
    """
    
    try:
        # Use default model (Gemini) for text reasoning
        loc_resp = get_response(location_prompt, LocationVerification)
        if not loc_resp.is_match:
            print(f"Location mismatch: {loc_resp.reason}")
            return False
        print(f"Location match: {loc_resp.reason}")
    except Exception as e:
        print(f"Error calling LLM for location: {e}")
        return False

    # 4. Verify Aesthetics with Vision LLM
    print("Verifying aesthetics...")
    if not image_urls:
        print("No images found to verify.")
        return False
        
    # Construct Multimodal Prompt
    content_parts = []
    content_parts.append({"type": "text", "text": "Does this listing look minimalist, clean, bright, and aesthetic? Analyze the interior design, clutter, and color palette. Be strict."})
    
    for url in image_urls:
         content_parts.append({"type": "image_url", "image_url": {"url": url}})
         
    try:
        vision_resp = get_response(
            content_parts, 
            AestheticVerification, 
            model=VISION_MODEL
        )
        
        if vision_resp.is_aesthetic:
            print(f"Aesthetic verification passed: {vision_resp.reason}")
            return True
        else:
            print(f"Aesthetic verification failed: {vision_resp.reason}")
            return False
            
    except Exception as e:
        print(f"Error calling Vision LLM: {e}")
        return False


def verify_listings(listings: List[Listing], required_location: str) -> List[Listing]:
    return [listing for listing in listings if verify_listing(listing, required_location)]
