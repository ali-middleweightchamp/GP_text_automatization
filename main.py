import sys
import logging
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from auth import login
from scraper import scrape_organizations, get_official_names
from rewriter import init_openai, rewrite, translate, detect_subject, force_official_name
from updater import update_organization, read_descriptions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    load_dotenv()
    processed = 0
    errors = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("Выполняю вход...")
        page = login(page)

        print("Собираю записи...")
        records = scrape_organizations(page)
        total = len(records)
        print(f"Найдено {total} записей")

        if total == 0:
            print("Нет записей.")
            browser.close()
            return

        client = init_openai()

        for i, record in enumerate(records, 1):
            try:
                print(f"\n[{i}/{total}] {record['name']}")

                text_ru, text_uz, text_en, company_name = read_descriptions(page, record["edit_url"])

                # Получаем официальные названия с goldenpages.uz
                official = get_official_names(record.get("id"), page)
                print(f"  Official RU: {official.get('ru', '-')}")
                print(f"  Official UZ: {official.get('uz', '-')}")
                print(f"  Official EN: {official.get('en', '-')}")

                # Определяем subject/clean/has_quotes из оригинального названия в базе
                alt_idx = (i - 1) % 3
                subject_ru, clean_name_ru, has_quotes = detect_subject(company_name, 'ru')
                subject_uz, clean_name_uz, _ = detect_subject(official.get('uz', company_name), 'uz')
                subject_en, clean_name_en, _ = detect_subject(official.get('en', company_name), 'en')

                print(f"  Subject: RU={subject_ru!r} clean={clean_name_ru!r} has_quotes={has_quotes}")

                # RU рерайт
                if text_ru and text_ru.strip():
                    new_ru_raw = rewrite(
                        client, text_ru,
                        company_name=company_name,
                        subject=subject_ru,
                        clean_name=clean_name_ru,
                        alt_idx=alt_idx,
                        has_quotes=has_quotes
                    )
                    new_ru = force_official_name(new_ru_raw, official.get('ru', ''), lang='ru')
                else:
                    new_ru = text_ru

                # UZ перевод
                if text_ru and text_ru.strip():
                    new_uz_raw = translate(
                        client, new_ru, 'uz',
                        has_quotes=has_quotes,
                        official_name=official.get('uz', ''),
                        official_subject=subject_uz if subject_uz != 'AUTO' else ''
                    )
                    new_uz = force_official_name(new_uz_raw, official.get('uz', ''), lang='uz')
                else:
                    new_uz = text_uz

                # EN перевод
                if text_ru and text_ru.strip():
                    new_en_raw = translate(
                        client, new_ru, 'en',
                        has_quotes=has_quotes,
                        official_name=official.get('en', ''),
                        official_subject=subject_en if subject_en != 'AUTO' else ''
                    )
                    new_en = force_official_name(new_en_raw, official.get('en', ''), lang='en')
                else:
                    new_en = text_en

                print(f"  RU: {new_ru[:120]}")
                print(f"  UZ: {new_uz[:120]}")
                print(f"  EN: {new_en[:120]}")

                success = update_organization(page, record, new_ru, new_uz, new_en)
                status = '✓' if success else '✗'
                if success:
                    processed += 1
                else:
                    errors += 1
                print(f"  {status} Сохранение")

            except Exception as e:
                errors += 1
                logger.error(f"[{i}/{total}] Ошибка для {record['name']}: {e}", exc_info=True)

        browser.close()

    print(f"\nГотово. Обработано: {processed}, Ошибок: {errors}")


if __name__ == "__main__":
    main()
