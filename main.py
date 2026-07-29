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
from rewriter import (
    init_openai, rewrite, translate, detect_subject, force_official_name,
    _is_service_company, _strip_uz_city, RU_FORM_ABBRS,
    _normalize_official_latin_desc, _UZ_FORM_ABBRS,
)
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

                # Чистим мусор в RU тексте: "Ооо, ташкент", "Зао, город" и т.п.
                import re as _re
                if text_ru:
                    _ru_cities = r'(?:ташкент\w*|самарканд\w*|бухар\w*|фергана\w*|андижан\w*|наманган\w*|карши|нукус\w*|ургенч\w*|навои\w*|термез\w*|джизак\w*|сырдарь\w*)'
                    _ru_forms  = r'(?:ооо|зао|оао|чп|ип|уп|гп|ао|сп|тм|мчж|мчп|пк|нпо|нии)'
                    # "Ооо, ташкент NAME" → "NAME"
                    text_ru = _re.sub(
                        r'^(<p>)\s*' + _ru_forms + r'\s*,\s*' + _ru_cities + r'\s+',
                        r'\1', text_ru, flags=_re.IGNORECASE
                    )
                    # "Ооо, NAME" → "NAME"
                    text_ru = _re.sub(
                        r'^(<p>)\s*' + _ru_forms + r'\s*,\s*',
                        r'\1', text_ru, flags=_re.IGNORECASE
                    )
                    # "Компания офис в г.ташкенте NAME" / "офис в г. NAME" → "NAME"
                    text_ru = _re.sub(
                        r'^(<p>)\s*(?:компания\s+)?(?:\w+\s+)?(?:в\s+г\.?\s*)' + _ru_cities + r'\s*',
                        r'\1', text_ru, flags=_re.IGNORECASE
                    )
                    # Любой мусор до открывающей кавычки если содержит город
                    text_ru = _re.sub(
                        r'^(<p>)[^«"""]*' + _ru_cities + r'[^«"""]*(?=[«"""])',
                        r'\1', text_ru, flags=_re.IGNORECASE
                    )

                # Получаем официальные названия с goldenpages.uz
                official = get_official_names(record.get("id"), page)
                # Локализуем латинский дескриптор-тип (HOTEL/RESTAURANT/…) в RU/UZ названиях
                official = {k: _normalize_official_latin_desc(v, k) for k, v in official.items()}
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

                    # Ведущий ALL-CAPS дескриптор перед кавычкой → sentence case
                    # "РЕКЛАМНОЕ АГЕНТСТВО \"SIYMO\"" → "Рекламное агентство \"SIYMO\""
                    # Аббревиатуры (ООО, ИП, СП…) остаются капсом; название в кавычках не трогаем.
                    # Базовый ручной набор + все RU-аббревиатуры форм из реестра (ПТП, ЧТФ, ЧСП…),
                    # чтобы форма не приводилась к «Птп»/«Чтф» при sentence-case дескриптора.
                    _RU_ABBR = ({'ООО', 'ЗАО', 'ОАО', 'ЧП', 'ИП', 'УП', 'ГП', 'АО', 'СП', 'ТМ',
                                 'МЧЖ', 'МЧП', 'ПК', 'НПО', 'НИИ', 'СПП', 'СЭЗ', 'ДП', 'ФХ',
                                 'КФХ', 'ЧФ', 'СПК', 'ТЧСЖ', 'ГУП', 'МУП',
                                 # формы-инициализмы с гласными (правило «без гласных» их не ловит)
                                 'УПП', 'УПК', 'УПО', 'СМУ', 'ПМК', 'ТЭЦ', 'ГЭС', 'АЗС', 'СТО'}
                                | set(RU_FORM_ABBRS))

                    # Стемы стран-«связок» для двунациональных компаундов СП/ИП
                    # ("узбекско-британское", "узбекско-южнокорейское"). Пишем обе части
                    # с прописной. НЕ трогаем обычные компаунды (торгово-промышленное и т.п.).
                    _ru_country_stems = {
                        'узбекско', 'российско', 'казахско', 'киргизско', 'таджикско',
                        'туркменско', 'американо', 'англо', 'франко', 'германо', 'итало',
                        'индо', 'китайско', 'корейско', 'японско', 'турецко', 'иранско',
                        'украинско', 'белорусско', 'азербайджанско', 'грузинско',
                        'афгано', 'пакистано', 'арабо', 'испано',
                    }

                    # Инициализм-форма: в русском нет слов без гласных, поэтому ALL-CAPS токен
                    # из одних согласных (НТЦ, ПТП, КБ, СМР, НПП…) — гарантированно аббревиатура.
                    # Это ловит формы, которых нет в реестре, и не даёт их приводить к «Нтц».
                    _RU_VOWELS = set('АЕЁИОУЫЭЮЯ')

                    def _is_ru_abbr(w):
                        wu = w.upper()
                        if wu in _RU_ABBR:
                            return True
                        return bool(_re.fullmatch(r'[А-ЯЁ]{2,6}', wu)) and not (set(wu) & _RU_VOWELS)

                    def _ru_desc_sentence(_m):
                        words = _m.group(1).split()
                        out = []
                        first_full = False
                        for w in words:
                            if _is_ru_abbr(w):
                                out.append(w.upper())
                            else:
                                lw = w.lower()
                                is_country = '-' in lw and lw.split('-')[0] in _ru_country_stems
                                if not first_full:
                                    lw = lw[0].upper() + lw[1:]
                                    first_full = True
                                if is_country:
                                    lw = '-'.join(
                                        p[:1].upper() + p[1:] if p else p
                                        for p in lw.split('-')
                                    )
                                out.append(lw)
                        return '<p>' + ' '.join(out) + ' '

                    new_ru = _re.sub(
                        r'<p>((?:[А-ЯЁ][А-ЯЁ0-9\'’-]*\s+)+)(?=[«"“„])',
                        _ru_desc_sentence, new_ru
                    )
                    # Название БЕЗ кавычек: ведущий длинный (3+) ALL-CAPS дескриптор → sentence case.
                    # "БУХАРСКОЕ УПП ОБЩЕСТВА СЛЕПЫХ ООО занимается" → "Бухарское УПП общества слепых ООО..."
                    if not has_quotes:
                        new_ru = _re.sub(
                            r'<p>\s*((?:[А-ЯЁ][А-ЯЁ0-9\'’-]*\s+){3,})',
                            _ru_desc_sentence, new_ru
                        )
                else:
                    new_ru = text_ru

                # Сервисная компания (услуги/HoReCa/связь)? Влияет на лексику товары↔услуги.
                _is_service = _is_service_company(new_ru, company_name)

                # UZ и EN — параллельно
                if text_ru and text_ru.strip():
                    def _do_uz():
                        raw = translate(
                            client, new_ru, 'uz',
                            has_quotes=has_quotes,
                            official_name=official.get('uz', ''),
                            official_subject=subject_uz if subject_uz != 'AUTO' else ''
                        )
                        result = force_official_name(raw, official.get('uz', ''), lang='uz')
                        # Галлюцинация слова из названия: слово внутри кавычек (CENTER/GROUP/…)
                        # переведено и вставлено ЛИШНИМ заглавным токеном снаружи
                        # ('"SARBON TOUR CENTER" mehmonxonasi Markaz ...'). Название целиком в
                        # кавычках, поэтому перевод его слов снаружи — артефакт, убираем.
                        _qm = _re.match(r'<p>\s*"([^"]*)"', result)
                        if _qm:
                            _qn = _qm.group(1).upper()
                            for _eng, _uz in (('CENTER|CENTRE', 'Markazi?'),
                                              ('GROUP', 'Guruhi?|Grupp'),
                                              ('COMPANY', 'Kompaniyasi?'),
                                              ('SERVICE', 'Servisi?'),
                                              ('TOUR', 'Turi?')):
                                if _re.search(r'\b(?:' + _eng + r')\b', _qn):
                                    result = _re.sub(
                                        r'\s+(?:' + _uz + r")\b(?=\s+[a-z'])",
                                        '', result, count=1
                                    )
                        # B2B-термин: временное проживание в отеле — istiqomat qilish,
                        # а не бытовое yashash («постоянное жительство»).
                        if 'mehmonxona' in result.lower():
                            result = _re.sub(r'\byashash\b', 'istiqomat qilish', result, flags=_re.IGNORECASE)
                        # Дескриптор из goldenpages (sanatoriyasi) — приоритетный; идущее следом
                        # избыточное "sanatoriy-kurort" (перевод «санаторно-курортного») убираем.
                        # '"NAME" sanatoriyasi sanatoriy-kurort davolash' → '"NAME" sanatoriyasi davolash'.
                        result = _re.sub(
                            r'\b(sanatoriyasi|sanatoriysi|kurorti|pansionati)\s+sanatoriy[-\s]kurort\b',
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        result = _re.sub(r'\bxorijiy\s+korxonasi\b', 'XK', result, flags=_re.IGNORECASE)
                        # Длинные формы РАНЬШЕ коротких чтобы не было частичных замен
                        result = _re.sub(r'\bixtisoslashgan\s+sanoat\s+korxonasi\b', 'ISK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bxususiy\s+savdo\s+firmasi\b', 'XSF', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bsavdo\s+firmasi\b', 'SF', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bqo[\'ʻʼ]shma\s+korxonasi\b', 'QK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bqo[\'ʻʼ]shma\s+korxona\b', 'QK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bdavlat\s+unitar\s+korxonasi\b', 'DUK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bdavlat\s+korxonasi\b', 'DK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bkommunal\s+korxona\b', 'KK', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bunitar\s+korxona\b', 'UK', result, flags=_re.IGNORECASE)
                        # UZ порядок: форма ПОСЛЕ имени — MChJ "NAME" / QK MChJ "NAME" → "NAME" MChJ / "NAME" QK MChJ
                        _uz_abbr_atom = r'(?:MChJ|MCHJ|XK|AJ|YTT|QK|OAJ|YoAJ|ATB|DUK|DK|UK|SK|IK|KK|ICHK|ISK|XSIK|KTXF|EIZ|SF|TF|XSF|XSICHK|ICHSK)'
                        result = _re.sub(
                            r'<p>(' + _uz_abbr_atom + r'(?:\s+' + _uz_abbr_atom + r')?)\s+([«"""][^«"""»]*[»"""])',
                            lambda m: f'<p>{m.group(2)} {m.group(1)}',
                            result
                        )
                        # Дедупликация: "NAME" MChJ MChJ → "NAME" MChJ
                        _uz_abbr_inner = r'(?:MChJ|MCHJ|XK|AJ|YTT|QK|OAJ|YoAJ|ATB|DUK|DK|UK|SK|IK|KK|ICHK|ISK|XSIK|KTXF|EIZ|SF|TF|XSF|XSICHK|ICHSK)'
                        result = _re.sub(
                            r'([«"""][^«"""»]*[»"""])\s+(' + _uz_abbr_inner + r')(\s+\2)+',
                            r'\1 \2',
                            result, flags=_re.IGNORECASE
                        )
                        # Одинаковая форма подряд ГДЕ УГОДНО (не только после кавычки):
                        # "XK MChJ MChJ" → "XK MChJ" (дубль формы из офиц. названия + из перевода).
                        result = _re.sub(
                            r'(?<![\w])(' + _uz_abbr_inner + r')(?:\s+\1)+(?![\w])',
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        # Общий дедуп подряд идущих ОДИНАКОВЫХ слов: "reklama reklama" → "reklama".
                        # В B2B-описаниях соседние идентичные слова — всегда артефакт генерации.
                        result = _re.sub(
                            r"(?<![\w'ʼʻ’‘-])([\w'ʼʻ’‘]{2,})(?:\s+\1)+(?![\w'ʼʻ’‘-])",
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        # Дубль ЦЕЛОГО многословного блока подряд (2-7 слов): "A B C D A B C D" → "A B C D".
                        # Длинные названия без кавычек: "... ISHLAB CHIQARISH KORXONASI MChJ ×2".
                        for _ in range(2):
                            result = _re.sub(
                                r"(?<![\w'ʼʻ’‘-])((?:[\w'ʼʻ’‘]+)(?:\s+[\w'ʼʻ’‘]+){1,6})\s+\1(?![\w'ʼʻ’‘-])",
                                r'\1', result, flags=_re.IGNORECASE
                            )
                        # Название БЕЗ кавычек: ведущий длинный (3+) ALL-CAPS дескриптор → sentence case.
                        # "BUXORO KO'ZI OJIZLAR ... KORXONASI MChJ uy..." → "Buxoro ko'zi ojizlar ... korxonasi MChJ uy..."
                        # Формы-аббревиатуры (XK, ISK…) сохраняем капсом; страны/O'zbekiston капитализируются ниже.
                        if not has_quotes:
                            def _lc_uz_run(m):
                                ws = m.group(1).split()
                                out = [w if w.upper() in _UZ_FORM_ABBRS else w.lower() for w in ws]
                                s = ' '.join(out)
                                return '<p>' + (s[:1].upper() + s[1:]) + ' '
                            result = _re.sub(
                                r"<p>\s*((?:[A-Z][A-Z'ʼʻ’‘]*\s+){3,})", _lc_uz_run, result
                            )
                        # Дедупликация первого слова дескриптора: "X tsexi X..." / "X korxona X..." → "X DESCRIPTOR ..."
                        # Слово-класс включает апострофы (o'/g'), иначе "sog'lomlashtirish markazi
                        # sog'lomlashtirish" не ловится (\w обрывается на апострофе).
                        _uzw = r"[\w'ʼʻ’‘]+"
                        _desc_nouns = r"(?:tse?xi|korxona|markazi|fabrikasi|zavodi|kompaniyasi|do['ʼʻ’‘]koni|xizmati|shourumi?)"
                        result = _re.sub(
                            r"(?<![\w'ʼʻ’‘])(" + _uzw + r")\s+(" + _desc_nouns + r")\s+\1(?![\w'ʼʻ’‘])",
                            r'\1 \2', result, flags=_re.IGNORECASE
                        )
                        # Дедупликация самого дескриптора: "shourum shourum" / "do'koni do'koni" → одно слово
                        result = _re.sub(
                            r"\b(shourumi?|fabrikasi|zavodi|markazi|korxona|tse?xi|do[''ʻʼ]koni)\s+\1\b",
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        # Заикание дескриптора с РАЗНЫМИ окончаниями (один корень подряд):
                        # "sanatoriyasi sanatoriyi sanatoriyasi" → "sanatoriyasi".
                        # ВАЖНО: повтор — только ЦЕЛОЕ слово; часть дефисного компаунда
                        # (sanatoriy-kurort) НЕ считается повтором (иначе выходит "sanatoriyasi-kurort").
                        _uz_stem = (r"(?:sanatoriy|mehmonxona|xostel|kasalxona|poliklinika|shifoxona|"
                                    r"pansionat|klinika|restoran|kafe|zavod|fabrika|korxona|markaz|"
                                    r"agentli|do['ʼʻ’‘]kon|bo['ʼʻ’‘]lim)")
                        _wt = r"[\w'ʼʻ’‘]*"
                        _wb = r"(?![\w'ʼʻ’‘-])"   # конец слова, не дефисный компаунд
                        result = _re.sub(
                            r"(?<![\w'ʼʻ’‘-])(" + _uz_stem + r")(" + _wt + r")" + _wb
                            + r"((?:\s+\1" + _wt + _wb + r")+)",
                            r'\1\2',
                            result, flags=_re.IGNORECASE
                        )
                        # Русские кальки → узбекские термины
                        result = _re.sub(r'\bsanatorno-kurort\b', 'sanatoriy-kurort', result, flags=_re.IGNORECASE)
                        result = _re.sub(r'\bsanator-kurort\b', 'sanatoriy-kurort', result, flags=_re.IGNORECASE)
                        # Дефисные дескрипторы: "do'kon-salon Salon" / "salon-do'kon Do'kon" → убираем дубль
                        result = _re.sub(
                            r"\b(do[''ʻʼ]kon-salon|salon-do[''ʻʼ]kon)\s+(?:salon|do[''ʻʼ]kon)\b",
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        result = _re.sub(
                            r"\b(restoran-do[''ʻʼ]kon|do[''ʻʼ]kon-restoran)\s+(?:restoran|do[''ʻʼ]kon)\b",
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        # Дедупликация длинных дескрипторов
                        _long_descs = [
                            r"ishlab chiqarish kooperativi",
                            r"restoran[ia]-?do[''ʻʼ]kon[ia]?",
                            r"o[''ʻʼ]z-o[''ʻʼ]zini ish bilan band qilgan shaxs",
                            r"rasmiy vakil",
                            r"maishiy kimyoviy mahsulotlar",
                        ]
                        for _ld in _long_descs:
                            result = _re.sub(r'(' + _ld + r')\s+' + _ld, r'\1', result, flags=_re.IGNORECASE)
                        # rasmiy vakil rasmiy vakili → rasmiy vakili
                        result = _re.sub(r'\brasmiy vakil\s+rasmiy vakili\b', 'rasmiy vakili', result, flags=_re.IGNORECASE)
                        # Дедупликация номеров: №6 №6 → №6
                        result = _re.sub(r'(№\s*\d+)\s+\1', r'\1', result)
                        # Удаляем адресные галлюцинации: улицы, города, районы
                        result = _re.sub(
                            r'\b(?:\w+\s+){0,3}ko[''ʻʼ]chas(?:ida|i)\b[^<]{0,80}',
                            '', result, flags=_re.IGNORECASE
                        )
                        # shahrida/shahri — городские указатели
                        result = _re.sub(r',?\s+\w+\s+shahrida\b[^<]{0,60}', '', result, flags=_re.IGNORECASE)
                        result = _re.sub(r',?\s+\w+\s+shahri\b[^<]{0,30}', '', result, flags=_re.IGNORECASE)
                        result = _re.sub(
                            r'\bin\s+(?:toshkent|samarqand|buxoro|farg[''ʻʼ]ona|andijon|namangan|qarshi|nukus|urganch|navoiy|termiz)\b[^<]*?(?=[,.]|ishlab|sotadi|taqdim)',
                            '', result, flags=_re.IGNORECASE
                        )
                        # Удаляем "viloyatida/viloyati" конструкции (Toshkent viloyatida amalga oshiriladi и т.п.)
                        result = _re.sub(
                            r'[^.]*\b(?:toshkent|samarqand|buxoro|farg[''ʻʼ]ona|andijon|namangan)\s+viloyat(?:ida|i|ga|dan)?\b[^.]*\.',
                            '', result, flags=_re.IGNORECASE
                        )
                        # Капитализация собственных имён: o'zbekiston respublikasi → O'zbekiston Respublikasi
                        result = _re.sub(r"\bo'zbekiston\b", "O'zbekiston", result)
                        result = _re.sub(r'\brespublikasi\b', 'Respublikasi', result)
                        result = _re.sub(r'\brespublika\b', 'Respublika', result)
                        # Капитализация стран-собственных имён (в т.ч. партнёр в СП "O'zbekiston-Rossiya QK")
                        _uz_countries = ['rossiya', 'xitoy', 'turkiya', 'koreya', 'amerika',
                                         'germaniya', 'eron', "qozog'iston", 'ukraina', 'belarus',
                                         'hindiston', 'yaponiya', 'fransiya', 'italiya', 'ispaniya',
                                         "afg'oniston", "qirg'iziston", 'tojikiston', 'turkmaniston',
                                         'ozarbayjon', 'gruziya']
                        for _country in _uz_countries:
                            result = _re.sub(
                                r'\b' + _country + r'\b',
                                _country[0].upper() + _country[1:],
                                result, flags=_re.IGNORECASE
                            )
                        # Капитализация города перед filiali (город — часть юр.имени филиала)
                        _cities_uz = ['Toshkent', 'Samarqand', 'Buxoro', "Farg'ona", 'Andijon',
                                      'Namangan', 'Qarshi', 'Nukus', 'Urganch', 'Navoiy', 'Termiz',
                                      'Jizzax', 'Sirdaryo', 'Surxondaryo', 'Xorazm']
                        for _city in _cities_uz:
                            result = _re.sub(
                                r'\b' + _city.lower() + r'\s+(filiali)\b',
                                _city + r' \1', result
                            )
                        # Заикание дескриптора филиала: "filiali filiali" → "filiali"
                        result = _re.sub(
                            r"\b(filiali|filial|bo['ʻʼ]limi)\s+\1\b",
                            r'\1', result, flags=_re.IGNORECASE
                        )
                        # B2B-термин: физ./частные клиенты → jismoniy (xususiy = буквализм)
                        result = _re.sub(
                            r'\bxususiy\s+(mijoz\w*|shaxs\w*|iste[\'ʻʼ]?molchi\w*)',
                            r'jismoniy \1', result, flags=_re.IGNORECASE
                        )
                        # Гео-шум: остаточный город в локативе ("... Navoiyda ...")
                        result = _strip_uz_city(result)
                        # Сервисная лексика: товары → услуги ("Mahsulotlar ..." → "Xizmatlar ...")
                        if _is_service:
                            result = _re.sub(
                                r'\bMahsulot(?:lar)?(?:ning)?\s+(assortiment\w*|qator\w*|tur\w*|tarkib\w*)',
                                r'Xizmatlar \1', result, flags=_re.IGNORECASE
                            )
                        return result

                    def _do_en():
                        raw = translate(
                            client, new_ru, 'en',
                            has_quotes=has_quotes,
                            official_name=official.get('en', ''),
                            official_subject=subject_en if subject_en != 'AUTO' else ''
                        )
                        result = force_official_name(raw, official.get('en', ''), lang='en')
                        # Юр.форма затесалась ВНУТРЬ кавычек названия:
                        # "ASKLEPIY FOREIGN ENTERPRISE LTD" → "ASKLEPIY" (форма не часть имени)
                        _en_form_in_quotes = (
                            r'(?:FOREIGN ENTERPRISE|PRIVATE ENTERPRISE|JOINT VENTURE|'
                            r'FAMILY ENTERPRISE|STATE ENTERPRISE|STATE UNITARY ENTERPRISE|'
                            r'MUNICIPAL UNITARY ENTERPRISE|UNITARY ENTERPRISE|INDUSTRIAL ENTERPRISE|'
                            r'PRIVATE TRADING FIRM|TRADING FIRM|TRADING COMPANY|LLC|LTD|CO|JSC|CJSC|OJSC|JV|ALC|'
                            r'PE|FE|ME|SUE|MUE|UE|SE|IE|PTF)'
                        )
                        result = _re.sub(
                            r'"([^"]+?)(?:\s+' + _en_form_in_quotes + r')+"',
                            r'"\1"', result, flags=_re.IGNORECASE
                        )
                        # Ложные друзья: Domestic chemistry → Household chemicals
                        result = _re.sub(r'\bDomestic\s+[Cc]hemistry\b', 'Household chemicals', result)
                        result = _re.sub(r'\bForeign\s+[Ee]nterprise\b', 'FE', result)
                        result = _re.sub(r'\bState\s+[Uu]nitary\s+[Ee]nterprise\b', 'SUE', result)
                        result = _re.sub(r'\bMunicipal\s+[Uu]nitary\s+[Ee]nterprise\b', 'MUE', result)
                        result = _re.sub(r'\bUnitary\s+[Ee]nterprise\b', 'UE', result)
                        result = _re.sub(r'\bState\s+[Ee]nterprise\b', 'SE', result)
                        result = _re.sub(r'\bIndustrial\s+[Ee]nterprise\b', 'IE', result)
                        result = _re.sub(r'\bPrivate\s+[Ee]nterprise\b', 'PE', result)
                        result = _re.sub(r'\bPrivate\s+[Tt]rading\s+[Ff]irm\b', 'PTF', result)
                        result = _re.sub(r'\bTrading\s+[Ff]irm\b', 'TF', result)
                        result = _re.sub(r'\bTrading\s+[Cc]ompany\b', 'TF', result)
                        result = _re.sub(r'(?<!is )(?<!\w)engaged in', 'is engaged in', result)
                        # "Company "NAME"" → "The company "NAME""
                        result = _re.sub(r'<p>(Company|Enterprise|Store|Plant|Factory)\s+"', lambda m: f'<p>The {m.group(1).lower()} "', result)
                        # Заголовочная форма-дескриптор в начале → name-first "The "NAME" descriptor"
                        # BRANCH "NAME" → The "NAME" branch; HOTEL "NAME" → The "NAME" hotel
                        _en_namefirst_desc = {'branch': 'branch', 'filial': 'branch',
                                              'filiali': 'branch', 'hotel': 'hotel'}
                        result = _re.sub(
                            r'<p>\s*(BRANCH|Branch|Filial|Filiali|HOTEL|Hotel)\s+("[^"]+")',
                            lambda m: f'<p>The {m.group(2)} {_en_namefirst_desc[m.group(1).lower()]}',
                            result
                        )
                        # Двусловные дескрипторы-объекты на center/centre (wellness/medical/health center)
                        # WELLNESS CENTER "NAME" → The "NAME" wellness center
                        result = _re.sub(
                            r'<p>\s*(?:The\s+)?((?:[A-Za-z]+\s+){0,2}(?:CENTER|CENTRE|Center|Centre))\s+("[^"]+")',
                            lambda m: f'<p>The {m.group(2)} {m.group(1).lower()}',
                            result
                        )
                        # B2B-термин: частные/физ. клиенты → individual (не private = буквализм)
                        result = _re.sub(
                            r'\bprivate\s+(client|customer|individual|person)s?\b',
                            lambda m: 'individual ' + m.group(1) + 's',
                            result, flags=_re.IGNORECASE
                        )
                        # Сервисная лексика: product line/range → range of services
                        if _is_service:
                            result = _re.sub(
                                r'\bThe\s+product\s+(?:line|range)\b',
                                'The range of services', result, flags=_re.IGNORECASE
                            )
                            result = _re.sub(
                                r'\bproduct\s+(?:line|range)\b',
                                'range of services', result, flags=_re.IGNORECASE
                            )
                        # Удаляем адресный шум: "within/in the Tashkent region" и т.п.
                        result = _re.sub(
                            r'[^.]*\b(?:within|in)\s+(?:the\s+)?(?:Tashkent|Samarkand|Bukhara|Fergana|Andijan|Namangan)\s+(?:region|oblast|province|area|viloyati?)\b[^.]*\.',
                            '', result, flags=_re.IGNORECASE
                        )
                        # Проверка языка: если EN содержит узбекские слова — вернуть пустой текст (триггер регенерации)
                        _uz_markers = r'\b(?:ishlab|sotadi|yetkazib|hamda|shuningdek|korxona|kompaniyasi|taqdim|etadi|qiladi|beradi)\b'
                        if _re.search(_uz_markers, result, _re.IGNORECASE):
                            result = ''
                        return result

                    with ThreadPoolExecutor(max_workers=2) as ex:
                        fut_uz = ex.submit(_do_uz)
                        fut_en = ex.submit(_do_en)
                        new_uz = fut_uz.result()
                        new_en = fut_en.result()
                    # Если EN пустой (языковая мутация) — повторяем
                    if not _is_valid_text(new_en):
                        print(f"  ⚠ EN языковая мутация, повтор...")
                        new_en = _do_en()
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
