import sys
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Дублируем весь вывод в run_log.txt для мониторинга
import io
_log_file = open('run_log.txt', 'w', encoding='utf-8', buffering=1)

class _Tee(io.TextIOBase):
    def __init__(self, *streams):
        self._streams = streams
    def write(self, s):
        for st in self._streams:
            st.write(s)
            st.flush()
        return len(s)
    def flush(self):
        for st in self._streams:
            st.flush()

sys.stdout = _Tee(sys.__stdout__, _log_file)
sys.stderr = _Tee(sys.__stderr__, _log_file)

from auth import login
from scraper import scrape_organizations, get_official_names
from rewriter import init_openai, rewrite, translate, extract_facts, detect_subject, force_official_name
from updater import update_organization, read_descriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # через Tee → в run_log.txt тоже
    ]
)
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = "checkpoint.txt"


def _load_checkpoint() -> set:
    """Загружает ID уже обработанных записей."""
    try:
        with open(CHECKPOINT_FILE, encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def _save_checkpoint(record_id) -> None:
    """Добавляет ID в checkpoint после успешной обработки."""
    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{record_id}\n")


def _is_valid_text(text: str) -> bool:
    """Проверяет что текст не пустой после постобработки."""
    if not text or not text.strip():
        return False
    inner = re.sub(r'<[^>]+>', '', text).strip()
    return len(inner) > 20


def main():
    load_dotenv()
    processed = 0
    errors = 0
    skipped = 0

    done_ids = _load_checkpoint()
    if done_ids:
        print(f"Checkpoint: пропускаем {len(done_ids)} уже обработанных записей")

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

        processed_new = 0
        for i, record in enumerate(records, 1):
            record_key = str(record.get("id") or record["edit_url"])

            # Пропускаем уже обработанные
            if record_key in done_ids:
                skipped += 1
                print(f"[{i}/{total}] Пропуск (уже обработан): {record['name']}")
                continue


            try:
                print(f"\n[{i}/{total}] {record['name']}")

                text_ru, text_uz, text_en, company_name = read_descriptions(page, record["edit_url"])

                # Получаем официальные названия с goldenpages.uz
                official = get_official_names(record.get("id"), page)
                print(f"  Official RU: {official.get('ru', '-')}")
                print(f"  Official UZ: {official.get('uz', '-')}")
                print(f"  Official EN: {official.get('en', '-')}")

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

                # UZ и EN — параллельно
                if text_ru and text_ru.strip():
                    # Извлекаем факты из RU для качественной нативной генерации UZ/EN
                    ru_facts = extract_facts(client, new_ru)

                    def _do_uz():
                        raw = translate(
                            client, new_ru, 'uz',
                            has_quotes=has_quotes,
                            official_name=official.get('uz', ''),
                            official_subject=subject_uz if subject_uz != 'AUTO' else '',
                            facts=ru_facts
                        )
                        return force_official_name(raw, official.get('uz', ''), lang='uz')

                    def _do_en():
                        raw = translate(
                            client, new_ru, 'en',
                            has_quotes=has_quotes,
                            official_name=official.get('en', ''),
                            official_subject=subject_en if subject_en != 'AUTO' else '',
                            facts=ru_facts
                        )
                        return force_official_name(raw, official.get('en', ''), lang='en')

                    with ThreadPoolExecutor(max_workers=2) as ex:
                        fut_uz = ex.submit(_do_uz)
                        fut_en = ex.submit(_do_en)
                        new_uz = fut_uz.result()
                        new_en = fut_en.result()
                else:
                    new_uz = text_uz
                    new_en = text_en

                print(f"  RU: {new_ru}")
                print(f"  UZ: {new_uz}")
                print(f"  EN: {new_en}")

                # Проверяем что тексты не пустые после постобработки
                if not _is_valid_text(new_ru):
                    print(f"  ⚠ Пропуск: RU текст пустой после обработки")
                    errors += 1
                    continue
                if not _is_valid_text(new_uz):
                    print(f"  ⚠ UZ текст пустой после обработки, оставляем оригинал")
                    new_uz = text_uz
                if not _is_valid_text(new_en):
                    print(f"  ⚠ EN текст пустой после обработки, оставляем оригинал")
                    new_en = text_en

                success = update_organization(page, record, new_ru, new_uz, new_en)
                if success:
                    processed += 1
                    processed_new += 1
                    _save_checkpoint(record_key)
                    print(f"  ✓ Сохранено")
                else:
                    errors += 1
                    print(f"  ✗ Ошибка сохранения")

            except Exception as e:
                errors += 1
                logger.error(f"[{i}/{total}] Ошибка для {record['name']}: {e}", exc_info=True)

        browser.close()

    print(f"\nГотово. Обработано: {processed}, Пропущено: {skipped}, Ошибок: {errors}")


if __name__ == "__main__":
    main()
