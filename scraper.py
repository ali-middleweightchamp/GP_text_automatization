import logging
import os
from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def get_official_names(company_id: int, page: Page) -> dict:
    """Возвращает {'ru': '...', 'uz': '...', 'en': '...'} с официальными названиями."""
    if not company_id:
        return {}
    results = {}
    urls = {
        'ru': f'https://goldenpages.uz/ru/company/?Id={company_id}',
        'uz': f'https://goldenpages.uz/uz/company/?Id={company_id}',
        'en': f'https://goldenpages.uz/en/company/?Id={company_id}',
    }
    for lang, url in urls.items():
        for attempt in range(2):
            try:
                page.goto(url)
                page.wait_for_load_state('networkidle', timeout=15000)
                el = page.query_selector('h1')
                if el:
                    name = el.inner_text().strip()
                    # Убираем суффикс " - Город" если есть
                    if ' - ' in name:
                        name = name.rsplit(' - ', 1)[0].strip()
                    if name and len(name) > 2:
                        results[lang] = name
                break
            except Exception as e:
                if attempt == 1:
                    print(f"  Не удалось получить {lang} название: {e}")
    return results


def scrape_organizations(page: Page) -> list[dict]:
    site_url = os.getenv("SITE_URL")
    index_url = f"{site_url}/organizations-temp/index"

    # 1. Открываем список и применяем фильтр "Сгенерирована" (value=3)
    page.goto(index_url)
    page.wait_for_load_state("networkidle")

    with page.expect_navigation(wait_until="networkidle"):
        page.select_option(
            'select[name="OrganizationsTempDescriptionSearch[status]"]',
            value="3"
        )

    records = []
    page_num = 1

    while True:
        print(f"  Страница {page_num}...")

        rows = page.query_selector_all("table tbody tr")
        if not rows:
            break

        for row in rows:
            edit_link = row.query_selector('a[href*="/organizations-temp/update"]')
            if not edit_link:
                continue

            href = edit_link.get_attribute("href")
            edit_url = href if href.startswith("http") else f"{site_url}{href}"

            record_id = None
            if "id=" in edit_url:
                try:
                    record_id = int(edit_url.split("id=")[-1].split("&")[0])
                except ValueError:
                    pass

            name = f"ID:{record_id}"
            cells = row.query_selector_all("td")
            for cell in cells:
                text = cell.inner_text().strip()
                if text and not text.isdigit() and len(text) > 3:
                    name = text
                    break

            records.append({
                "id": record_id,
                "edit_url": edit_url,
                "name": name,
            })

        next_btn = page.query_selector('li.next a, a:has-text("›"), a:has-text("»")')
        if not next_btn:
            break

        next_url = next_btn.get_attribute("href")
        if not next_url:
            break
        if not next_url.startswith("http"):
            next_url = f"{site_url}{next_url}"

        page.goto(next_url)
        page.wait_for_load_state("networkidle")
        page_num += 1

    return records
