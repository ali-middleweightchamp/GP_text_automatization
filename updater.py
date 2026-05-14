import os
from playwright.sync_api import Page


def read_descriptions(page: Page, edit_url: str) -> tuple[str, str, str, str]:
    """Возвращает (text_ru, text_uz, text_en, company_name)"""
    site_url = os.getenv("SITE_URL")
    full_url = edit_url if edit_url.startswith("http") else f"{site_url}{edit_url}"

    page.goto(full_url)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('textarea[name="OrganizationsTempDescription[description_ru]"]', timeout=60000)

    # Структура страницы: h1 = ID записи, h5 = название компании
    company_name = ""
    h5_el = page.query_selector('h5')
    if h5_el:
        company_name = h5_el.inner_text().strip()
    print(f"  Считано название: {company_name}")

    text_ru = page.input_value('textarea[name="OrganizationsTempDescription[description_ru]"]')
    text_uz = page.input_value('textarea[name="OrganizationsTempDescription[description_uz]"]')
    text_en = page.input_value('textarea[name="OrganizationsTempDescription[description_en]"]')

    return text_ru, text_uz, text_en, company_name


def update_organization(page: Page, record: dict, text_ru: str, text_uz: str, text_en: str) -> bool:
    site_url = os.getenv("SITE_URL")
    edit_url = record["edit_url"]
    full_url = edit_url if edit_url.startswith("http") else f"{site_url}{edit_url}"

    page.goto(full_url)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('textarea[name="OrganizationsTempDescription[description_ru]"]', timeout=60000)

    try:
        page.fill('textarea[name="OrganizationsTempDescription[description_ru]"]', text_ru)
        page.fill('textarea[name="OrganizationsTempDescription[description_uz]"]', text_uz)
        page.fill('textarea[name="OrganizationsTempDescription[description_en]"]', text_en)

        # Выбираем "Отмодерирована" (value=4)
        page.select_option(
            'select[name="OrganizationsTempDescription[status]"]',
            value="4"
        )

        with page.expect_navigation():
            page.click('button.btn-success[type="submit"]')

        return True

    except Exception as e:
        print(f"  Ошибка при обновлении {record['name']}: {e}")
        return False
