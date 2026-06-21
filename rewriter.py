import os
import re
import time
import logging
from typing import Optional, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─── Определение формы компании (Python, точно) ──────────────────────────────

# Все известные формы → (ru, uz, en)
_FORM_MAP = {
    'ООО':  ('ООО',  'MCHJ', 'LTD'),
    'ОАО':  ('ОАО',  'OAJ',  'OJSC'),
    'ЗАО':  ('ЗАО',  'YoAJ', 'CJSC'),
    'АКБ':  ('АКБ',  'ATB',  'JSB'),
    'АИКБ': ('АИКБ', 'ATIB', 'JISB'),
    'АТБ':  ('АТБ',  'ATB',  'JSB'),
    'ИП':   ('ИП',   'YT',   'IE'),
    'ЧП':   ('ЧП',   'XK',   'PE'),
    'ЧПФ':  ('ЧПФ',  'XKF',  'PE'),
    'МЧП':  ('МЧП',  'MCHX', 'SPE'),
    'ГП':   ('ГП',   'DK',   'SE'),
    'ДФХ':  ('ДФХ',  'DXK',  'PFE'),
    'ТМ':   ('ТМ',   'SB',   'TM'),
    'АО':   ('АО',   'AJ',   'JSC'),
    'УП':   ('УП',   'KK',   'UE'),
    'ГУП':  ('ГУП',  'DUK',  'SUE'),
    'САВДО БЕЛГИСИ': ('ТМ',  'SB', 'TM'),
    'MCHJ': ('ООО',  'MCHJ', 'LTD'),
    'OAJ':  ('ОАО',  'OAJ',  'OJSC'),
    'YoAJ': ('ЗАО',  'YoAJ', 'CJSC'),
    'YT':   ('ИП',   'YT',   'IE'),
    'XK':   ('ЗАО',  'XK',   'PE'),
    'AJ':   ('АО',   'AJ',   'JSC'),
    'KK':   ('УП',   'KK',   'UE'),
    'DUK':  ('ГУП',  'DUK',  'SUE'),
    'LLC':  ('ООО',  'MCHJ', 'LTD'),
    'OJSC': ('ОАО',  'OAJ',  'OJSC'),
    'CJSC': ('ЗАО',  'YoAJ', 'CJSC'),
    'JSC':  ('АО',   'AJ',   'JSC'),
    'НПФ':  ('НПФ',  'IIF',   'SRPF'),
    'НПО':  ('НПО',  'IICHB', 'SPA'),
    'НИИ':  ('НИИ',  'ITI',   'RI'),
    'СП':   ('СП',   'QK',    'JV'),
    'ОДО':  ('ОДО',  'QMJ',   'ALC'),
    'ПК':   ('ПК',   'IK',    'PC'),
    'ХП':   ('ХП',   'XK',    'PE'),
    'ХТ':   ('ХТ',   'XSH',   'BP'),
    'ПТ':   ('ПТ',   'TUSH',  'GP'),
    'КТ':   ('КТ',   'KUSH',  'LP'),
    'НКО':  ('НКО',  'NTT',   'NCO'),
    'ОО':   ('ОО',   'JT',    'PA'),
    'ДП':   ('ДП',   'DK',    'SE'),
    'ИФ':   ('ИФ',   'IF',    'IF'),
    'ФП':   ('ФП',   'FK',    'BF'),
    'ДХ':   ('ДХ',   'DX',    'FH'),
    # ── Составные формы (СП + ООО/ЗАО/АО) ───────────────────
    'СП ООО':  ('СП ООО',  'MChJ QK',  'LTD JV'),
    'ООО СП':  ('ООО СП',  'MChJ QK',  'LTD JV'),
    'СП ЗАО':  ('СП ЗАО',  'YoAJ QK',  'CJSC JV'),
    'ЗАО СП':  ('ЗАО СП',  'YoAJ QK',  'CJSC JV'),
    'СП АО':   ('СП АО',   'AJ QK',    'JSC JV'),
    'АО СП':   ('АО СП',   'AJ QK',    'JSC JV'),
    # ── Составные формы с ИП/ЧП ──────────────────────────────
    'ООО ИП':  ('ООО ИП',  'MCHJ YT',  'LTD IE'),
    'ИП ООО':  ('ИП ООО',  'YT MCHJ',  'IE LTD'),
    'ЧП ООО':  ('ЧП ООО',  'XK MCHJ',  'PE LTD'),
    'ООО ЧП':  ('ООО ЧП',  'MCHJ XK',  'LTD PE'),
    'ИП ЧП':   ('ИП ЧП',   'YT XK',    'IE PE'),
    'ЧП ИП':   ('ЧП ИП',   'XK YT',    'PE IE'),
    # ── Банки (новые) ────────────────────────────────────────
    'ОАКБ':  ('ОАКБ',  'OATB',   'OJSB'),
    'ЗАКБ':  ('ЗАКБ',  'YoATB',  'CJSB'),
    'ЧКБ':   ('ЧКБ',   'XTB',    'PCB'),
    # ── Товарищества ─────────────────────────────────────────
    'ТОО':   ('ТОО',   'CHJTSh', 'LLP'),
    # ── Унитарные (новые) ────────────────────────────────────
    'МУП':   ('МУП',   'MUK',    'MUE'),
    'КП':    ('КП',    'KK',     'CE'),
    # ── Частные предприятия (новые) ──────────────────────────
    'ИЧП':   ('ИЧП',   'YXK',    'IPE'),
    'СЧП':   ('СЧП',   'OXK',    'FPE'),
    'ЧФ':    ('ЧФ',    'XF',     'PF'),
    'ЧФП':   ('ЧФП',   'XFK',    'PPF'),
    'ЧКФ':   ('ЧКФ',   'XKF',    'PKF'),
    'ЧСП':   ('ЧСП',   'XQK',    'PCE'),
    'ПБОЮЛ': ('ПБОЮЛ', 'YTSh',   'SP'),
    'СПД':   ('СПД',   'TSF',    'JBE'),
    # ── Иностранные ──────────────────────────────────────────
    'ИПП':   ('ИПП',   'CHIK',   'FIE'),
    'ПИИ':   ('ПИИ',   'XSIK',   'FIE'),
    # ── Государственные (новые) ──────────────────────────────
    'ГК':    ('ГК',    'DK',     'SCorp'),
    # ── Кооперативы (новые) ──────────────────────────────────
    'СПК':   ('СПК',   'QXK',    'APC'),
    'ПотК':  ('ПотК',  'IK',     'CC'),
    # ── Сельское хозяйство ───────────────────────────────────
    'ФХ':                        ('Фермерское хозяйство',           "Fermerlik xo'jaligi", 'Farm'),
    'ФЕРМЕРСКОЕ ХОЗЯЙСТВО':      ('Фермерское хозяйство',           "Fermerlik xo'jaligi", 'Farm'),
    "FERMERLIK XO'JALIGI":       ('Фермерское хозяйство',           "Fermerlik xo'jaligi", 'Farm'),
    "FERMER XO'JALIGI":          ('Фермерское хозяйство',           "Fermer xo'jaligi",    'Farm'),
    'КФХ':                       ('Крестьянское фермерское хозяйство', "Dehqon fermer xo'jaligi", 'Peasant farm'),
    'КРЕСТЬЯНСКОЕ ФЕРМЕРСКОЕ ХОЗЯЙСТВО': ('Крестьянское фермерское хозяйство', "Dehqon fermer xo'jaligi", 'Peasant farm'),
    # ── Некоммерческие (новые) ───────────────────────────────
    'НИЦ':   ('НИЦ',   'ITM',    'RC'),
    'РЦ':    ('РЦ',    'RM',     'RC'),
    'ФОНД':  ('Фонд',  'Fond',   'Foundation'),
    'АНО':   ('АНО',   'AYoT',   'ANO'),
    # ── Латинские (новые) ────────────────────────────────────
    'XF':    ('ЧФ',    'XF',     'PF'),
    'PF':    ('ЧФ',    'XF',     'PF'),
    'IE':   ('ИП',   'YT',   'IE'),
    'DK':   ('ГП',   'DK',   'SE'),
    'SE':   ('ГП',   'DK',   'SE'),
    'PE':   ('ЧП',   'XK',   'PE'),
    'SUE':  ('ГУП',  'DUK',  'SUE'),
    # ── Новые формы ──────────────────────────────────────────
    'ПКП':  ('ПКП',  'PKK',  'CCP'),
    'МП':   ('МП',   'MK',   'ME'),
    'КПП':  ('КПП',  'QXK',  'CME'),
    'ПП':   ('ПП',   'IK',   'PE'),
    'ТЗБ':  ('ТЗБ',  'TZB',  'CTB'),
    'МЧФ':  ('МЧФ',  'KTXF', 'MPE'),
    'СЭЗ':  ('СЭЗ',  'EIZ',  'FEZ'),
    'EIZ':  ('СЭЗ',  'EIZ',  'FEZ'),
    'FEZ':  ('СЭЗ',  'EIZ',  'FEZ'),
    'ТК':   ('ТК',   'TK',   'TC'),
    'ИндП': ('ИндП', 'YT',   'IE'),
    'ИНДП': ('ИндП', 'YT',   'IE'),
    'YAKKA TARTIBDAGI TADBIRKOR': ('ИндП', 'Yakka tartibdagi tadbirkor', 'IE'),
    'YAKKA TADBIRKOR':             ('ИндП', 'Yakka tadbirkor',            'IE'),
    'СЕМП': ('Семейное предприятие', 'Oilaviy korxona', 'Family enterprise'),
    'СЕМ':  ('Семейное предприятие', 'Oilaviy korxona', 'Family enterprise'),
    'СЕМЕЙНОЕ ПРЕДПРИЯТИЕ':         ('Семейное предприятие',     'Oilaviy korxona',            'Family enterprise'),
    'СЕМЕЙНОЕ ЧП':                  ('Семейное ЧП',              'Oilaviy XK',                 'Family PE'),
    'ТОВАРНО-ЗАГОТОВИТЕЛЬНАЯ БАЗА': ('Товарно-заготовительная база', 'Tovar-tayyorlov bazasi',  'Commercial storage base'),
    'ЧПКФ':  ('ЧПКФ',  'XICHTF', 'PRIVATE INDUSTRIAL COMMERCIAL FIRM'),
    'ХИЧТФ': ('ЧПКФ',  'XICHTF', 'PRIVATE INDUSTRIAL COMMERCIAL FIRM'),
    'XICHTF': ('ЧПКФ', 'XICHTF', 'PRIVATE INDUSTRIAL COMMERCIAL FIRM'),
}

_LANG_IDX = {'ru': 0, 'uz': 1, 'en': 2}

# Набор однословных UZ-форм из _FORM_MAP для нормализации порядка в официальных названиях
_UZ_FORM_ABBRS = frozenset(
    v[1].upper() for v in _FORM_MAP.values()
    if v[1] and ' ' not in v[1] and re.match(r'^[A-Za-z]', v[1])
)

# Многословные UZ-формы (ключи _FORM_MAP) — для распознавания в официальных названиях
_UZ_MULTI_FORM_KEYS = frozenset(
    k.upper() for k in _FORM_MAP
    if re.match(r'^[A-Za-z]', k) and ' ' in k
)

# UZ описательные многословные формы (fermerlik xo'jaligi, oilaviy korxona и т.п.)
# идут ПОСЛЕ имени: "NAME" fermerlik xo'jaligi  (НЕ перед именем как аббревиатуры)
_UZ_DESC_FORMS = sorted(
    {v[1] for v in _FORM_MAP.values() if v[1] and ' ' in v[1] and re.search(r'[a-z]', v[1])},
    key=len, reverse=True
)
# Будет дополнено после определения _DESCRIPTORS (см. ниже)

# Частые дескрипторы → (ru, uz, en). Длинные варианты идут перед короткими.
_DESCRIPTORS = {
    # ── многословные (длинные вперёд) ──────────────────────────────────────────
    'санаторно курортный':    ('Санаторно-курортный комплекс', 'Sanatoriy-kurort majmuasi', 'Resort complex'),
    'фермерское хозяйство':   ('Фермерское хозяйство',   "Fermer xo'jaligi",       'Farm'),
    'дехканское хозяйство':   ('Дехканское хозяйство',   "Dehqon xo'jaligi",       'Peasant farm'),
    'медицинский колледж':    ('Медицинский колледж',    'Tibbiyot kolleji',       'Medical college'),
    'технический колледж':    ('Технический колледж',    'Texnika kolleji',        'Technical college'),
    'астигматический центр':  ('Астигматический центр',  'Astigmatik markaz',      'Astigmatic center'),
    'сахарный завод':         ('Сахарный завод',         "Qand zavodi",            'Sugar plant'),
    'кирпичный завод':        ('Кирпичный завод',        "G'isht zavodi",          'Brick plant'),
    'цементный завод':        ('Цементный завод',        "Sement zavodi",          'Cement plant'),
    'теннисный клуб':         ('Теннисный клуб',         'Tennis klubi',           'Tennis club'),
    'языковой центр':         ('Языковой центр',         'Til markazi',            'Language center'),
    'тренинг центр':          ('Тренинг-центр',          'Trening markazi',        'Training center'),
    'торговая марка':         ('Торговая марка',         'Savdo belgisi',          'Trademark'),
    'центр обучения':         ('Учебный центр',          "O'quv markaz",           'Training center'),
    'гольф клуб':             ('Гольф-клуб',             'Golf klubi',             'Golf club'),
    'яхт клуб':               ('Яхт-клуб',               'Yaxt klubi',             'Yacht club'),
    'дом отдыха':             ('Дом отдыха',             "Dam olish uyi",          'Rest house'),
    'ветеринарная клиника':   ('Ветеринарная клиника',   'Veterinariya klinikasi', 'Veterinary clinic'),
    'страховая компания':     ('Страховая компания',     "Sug'urta kompaniyasi",   'Insurance company'),
    'медицинский центр':      ('Медицинский центр',      'Tibbiy markaz',          'Medical center'),
    'учебный центр':          ('Учебный центр',          "O'quv markaz",           'Training center'),
    'сервисный центр':        ('Сервисный центр',        'Servis markazi',         'Service center'),
    'бизнес центр':           ('Бизнес-центр',           'Biznes markaz',          'Business center'),
    'торговый центр':         ('Торговый центр',         'Savdo markazi',          'Shopping center'),
    'торговый дом':           ('Торговый дом',           'Savdo uyi',              'Trading house'),
    'частный нотариус':       ('Частный нотариус',       'Xususiy notarius',       'Private notary'),
    'адвокатская фирма':      ('Адвокатская фирма',      'Advokatlik firmasi',     'Law firm'),
    'курьерская служба':      ('Курьерская служба',      'Kuryerlik xizmati',      'Courier service'),
    'детский сад':            ('Детский сад',            "Bog'cha",                'Kindergarten'),
    'головной офис':          ('Головной офис',          'Bosh ofis',              'Head office'),
    # ── однословные русские ────────────────────────────────────────────────────
    'астигматический':        ('Астигматический центр',  'Astigmatik markaz',      'Astigmatic center'),
    'турагентство':           ('Турагентство',           'Turistik agentlik',      'Travel agency'),
    'автосервис':             ('Автосервис',             'Avtoservis',             'Auto service'),
    'автомойка':              ('Автомойка',              'Avtoyuvish',             'Car wash'),
    'типография':             ('Типография',             'Bosmaxona',              'Print house'),
    'издательство':           ('Издательство',           'Nashriyot',              'Publishing house'),
    'поликлиника':            ('Поликлиника',            'Poliklinika',            'Polyclinic'),
    'кондитерская':           ('Кондитерская',           'Qandolatxona',           'Confectionery'),
    'химчистка':              ('Химчистка',              'Kimyoviy tozalash',      'Dry cleaner'),
    'консалтинг':             ('Консалтинговая компания','Konsalting kompaniyasi', 'Consulting company'),
    'логистика':              ('Логистическая компания', 'Logistika kompaniyasi',  'Logistics company'),
    'супермаркет':            ('Супермаркет',            'Supermarket',            'Supermarket'),
    'представительство':      ('Представительство',      'Vakolatxona',            'Representative office'),
    'университет':            ('Университет',            'Universitet',            'University'),
    'лаборатория':            ('Лаборатория',            'Laboratoriya',           'Laboratory'),
    'стоматология':           ('Стоматология',           'Stomatologiya',          'Dental clinic'),
    'санаторий':              ('Санаторий',              'Sanatoriy',              'Sanatorium'),
    'мастерская':             ('Мастерская',             'Ustaxona',               'Workshop'),
    'прачечная':              ('Прачечная',              'Kir yuvish',             'Laundry'),
    'библиотека':             ('Библиотека',             'Kutubxona',              'Library'),
    'кооператив':             ('Кооператив',             'Kooperativ',             'Cooperative'),
    'ассоциация':             ('Ассоциация',             'Assotsiatsiya',          'Association'),
    'ассоциации':             ('Ассоциация',             'Assotsiatsiya',          'Association'),
    'агрохолдинг':            ('Агрохолдинг',            'Agroxolding',            'Agro holding'),
    'агрокомпания':           ('Агрокомпания',           'Agrokompaniya',          'Agro company'),
    'агрофирма':              ('Агрофирма',              'Agrofirma',              'Agrofirm'),
    'птицефабрика':           ('Птицефабрика',           'Parranda fabrikasi',     'Poultry farm'),
    'комбинат':               ('Комбинат',               'Kombinat',               'Industrial complex'),
    'пекарня':                ('Пекарня',                'Novvoyxona',             'Bakery'),
    'ресторан':               ('Ресторан',               'Restoran',               'Restaurant'),
    'агентство':              ('Агентство',              'Agentlik',               'Agency'),
    'гостиница':              ('Гостиница',              'Mehmonxona',             'Hotel'),
    'галерея':                ('Галерея',                'Galereya',               'Gallery'),
    'больница':               ('Больница',               'Kasalxona',              'Hospital'),
    'ярмарка':                ('Ярмарка',                'Yarmarka',               'Fair'),
    'столовая':               ('Столовая',               'Oshxona',                'Canteen'),
    'институт':               ('Институт',               'Institut',               'Institute'),
    'заправка':               ('АЗС',                    'Yoqilgi stansiyasi',     'Gas station'),
    'спортзал':               ('Спортзал',               'Sport zal',              'Gym'),
    'бассейн':                ('Бассейн',                'Basseyn',                'Swimming pool'),
    'клиника':                ('Клиника',                'Klinika',                'Clinic'),
    'ломбард':                ('Ломбард',                'Lombard',                'Pawnshop'),
    'фитнес':                 ('Фитнес-клуб',            'Fitnes klub',            'Fitness club'),
    'аптека':                 ('Аптека',                 'Dorixona',               'Pharmacy'),
    'магазин':                ('Магазин',                "Do'kon",                 'Store'),
    'фабрика':                ('Фабрика',                'Fabrika',                'Factory'),
    'студия':                 ('Студия',                 'Studiya',                'Studio'),
    'нотариус':               ('Нотариус',               'Notarius',               'Notary'),
    'театр':                  ('Театр',                  'Teatr',                  'Theater'),
    'музей':                  ('Музей',                  'Muzey',                  'Museum'),
    'школа':                  ('Школа',                  'Maktab',                 'School'),
    'базар':                  ('Базар',                  'Bozor',                  'Market'),
    'рынок':                  ('Рынок',                  'Bozor',                  'Market'),
    'такси':                  ('Такси',                  'Taksi',                  'Taxi'),
    'ателье':                 ('Ателье',                 'Atele',                  'Atelier'),
    'склад':                  ('Склад',                  'Ombor',                  'Warehouse'),
    'завод':                  ('Завод',                  'Zavod',                  'Plant'),
    'салон':                  ('Салон',                  'Salon',                  'Salon'),
    'центр':                  ('Центр',                  'Markaz',                 'Center'),
    'хостел':                 ('Хостел',                 'Xotel',                  'Hostel'),
    'отель':                  ('Отель',                  'Mehmonxona',             'Hotel'),
    'фирма':                  ('Фирма',                  'Firma',                  'Firm'),
    'бюро':                   ('Бюро',                   'Byuro',                  'Bureau'),
    'клуб':                   ('Клуб',                   'Klub',                   'Club'),
    'офис':                   ('Офис',                   'Ofis',                   'Office'),
    'банк':                   ('Банк',                   'Bank',                   'Bank'),
    'фонд':                   ('Фонд',                   'Fond',                   'Foundation'),
    'кафе':                   ('Кафе',                   'Kafe',                   'Cafe'),
    'бар':                    ('Бар',                    'Bar',                    'Bar'),
    # ── дополнительные русские ─────────────────────────────────────────────────
    'развлекательный центр':  ('Развлекательный центр',  "Ko'ngilochar markaz",    'Entertainment center'),
    'нотариальная контора':   ('Нотариальная контора',   'Notarial idora',         'Notary office'),
    'строительная компания':  ('Строительная компания',  'Qurilish kompaniyasi',   'Construction company'),
    'мебельный салон':        ('Мебельный салон',        'Mebel saloni',           'Furniture salon'),
    'детский клуб':           ('Детский клуб',           'Bolalar klubi',          "Children's club"),
    'спортивный магазин':     ('Спортивный магазин',     "Sport do'koni",          'Sports store'),
    'ногтевая студия':        ('Ногтевая студия',        'Nail studiyasi',         'Nail studio'),
    'обменный пункт':         ('Обменный пункт',         'Valyuta almashtirish',   'Currency exchange'),
    'детское питание':        ('Магазин детского питания',"Bolalar oziq-ovqat do'koni",'Baby food store'),
    'микрофинансовая':        ('Микрофинансовая организация','Mikromoliya tashkiloti','Microfinance organization'),
    'агентство недвижимости': ('Агентство недвижимости', "Ko'chmas mulk agentligi",'Real estate agency'),
    'строительство':          ('Строительная компания',  'Qurilish kompaniyasi',   'Construction company'),
    'недвижимость':           ('Агентство недвижимости', "Ko'chmas mulk agentligi",'Real estate agency'),
    'парикмахерская':         ('Парикмахерская',         'Sartaroshxona',          'Barbershop'),
    'фотостудия':             ('Фотостудия',             'Fotostudiya',            'Photo studio'),
    'автосалон':              ('Автосалон',              'Avto salon',             'Car dealership'),
    'пиццерия':               ('Пиццерия',               'Pitseriya',              'Pizzeria'),
    'аквапарк':               ('Аквапарк',               'Akvapark',               'Water park'),
    'барбершоп':              ('Барбершоп',              'Barbershop',             'Barbershop'),
    'бильярд':                ('Бильярдный клуб',        'Bilyard klubi',          'Billiard club'),
    'кинотеатр':              ('Кинотеатр',              'Kinoteatr',              'Cinema'),
    'боулинг':                ('Боулинг',                'Bouling',                'Bowling'),
    'зоомагазин':             ('Зоомагазин',             'Zoomagizin',             'Pet store'),
    'шиномонтаж':             ('Шиномонтаж',             'Shinomontaj',            'Tire service'),
    'хлебопекарня':           ('Хлебопекарня',           'Non zavodi',             'Bakery'),
    'кондитерия':             ('Кондитерская',           'Qandolatxona',           'Confectionery'),
    'шаурма':                 ('Шаурмичная',             'Shaurma',                'Shawarma place'),
    'фастфуд':                ('Фастфуд',                'Tezkor ovqat',           'Fast food'),
    'риелтор':                ('Риелторское агентство',  'Rieltorlik agentligi',   'Real estate agency'),
    'клининг':                ('Клининговая компания',   'Klinink kompaniyasi',    'Cleaning company'),
    'паркинг':                ('Паркинг',                'Parkovka',               'Parking'),
    'стоянка':                ('Стоянка',                'Parkovka',               'Parking'),
    'кулинария':              ('Кулинария',              'Oshxona',                'Deli'),
    'барбекю':                ('Гриль-бар',              'Grill bar',              'Grill bar'),
    'гриль':                  ('Гриль-бар',              'Grill bar',              'Grill bar'),
    'охрана':                 ('Охранное агентство',     "Qo'riqlash agentligi",   'Security agency'),
    'оптика':                 ('Оптика',                 'Optika',                 'Optical store'),
    'массаж':                 ('Массажный кабинет',      'Massaj xonasi',          'Massage center'),
    'квест':                  ('Квест-комната',          'Kvest xona',             'Quest room'),
    'дизайн':                 ('Дизайн-студия',          'Dizayn studiyasi',       'Design studio'),
    'интернет':               ('Интернет-провайдер',     'Internet provayder',     'Internet provider'),
    'мебель':                 ('Мебельный магазин',      "Mebel do'koni",          'Furniture store'),
    'электроника':            ('Магазин электроники',    "Elektronika do'koni",    'Electronics store'),
    'техника':                ('Магазин техники',        "Texnika do'koni",        'Electronics store'),
    'цветочный':              ('Цветочный магазин',      "Gul do'koni",            'Flower shop'),
    'книжный':                ('Книжный магазин',        "Kitob do'koni",          'Bookstore'),
    'ювелирный':              ('Ювелирный магазин',      "Zargarlik do'koni",      'Jewelry store'),
    'спа':                    ('СПА-салон',              'Spa salon',              'Spa salon'),
    'пицца':                  ('Пиццерия',               'Pitseriya',              'Pizzeria'),
    'суши':                   ('Суши-бар',               'Sushi bar',              'Sushi bar'),
    'букет':                  ('Цветочный магазин',      "Gul do'koni",            'Flower shop'),
    'it':                     ('IT-компания',            'IT kompaniya',           'IT company'),
    'мясокомбинат':           ('Мясокомбинат',           "Go'sht kombinati",       'Meat processing plant'),
    'молокозавод':            ('Молокозавод',            "Sut zavodi",             'Dairy plant'),
    'хлебозавод':             ('Хлебозавод',             'Non zavodi',             'Bakery plant'),
    'пивоварня':              ('Пивоварня',              "Pivo zavodi",            'Brewery'),
    'винзавод':               ('Винзавод',               "Vino zavodi",            'Winery'),
    'элеватор':               ('Элеватор',               'Elevator',               'Grain elevator'),
    'мельница':               ('Мельница',               'Tegirmon',               'Mill'),
    'прокат':                 ('Прокатная компания',     'Ijara kompaniyasi',      'Rental company'),
    'колледж':                ('Колледж',                'Kollej',                 'College'),
    'академия':               ('Академия',               'Akademiya',              'Academy'),
    'хокимият':               ('Хокимият',               'Hokimlik',               'Hokimiyat'),
    'министерство':           ('Министерство',           'Vazirlik',               'Ministry'),
    'комитет':                ('Комитет',                "Qo'mita",               'Committee'),
    'управление':             ('Управление',             "Boshqarma",              'Department'),
    'союз':                   ('Союз',                   'Ittifoq',                'Union'),
    'федерация':              ('Федерация',              'Federatsiya',            'Federation'),
    'комплекс':               ('Комплекс',               'Majmua',                 'Complex'),
    # ── английские ─────────────────────────────────────────────────────────────
    'travel':                 ('Туристическое агентство','Turistik agentlik',      'Travel agency'),
    'tours':                  ('Туристическое агентство','Turistik agentlik',      'Travel agency'),
    'restaurant':             ('Ресторан',               'Restoran',               'Restaurant'),
    'pharmacy':               ('Аптека',                 'Dorixona',               'Pharmacy'),
    'hostel':                 ('Хостел',                 'Xotel',                  'Hostel'),
    'clinic':                 ('Клиника',                'Klinika',                'Clinic'),
    'agency':                 ('Агентство',              'Agentlik',               'Agency'),
    'studio':                 ('Студия',                 'Studiya',                'Studio'),
    'center':                 ('Центр',                  'Markaz',                 'Center'),
    'market':                 ('Рынок',                  'Bozor',                  'Market'),
    'hotel':                  ('Отель',                  'Mehmonxona',             'Hotel'),
    'store':                  ('Магазин',                "Do'kon",                 'Store'),
    'salon':                  ('Салон',                  'Salon',                  'Salon'),
    'service':                ('Сервис',                 'Servis',                 'Service'),
    'shop':                   ('Магазин',                "Do'kon",                 'Shop'),
    'cafe':                   ('Кафе',                   'Kafe',                   'Cafe'),
    'bank':                   ('Банк',                   'Bank',                   'Bank'),
    # ── общие слова (для случаев типа "NAVRUZ" КОМПАНИЯ) ──────────────────────
    'компания':               ('Компания',               'Kompaniya',              'Company'),
    'предприятие':            ('Предприятие',            'Korxona',                'Enterprise'),
    'организация':            ('Организация',            'Tashkilot',              'Organization'),
}

# Сортируем по длине ключа (длинные раньше: "торговый центр" до "центр")
_DESCRIPTORS_SORTED = sorted(_DESCRIPTORS.keys(), key=len, reverse=True)

# Расширяем _UZ_DESC_FORMS многословными UZ-значениями из _DESCRIPTORS
_UZ_DESC_FORMS = sorted(
    set(_UZ_DESC_FORMS)
    | {v[1] for v in _DESCRIPTORS.values() if v[1] and ' ' in v[1] and re.search(r'[a-z]', v[1])},
    key=len, reverse=True
)

# RU/EN метки (формы + дескрипторы) для нормализации '"NAME" МЕТКА' → 'МЕТКА "NAME"'
_RU_ALL_LABELS_SORTED = sorted(
    {v[0] for v in _FORM_MAP.values() if v[0] and re.match(r'^[А-ЯЁа-яё]', v[0])}
    | {v[0] for v in _DESCRIPTORS.values() if v[0] and re.match(r'^[А-ЯЁа-яё]', v[0])},
    key=len, reverse=True
)
_EN_ALL_LABELS_SORTED = sorted(
    {v[2] for v in _FORM_MAP.values() if v[2] and re.match(r'^[A-Za-z]', v[2])}
    | {v[2] for v in _DESCRIPTORS.values() if v[2] and re.match(r'^[A-Za-z]', v[2])},
    key=len, reverse=True
)


# Однословные аббревиатуры форм (остаются ALL CAPS при нормализации)
_RU_FORM_ABBRS = frozenset(
    v[0] for v in _FORM_MAP.values()
    if v[0] and v[0] == v[0].upper() and re.match(r'^[А-ЯЁ]', v[0]) and ' ' not in v[0]
)
_EN_FORM_ABBRS = frozenset(
    v[2] for v in _FORM_MAP.values()
    if v[2] and v[2] == v[2].upper() and re.match(r'^[A-Z]', v[2]) and ' ' not in v[2]
)


# Собственные имена — всегда с заглавной при нормализации регистра
_PROPER_NOUNS = frozenset({
    'Uzbekistan', 'Republic', 'Karakalpakstan',
    'Узбекистан', 'Узбекистана', 'Узбекистане',
    'Республика', 'Республики', 'Республике',
    'Каракалпакстан',
})


def _normalize_descriptor_case(label: str, lang: str) -> str:
    """Нормализует регистр дескриптора: КОНДИТЕРСКИЙ ДОМ → Кондитерский дом.
    Аббревиатуры форм (ООО, LTD, JV и т.п.) остаются заглавными.
    Собственные имена (Uzbekistan, Республики и т.п.) остаются с заглавной."""
    if not label or label == label.lower():
        return label
    abbrs = _RU_FORM_ABBRS if lang == 'ru' else _EN_FORM_ABBRS
    abbrs_upper = {a.upper() for a in abbrs}
    words = label.split()
    result = []
    for i, w in enumerate(words):
        w_up = w.upper()
        if w_up in abbrs_upper:
            result.append(next((a for a in abbrs if a.upper() == w_up), w))
        elif w.capitalize() in _PROPER_NOUNS or w.title() in _PROPER_NOUNS:
            result.append(w.capitalize())
        else:
            result.append(w[0].upper() + w[1:].lower() if i == 0 else w.lower())
    return ' '.join(result)


def _tokenize(name: str) -> set:
    return set(re.split(r'[\s"«»()\[\]/]+', name.upper()))


_BRANCH_PATTERN = re.compile(
    r'\s+(?:[А-ЯЁA-Z][а-яёa-z]+(?:ский|ской|ный|ной|ский|зский|тский|вский)\s+)?'
    r'(?:ФИЛИАЛ|FILIALI|BRANCH|FILIAL)\b.*',
    re.IGNORECASE,
)


def _extract_clean(company_name: str, pattern: str) -> str:
    """Убирает pattern из имени и возвращает очищённую строку.
    Если в остатке есть кавычки — берёт только первое содержимое кавычек.
    Дополнительно удаляет ФИЛИАЛ/BRANCH и географические прилагательные перед ними."""
    remainder = re.sub(pattern, '', company_name, flags=re.IGNORECASE).strip()
    m = re.search(r'[«""](.+?)[»""]', remainder)
    if m:
        return m.group(1).strip()
    # Нет кавычек — убираем ФИЛИАЛ и прилагательное перед ним
    remainder = _BRANCH_PATTERN.sub('', remainder).strip()
    return remainder.strip('"«»').strip() or company_name


def _detect_unknown_form(company_name: str) -> Optional[Tuple[str, str, bool]]:
    """Определяет неизвестную форму если она стоит рядом с кавычками.

    "NAME" FORM  или  FORM "NAME"  где FORM — 2-6 заглавных букв не из _FORM_MAP.
    """
    has_quotes = bool(re.search(r'[«»"""]', company_name))
    if not has_quotes:
        return None

    # Паттерн: "NAME" FORM — форма после закрывающей кавычки
    m = re.search(r'[»"""]\s+([А-ЯЁA-Z]{2,6})\s*$', company_name)
    if m:
        form = m.group(1)
        name_m = re.search(r'[«"""]([^«"""»]+)[»"""]', company_name)
        clean = name_m.group(1).strip() if name_m else company_name
        return form, clean, has_quotes

    # Паттерн: FORM "NAME" — форма перед открывающей кавычкой
    m = re.match(r'^([А-ЯЁA-Z]{2,6})\s+[«"""]', company_name)
    if m:
        form = m.group(1)
        name_m = re.search(r'[«"""]([^«"""»]+)[»"""]', company_name)
        clean = name_m.group(1).strip() if name_m else company_name
        return form, clean, has_quotes

    return None


def detect_subject(company_name: str, lang: str) -> Tuple[str, str, bool]:
    """
    Возвращает (subject, clean_name, has_quotes).
    Приоритет: 1) юридическая форма  2) дескриптор  3) AUTO.
    clean_name — название без формы/дескриптора (содержимое кавычек, если есть).
    has_quotes — есть ли кавычки в исходном названии.
    """
    has_quotes = bool(re.search(r'[«»"""]', company_name))
    idx = _LANG_IDX.get(lang, 0)

    # 0. Многословные формы (подстрока, длинные раньше)
    multi_keys = sorted(
        [k for k in _FORM_MAP if ' ' in k or (len(k) > 3 and '-' in k)],
        key=len, reverse=True
    )
    for form_key in multi_keys:
        if re.search(r'(?<![А-Яа-яA-Za-z])' + re.escape(form_key) + r'(?![А-Яа-яA-Za-z])',
                     company_name, re.IGNORECASE):
            subject = _FORM_MAP[form_key][idx]
            clean = _extract_clean(company_name, re.escape(form_key))
            return subject, clean, has_quotes

    # 1. Юридическая форма (точное совпадение токена)
    tokens = _tokenize(company_name)
    for form_key in sorted(_FORM_MAP.keys(), key=len, reverse=True):
        if form_key.upper() in tokens:
            subject = _FORM_MAP[form_key][idx]
            clean = _extract_clean(company_name, r'\b' + re.escape(form_key) + r'\b')
            return subject, clean, has_quotes

    # 2. Дескриптор (подстрока, без учёта регистра, длинные раньше)
    for desc_key in _DESCRIPTORS_SORTED:
        pattern = r'(?<![А-Яа-яA-Za-z])' + re.escape(desc_key) + r'(?![А-Яа-яA-Za-z])'
        if re.search(pattern, company_name, flags=re.IGNORECASE):
            subject = _DESCRIPTORS[desc_key][idx]
            clean = _extract_clean(company_name, pattern)
            return subject, clean, has_quotes

    # 3. Эвристика: неизвестная форма рядом с кавычками (ТПП, ПКП, ЧФ и т.п.)
    unknown = _detect_unknown_form(company_name)
    if unknown:
        form, clean, hq = unknown
        return form, clean, hq

    # Если в названии есть кавычки — берём их содержимое
    # При двух кавычках ("ТЕРМЕЗ" "IMZO") — берём ПОСЛЕДНЕЕ (основной бренд)
    all_quoted = re.findall(r'[«"""]([^«"""»]+)[»"""]', company_name)
    if len(all_quoted) >= 2:
        clean = all_quoted[-1].strip()
    elif all_quoted:
        clean = all_quoted[0].strip()
    else:
        clean = company_name.strip('«»"""\'"').strip()
    return 'AUTO', clean, has_quotes


def _uz_possessive(word: str) -> str:
    """Добавляет узбекский посессивный суффикс -i/-si к однословному дескриптору."""
    w = word.strip().lower()
    if not w:
        return w
    if w[-1] in 'aeiou':
        return w + 'si'
    return w + 'i'


# Автогенерация маппинга из _DESCRIPTORS: русский дескриптор → узбекский с суффиксом
_RU_TO_UZ_DESC: dict[str, str] = {}
for _dk, (_dru, _duz, _den) in _DESCRIPTORS.items():
    if re.match(r'[а-яА-Я]', _dk):           # только русские ключи
        _ru_key = _dru.lower()
        _uz_val = _duz.lower()
        # Однословные — добавляем посессивный суффикс; многословные — уже содержат его
        if ' ' not in _uz_val:
            _uz_val = _uz_possessive(_uz_val)
        _RU_TO_UZ_DESC[_ru_key] = _uz_val

# Базовые слова, которых нет в _DESCRIPTORS
_RU_TO_UZ_DESC.setdefault('компания',                 'kompaniyasi')
_RU_TO_UZ_DESC.setdefault('организация',              'tashkiloti')
_RU_TO_UZ_DESC.setdefault('предприятие',              'korxonasi')
_RU_TO_UZ_DESC.setdefault('туристическое агентство',  'turistik agentlik')
_RU_TO_UZ_DESC.setdefault('логистическая компания',   'logistika kompaniyasi')
_RU_TO_UZ_DESC.setdefault('консалтинговая компания',  'konsalting kompaniyasi')

# Однословные UZ дескрипторы в посессивной форме — используются для стрипинга дублей
_UZ_DESCRIPTOR_WORDS = frozenset({
    'kafesi', 'restorani', 'stomatologiyasi', 'markazi', 'klinikasi',
    'advokatlik', 'firmasi', 'banki', 'xoteli', 'dorixonasi',
    'maktabi', 'instituti', 'universiteti', 'zavodi', 'studiyasi',
    'agentligi', 'notariusi', 'vakolatxonasi', 'laboratoriyasi',
    'supermarketi', 'saloni', 'ofisi', 'fondi', 'klubi',
    'tashkiloti', 'korxonasi', 'kompaniyasi', 'agrofirmasi',
    'kombinati', 'fabrikasi', 'bazasi', 'majmuasi', 'xizmati',
    'savdosi', 'parrandasi', 'bosmaxonasi', 'nashriyoti',
    # магазин: ASCII apostrophe и Unicode-варианты
    "do'koni", "do'koni", "doʻkoni", "doʼkoni",
    # прочие пропущенные
    'mehmonxonasi', 'oshxonasi', 'novvoyxonasi', 'ustaxonasi',
    'kasalxonasi', 'poliklinikasi', 'shifoxonasi', 'sartaroshxonasi',
    'avtoservisi', 'omborxonasi', 'qandolatxonasi', 'pitseriyasi',
    'kinoteatri', 'muzeyi', 'teatri', 'lombardi', 'bozori',
    # составные компоненты (не дают попасть под pop)
    'filiali', 'filial', 'bosh', 'ofisi',
    # дополнительные дескрипторы
    'kooperativi', 'shirkatining', 'shirkat', 'jamiyati',
    'xoldingi', 'tresti', 'birlashmasi', 'uyushmasi',
    # кондитерские и другие частые
    'qandolat', 'uyi', 'choyxonasi', 'shirinliklar',
    # дополнительные дескрипторы
    'galereyasi', 'parki', 'xonadoni', 'muassasasi',
    'kompleksi', 'klubi', 'markazi', 'shahobchasi',
    # фермерское хозяйство — все варианты написания первого слова
    "xo'jaligi", "xo'jaligi", "xojaligi",
})


# ─── Промпты ─────────────────────────────────────────────────────────────────

PROMPT_RU = """Ты редактор корпоративных описаний. Перепиши текст строго по правилам.

СУБЪЕКТ: {subject}
ОЧИЩЕННОЕ НАЗВАНИЕ: {clean_name}
ПОЛНОЕ НАЗВАНИЕ: {company_name}
ИСХОДНЫЙ ТЕКСТ: {text}

ПРАВИЛО НАЧАЛА ТЕКСТА:
Если {has_quotes} = False → КРИТИЧНО:
  Писать ТОЛЬКО: {company_name} занимается...
  ЗАПРЕЩЕНО: добавлять кавычки / писать "Организация", "Компания", "Предприятие" перед названием / переставлять слова

Если {has_quotes} = True и СУБЪЕКТ ≠ AUTO → начни точно так: {subject} "{clean_name}"

Если {has_quotes} = True и СУБЪЕКТ = AUTO → пиши слово по {alt_idx}, затем название В КАВЫЧКАХ:
  0 = Организация "{clean_name}"
  1 = Компания "{clean_name}"
  2 = Предприятие "{clean_name}"

ПРИМЕРЫ ПРАВИЛЬНЫХ НАЧАЛ:
✅ ООО "AMEKS TRAVEL" занимается организацией туров...          (subject=ООО, has_quotes=True)
✅ Компания "TANTANA" производит кондитерские изделия...        (subject=AUTO alt_idx=1, has_quotes=True)
✅ Кафе "ARIANA" специализируется на узбекской кухне...         (subject=Кафе, has_quotes=True)
✅ ФЕРГАНСКИЙ НЕФТЕПЕРЕРАБАТЫВАЮЩИЙ ЗАВОД осуществляет...       (has_quotes=False)
✅ ШАХРИСАБЗСКОЕ ГОРОДСКОЕ ПЭС обеспечивает электроснабжение... (has_quotes=False)

ПРИМЕРЫ НЕПРАВИЛЬНЫХ НАЧАЛ:
❌ "AMEKS TRAVEL" ООО занимается...          (форма ПЕРВОЙ, потом кавычки)
❌ Компания TANTANA производит...             (кавычки вокруг названия ОБЯЗАТЕЛЬНЫ)
❌ Завод "ФЕРГАНСКИЙ НЕФТЕПЕРЕРАБАТЫВАЮЩИЙ" осуществляет...  (нельзя переставлять слова в названии без кавычек)
❌ Организация "ФЕРГАНСКИЙ ЗАВОД"...          (название без кавычек — кавычки не добавлять)
❌ ЧП ПРЕДПРИЯТИЕ "ЭКОМАТРАС" занимается...  (ПРЕДПРИЯТИЕ — дубль формы ЧП, убирай)
✅ ЧП "ЭКОМАТРАС" занимается...              (форма только один раз)
❌ ООО ОБЩЕСТВО "NAME" производит...         (ОБЩЕСТВО — дубль формы ООО, убирай)
✅ ООО "NAME" производит...
❌ ООО "AMEKS TRAVEL" ООО занимается...       (форма только один раз)

ПРАВИЛА ТЕКСТА:
- 3-5 предложений, сохраняй объём исходного текста — не урезай
- Только факты: чем занимается, какие услуги, что производит — конкретные товары/услуги, без общих слов
- ⚠️ ИСПРАВЛЯЙ ЛОГИЧЕСКИЕ ОШИБКИ ОРИГИНАЛА: если в исходнике написано «ассортимент включает оптовую и розничную торговлю» — это ошибка (торговля — канал сбыта, не товар). Перепиши правильно: опиши ЧТО продаётся, а как (оптом/в розницу) упомяни отдельно. НЕ НАСЛЕДУЙ логические ошибки оригинала.
- ⚠️ НЕ ДОБАВЛЯЙ характеристики и свойства, которых нет в оригинале: нельзя превращать «нетканый материал» в «деликатный нетканый материал», «кабели» в «высококачественные кабели». Только то, что есть в источнике.
- ⚠️ КОНКРЕТИКА ЧЕРЕЗ ПЕРЕЧИСЛЕНИЕ: если в тексте есть материалы — называй их (МДФ, полипропилен, шерсть, ПВХ, алюминий). Если есть категории — называй их (мужские/женские/детские, оптом/в розницу, бытовые/промышленные). Если есть виды продукции — перечисляй через запятую или тире. НЕ заменяй конкретный список словом "различные" или "разнообразные".
- СТРУКТУРА: 1-е предложение = основной продукт/деятельность. 2-е предложение = конкретный ассортимент, материалы, типы. 3-е предложение (если нужно) = дополнительное направление или экспорт. Каждое предложение добавляет НОВУЮ информацию.
- ЗАПРЕЩЕНО рекламные слова и фразы: "широкий спектр", "высокое качество", "качественный/качественные/качественными", "комфортный", "динамично развивается", "является лидером", "квалифицированные специалисты", "что позволяет удовлетворить", "разнообразные", "различные", "уникальный", "особый", "индивидуальный подход", "эффективный/эффективно", "надёжный/надёжно", "профессиональный", "для улучшения", "на высоком уровне", "в сфере", "в области", "современный", "передовой", "инновационный", "оптимальный", "ориентируясь на потребности"
- ⚠️ СТРОГО ЗАПРЕЩЕНО — размытые фразы без конкретики: "производство осуществляется на собственных мощностях", "деятельность сосредоточена на", "представлена информация о", "информация о направлениях деятельности", "ориентированных на выпуск", "основное внимание уделяется", "предлагаются условия сотрудничества", "условия сотрудничества", "условия партнёрства", "компания уделяет особое внимание", "приоритетом является", "ставит своей целью", "осуществляет полный цикл изготовления", "как внутренние так и внешнеэкономические операции", "предоставляет возможности для клиентов", "используя стандартные технологии", "соответствующей современным стандартам", "мощности позволяют изготавливать", "производственные мощности предприятия позволяют", "товары народного потребления", "предоставляя клиентам необходимые", "взаимодействует с заводами", "для строительных нужд", "для промышленных нужд", "для различных нужд"
- ⚠️ ПРАВИЛО КОНКРЕТИКИ: каждое предложение должно называть КОНКРЕТНЫЙ товар, услугу или факт. ЗАПРЕЩЕНО: "рассматривает возможности экспорта", "изучает возможности расширения", "основные направления включают оптовую и розничную реализацию продукции", "выпускаются изделия, которые применяются в строительстве" — это пустышки без конкретики. Предложения типа "Деятельность включает внутренние и внешнеэкономические операции" — запрещены, потому что не говорят ЧТО именно производится или продаётся.
- ⚠️ СТРОГО ЗАПРЕЩЕНО географические предложения-пустышки: "деятельность охватывает [город/область/регион]", "деятельность компании охватывает", "деятельность предприятия охватывает", "реализуется на рынке Узбекистана", "на внутреннем рынке", "на отечественном рынке", "ориентировано на рынок", "в данных сегментах", "основное направление деятельности ориентировано". Такие предложения ничего не говорят о том ЧЕМ занимается компания — удаляй их полностью. ИСКЛЮЧЕНИЕ: "экспортирует на рынки СНГ/зарубежные рынки" — это факт, оставляй.
- ⚠️ СТРОГО ЗАПРЕЩЕНО: "производственные мощности расположены в [месте]", "производственные мощности находятся в [месте]", "производственные мощности размещены в [месте]" — это пустышки без содержания. Если хочешь упомянуть производство — пиши ЧТО там производят, а не где расположены мощности.
- ⚠️ ЗАПРЕЩЕНА ТАВТОЛОГИЯ: нельзя использовать однокоренные слова в соседних предложениях. Если в 1-м предложении «текстильная продукция» — во 2-м нельзя писать «текстильные изделия» или «текстильная промышленность». Меняй корень: ткань → полотно → материал → волокно.
- ⚠️ ЗАПРЕЩЕНО повторять одну и ту же информацию в разных предложениях. Если первое предложение говорит "производит автозапчасти" — не пиши "изготавливает компоненты для автомобильной отрасли" в следующем предложении.

ПРИМЕР (Было → Стало):
❌ «Компания производит текстильную продукцию. Ассортимент включает текстильные изделия. Предприятие работает в текстильной отрасли.»
✅ «ООО "ALFA" выпускает хлопчатобумажные и синтетические ткани. Ассортимент охватывает полотна для одежды, постельного белья и технических нужд.»
- ⚠️ СТРОГО ЗАПРЕЩЕНО упоминать сайт/сайты, официальный сайт, веб-сайт, веб-ресурс, онлайн-ресурс, интернет, соцсети, контакты, каталог товаров.
- ⚠️ ЗАПРЕЩЕНО: "что позволяет", "что обеспечивает", "ориентируясь на потребности клиентов", "ориентируясь на нужды клиентов", "удовлетворить потребности клиентов", "удовлетворяющие потребности", "широкий ассортимент", "с учётом специфических требований", "с учётом индивидуальных требований", "пользуются спросом среди потребителей", "в соответствии со стандартами качества", "ориентировано на рынок", "фокусируется на выполнении заказов", "развивается направление"
- ⚠️ СТРОГО ЗАПРЕЩЕНО упоминать города и регионы: Ташкент, Самарканд, Бухара, Фергана, Андижан, Наманган, Карши, Нукус, Термез, Джизак, Гулистан, Навои, Ургенч, Коканд, Маргилан, Нурафшон, а также любые сочетания "[Город]ская область", "[Город]ский район", "[Город]ский регион". ИСКЛЮЧЕНИЕ: только если компания работает по всей стране — тогда допустимо одно упоминание "на территории Узбекистана". НЕЛЬЗЯ упоминать локацию в каждом предложении — если уж упоминаешь географию, это должно быть один раз и только если это важный факт (например, единственный завод в регионе).
- ЗАПРЕЩЕНО: повторять одну информацию дважды
- ⚠️ ЗАПРЕЩЕНО ломать грамматику: нельзя писать "сосредоточено предлагая", "направлено осуществляя", "ориентировано производя" — деепричастие не может быть сказуемым при кратком прилагательном
- ЗАПРЕЩЕНО: местоимения — она, он, они, оно, её, его, их.
- ⚠️ РАЗНООБРАЗИЕ СТРУКТУРЫ — КРИТИЧНО. ЗАПРЕЩЕНО каждый раз использовать одну и ту же схему предложений.
  НЕ ИСПОЛЬЗОВАТЬ шаблон: "[Company] специализируется... Также выполняет... Дополнительно осуществляет..."
  Выбирай РАЗНЫЕ структуры из вариантов ниже:
  Вариант А: начни с конкретного продукта/услуги → потом рынки/объём → потом дополнительные направления
  Вариант Б: начни с главного направления → перечисли конкретные товары/услуги через тире или запятую → экспорт/рынки
  Вариант В: начни с производства → потом реализация → потом ассортимент конкретно
  Вариант Г: начни с рынка/клиентов → потом что производит/поставляет → потом масштаб
  Примеры разных начал: "Выпускает...", "Производит и реализует...", "Среди основных продуктов —", "К ключевым направлениям относятся...", "Поставляет на рынок...", "Изготавливает и экспортирует..."
- ⚠️ ЛЕКСИЧЕСКОЕ РАЗНООБРАЗИЕ: не повторяй одно и то же существительное или прилагательное в соседних предложениях — используй синонимы или перефразируй. Например, если в первом предложении "продукция", во втором используй "товары", "изделия", "ассортимент". Если в первом "производство", во втором — "выпуск", "изготовление". Текст должен читаться плавно и профессионально, без словесных повторов.
- ⚠️ ЧЕРЕДОВАНИЕ ГЛАГОЛОВ: каждое предложение — РАЗНЫЙ глагол. "занимается" — не более одного раза и ТОЛЬКО если нет лучшей замены.
  СЛОВАРЬ профессиональных глаголов для первого предложения (выбирай подходящий по смыслу):
  производство: выпускает / изготавливает / производит / осуществляет выпуск / наладил производство
  продажа/поставка: реализует / поставляет / осуществляет поставки / ведёт оптовую торговлю / экспортирует
  услуги: оказывает услуги по / выполняет / осуществляет / обслуживает / предоставляет
  специализация: специализируется на / сосредоточена на выпуске / профилируется на
  СЛОВАРЬ для последующих предложений:
  "Ассортимент включает / охватывает / представлен..." / "Номенклатура продукции насчитывает..."
  "Предприятие также выпускает / поставляет / экспортирует..."
  "В линейке продукции — [перечень через тире]"
  "Производственный цикл охватывает полный этап от ... до ..."
  "Продукция сертифицирована / соответствует ГОСТ / прошла сертификацию"
- ⚠️ ЗАПРЕЩЕНЫ фразы-заготовки: "различных отраслей", "различных видов", "различного объёма", "различные каналы", "для различных", "обеспечивая поставки", "обеспечивая широкий ассортимент", "реализация продукции через различные каналы", "производственные мощности позволяют", "дополнительно осуществляется реализация"
- РЕГИСТР: аббревиатуры форм (ООО, ИП, ЧП, АО, СП и т.п.) — ВСЕГДА заглавными. Дескрипторы (компания, предприятие, завод, кафе, магазин и т.п.) — с заглавной ТОЛЬКО в начале предложения, в середине — строчными. Примеры: ✅ "ООО «NAME» производит..." ✅ "Компания «NAME» выпускает..." ✅ "Предприятие также реализует..." ❌ "Предприятие также Реализует..." ❌ "ООО «NAME» занимается производством. Компания Также..."
- Сохрани теги <p> в начале и </p> в конце
- Если в названии есть слово ФИЛИАЛ/FILIALI/BRANCH — упоминай только если важно для сути деятельности

ПРИМЕРЫ ПРАВИЛЬНОГО РЕРАЙТА (образцы стиля и структуры):

Пример 1:
[Вход] <p>Компания осуществляет производство и продажу пряжи, трикотажного полотна и готовых трикотажных изделий на территории Узбекистана. Основные направления деятельности включают работу прядильных и текстильных фабрик, а также экспорт трикотажной продукции. Официальный сайт www.compacttextile.uz содержит подробную информацию о направлениях деятельности предприятия.</p>
[Выход] <p>ИП ООО "LUKBO TEXTILE" осуществляет производство и реализацию пряжи, трикотажного полотна и готовых изделий на территории Узбекистана. Предприятие управляет прядильными и текстильными фабриками, а также занимается экспортом собственной продукции.</p>

Пример 2:
[Вход] <p>Организация "АБДУРАХИМ А.Д." ИндП" занимается продажей и производством жалюзи, а также реализацией штор. В дополнение к этому, представлены товары для оформления окон. В магазинах и салонах можно ознакомиться с образцами продукции и готовыми решениями для интерьера.</p>
[Выход] <p>ИндП "АБДУРАХИМ А.Д." производит и реализует жалюзи, а также шторы и другие аксессуары для оформления окон. Предприятие предоставляет возможность ознакомиться с образцами продукции и готовыми интерьерными решениями в сети своих салонов.</p>

Пример 3:
[Вход] <p>Компания занимается производством и продажей велосипедов, детской мебели, игрушек, игр и ходунков в Ташкенте.</p><p>В ассортименте представлены детские кроватки и другая мебель для детей, изготовленная собственными силами.</p><p>Деятельность охватывает как розничную продажу, так и выпуск товаров.</p>
[Выход] <p>Предприятие "BROTHERS" занимается производством и реализацией велосипедов, детской мебели, игрушек, игр и ходунков. Компания осуществляет выпуск детских кроваток и иной мебели собственного производства, а также ведёт розничную торговлю этой продукцией.</p>

Пример 4:
[Вход] <p>Компания занимается продажей и производством электроинструментов, деревообрабатывающих и измерительных инструментов, а также сварочного оборудования и электродов. В ассортименте представлены лакокрасочные материалы, клеи и герметики под брендами Artelit и Tytan, включая монтажные, полиуретановые и силиконовые составы. Предприятие также специализируется на выпуске отрезных и шлифовальных дисков, кровельных и гидроизоляционных материалов, облицовочных и декоративных изделий. Дополнительно компания изготавливает лестницы и лестничные ограждения, а управляет строительными магазинами в Ташкенте.</p>
[Выход] <p>Строй центр "NGM" специализируется на производстве и реализации электроинструментов, сварочного оборудования, деревообрабатывающих и измерительных приборов. Ассортимент включает лакокрасочные материалы, монтажные клеи, полиуретановые и силиконовые герметики брендов Artelit и Tytan. Предприятие также производит отрезные и шлифовальные диски, кровельные, гидроизоляционные и декоративные облицовочные материалы, а также лестничные конструкции и ограждения. Организация управляет сетью строительных магазинов.</p>

Пример 5:
[Вход] <p>Компания занимается оптовой торговлей, а также производством чулочно-носочных изделий. Ассортимент включает мужские, женские, детские, спортивные, шерстяные и бамбуковые носки, а также классические и высокие модели. Дополнительно производится продажа искусственных и синтетических нитей. Деятельность сосредоточена на рынке Ташкента, Ташкентской области и Узбекистана в целом, а также включает экспорт трикотажных изделий.</p>
[Выход] <p>ТМ "LIMAX" специализируется на производстве и оптовой реализации чулочно-носочных изделий. Ассортимент включает мужские, женские, детские и спортивные модели из шерсти и бамбукового волокна. Предприятие также осуществляет поставки искусственных и синтетических нитей и экспорт готовой трикотажной продукции.</p>

Пример 6:
[Вход] <p>Компания занимается заготовкой, переработкой и производством сельскохозяйственной продукции в Узбекистане. Основу деятельности составляют фермерские хозяйства, обеспечивающие сырьём собственные перерабатывающие мощности. Сфера охватывает полный цикл — от выращивания до выпуска готовой продукции. Подробные сведения о направлениях работы представлены на официальном сайте.</p>
[Выход] <p>Фермерское хозяйство "OZOD DIYOR ZAHMATKASH" осуществляет заготовку, переработку и производство сельскохозяйственной продукции в Узбекистане. Деятельность предприятия охватывает полный цикл: от выращивания сырья на собственных полях до выпуска готовой продукции.</p>

Пример 7:
[Вход] <p>Компания занимается продажей и производством рабочей и специальной одежды в Самарканде и Самаркандской области.</p><p>Деятельность также охватывает рынок Узбекистана, включая оптовые поставки и изготовление средств индивидуальной защиты.</p><p>Помимо внутреннего рынка, организация осуществляет экспорт спецодежды из Узбекистана.</p><p>Официальный сайт содержит каталог продукции и информацию о направлениях работы.</p>
[Выход] <p>Семейное предприятие "MAHMUD SIFAT TEKSTIL" занимается производством и реализацией рабочей и специальной одежды в Самарканде и Самаркандской области. Деятельность предприятия включает оптовые поставки спецодежды и средств индивидуальной защиты на рынок Узбекистана, а также экспорт продукции.</p>

Пример 8:
[Вход] <p>Компания специализируется на производстве и продаже кожаных и кожгалантерейных изделий, а также обуви, включая специальную и рабочую. Производственные мощности расположены в Ташкенте и ориентированы на выпуск обуви для различных сфер применения. Организация также занимается экспортом кожи и готовых изделий из кожи из Узбекистана. Подробная информация о направлениях деятельности представлена на официальном сайте.</p>
[Выход] <p>ООО с ИИ "ANKA" специализируется на производстве и реализации кожгалантереи, а также рабочей и специальной обуви. Производственные мощности компании расположены в Ташкенте. Предприятие осуществляет экспорт кожевенного сырья и готовых изделий из кожи.</p>

Пример 9:
[Вход] <p>Компания занимается продажей и производством дверей, окон и металлических решеток. В ассортименте представлены окна и оконные рамы, доступные на рынке Узбекистана. Организация имеет сеть филиалов, работающих под брендом Imzo Akfa. На официальном сайте можно ознакомиться с полным перечнем товаров и услуг.</p>
[Выход] <p>Каракалпакстанский республиканский филиал №1 "IMZO" осуществляет производство и реализацию дверей, окон и металлических решеток. Ассортимент включает оконные системы, реализуемые на территории Узбекистана. Предприятие входит в сеть филиалов, работающих под брендом Imzo Akfa.</p>

Пример 10:
[Вход] <p>Компания занимается продажей и производством строительных красок, лаков и другой лакокрасочной продукции в Андижане и Андижанской области, а также на территории Узбекистана. В сферу деятельности также входит реализация и выпуск огнезащитных материалов и технологий. Организация осуществляет экспорт строительных красок. Подробная информация о направлениях работы представлена на официальном сайте anco-paint.uz.</p>
[Выход] <p>ООО "ANCO PAINT" специализируется на производстве и реализации строительных красок, лаков и другой лакокрасочной продукции в Андижане, Андижанской области и на территории Узбекистана. В сферу деятельности предприятия также входит выпуск огнезащитных материалов и технологий, а также экспорт продукции.</p>

Пример 11:
[Вход] <p>Компания занимается продажей мебели в Ташкенте и по всему Узбекистану, а также реализует и производит посуду. На официальном сайте представлены мебельные салоны Ташкента с ассортиментом товаров. Основные направления деятельности включают оптовую и розничную торговлю мебелью, а также выпуск и продажу посуды. Деятельность сосредоточена на внутреннем рынке республики.</p>
[Выход] <p>Мебельный салон "OLIMPIYA" специализируется на производстве и реализации мебели, а также выпуске и продаже посуды. Предприятие осуществляет оптовую и розничную торговлю на внутреннем рынке.</p>

Пример 12:
[Вход] <p>Сеть мастерских специализируется на ремонте и обслуживании электроинструмента. Компания также занимается продажей строительного оборудования и техники. Дополнительным направлением деятельности является производство отдельных видов строительного инструмента.</p>
[Выход] <p>Ремонтная мастерская "EPA" специализируется на обслуживании и ремонте электроинструмента. Компания также занимается продажей строительной техники и оборудования, а также производством отдельных видов строительного инструмента.</p>

- Верни только текст, без комментариев"""

PROMPT_UZ = """Переведи текст на узбекский язык (латиница). Пиши ТОЛЬКО латиницей — без кириллицы.

ШАГ 1: Перед переводом напиши одну строку:
MAHSULOT: [что производит/продаёт/делает компания — конкретные товары/услуги из текста]

ШАГ 2: Напиши полный перевод. В первом предложении ОБЯЗАТЕЛЬНО включи MAHSULOT перед глаголом:
✅ "SARBON MEBEL" MChJ [mahsulot]ni ishlab chiqaradi va sotadi.
✅ "BUXARA GRAND" XK [mahsulot]ni ishlab chiqaradi.

СТРУКТУРА НАЗВАНИЯ КОМПАНИИ — КРИТИЧНО:
• Аббревиатуры форм (MChJ, XK, AJ, QK и т.п.) — ПОСЛЕ имени в кавычках (узбекский стандарт):
  ✅ "SARBON MEBEL" MChJ mebel ishlab chiqaradi.   ❌ MChJ "SARBON MEBEL" ...
  ✅ "BUXARA GRAND" XK ishlab chiqaradi.            ❌ XK "BUXARA GRAND" ...
• Словесные дескрипторы (galereya, restoran, kafe, do'kon, zavod и т.п.) — ПОСЛЕ имени, ОДИН РАЗ, в посессивной форме:
  ✅ "ONTO.ARTE" galereyasi bo'yoqlar ishlab chiqaradi.
  ✅ "BROOKLYN" do'koni alkogolli mahsulotlarni sotadi.
  ❌ "ONTO.ARTE" galereyasi galereyasi ... (дескриптор ДВАЖДЫ — ЗАПРЕЩЕНО)
  ❌ "BROOKLYN" do'koni do'koni ...       (дескриптор ДВАЖДЫ — ЗАПРЕЩЕНО)

ТЕХНИЧЕСКИЕ АББРЕВИАТУРЫ из оригинала (ПЭТ → PET, ПВХ → PVC, МДФ → MDF и т.п.) — сохраняй как латинский аналог, НЕ УДАЛЯЙ. Пример: «ПЭТ-преформ» → «PET-preformalar».

ЛЕКСИЧЕСКОЕ РАЗНООБРАЗИЕ И ТАВТОЛОГИЯ: не повторяй однокоренные слова в соседних предложениях. Если в первом предложении «to'qimachilik mahsulotlari» — во втором нельзя писать «to'qimachilik buyumlari» или «to'qimachilik sanoati». Используй синонимы: mahsulot / tovar / buyum / assortiment; ishlab chiqarish / tayyorlash / yasash; sotadi / yetkazib beradi / taklif etadi.
ЗАПРЕЩЁН ПАССИВНЫЙ ЗАЛОГ И КАНЦЕЛЯРИЗМЫ: вместо «ishlab chiqarish bilan shug'ullanadi» пиши «ishlab chiqaradi». Только активные глаголы.
ЗАПРЕЩЕНО КАЛЬКИРОВАТЬ РУССКИЙ СИНТАКСИС: не переноси русские конструкции дословно. ❌ «suyuq shisha (natriy silikat)ni» → ✅ «suyuq shisha, ya'ni natriy silikatni» или просто «suyuq shishani».
КРИТИЧНО: не добавляй прилагательные и свойства, которых нет в оригинале.
КРИТИЧНО: исправляй логические ошибки оригинала.

ПРИМЕР (Было → Стало):
❌ «"ALFA" MChJ to'qimachilik mahsulotlarini ishlab chiqarish bilan shug'ullanadi. Assortiment to'qimachilik buyumlarini o'z ichiga oladi. Faoliyat to'qimachilik sanoatiga yo'naltirilgan.»
✅ «"ALFA" MChJ jun, paxta va sintetik gazlamalar ishlab chiqaradi va sotadi. Assortimentga kiyim-kechak va uy-ro'zg'or uchun matolar kiradi.»
ЗАПРЕЩЕНО: первое предложение без конкретного названия товара/услуги. Нельзя писать просто "ishlab chiqarish bilan shug'ullanadi", "ishlab chiqaradi va sotadi" или "mahsulotlarini ishlab chiqaradi" без указания ЧТО именно.
⚠️ ДЛИННЫЕ НАЗВАНИЯ БЕЗ КАВЫЧЕК: если название компании длинное (министерство, завод, государственное предприятие) — ОБЯЗАТЕЛЬНО включай MAHSULOT перед глаголом:
✅ YOG'OCHNI QAYTA ISHLASH ZAVODI ... yog'och mahsulotlarini ishlab chiqaradi va sotadi.
❌ YOG'OCHNI QAYTA ISHLASH ZAVODI ... ishlab chiqaradi va sotadi.  ← MAHSULOT пропущен! — перед глаголом должен стоять конкретный продукт из MAHSULOT: ✅ metalloprokat ishlab chiqaradi va sotadi  ❌ ishlab chiqarish bilan shug'ullanadi
РЕГИСТР: аббревиатуры форм (MCHJ, XK, AJ и т.п.) — ВСЕГДА заглавными. Дескрипторы (kompaniya, korxona, zavod, kafe и т.п.) — с заглавной ТОЛЬКО в начале предложения, в середине — строчными.
ЗАПРЕЩЕНО: упоминать города (Toshkent, Samarqand, Buxoro, Farg'ona и т.д.)

Каждое предложение переводи ПОЛНОСТЬЮ — ничего не пропускай, включая все уточнения (для дома и офиса → uy va ofis uchun, оптом и в розницу → ulgurji va chakana va h.k.).

ПРОФЕССИОНАЛЬНЫЙ СЛОВАРЬ ГЛАГОЛОВ — чередуй, не повторяй один и тот же:
  производство/изготовление: ishlab chiqaradi / tayyorlaydi / yasaydi / ishlab chiqarish bilan shug'ullanadi
  продажа/поставка: sotadi / yetkazib beradi / ta'minlaydi / amalga oshiradi / savdo qiladi
  услуги: xizmat ko'rsatadi / bajaradi / amalga oshiradi / taqdim etadi
  специализация: ixtisoslashgan / faoliyat yuritadi / yo'naltirilgan
  ассортимент: assortimentga kiradi / o'z ichiga oladi / mavjud / taklif etiladi
ЗАПРЕЩЕНО: писать просто "sotadi" когда в оригинале есть конкретика — переводи полностью.

Сохрани теги <p> и </p>.

ПРАВИЛА УЗБЕКСКОЙ ОРФОГРАФИИ:
- ОБЯЗАТЕЛЬНО используй правильные апострофы: o' и g' (перевёрнутые) — НЕ o' и g' (прямые). Примеры: to'g'ri, g'oya, o'rmon, so'z, g'isht.
- НЕ копируй русские слова напрямую. Используй узбекские/международные эквиваленты:
  «канцелярия» → kanselyariya (не kantselyariya)
  «стеллаж» → stelajlar или tokchalar (не stellajlar)
  «шкаф-купе» → sürüşli shkaf или eshikli shkaf
  «бухгалтерский шкаф» → hujjatlar shkaflari
  «шкаф для раздевалки» → kiyim-kechak shkaflari

Отвечай строго в формате:
MAHSULOT: ...
<p>...</p>"""

PROMPT_EN = """Translate the text to English. Do not leave any Russian words in the output.

RULES:
- Translate every sentence FULLY — do not skip or shorten anything
- CRITICAL: do NOT add adjectives, properties, or characteristics absent from the source. If the source says "non-woven fabric" — do NOT write "delicate non-woven fabric". If it says "cables" — do NOT write "high-quality cables". Translate only what is explicitly stated.
- CRITICAL: fix logical errors in the source — if the original says "the range includes wholesale and retail trade", that is wrong (trade is a channel, not a product). Restate it correctly: describe WHAT is sold, mention wholesale/retail separately if needed.
- NO TAUTOLOGY: never use words with the same root in adjacent sentences. If sentence 1 has "textile products" — sentence 2 cannot have "textile goods" or "textile industry". Change the root word entirely: fabric → cloth → material → fiber.
- ACTIVE VERBS ONLY: "produces", "manufactures", "supplies", "exports" — never "is engaged in production", "carries out manufacturing", "provides services in the field of".
- NO CALQUING: do not translate Russian syntax literally. Write natural English B2B.
- LEXICAL VARIETY: do not repeat the same noun in adjacent sentences — use synonyms.

EXAMPLE (Before → After):
❌ "The company produces textile products. The range includes textile goods. The enterprise operates in the textile industry."
✅ "LTD 'ALFA' manufactures cotton and synthetic fabrics. The range covers apparel, bedding, and industrial cloth."
- VARY verbs across sentences. Professional vocabulary to rotate:
  Manufacturing: produces / manufactures / fabricates / processes / assembles / outputs
  Trade/supply: supplies / delivers / distributes / exports / trades in / markets
  Services: provides / offers / performs / carries out / handles / renders
  Specialization: specializes in / focuses on / is dedicated to / operates in
  For subsequent sentences: "The range includes..." / "The product line covers..." / "The company also supplies..." / "The enterprise exports..." / "Output includes [list with em-dashes]"
- Every specific product/service from the source MUST appear in the translation
- FORBIDDEN: wide range, high quality, individual approach, meets the needs, satisfies demands, diverse, various types, in accordance with standards, on the domestic market, for various customers
- CAPITALIZATION: form abbreviations (LTD, PE, JV, JSC, IE etc.) are ALWAYS ALL CAPS. Descriptors (company, enterprise, plant, cafe, store etc.) are capitalized ONLY at the start of a sentence — lowercase elsewhere. ✅ "PE \"NAME\" produces..." ✅ "The enterprise also exports..." ❌ "The Enterprise also exports..."
- COMPANY NAME STRUCTURE — follow these patterns strictly:
  • Form abbreviations (LTD, PE, JV, JSC etc.): FORM "NAME" — no article. ✅ LTD "NAME" produces... ✅ PE "NAME" specializes...
  • Word descriptors (store, cafe, plant, salon, clinic, company, enterprise etc.): The [descriptor] "NAME" — article + lowercase descriptor + name. ✅ The store "STYLE MEBEL" offers... ✅ The cafe "ARIANA" specializes... ✅ The plant "NAME" produces... ❌ Store "NAME"... ❌ Cafe "NAME"...
  • Branch/filial: The "NAME" branch — name first, descriptor after. ✅ The "PANDA" branch specializes... ❌ Branch "PANDA" is engaged...
- FORBIDDEN: bare "engaged in" without "is" — always write "is engaged in" or use a different verb (produces / supplies / specializes in / manufactures / provides)
- USE STANDARD ENGLISH INDUSTRY TERMS — do not translate Russian product names word-for-word. Examples: «шкафы-купе» → "sliding-door wardrobes" (not "wardrobe cabinets"), «шкаф для раздевалки» → "lockers" (not "locker room cabinets"), «бухгалтерский шкаф» → "filing cabinet" (not "accounting cabinet"), «стеллаж» → "shelving unit" or "rack", «кассетный кондиционер» → "cassette air conditioner". Use the term a native English speaker in that industry would use.
- FORBIDDEN: city names (Tashkent, Samarkand, Bukhara, Fergana, Andijan etc.) — exception only if the company operates nationwide
- FORBIDDEN: pronouns it/its/they/their referring to the company — use the company name or "the enterprise/company"
- Keep <p> and </p> tags
- CRITICAL: if the company name appears in double quotes in the source (e.g. "ПРО НЕРЖ"), it MUST stay in double quotes in the translation (e.g. "PRO NERJ"). Never drop the quotes around the company name.
- CRITICAL: do NOT translate individual words that are inside double quotes (company name). Keep them verbatim or transliterated.
- CRITICAL: the company form (PE, LTD, JV etc.) must appear ONCE only. Do NOT add a second translated form word (Enterprise, Company, Venture) before or after the quoted name if the form abbreviation is already present. Example: "PE \"NAME\"" is correct — NOT "Private Enterprise ENTERPRISE \"NAME\"".
- CRITICAL: form abbreviations (LTD, PE, JSC, JV, LLC etc.) must ALWAYS be OUTSIDE and BEFORE the quoted name. NEVER place the form inside the quotes. ❌ "PKF TULPAR LTD" → ✅ LTD "PKF TULPAR". ❌ "SOUND SLEEP PE" → ✅ PE "SOUND SLEEP".

EXAMPLES:
[IN] <p>ООО "SARBON MEBEL" производит и реализует корпусную и мягкую мебель. Ассортимент включает шкафы, кровати, диваны и кресла. Предприятие экспортирует продукцию в страны СНГ.</p>
[OUT] <p>LTD "SARBON MEBEL" produces and sells case and upholstered furniture. The range includes wardrobes, beds, sofas, and armchairs. The enterprise exports products to CIS countries.</p>

[IN] <p>ЧП "ANCO PAINT" специализируется на производстве строительных красок, лаков и огнезащитных материалов. Компания также осуществляет экспорт лакокрасочной продукции.</p>
[OUT] <p>PE "ANCO PAINT" specializes in manufacturing construction paints, varnishes, and fire-retardant materials. The company also exports paint and varnish products.</p>

Only translation:"""


PROMPT_EXTRACT_FACTS = """Выпиши только сухие факты о компании из текста ниже. Формат — по одному факту на строку, без нумерации, без прилагательных и рекламы.

Включай:
- что производит (с конкретными товарами и материалами если указаны)
- что продаёт или поставляет
- какие услуги оказывает
- дополнительные направления деятельности
- экспорт (если упомянут, с указанием рынков)

НЕ включай: рекламные эпитеты, каналы сбыта как товары (оптовая/розничная торговля — только если это профиль компании), города и регионы.

Текст: {text}"""

PROMPT_UZ_FROM_FACTS = """Quyidagi faktlar asosida kompaniya haqida {n} ta professional uzbekcha gap yozing (lotin yozuvi, kirillcha yo'q).

Kompaniya: {official_name}
Faktlar:
{facts}

QOIDALAR:
- Birinchi gapda kompaniya nomi va asosiy mahsulot/xizmat aniq bo'lishi shart
- Faol fe'llar: ishlab chiqaradi / sotadi / yetkazib beradi / taqdim etadi / eksport qiladi
- Qo'shni gaplarda bir xil so'zni takrorlamang — sinonimlar ishlating
- Manbada bo'lmagan xususiyat yoki sifat qo'shmang
- Shahar nomlarini eslatmang
- To'g'ri apostrof: o' va g' (o'girilgan) — to'g'ri, g'oya, so'z
- <p> va </p> teglari bilan o'rang"""

PROMPT_EN_FROM_FACTS = """Write a {n}-sentence professional B2B description in English for the company below, using only the facts provided. Do not translate — write naturally in English.

Company: {official_name}
Facts:
{facts}

RULES:
- First sentence: state the company name and its primary product/service explicitly
- Use strong active verbs: produces, manufactures, supplies, distributes, provides, exports, delivers
- Do not repeat the same noun or verb in adjacent sentences — use synonyms
- Do not add adjectives or properties not listed in the facts
- No city or region names
- No pronouns (it/its/they/their) referring to the company — use the company name or "the enterprise/company"
- Wrap in <p> and </p> tags"""


PROMPT_VALIDATE_UZ = """Matnda qoidabuzarliklarni tekshir. Faqat ikkita satr bilan javob ber:
1-satr: PASS yoki FAIL
2-satr (faqat FAIL bo'lsa): qoidabuzarliklarni nuqtali vergul bilan sanab o't

TEKSHIR:
1. Grammatik xatolar: noto'g'ri kelishik boshqaruvi, mantiqsiz so'z birikmalari, tugallanmagan jumlalar
2. Mantiqiy xatolar: jumlalar o'rtasidagi ziddiyat, kompaniya faoliyati haqida hech narsa aytmaydigan jumlalar
3. Reklama iboralari: keng assortiment, yuqori sifat, individual yondashuv, turli xil, xilma-xil, kafolatlaydi, samarali, zamonaviy
4. Shahar nomlari (Toshkent, Samarqand, Buxoro, Farg'ona, Andijon va boshqalar) — agar kompaniya butun mamlakat miqyosida ishlamasa
5. Gaplarning takrorlanishi — bir xil ma'lumot ikki gapda
6. Bo'sh so'ngi gaplar: "ichki bozorda amalga oshiriladi", "turli mijozlar uchun mo'ljallangan", "talablariga javob beradi", "faoliyat ishlab chiqarish va ulgurji savdoni qamrab oladi", "faoliyat ... qamrab oladi"
7. Birinchi gapda mahsulot nomi yo'q: "ishlab chiqaradi va sotadi", "ishlab chiqarish bilan shug'ullanadi", "xizmatlarni taqdim etadi" yoki "mahsulotlarini ishlab chiqaradi" (aniq nom ko'rsatmasdan) — mahsulot ANIQ nomlanishi kerak (masalan: "yog'och mahsulotlarini", "qandolat mahsulotlarini", "to'qimachilik mahsulotlarini")
8. Kiriллица harflari (kotirovkalardagi nomlardan tashqari)

MATN:
{text}"""

PROMPT_VALIDATE_EN = """Check the text for rule violations. Reply strictly with two lines:
Line 1: PASS or FAIL
Line 2 (only if FAIL): list violations separated by semicolons

CHECK:
1. Grammar errors: wrong prepositions, broken sentence structure, dangling participles, subject-verb disagreement, incomplete sentences
2. Logic errors: contradictions between sentences, sentences that say nothing about the company's activity, meaningless word combinations
3. Ad phrases: wide range, high quality, individual approach, is a leader, dynamically developing, meets the needs, satisfies demands, of various types, diverse, cutting-edge, innovative, reliable, optimal
4. City mentions (Tashkent, Samarkand, Bukhara, Fergana, Andijan etc.) — unless company operates nationwide
5. Repetition — same information restated in different words
6. Filler sentences: "for various customers", "on the domestic market", "in accordance with quality standards", "products are designed for"
7. Using "is engaged in" more than once per text; or bare "engaged in" without "is" (grammar error)
8. Pronouns it/its/they/their referring to company outside of quotes

TEXT:
{text}"""

PROMPT_VALIDATE_RU = """Проверь текст на нарушения правил. Отвечай строго двумя строками:
Строка 1: PASS или FAIL
Строка 2 (только при FAIL): перечисли нарушения через точку с запятой

ПРОВЕРЯЙ:
1. Грамматические ошибки: неправильное управление падежами, деепричастный оборот при кратком прилагательном ("сосредоточено предлагая"), несогласование подлежащего со сказуемым, оборванные конструкции
2. Логические ошибки: противоречия между предложениями, бессмысленные сочетания слов, предложения которые ничего не сообщают о деятельности компании
3. Рекламные фразы: широкий спектр, высокое качество, качественный/качественные, индивидуальный подход, является лидером, динамично развивается, ориентируясь на потребности, различные (в любом сочетании), разнообразные, профессиональный, современный, инновационный, надёжный, эффективный, оптимальный, комфортный, уникальный
4. Упоминание городов (Ташкент, Самарканд, Бухара, Фергана, Андижан, Наманган, Карши, Нукус, Термез, Джизак, Гулистан, Навои, Ургенч, Коканд, Маргилан) — если компания не общенациональная
5. Местоимения она/он/они/оно/её/его/их вне кавычек
6. Повтор одной и той же информации в разных предложениях — например "производит мебель" в первом и "изготавливает мебельную продукцию" во втором это повтор
7. Упоминание сайта, интернета, соцсетей, каталога
8. Запрещённые шаблоны: "что позволяет", "что обеспечивает", "деятельность охватывает", "производственные мощности расположены", "условия сотрудничества", "ориентируясь на потребности", "удовлетворить потребности", "широкий ассортимент", "пользуются спросом среди потребителей", "в соответствии со стандартами качества", "ориентировано на рынок", "на внутреннем рынке", "на рынке Узбекистана", "разнообразие продукции"

ТЕКСТ:
{text}"""


_AD_SENTENCE_PATTERNS = re.compile(
    r'официальн\w+\s+сайт'
    r'|на\s+сайт\w+\s+(?:компании|организации|предприятия)'
    r'|подробн\w+\s+информаци\w+\s+(?:на\s+сайт|о\s+каталоге|представлен\w+\s+на)'
    r'|информаци\w+\s+о\s+каталоге'
    r'|сайт\w*\s+содержит'
    r'|представлен\w+\s+на\s+официальн'
    r'|на\s+официальн\w+\s+сайт'
    r'|информаци\w+\s+о\s+своих\s+услугах\s+на'
    r'|(?:visit|see|find\s+(?:more|information)\s+on|available\s+on|catalog\s+available\s+on|learn\s+more\s+on)\b[^.!?]*\bwebsite'
    r'|(?:official|company|our)\s+website'
    r'|website\s+(?:contains|provides|has\s+|at\s+)'
    r'|web[\s\-]?site\s+(?:contains|provides|has\s+)|catalog\s+of\s+(?:goods|products|services)'
    r'|rasmiy\s+sayt|saytida\s+batafsil|katalog\s+haqida'
    # Рекламные клише — целые предложения
    r'|является\s+лидером'
    r'|динамично\s+развивается'
    r'|гарантирует\s+высо\w+\s+качество'
    r'|соответствует\s+(?:международным|мировым)\s+стандартам'
    r'|квалифицированн\w+\s+специалист\w+\s+обеспечива'
    r'|стремится\s+к\s+(?:совершенству|высок\w+\s+качеств)'
    r'|завоевал\w*\s+доверие\s+клиентов'
    r'|индивидуальн\w+\s+подход'
    r'|производство\s+осуществляется\s+на\s+собственных\s+мощностях'
    r'|деятельность\s+сосредоточена\s+на\s+обслуживании'
    r'|представлен\w*\s+информаци\w+\s+о\s+(?:направлениях|товарах|услугах|ассортименте)'
    r'|информаци\w+\s+о\s+направлениях\s+деятельности'
    r'|ориентированных\s+на\s+выпуск'
    r'|основное\s+внимание\s+уделяется'
    r'|производственные\s+мощности\s+позволяют'
    r'|мощности\s+позволяют\s+выполнять'
    r'|реализация\s+продукции\s+через\s+различные\s+каналы'
    r'|дополнительно\s+осуществляется\s+реализация'
    r'|развивая\s+производственные\s+мощности'
    r'|расширяя\s+производственные\s+мощности'
    r'|developing\s+production\s+capacities'
    r'|expanding\s+production\s+capacities'
    r'|providing\s+the\s+market\s+with\s+high[\-\s]quality'
    r'|ishlab\s+chiqarish\s+quvvatlarini\s+rivojlantiradi'
    r'|sifatli\s+\w+\s+bilan\s+bozorni'
    r'|производственные\s+мощности\s+(?:расположены|находятся|размещены)'
    r'|деятельность\s+осуществляется\s+(?:на\s+территории|в\s+регионах?)'
    r'|предлагаются\s+условия\s+сотрудничества'
    r'|условия\s+(?:сотрудничества|партнёрства|партнерства)'
    r'|компания\s+уделяет\s+особое\s+внимание'
    r'|приоритетом\s+(?:является|считается)'
    r'|ставит\s+своей\s+целью'
    # Фиктивные «партнёрство с заводами»
    r'|взаимодейству\w+\s+с\s+(?:производственными\s+)?предприятиями'
    r'|сотрудничает\s+с\s+(?:производственными\s+)?предприятиями'
    # UZ: "hamkorlik qiladi" как единственное содержание
    r'|ishlab\s+chiqarish\s+korxonalari\s+bilan\s+hamkorlik\s+qiladi'
    r'|деятельность\s+ведется\s+на\s+внутреннем\s+рынке'
    r"|faoliyat\s+(?:O[''']zbekiston\s+)?ichki\s+bozorida\s+olib\s+boriladi"
    r'|для\s+различных\s+сфер\s+применения'
    r'|для\s+различных\s+(?:категорий|областей|направлений)'
    r'|удовлетворить\s+потребности\s+клиентов'
    r'|удовлетворяющ\w+\s+потребности'
    r'|с\s+учётом\s+специфических\s+требований\s+каждого\s+клиента'
    r'|с\s+учётом\s+(?:индивидуальных|специфических)\s+требований'
    r'|ориентировано\s+на\s+рынок\s+Узбекистана'
    r'|деятельность\s+(?:компании|предприятия|организации)\s+охватывает\s+территорию'
    r'|пользуются\s+спросом\s+среди\s+(?:местных|конечных)?\s*потребителей'
    r'|в\s+соответствии\s+с\s+установленными\s+стандартами\s+качества'
    r'|в\s+соответствии\s+с\s+(?:международными|мировыми|установленными)\s+стандартами'
    r'|развивается\s+направление\s+по'
    r'|фокусируется\s+на\s+выполнении\s+заказов'
    r'|осуществляет\s+полный\s+цикл\s+(?:изготовления|производства|выпуска)'
    r'|деятельность\s+включает\s+как\s+внутренние'
    r'|как\s+внутренние,?\s+так\s+и\s+внешнеэкономические'
    r'|предоставляет\s+возможности\s+для\s+(?:оптовых|розничных|клиентов)'
    r'|взаимодейству\w+\s+с\s+заводами'
    r'|(?:также\s+)?используется\s+в\s+других\s+промышленных\s+направлениях'
    r'|предоставляя\s+клиентам\s+необходимые'
    r'|товары\s+народного\s+потребления'
    r'|сосредоточен\w+\s+предлага\w+'
    r'|изготавливаем\w+\s+в\s+республике'
    r'|,?\s*в\s+республике\s*,?'
    r'|производственные\s+мощности\s+\w+\s+позволяют\s+изготавливать'
    r'|мощности\s+предприятия\s+позволяют'
    r'|основные\s+направления\s+включают\s+(?:оптовую|розничную|производство|реализацию)'
    r'|выпускаются\s+изделия,?\s+которые\s+применяются'
    r'|изделия,?\s+которые\s+(?:применяются|используются)\s+в\s+\w+'
    r'|qo[''ʻʼ]llaniladigan\s+mahsulotlar\s+chiqariladi'
    r'|работа\s+организована\s+в\s+рамках\s+фермерских\s+хозяйств'
    r'|деятельность\s+организована\s+в\s+рамках'
    r'|работа\s+ведётся\s+в\s+рамках'
    r'|рассматривает\s+возможности\s+экспорта'
    r'|рассматривает\s+возможности\s+(?:расширения|сотрудничества|выхода)'
    r'|изучает\s+возможности\s+(?:экспорта|расширения)'
    # Рынки и локации как самостоятельные пустые предложения
    r'|деятельность\s+\w+\s+охватывает\s+(?:территорию|рынок|регион)'
    r'|(?:реализуется|продаётся|поставляется)\s+на\s+(?:внутреннем\s+)?рынке\s+Узбекистана'
    r'|основное\s+направление\s+деятельности\s+ориентировано'
    r'|продукция\s+(?:предназначена|реализуется|пользуется\s+спросом)\s+(?:на|среди)\s+(?:внутреннем|местн\w+|конечн\w+)'
    r'|разнообразие\s+продукции\s+позволяет'
    r'|в\s+данных\s+сегментах'
    r'|которые\s+пользуются\s+спросом'
    r'|спросом\s+среди\s+(?:местных|конечных|потенциальных)\s+\w+'
    r'|на\s+(?:отечественном|внутреннем)\s+рынке\s+(?:страны|республики|Узбекистана)'
    r'|производственный\s+процесс\s+сосредоточен'
    r'|(?:продаёт|реализует|продает)\s+свою\s+продукцию\s+на\s+рынке'
    r'|в\s+сферу\s+деятельности\s+входит\s+реализация'
    r'|в\s+сферу\s+деятельности\s+входит\s+(?:производство|выпуск|изготовление)\s+\w+\s+на\s+территории'
    r'|деятельность\s+охватывает\s+(?:как\s+производство|производство\s+и\s+реализацию)',
    re.IGNORECASE,
)

# Рекламные обороты внутри предложений — удаляются
_AD_INLINE_RE = re.compile(
    r'\s+широк\w+\s+спектр\w*\s+(?=\w)'
    r'|,?\s*на\s+высоком\s+уровне\s*,?'
    r'|,?\s*высок\w+\s+качеств\w+\s+(?:продукции|услуг|работ|товаров|комплектующими?|изделиями?)\s*,?'
    r'|,?\s*качественными\s+\w+\s*,?'
    r'|,?\s*high[\-\s]quality\s+\w+\s*,?'
    r'|,?\s*обеспечивая\s+(?:широк\w+\s+)?ассортимент\w*(?:\s+продукци\w+)?\s*,?'
    r'|,?\s*широк\w+\s+ассортимент\w*(?:\s+\w+)?\s*,?'
    r'|,?\s*удовлетворяющ\w+\s+потребности[^.!?]*,?'
    r'|,?\s*для\s+различных\s+отраслей(?:\s+экономики)?\s*,?'
    r'|,?\s*различн\w+\s+(?:отраслей|видов|объём\w*|объем\w*|каналов|категорий|сфер|областей|направлений)\s*,?'
    r'|,?\s*предлагая\s+(?:их|продукцию|товары)?\s*на\s+рынке\s*,?'
    r'|,?\s*(?:осуществляемых?\s+)?на\s+территории\s+(?:всего\s+)?Узбекистана\s*,?'
    r'|,?\s*(?:осуществляемых?\s+)?в\s+регионах?\s+Узбекистана\s*,?'
    r'|,?\s*на\s+рынке\s+Узбекистана\s*,?'
    r'|,?\s*на\s+(?:отечественном|внутреннем)\s+рынке\s*,?'
    r'|,?\s*в\s+Узбекистане\s*,?'
    r'|разнообразн\w+\s+\w+'
    r'|разнообразие\s+\w+\s+позволяет[^.!?]*'
    r'|,?\s*используя\s+стандартные\s+технологии[^.!?]*,?'
    r'|,?\s*соответствующ\w+\s+современным\s+стандартам[^.!?]*,?'
    r'|,?\s*(?:мощности|предприятие)\s+позволяют?\s+изготавливать[^.!?]*,?'
    r'|,?\s*для\s+(?:различных\s+)?строительных\s+(?:проектов|нужд|задач)\s*,?'
    r'|,?\s*для\s+(?:различных\s+)?промышленных\s+(?:нужд|целей|задач)\s*,?'
    r'|,?\s*предоставляя\s+клиентам\s+необходимые[^.!?]*,?',
    re.IGNORECASE,
)

_AD_CLAUSE_RE = re.compile(
    r',?\s*что\s+(?:позволяет|обеспечивает)[^.!?]*'
    r'|,?\s*\w+ные\s+мощности\s+позволяют[^.!?]*'
    r'|,\s*обеспечивая\s+(?:\w+\s+){0,3}(?:качественн\w+|высококачественн\w+|надёжн\w+)[^.!?]*'
    r'|,\s*развивая\s+(?:производственные|свои)\s+\w+[^.!?]*'
    r'|,\s*расширяя\s+(?:производственные|свои|рыночные)\s+\w+[^.!?]*'
    r'|,\s*повышая\s+(?:качество|эффективность|уровень)\s*\w*[^.!?]*'
    r'|,?\s*ориентируясь на потребности[^.!?]*',
    re.IGNORECASE,
)

# Местоимения в начале предложения (RU): "Она также" → "Также", "Она " → "Также "
_PRONOUN_START_RE = re.compile(
    r'(?<=[.!?]\s)(?:Она|Он|Они|Оно)\s+также\s+',
)
_PRONOUN_START_RE2 = re.compile(
    r'(?<=[.!?]\s)(?:Она|Он|Они|Оно)\s+(?=[а-яА-Я])',
)
# Посессивные местоимения внутри предложения: "В её ассортименте" → "В ассортименте"
_PRONOUN_POSSESSIVE_RE = re.compile(
    r'\bВ\s+(?:её|его|их)\s+(?=ассортимент|продукц|товар|услуг|деятельност|линейк|каталог|составе)',
    re.IGNORECASE,
)
_PRONOUN_POSSESSIVE_RE2 = re.compile(
    r'(?<!\w)(?:её|его|их)\s+(?=ассортимент\w*|продукц\w*|товар\w*|услуг\w*|деятельност\w*)',
    re.IGNORECASE,
)

# Объектное местоимение после глагола: "доставляет её клиентам" → "доставляет клиентам"
_PRONOUN_OBJ_RE = re.compile(
    r'(?<=\w)\s+(её|его|их)\s+(?=\w)',
    re.IGNORECASE,
)

# Канцеляризмы → активные глаголы (применяется ДО валидации)
_CANCEL_RU = [
    # Восстанавливаем правильный регистр смешанных аббревиатур
    (re.compile(r'\bИндп\b'), 'ИндП'),
    (re.compile(r'\bиндп\b', re.I), 'ИндП'),
    # Канцеляризмы → активные глаголы
    (re.compile(r'\bзанимается\s+производством\s+и\s+(?:реализацией|продажей)\b', re.I), 'производит и реализует'),
    (re.compile(r'\bзанимается\s+производством\b', re.I), 'производит'),
    (re.compile(r'\bзанимается\s+реализацией\b', re.I), 'реализует'),
    (re.compile(r'\bзанимается\s+продажей\b', re.I), 'продаёт'),
    (re.compile(r'\bзанимается\s+поставками?\b', re.I), 'поставляет'),
    (re.compile(r'\bзанимается\s+розничной\s+торговлей\b', re.I), 'ведёт розничные продажи'),
    (re.compile(r'\bзанимается\s+оптовой\s+торговлей\b', re.I), 'осуществляет оптовые поставки'),
    (re.compile(r'\bведёт\s+(?:оптовую|розничную)\s+(?:продажу|торговлю)\b', re.I), 'поставляет'),
    (re.compile(r'\bосуществляет\s+производство\b', re.I), 'производит'),
    (re.compile(r'\bосуществляет\s+поставки\b', re.I), 'поставляет'),
    (re.compile(r'\bосуществляет\s+реализацию\b', re.I), 'реализует'),
    (re.compile(r'\bосуществляет\s+продажу\b', re.I), 'продаёт'),
    (re.compile(r'\bосуществляет\s+(?:оптовую|розничную)\s+торговлю\b', re.I), 'поставляет'),
    (re.compile(r'\bведёт\s+оптовую\s+торговлю\b', re.I), 'поставляет оптом'),
]
_CANCEL_EN = [
    (re.compile(r'\bis\s+engaged\s+in\s+the\s+production\s+and\s+sale\b', re.I), 'produces and sells'),
    (re.compile(r'\bis\s+engaged\s+in\s+the\s+production\b', re.I), 'produces'),
    (re.compile(r'\bis\s+engaged\s+in\s+the\s+sale\b', re.I), 'sells'),
    (re.compile(r'\bis\s+engaged\s+in\s+providing\b', re.I), 'provides'),
    (re.compile(r'\bis\s+engaged\s+in\s+manufacturing\b', re.I), 'manufactures'),
    (re.compile(r'\bis\s+engaged\s+in\s+(?:retail|wholesale)\s+(?:trade|sales?|trading)\b', re.I), 'sells'),
    (re.compile(r'\bconducts\s+(?:wholesale|retail)\s+(?:trade|sales?)\b', re.I), 'sells'),
    (re.compile(r'\bprovides\s+services\s+in\s+the\s+field\s+of\b', re.I), 'provides'),
    (re.compile(r'\bcarries\s+out\s+the\s+production\b', re.I), 'produces'),
    (re.compile(r'\bcarries\s+out\s+(?:the\s+)?sale\b', re.I), 'sells'),
    (re.compile(r'\bForeign\s+[Ee]nterprise\b'), 'FE'),
]
_CANCEL_UZ = [
    (re.compile(r"\bo['ʻʼ]z\s+ichiga\s+oladi\b", re.I), 'kiradi'),
    (re.compile(r'\bsotish\s+va\s+ishlab\s+chiqarish\s+bilan\s+shug[''ʻʼ]ullanadi\b', re.I), 'ishlab chiqaradi va sotadi'),
    (re.compile(r'\bishlab\s+chiqarish\s+va\s+sotish\s+bilan\s+shug[''ʻʼ]ullanadi\b', re.I), 'ishlab chiqaradi va sotadi'),
    (re.compile(r'\bsotish\s+bilan\s+shug[''ʻʼ]ullanadi\b', re.I), 'sotadi'),
    (re.compile(r'\bsavdo\s+bilan\s+shug[''ʻʼ]ullanadi\b', re.I), 'sotadi'),
    (re.compile(r'\bamalga\s+oshiradi\s+ishlab\s+chiqarish\b', re.I), 'ishlab chiqaradi'),
    (re.compile(r'\bamalga\s+oshiradi\s+sotish\b', re.I), 'sotadi'),
    (re.compile(r'\brealizatsiya\s+qilish\b', re.I), "sotish"),
    (re.compile(r'\brealizatsiya\s+qiladi\b', re.I), "sotadi"),
    (re.compile(r'\bsavdo\s+belgisi\b', re.I), 'SB'),
    (re.compile(r'\bxorijiy\s+korxonasi\b', re.I), 'XK'),
    # "oilaviy korxonasi oilaviy [product]" → убираем второй oilaviy (ошибка модели)
    (re.compile(r'(oilaviy\s+korxonasi)\s+oilaviy\b', re.I), r'\1'),
    # Тройной дескриптор фермерского хозяйства → оставляем один
    (re.compile(r"(?:fermerlik|fermer)\s+xo[''ʻʼ]jaligi(?:\s+(?:fermerlik|fermer)\s+xo[''ʻʼ]jaligi)+", re.I),
     "fermerlik xo'jaligi"),
    # "IP" как слово (ip = пряжа/нить) → строчная, чтобы не путать с формой ИП
    (re.compile(r'\bIP\b(?!\s*(?:address|addr|\d))'), 'ip'),
]

# Повтор глагола "занимается" в тексте
_ZAJMAETSYA_RE = re.compile(r'\bзанимается\b', re.IGNORECASE)

_VERB_REPLACEMENTS = [
    'Также осуществляет', 'Дополнительно выполняет', 'Кроме того предоставляет',
    'Помимо этого реализует', 'В сферу деятельности входит',
]


_BANNED_WORDS_RE = re.compile(
    r'широк\w+\s+спектр'
    r'|является\s+лидером'
    r'|динамично\s+развивается'
    r'|индивидуальн\w+\s+подход'
    r'|гарантирует\s+высок\w+\s+качество'
    r'|на\s+высоком\s+уровне'
    r'|основное\s+внимание\s+уделяется'
    r'|условия\s+(?:сотрудничества|партнёрства|партнерства)'
    r'|качественн\w+\s+(?:комплектующ\w+|продукци\w+|товар\w+|изделия\w*|услуг\w*)'
    r'|sifatli\s+\w+'
    r'|ishlab\s+chiqarish\s+quvvatlarini\s+rivojlantiradi'
    r'|официальн\w+\s+сайт'
    r'|сайт\w*\s+содержит'
    r'|производство\s+осуществляется\s+на\s+собственных\s+мощностях'
    r'|представлен\w*\s+информаци\w+\s+о\s+(?:направлениях|товарах|услугах)'
    r'|для\s+различных\s+отраслей'
    r'|различн\w+\s+(?:отраслей|видов|объём\w*|объем\w*|каналов)'
    r'|обеспечивая\s+(?:широк\w+\s+)?ассортимент'
    r'|производственные\s+мощности\s+позволяют'
    r'|реализация\s+продукции\s+через\s+различные\s+каналы'
    r'|производственные\s+мощности\s+(?:расположены|находятся|размещены)',
    re.IGNORECASE,
)


def _strip_ad_sentences(text: str) -> str:
    """Удаляет рекламные предложения, клише, местоимения, дубли глагола занимается."""
    # Сохраняем теги <p></p>
    p_open = '<p>' if text.startswith('<p>') else ''
    p_close = '</p>' if text.endswith('</p>') else ''
    inner = text[len(p_open):len(text) - len(p_close)] if p_open or p_close else text

    # Удаляем придаточные "что позволяет/обеспечивает..."
    inner = _AD_CLAUSE_RE.sub('', inner)

    # Удаляем рекламные inline-обороты
    inner = _AD_INLINE_RE.sub(' ', inner)

    # Заменяем местоимения в начале предложения: "Она также " → "Также ", "Она " → "Также "
    inner = _PRONOUN_START_RE.sub('Также ', inner)
    inner = _PRONOUN_START_RE2.sub('Также ', inner)
    # Убираем посессивные местоимения: "В её ассортименте" → "В ассортименте"
    inner = _PRONOUN_POSSESSIVE_RE.sub('В ', inner)
    inner = _PRONOUN_POSSESSIVE_RE2.sub('', inner)
    # Убираем объектные местоимения в середине: "доставляет её клиентам" → "доставляет клиентам"
    inner = _PRONOUN_OBJ_RE.sub(' ', inner)

    # Разбиваем на предложения, фильтруем рекламные
    sentences = re.split(r'(?<=[.!?])\s+', inner.strip())
    clean = [s for s in sentences if s and not _AD_SENTENCE_PATTERNS.search(s)]

    # Убираем повтор "занимается": второе и далее вхождение заменяем на другой глагол
    repl_idx = 0
    result_sentences = []
    first_seen = False
    for s in clean:
        if _ZAJMAETSYA_RE.search(s):
            if not first_seen:
                first_seen = True
                result_sentences.append(s)
            else:
                replacement = _VERB_REPLACEMENTS[repl_idx % len(_VERB_REPLACEMENTS)]
                repl_idx += 1
                # Заменяем "занимается" → слово-заменитель, убираем лишнее подлежащее если нужно
                s = _ZAJMAETSYA_RE.sub(lambda m: replacement.split()[-1], s, count=1)
                result_sentences.append(s)
        else:
            result_sentences.append(s)

    inner = ' '.join(result_sentences)
    inner = re.sub(r'\s{2,}', ' ', inner).strip()
    inner = re.sub(r',\s*\.', '.', inner)
    inner = re.sub(r'\s+([.!?])', r'\1', inner)   # убираем пробел перед точкой
    inner = re.sub(r'\.{2,}', '.', inner)          # убираем двойные точки
    # Убираем предложения где после inline-чистки осталось менее 3 слов
    sentences2 = re.split(r'(?<=[.!?])\s+', inner.strip())

    def _is_uz_stub(s):
        """Возвращает True если предложение — только ALL-CAPS название + 1-2 глагола (семантически пустое)."""
        words = s.split()
        if len(words) < 3 or len(words) > 8:
            return False
        caps = sum(1 for w in words if re.match(r'^[A-Z\']{2,}', w))
        return caps >= len(words) - 2  # почти все слова ALL-CAPS кроме 1-2 глаголов

    inner = ' '.join(s for s in sentences2 if s and len(s.split()) >= 3 and not _is_uz_stub(s))
    # RU: первое слово после кавычек компании должно быть строчным
    # e.g. 'ООО "NAME" Занимается' → 'ООО "NAME" занимается'
    inner = re.sub(
        r'^([^"]*"[^"]*")\s+([А-ЯЁ])(?=[а-яё])',
        lambda m: m.group(1) + ' ' + m.group(2).lower(),
        inner,
    )
    return f'{p_open}{inner}{p_close}'


def init_openai():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r'[а-яА-Я]', text))


def _has_cyrillic_uz(text: str) -> bool:
    text_no_quotes = re.sub(r'"[^"]*"', '', text)
    return bool(re.search(r'[а-яА-ЯёЁ]', text_no_quotes))


def _call_api(client: OpenAI, prompt: str, lang_label: str,
              system_prompt: str = "", temperature: float = 0.7) -> Optional[str]:
    for attempt in range(3):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
            else:
                messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=temperature,
                timeout=60,
            )
            time.sleep(2)
            content = response.choices[0].message.content.strip()
            # Убираем markdown-обёртку ```html ... ``` если модель её добавила
            content = re.sub(r'^```\w*\s*', '', content, flags=re.MULTILINE).strip()
            content = re.sub(r'```\s*$', '', content, flags=re.MULTILINE).strip()
            return content
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate_limit" in err_str:
                wait = 30
                logger.warning(f"Rate limit, жду {wait} сек (попытка {attempt+1}/3)...")
                time.sleep(wait)
            elif any(t in err_str for t in ("timeout", "connection", "network", "socket")):
                wait = 10 * (attempt + 1)
                logger.warning(f"Сетевая ошибка ({lang_label}), жду {wait} сек (попытка {attempt+1}/3)...")
                time.sleep(wait)
            else:
                logger.error(f"Ошибка OpenAI API ({lang_label}): {e}")
                return None
    logger.error(f"OpenAI API не ответил после 3 попыток ({lang_label})")
    return None


def _validate_ru(client: OpenAI, text: str) -> tuple[bool, str]:
    """Возвращает (is_valid, reasons). is_valid=True если текст прошёл проверку."""
    prompt = PROMPT_VALIDATE_RU.format(text=text)
    response = _call_api(client, prompt, "validate_ru", temperature=0.0)
    if not response:
        return True, ""
    lines = response.strip().splitlines()
    verdict = lines[0].strip().upper()
    reasons = lines[1].strip() if len(lines) > 1 else ""
    return verdict == "PASS", reasons


def _validate_uz(client: OpenAI, text: str) -> tuple[bool, str]:
    prompt = PROMPT_VALIDATE_UZ.format(text=text)
    response = _call_api(client, prompt, "validate_uz", temperature=0.0)
    if not response:
        return True, ""
    lines = response.strip().splitlines()
    verdict = lines[0].strip().upper()
    reasons = lines[1].strip() if len(lines) > 1 else ""
    return verdict == "PASS", reasons


def _validate_en(client: OpenAI, text: str) -> tuple[bool, str]:
    prompt = PROMPT_VALIDATE_EN.format(text=text)
    response = _call_api(client, prompt, "validate_en", temperature=0.0)
    if not response:
        return True, ""
    lines = response.strip().splitlines()
    verdict = lines[0].strip().upper()
    reasons = lines[1].strip() if len(lines) > 1 else ""
    return verdict == "PASS", reasons


PROMPT_CLEAN_RU = """Отредактируй текст компании. Правила:
1. Убери все размытые фразы которые не говорят ЧТО производит/продаёт компания
2. Убери повторы — если две фразы говорят одно и то же, оставь одну
3. НЕ добавляй ничего нового — только убирай лишнее
4. Сохрани <p> и </p>
5. Верни только текст, без комментариев

ПРИМЕРЫ того что надо убирать:
- "деятельность охватывает...", "работа организована в рамках...", "используя технологии..."
- "для различных нужд", "для строительных нужд", "предоставляя клиентам необходимые"
- "как внутренние так и внешнеэкономические операции"
- "соответствующей современным стандартам", "полный цикл изготовления"
- любое предложение которое можно применить к любой компании без изменений

ТЕКСТ:
{text}"""


def _clean_ru(client: OpenAI, text: str) -> str:
    """Чистящий шаг: убирает размытые фразы редактурой, не добавляя ничего нового."""
    if not text or not text.strip() or text == '<p></p>':
        return text
    prompt = PROMPT_CLEAN_RU.format(text=text)
    cleaned = _call_api(client, prompt, "clean_ru", temperature=0.0)
    if not cleaned:
        return text
    # Проверяем что чистящий шаг не обнулил текст
    inner = re.sub(r'<[^>]+>', '', cleaned).strip()
    if len(inner) < 20:
        return text
    return cleaned


def rewrite(client: OpenAI, text: str, company_name: str = "", subject: str = "AUTO", clean_name: str = "", alt_idx: int = 0, has_quotes: bool = True) -> str:
    """Рерайт на русском с автоматической валидацией и одним ретраем при FAIL."""
    if not text or not text.strip():
        return text

    # Нормализуем company_name с несколькими именами в кавычках через запятую:
    # '"EVRO MASTER", "NUKUS EVRO MASTER" ООО' → '"NUKUS EVRO MASTER" ООО'
    if re.search(r'[»"""][,]\s*[«"""]', company_name):
        _qs = re.findall(r'[«"""]([^«"""»]+)[»"""]', company_name)
        if len(_qs) > 1:
            _form_only = re.sub(r'[«"""][^«"""»]+[»"""]\s*,?\s*', '', company_name).strip()
            company_name = (f'"{_qs[-1]}"' + (f' {_form_only}' if _form_only else '')).strip()
            clean_name = _qs[-1]

    if has_quotes:
        prompt_subject = subject
        prompt_clean = clean_name or company_name
    else:
        prompt_subject = ''
        prompt_clean = company_name

    # П.4: ограничиваем количество предложений по длине исходника
    src_sentence_count = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', text)))
    if src_sentence_count <= 2:
        sentence_hint = "ВАЖНО: исходный текст короткий — пиши РОВНО 2 предложения, не раздувай."
    elif src_sentence_count >= 5:
        sentence_hint = "ВАЖНО: исходный текст длинный — можно писать 4-5 предложений."
    else:
        sentence_hint = ""

    prompt = PROMPT_RU.format(text=text, company_name=company_name, subject=prompt_subject,
                               clean_name=prompt_clean, alt_idx=alt_idx, has_quotes=has_quotes)
    if sentence_hint:
        prompt = prompt + f"\n\n{sentence_hint}"
    result = _call_api(client, prompt, "ru") or text
    result = _strip_ad_sentences(result)
    for _pat, _repl in _CANCEL_RU:
        result = _pat.sub(_repl, result)

    # Чистящий шаг: убираем размытые фразы редактурой
    result = _clean_ru(client, result)

    # Валидация с до 3 ретраев
    for attempt in range(3):
        is_valid, reasons = _validate_ru(client, result)
        if is_valid:
            break
        logger.warning(f"RU валидация FAIL (попытка {attempt + 1}/3). Нарушения: {reasons}")
        retry_prompt = (
            prompt
            + f"\n\n⚠️ ПРЕДЫДУЩАЯ ВЕРСИЯ НАРУШИЛА ПРАВИЛА: {reasons}\n"
            "Перепиши заново, строго избегая этих нарушений."
        )
        result = _call_api(client, retry_prompt, "ru_retry") or result
        result = _strip_ad_sentences(result)
        result = _clean_ru(client, result)

    return result


def _fix_false_form(original_ru: str, translated: str, lang: str, has_quotes: bool = True) -> str:
    """Убирает форму компании из перевода, если её не было в оригинале."""
    # EN: убираем дублированное слово-форму/дескриптор (всегда, до раннего возврата)
    if lang == 'en':
        # Сворачиваем полные формы в аббревиатуры перед кавычками: "Private Enterprise "N"" → PE "N""
        _expand_to_abbr = [
            (r'Private Enterprise', 'PE'),
            (r'Joint Venture', 'JV'),
            (r'Foreign Investment Enterprise', 'FIE'),
            (r'Foreign Enterprise', 'FE'),
            (r'Trade[- ]?[Mm]ark', 'TM'),
            (r'Trademark', 'TM'),
        ]
        for _full, _abbr in _expand_to_abbr:
            translated = re.sub(
                r'\b' + _full + r'\b(\s+[«""""«])',
                _abbr + r'\1',
                translated,
                flags=re.IGNORECASE,
            )
        # Форма внутри кавычек: "PKF TULPAR LTD" → LTD "PKF TULPAR"
        # Составные аббревиатурные формы — проверяем первыми (длиннее → приоритет)
        _abbr_token = r'(?:LLC|LTD\.?|OJSC|CJSC|JSC|IE|PE|ME|SUE|JV|ALC|SP|MUE|UE|SE|PCB|LLP|FIE|FE|TC)'
        _compound_abbr_pat = _abbr_token + r'(?:\s+' + _abbr_token + r')+'
        translated = re.sub(
            r'"([^"]{2,60}?)\s+(' + _compound_abbr_pat + r')\s*"',
            lambda m: f'{m.group(2).strip()} "{m.group(1)}"',
            translated,
            flags=re.IGNORECASE,
        )
        # Одиночные аббревиатуры
        translated = re.sub(
            r'"([^"]{2,60}?)\s+(' + _abbr_token + r')\s*"',
            lambda m: f'{m.group(2).rstrip(".")} "{m.group(1)}"',
            translated,
            flags=re.IGNORECASE,
        )
        # Составные словесные формы
        _compound_forms = r'(?:Family [Ee]nterprise|Family [Cc]ompany|Private [Ee]nterprise|Joint [Vv]enture|Foreign [Ee]nterprise)'
        translated = re.sub(
            r'"([^"]{2,60}?)\s+(' + _compound_forms + r')\s*"',
            lambda m: f'{m.group(2)} "{m.group(1)}"',
            translated,
            flags=re.IGNORECASE,
        )
        # Дубль перед кавычкой: "Private Enterprise ENTERPRISE "NAME"" → "Private Enterprise "NAME""
        _en_dup_words = r'(?:Enterprise|Company|Venture|Association|Bureau|Institute|Farm|Center|Foundation|Union|Plant|Factory|Studio|Salon|Clinic|Cafe|Hotel|Store|Market|School|Bank)'
        _any_open_quote = r'[«"""“«]'
        translated = re.sub(
            r'((?:Private Enterprise|Family Enterprise|Family [Cc]ompany|Joint Venture|Foreign Enterprise|LLC|LTD\.?|JSC|OJSC|CJSC|JV|PE|IE|ME|SUE|LLP|SE)\s+)'
            + _en_dup_words + r'\s+' + _any_open_quote,
            lambda m: m.group(1) + m.group(0)[-1],
            translated,
            flags=re.IGNORECASE
        )
        # Branch/Filial: "Branch "NAME"..." → "The "NAME" branch..."
        translated = re.sub(
            r'<p>\s*(?:Branch|Filial|Filiali)\s+([«""""«][^"""»"]+[»""""»])',
            lambda m: '<p>The ' + m.group(1) + ' branch',
            translated,
            flags=re.IGNORECASE
        )
        # Дескрипторы без артикля в начале: "Store "NAME"" → "The store "NAME""
        _desc_needs_the = (r'(?:Store|Cafe|Restaurant|Hotel|Salon|Clinic|Shop|Bakery|Pharmacy|Gym|'
                           r'Plant|Factory|Studio|Market|School|Center|Company|Enterprise|'
                           r'Bureau|Agency|Association|Foundation|Cooperative|Farm|Mill|'
                           r'Barbershop|Laundry|Workshop|Warehouse|Canteen|Library)')
        translated = re.sub(
            r'<p>\s*(' + _desc_needs_the + r')\s+([«""""«])',
            lambda m: '<p>The ' + m.group(1).lower() + ' ' + m.group(2),
            translated,
            flags=re.IGNORECASE
        )
        # Дубль после кавычки: "Plant "NAME" plant outputs" → "Plant "NAME" outputs"
        translated = re.sub(
            r'(\b(\w+)\s+[«"""“«][^”»"»"]*[»"""”»])\s+\2\.?\b',
            r'\1',
            translated,
            flags=re.IGNORECASE
        )

    # Проверяем есть ли ЛЮБАЯ русская форма в оригинальном тексте (все ключи _FORM_MAP)
    ru_forms = [k for k in _FORM_MAP if re.match(r'[А-Я]', k)]
    has_form = False
    for form_key in ru_forms:
        if re.search(r'(?<![А-Яа-яA-Za-z])' + re.escape(form_key) + r'(?![А-Яа-яA-Za-z])', original_ru):
            has_form = True
            break

    if has_form:
        return translated  # форма была в оригинале — не трогаем

    # Формы НЕ было в оригинале — убираем все известные формы из перевода
    if lang == 'uz':
        uz_forms = list({v[1] for v in _FORM_MAP.values() if v[1] and ' ' not in v[1]})
        for form in uz_forms:
            translated = re.sub(r'\b' + re.escape(form) + r'\b\s*', '', translated)
    elif lang == 'en':
        en_forms = list({v[2] for v in _FORM_MAP.values() if v[2] and ' ' not in v[2]})
        for form in en_forms:
            translated = re.sub(r'\b' + re.escape(form) + r'\b\s*', '', translated)

    # Убираем возможные двойные пробелы и пробелы после <p>
    translated = re.sub(r'\s+', ' ', translated)
    translated = translated.replace('<p> ', '<p>')

    # Если has_quotes=False — не добавляем никакие дескрипторы, возвращаем как есть
    if not has_quotes:
        return translated

    # UZ/EN: если модель написала название без кавычек — восстанавливаем по оригиналу RU
    if lang in ('uz', 'en') and not re.match(r'<p>\s*"', translated):
        name_m = re.search(r'[«"""]([^«"""»]{2,50})[»"""]', original_ru[:200])
        if name_m:
            bare = name_m.group(1).strip()
            bare_pat = re.compile(r'(<p>\s*)' + re.escape(bare) + r'(?!\w)', re.IGNORECASE)
            translated = bare_pat.sub(lambda m: m.group(1) + f'"{bare}"', translated, count=1)

    # UZ fallback: кириллическое имя транслитерировано (ПЕНОПЛЭКС → PENOPLEKS) — кавычки не нашлись
    if lang == 'uz' and '"' not in translated and has_quotes:
        _uz_skip = {a.upper() for a in _UZ_FORM_ABBRS} | {'MCHJ', 'XK', 'KK', 'AJ', 'UK', 'IK', 'QK', 'GK'}
        m_uz = re.match(r'(<p>\s*)([A-Z][A-Z0-9\'-]*(?:\s+[A-Z0-9\'-]+)*)\s+(\w)', translated)
        if m_uz:
            name_cand = m_uz.group(2).strip()
            if name_cand.upper() not in _uz_skip and len(name_cand) >= 3:
                translated = m_uz.group(1) + f'"{name_cand}"' + ' ' + m_uz.group(3) + translated[m_uz.end():]

    # EN fallback: если кириллический bare не найден в EN тексте (транслитерация)
    # ищем ALL-CAPS последовательность в начале предложения (допускаем цифровые токены: "U LI MAKSIMA 1718")
    if lang == 'en' and '"' not in translated:
        m = re.match(r'(<p>\s*)([A-Z][A-Z0-9]*(?:\s+[A-Z0-9][A-Z0-9]*)*)\s+(\w)', translated)
        if m:
            name_cand = m.group(2).strip()
            skip = {'LLC', 'LTD', 'JSC', 'PE', 'IE', 'LLP', 'THE', 'THIS', 'OUR', 'A', 'AN'}
            if name_cand.upper() not in skip and len(name_cand) >= 3:
                translated = m.group(1) + f'"{name_cand}"' + ' ' + m.group(3) + translated[m.end():]

    # UZ: если модель написала дескриптор/слово ПЕРЕД именем — <p>Kafe "NAME" → <p>"NAME"
    # (не-аббревиатура перед кавычкой при has_form=False)
    if lang == 'uz' and has_quotes and not re.match(r'<p>\s*"', translated):
        name_m2 = re.search(r'[«"""]([^«"""»]{2,50})[»"""]', original_ru[:200])
        if name_m2:
            bare2 = name_m2.group(1).strip()
            pre_word_pat = re.compile(
                r'^(<p>)\s*(\S+)\s+"' + re.escape(bare2) + r'"', re.IGNORECASE
            )
            pw_m = pre_word_pat.match(translated)
            if pw_m and pw_m.group(2).upper() not in _UZ_FORM_ABBRS:
                translated = pre_word_pat.sub(lambda m: f'<p>"{bare2}"', translated, count=1)

    if lang == 'uz' and re.match(r'<p>\s*"', translated):
        translated = re.sub(r'<p>\s*"', '<p>"', translated)

        # Определяем дескриптор из оригинального русского текста
        uz_desc = None
        pre_quote = re.match(r'<p>\s*(.*?)\s*"', original_ru)
        if pre_quote:
            pre_text = pre_quote.group(1).strip().lower()
            for ru_desc in sorted(_RU_TO_UZ_DESC.keys(), key=len, reverse=True):
                if ru_desc in pre_text:
                    uz_desc = _RU_TO_UZ_DESC[ru_desc]
                    break
        # Fallback: если дескриптор не найден, берём UZ-форму из _FORM_MAP (напр. УП → KK)
        if not uz_desc:
            _fm = _detect_form_in_text(original_ru)
            if _fm and _fm[1] and ' ' not in _fm[1]:
                uz_desc = _fm[1]

        def _fix_uz_subject(m):
            _ap = r"['''ʻʼ]"
            name = m.group(1)
            after = m.group(2)
            words = after.strip().split()
            # Сканируем первые 6 слов — дескриптор может стоять не на первой позиции
            first_words = [re.sub(_ap, "'", w.rstrip('.,;').lower()) for w in words[:6]]
            if any(w in _UZ_DESCRIPTOR_WORDS for w in first_words):
                return f'<p>{name} {after}'
            desc = uz_desc or 'kompaniyasi'
            # Если слова из desc уже есть в первых словах — не добавляем (напр. shourum)
            desc_words = set(re.sub(_ap, "'", desc.lower()).split())
            if desc_words & set(first_words):
                return f'<p>{name} {after}'
            return f'<p>{name} {desc} {after}'

        translated = re.sub(r'<p>([«"""][^«"""»]*[»"""])\s*(.*)', _fix_uz_subject, translated)

    elif lang == 'en':
        if re.match(r'<p>\s*"', translated):
            translated = re.sub(r'<p>\s*"', '<p>The company "', translated, count=1)
        elif re.match(r'<p>\s*(?!The\s)[A-Z][a-z]', translated):
            # Fix missing article: "Company "NAME"" → "The company "NAME""
            translated = re.sub(
                r'<p>\s*([A-Z][a-z][a-zA-Z]*(?:\s+[a-z][a-zA-Z]*)?)\s+"',
                lambda m: f'<p>The {m.group(1).lower()} "',
                translated, count=1
            )

    return translated


def _fix_uz_capslock(translated: str) -> str:
    """Если > 50% букв вне кавычек — заглавные, нормализует регистр текста вне кавычек."""
    text_outside_quotes = re.sub(r'"[^"]*"', '', translated)
    letters = [c for c in text_outside_quotes if c.isalpha()]
    if not letters:
        return translated
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio <= 0.5:
        return translated
    # Применяем нормализацию только к частям вне кавычек
    parts = re.split(r'("(?:[^"])*")', translated)
    result_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # внутри кавычек — не трогаем
            result_parts.append(part)
        else:
            result_parts.append(
                re.sub(r'(?<!["<>])[А-ЯA-Z]{2,}(?!["])',
                       lambda m: m.group(0).lower(),
                       part)
            )
    result = ''.join(result_parts)
    # Восстанавливаем аббревиатуры форм компаний (mchj → MCHJ, xk → XK и т.п.)
    _uz_caps_abbrs = _UZ_FORM_ABBRS | {'UK', 'GK', 'QK'}  # доп. формы из goldenpages
    for abbr in sorted(_uz_caps_abbrs, key=len, reverse=True):
        result = re.sub(r'\b' + re.escape(abbr.lower()) + r'\b', abbr, result, flags=re.IGNORECASE)
    return result


def _detect_form_in_text(text: str) -> Optional[tuple]:
    """Возвращает (ru_form, uz_form, en_form) если форма найдена в тексте."""
    ru_forms = [k for k in _FORM_MAP if re.match(r'[А-Я]', k)]
    for form_key in sorted(ru_forms, key=len, reverse=True):
        pattern = r'(?<![А-Яа-яA-Za-z])' + re.escape(form_key) + r'(?![А-Яа-яA-Za-z])'
        if re.search(pattern, text):
            return _FORM_MAP[form_key]
    return None


def _extract_clean_official(official_name: str) -> str:
    """Извлекает чистое название из официального: только содержимое первых кавычек, без формы и города."""
    if not official_name:
        return official_name
    # Ищем содержимое в кавычках «», "", ""
    m = re.search(r'[«"""]([^«"""]+)[»"""]', official_name)
    if m:
        return m.group(1).strip().rstrip('.')
    # Нет кавычек — убираем " in City" / " - City" в конце, потом берём до первой точки
    name = official_name.strip()
    name = re.sub(r'\s+in\s+\w[\w\s]*$', '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'\s+-\s+\w[\w\s]*$', '', name).strip()
    if '.' in name:
        name = name.split('.')[0].strip()
    return name


# Паттерны глаголов для поиска начала описания
_RU_VERB_RE = re.compile(
    r'\b(?:занимается|специализируется|осуществляет|предоставляет|выполняет|'
    r'производит|оказывает|реализует|ведёт|предлагает|поставляет|выпускает|является)\b',
    re.IGNORECASE,
)
_ANY_VERB_RE = re.compile(
    r'\b(?:занимается|специализируется|осуществляет|предоставляет|выполняет|производит|'
    r'оказывает|реализует|ведёт|предлагает|поставляет|выпускает|является|'
    r'specializes|carries|provides|offers|performs|produces|operates|focuses|delivers|'
    r'is\s+engaged|was\s+engaged|are\s+engaged|were\s+engaged|'
    r'manufactures|fabricates|assembles|processes|constructs|builds|installs|'
    r'supplies|delivers|distributes|exports|imports|outputs|markets|sells|trades|'
    r'repairs|designs|develops|manages|handles|renders|'
    r'ixtisoslashgan|faoliyat|taqdim|bajaradi|ishlab)\b',
    re.IGNORECASE,
)


def _normalize_uz_name(name: str) -> str:
    """'"NAME" FORM' → 'FORM "NAME"' если FORM — известная UZ-аббревиатура (MCHJ, QK, AJ…)."""
    m = re.match(r'^("[^"]*")\s+([A-Za-z][A-Za-z0-9]*)\s*$', name)
    if m and m.group(2).upper() in _UZ_FORM_ABBRS:
        return f'{m.group(2)} {m.group(1)}'
    return name


_EN_FORM_SUFFIX_RE = re.compile(
    r'\s+(LLC|LTD\.?|CO\.?|OJSC|CJSC|JSC|IE|PE|ME|SUE|JV|ALC|SP|MUE|UE|SE|PCB|JISB|JSB|PC|LLP)\s*$',
    re.IGNORECASE,
)
# Форму из goldenpages оставляем как есть; расширяем только описательные слова

# Только юридические формы из _FORM_MAP (не дескрипторы) — для catch-all в _normalize_en_name
_EN_FORM_LABELS_SORTED = sorted(
    {v[2] for v in _FORM_MAP.values() if v[2] and re.match(r'^[A-Za-z]', v[2])},
    key=len, reverse=True,
)
_EN_FORM_NORM = {'FAMILY': 'Family Enterprise', 'PRIVATE': 'Private Enterprise'}


# Составные формы-дескрипторы которые могут оказаться в хвосте имени компании
_EN_COMPOUND_FORM_SUFFIXES = [
    ('FOREIGN ENTERPRISE', 'Foreign Enterprise'),
    ('PRIVATE ENTERPRISE', 'Private Enterprise'),
    ('JOINT VENTURE', 'Joint Venture'),
    ('FAMILY ENTERPRISE', 'Family Enterprise'),
    ('FAMILY COMPANY', 'Family company'),
]

# Составные аббревиатурные формы из _FORM_MAP (JV LTD, LTD JV и т.п.)
_EN_COMPOUND_ABBR_FORMS = sorted(
    {v[2] for v in _FORM_MAP.values()
     if v[2] and ' ' in v[2]
     and all(2 <= len(w) <= 6 and w.isupper() for w in v[2].split())},
    key=len, reverse=True,
)

# Regex для извлечения чистой формы из form_part: "JV LTD HEAD OFFICE" → "JV LTD"
_ABBR_TOKEN = r'(?:LLC|LTD\.?|CO\.?|OJSC|CJSC|JSC|IE|PE|ME|SUE|JV|ALC|SP|MUE|UE|SE|PCB|JISB|JSB|LLP)'
_PURE_FORM_RE = re.compile(
    r'^(' + _ABBR_TOKEN + r'(?:\s+' + _ABBR_TOKEN + r')*)(?:\s|$)',
    re.IGNORECASE,
)


def _strip_en_compound_form(base: str, form_part: str) -> tuple:
    """Убирает составную форму из хвоста base и добавляет её к form_part."""
    for suffix_upper, suffix_label in _EN_COMPOUND_FORM_SUFFIXES:
        if base.upper().endswith(' ' + suffix_upper):
            base = base[: -len(suffix_upper)].rstrip()
            form_part = (suffix_label + ' ' + form_part).strip() if form_part else suffix_label
            return base, form_part
    return base, form_part


def _normalize_en_name(name: str) -> str:
    """Преобразует goldenpages EN формат 'NAME FORM.' или 'NAME. FORM DESC' в 'FORM "NAME"'."""
    name = name.rstrip('.')
    # Pattern: "NAME. FORM DESCRIPTOR" (точка отделяет имя от дескриптора)
    # Bug fix: точка в "NAME. FORM" должна разделять имя и форму ТОЛЬКО если после точки идёт
    # известная форма (LTD, LLC, JV и т.п.), а не просто заглавная буква имени.
    dot_m = re.match(r'^(.*?)\.\s+([A-Z].+)$', name)
    if dot_m:
        base = dot_m.group(1).strip()
        # Восстанавливаем точку если base заканчивается на одиночную заглавную букву (инициал: R.A → R.A.)
        if re.search(r'(?<![A-Z])[A-Z]$', base):
            base += '.'
        form_part = dot_m.group(2).strip().rstrip('.')
        form_part = re.sub(r'\s+on\s+[\w.][\w\s,.]+$', '', form_part, flags=re.IGNORECASE).strip()
        form_part = re.sub(r'\s+in\s+[\w.][\w\s,.]+$', '', form_part, flags=re.IGNORECASE).strip()
        base, form_part = _strip_en_compound_form(base, form_part)
        # Извлекаем чистые аббревиатуры из form_part, отбрасывая trailing дескрипторы
        # напр. "JV LTD HEAD OFFICE" → "JV LTD"
        _pm = _PURE_FORM_RE.match(form_part)
        if _pm:
            form_part = _pm.group(1).strip()
        else:
            words = form_part.split()
            if words and words[0].upper().rstrip('.') in _EN_FORM_NORM:
                mapped = _EN_FORM_NORM[words[0].upper().rstrip('.')]
                mapped_lower = set(mapped.lower().split())
                remaining = [w for w in words[1:] if w.lower() not in mapped_lower]
                form_part = (mapped + ' ' + ' '.join(remaining)).strip()
            else:
                form_part = _EN_FORM_NORM.get(form_part.upper(), form_part)
        return f'{form_part} "{base}"'
    # Pattern: "NAME FORM" — сначала проверяем составные аббревиатурные формы (JV LTD и т.п.)
    for _compound_abbr in _EN_COMPOUND_ABBR_FORMS:
        if name.upper().endswith(' ' + _compound_abbr):
            _base = name[:-len(_compound_abbr)].rstrip()
            if _base:
                return f'{_compound_abbr} "{_base}"'
    # Затем одиночные формы
    form_m = _EN_FORM_SUFFIX_RE.search(name)
    if form_m:
        form = form_m.group(1).rstrip('.')
        form = _EN_FORM_NORM.get(form.upper(), form)
        base = name[:form_m.start()].strip()
        base, extra = _strip_en_compound_form(base, '')
        if extra:
            form = f'{extra} {form}'
        return f'{form} "{base}"'
    # Нет стандартной формы — проверяем составные формы-дескрипторы в хвосте
    for suffix_upper, suffix_label in _EN_COMPOUND_FORM_SUFFIXES:
        if name.upper().endswith(' ' + suffix_upper):
            base = name[: -len(suffix_upper)].rstrip()
            return f'{suffix_label} "{base}"'
    # Catch-all: только юридические формы из _FORM_MAP (не дескрипторы типа Complex/Center/Store)
    for label in _EN_FORM_LABELS_SORTED:
        if not label:
            continue
        if name.upper().endswith(' ' + label.upper()):
            base = name[: -len(label)].rstrip()
            if base:
                return f'{label} "{base}"'
    # Нет формы → возвращаем без кавычек (безформенные компании кавычки не нужны)
    return name


def force_official_name(generated_text: str, official_name: str, lang: str = '') -> str:
    """Заменяет субъект+название в начале <p> на официальное название с goldenpages.

    Алгоритм:
    1. Очищает суффикс города из official_name.
    2. Для EN: нормализует формат 'NAME FORM.' → 'FORM "NAME"'.
    3. Если текст содержит кавычки → находит закрывающую кавычку, убирает trailing
       ALL-CAPS слова после неё (форма/дескриптор из сгенерированного текста),
       для RU — сплитит по первому глаголу если он близко.
    4. Иначе (без кавычек) → сплитит по первому глаголу-сказуемому.
    """
    if not official_name or not generated_text:
        return generated_text

    # Очищаем суффиксы города
    clean = official_name.strip()
    clean = re.sub(r'\s*\([^)]+\)\s*$', '', clean).strip()
    clean = re.sub(r'\s+in\s+[\w.][\w\s,.-]+$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s+on\s+[\w.][\w\s,.-]+$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s+-\s+[\w.][\w\s,.-]+$', '', clean).strip()
    clean = re.sub(r"\s+\w+\s+ko[''']chasida\b.*$", '', clean, flags=re.IGNORECASE).strip()
    clean = clean.rstrip('.')
    if not clean:
        return generated_text

    # Если clean — имя без кавычек, но в generated_text оно стоит в кавычках — сохраняем кавычки.
    # Делаем ДО AUTO-check, чтобы AUTO-check видел уже обёрнутое "ИМЯ".
    if not re.search(r'[«"""]', clean):
        if re.search(r'[«"""]' + re.escape(clean) + r'[»"""]', generated_text[:200]):
            clean = f'"{clean}"'
        elif lang == 'en' and re.search(r'[«"""]', generated_text[:100]):
            # Официальное имя без кавычек, но в тексте кавычки есть (напр. № vs #).
            # Сначала пробуем нормализацию — вдруг в имени есть форма (напр. "NAME. FORM").
            _norm = _normalize_en_name(clean)
            if '"' in _norm:
                clean = _norm  # форма извлечена: FORM "BASE NAME"
            else:
                clean = f'"{clean}"'  # форма не найдена — просто оборачиваем

    # RU AUTO: сохранить Компания/Организация/Предприятие из generated_text
    if lang == 'ru' and re.match(r'^[«"""][^«"""»]*[»"""]$', clean):
        subj_m = re.match(r'<p>\s*([^\s«"""»]+)\s+[«"""]', generated_text)
        if subj_m:
            clean = f'{subj_m.group(1)} {clean}'

    # EN AUTO: сохранить слово-субъект (The company / Organization / Enterprise…) из generated_text
    if lang == 'en' and re.match(r'^"[^"]*"$', clean):
        subj_m = re.match(r'<p>\s*([A-Z][a-zA-Z]*(?:\s+[a-z]+)?)\s+"', generated_text)
        if subj_m:
            clean = f'{subj_m.group(1)} {clean}'

    # RU: '"NAME" ФОРМА/ДЕСКРИПТОР' → 'ФОРМА/ДЕСКРИПТОР "NAME"' (в т.ч. составные ИП ООО)
    if lang == 'ru' and re.search(r'[«"""]', clean):
        forms_alt = '|'.join(re.escape(l) for l in _RU_ALL_LABELS_SORTED)
        m = re.match(r'^("[^"]*")\s+((?:(?:' + forms_alt + r')\s*)+)$', clean, re.IGNORECASE)
        if m:
            clean = f'{m.group(2).strip()} {m.group(1)}'
        else:
            for label in _RU_ALL_LABELS_SORTED:
                m = re.match(r'^("[^"]*")\s+(' + re.escape(label) + r')\s*$', clean, re.IGNORECASE)
                if m:
                    clean = f'{m.group(2)} {m.group(1)}'
                    break
            else:
                # Bug 1 fix: составные формы с нестандартными словами типа "NAME" ООО УЗБЕКСКО-ИРАНСКОЕ СП
                # → всё что после кавычек переносим перед кавычки
                m = re.match(r'^("[^"]*")\s+(.+)$', clean)
                if m:
                    clean = f'{m.group(2)} {m.group(1)}'

    # UZ: '"NAME" FORM' → 'FORM "NAME"' — однословные формы
    if lang == 'uz' and re.search(r'[«"""]', clean):
        clean = _normalize_uz_name(clean)

    # UZ составные аббревиатуры: '"NAME" FORM1 FORM2' → 'FORM1 FORM2 "NAME"' (QK MChJ и т.п.)
    if lang == 'uz' and re.search(r'[«"""]', clean):
        m_uz = re.match(r'^("[^"]*")\s+([A-Za-z]{2,10}\s+[A-Za-z0-9]{2,10})\s*$', clean)
        if m_uz:
            words = m_uz.group(2).split()
            if all(w.upper() in _UZ_FORM_ABBRS for w in words):
                clean = f'{m_uz.group(2)} {m_uz.group(1)}'

    # UZ описательные формы: 'DESCRIPTIVE_FORM "NAME"' → '"NAME" descriptive_form'
    # fermerlik xo'jaligi, oilaviy korxona и т.п. идут ПОСЛЕ имени как дескрипторы
    if lang == 'uz':
        for form in _UZ_DESC_FORMS:
            m_pre = re.match(
                r'^(' + re.escape(form) + r')\s+("[^"]*")\s*$',
                clean, re.IGNORECASE
            )
            if m_pre:
                clean = f'{m_pre.group(2)} {form.lower()}'
                break

    # EN: '"NAME" FORM/DESCRIPTOR' → 'FORM/DESCRIPTOR "NAME"'
    if lang == 'en' and re.search(r'[«"""]', clean):
        for label in _EN_ALL_LABELS_SORTED:
            m = re.match(r'^("[^"]*")\s+(' + re.escape(label) + r')\s*$', clean, re.IGNORECASE)
            if m:
                clean = f'{m.group(2)} {m.group(1)}'
                break

    if lang == 'en' and not re.search(r'[«"""]', clean):
        clean = _normalize_en_name(clean)

    # Нормализация регистра: АГРОФИРМА "NAME" → Агрофирма "NAME", "NAME" ZAVODI → "NAME" zavodi
    if re.search(r'[«"""]', clean):
        if lang in ('ru', 'en'):
            labels = _RU_ALL_LABELS_SORTED if lang == 'ru' else _EN_ALL_LABELS_SORTED
            m_pre = re.match(r'^(.+?)\s+("[^"]*".*)', clean)
            if m_pre:
                pre = m_pre.group(1).strip()
                for label in labels:
                    if pre.upper() == label.upper():
                        clean = f'{label} {m_pre.group(2)}'
                        break
        elif lang == 'uz':
            m_post = re.match(r'^(".*?")\s+(.+)$', clean)
            if m_post:
                post = m_post.group(2).strip()
                if post.upper() not in _UZ_FORM_ABBRS:
                    post_norm = post.lower()
                    _uz_extra_abbrs = {'IP', 'XK', 'QK', 'AJ'}
                    for abbr in sorted(_UZ_FORM_ABBRS | _uz_extra_abbrs, key=len, reverse=True):
                        post_norm = re.sub(r'(?<!\w)' + re.escape(abbr.lower()) + r'(?!\w)', abbr, post_norm)
                    clean = f'{m_post.group(1)} {post_norm}'

    # EN: убираем дублирующее слово-дескриптор внутри clean (Family Enterprise COMPANY "N" → Family Enterprise "N")
    if lang == 'en' and re.search(r'[«"""]', clean):
        _dup_w = r'(?:Enterprise|Company|Venture|Association|Bureau|Institute|Farm|Center|Foundation|Union|Plant|Factory|Studio|Salon|Clinic|Cafe|Hotel|Store|Market|School|Bank)'
        _form_pfx = r'(?:Private Enterprise|Family Enterprise|Family [Cc]ompany|Joint Venture|Foreign Enterprise|LLC|LTD\.?|JSC|OJSC|CJSC|JV|PE|IE|ME|SUE|LLP|SE|PC)'
        clean = re.sub(
            r'(' + _form_pfx + r'\s+)' + _dup_w + r'\s+([«""""«"])',
            lambda m: m.group(1) + m.group(2),
            clean, flags=re.IGNORECASE,
        )
        # Сворачиваем полные формы → аббревиатуры
        for _full, _abbr in [('Private Enterprise', 'PE'), ('Joint Venture', 'JV'), ('Foreign Enterprise', 'FE'), ('Trade Mark', 'TM'), ('Trademark', 'TM'), ('Trade-mark', 'TM')]:
            clean = re.sub(r'\b' + re.escape(_full) + r'\b(\s+[«""""«])', _abbr + r'\1', clean, flags=re.IGNORECASE)

    # Нормализуем регистр дескриптора: КОНДИТЕРСКИЙ ДОМ "N" → Кондитерский дом "N"
    if lang in ('ru', 'en') and re.search(r'[«"""]', clean):
        _cn_m = re.match(r'^(.+?)\s+([«"""].+)', clean)
        if _cn_m:
            _pre = _cn_m.group(1).strip()
            _pre_norm = _normalize_descriptor_case(_pre, lang)
            if _pre_norm != _pre:
                clean = _pre_norm + ' ' + _cn_m.group(2)

    p_m = re.match(r'(<p>)([\s\S]*)', generated_text)
    if not p_m:
        return generated_text
    p_tag, content = p_m.group(1), p_m.group(2)

    # ── Стратегия 1: в тексте есть кавычки ───────────────────────────────────
    quote_m = re.search(r'[«"""]([^«"""»]*)[»"""]', content[:150])
    if quote_m:
        after_quote = content[quote_m.end():]

        # RU: глагол сразу после имени (< 40 символов)
        vm = _RU_VERB_RE.search(after_quote)
        if lang == 'ru' and vm and vm.start() < 40:
            description = after_quote[vm.start():]
            if description:
                return f'{p_tag}{clean} {description}'

        # EN: ищем глагол в after_quote — он является точной границей описания
        if lang == 'en':
            vm = _ANY_VERB_RE.search(after_quote)
            if vm:
                description = after_quote[vm.start():]
                if description:
                    return f'{p_tag}{clean} {description}'

        # UZ: verb split ТОЛЬКО если перед глаголом пусто или стоит аббревиатура формы.
        # Учитываем смешанный регистр (MChJ, XK и т.п.) через _UZ_FORM_ABBRS.
        if lang == 'uz':
            vm = _ANY_VERB_RE.search(after_quote)
            if vm:
                before_verb = after_quote[:vm.start()].strip()
                is_form = (
                    not before_verb
                    or re.match(r'^[A-Z]{2,10}$', before_verb)
                    or before_verb.upper() in _UZ_FORM_ABBRS
                )
                if is_form:
                    description = after_quote[vm.start():]
                    if description:
                        return f'{p_tag}{clean} {description}'

        # Fallback: убираем trailing ALL-CAPS слова (форма/дескриптор из сгенерированного).
        # Используем \b чтобы не срезать часть слова (MChJ → не трогаем, т.к. \b после C не сработает)
        description = re.sub(r'^\s*(?:[A-ZА-ЯЁ]{2,}(?=[^a-zа-яёA-ZА-ЯЁ]|$)\'?\s*)+', '', after_quote).lstrip()
        # UZ: если clean заканчивается на описательную форму, убираем её дубль из description
        if lang == 'uz':
            clean_lower = clean.lower()
            for form in _UZ_DESC_FORMS:
                if clean_lower.endswith(' ' + form.lower()):
                    description = re.sub(
                        r'^' + re.escape(form.lower()) + r'(?=\s|$)',
                        '', description, flags=re.IGNORECASE
                    ).lstrip()
                    break
        # UZ: стрипим остаточный дескриптор ТОЛЬКО если clean уже содержит форму/дескриптор
        # рядом с именем (AGROFIRMASI "NAME" или "NAME" fermerlik xo'jaligi).
        # Если clean = просто '"NAME"' — дескриптор в description легитимен, не трогаем.
        if lang == 'uz':
            clean_has_extra = bool(re.search(r'^\S.*\s+"[^"]*"$|^"[^"]*"\s+\S', clean))
            if clean_has_extra:
                # Убираем ВСЕ дублирующиеся дескрипторы в начале description (цикл)
                changed = True
                while changed:
                    changed = False
                    description = description.strip()
                    # Многословные (fermerlik xo'jaligi, oilaviy korxona и т.п.)
                    for form in sorted(_UZ_DESC_FORMS, key=len, reverse=True):
                        pat = re.compile(r'^' + re.escape(form) + r'(?=\s|$)', re.IGNORECASE)
                        if pat.match(description):
                            description = pat.sub('', description).lstrip()
                            changed = True
                            break
                    # Однословные (kafesi, markazi и т.п.)
                    if not changed:
                        m_ud = re.match(r'^(\w[\w\']*)\s+', description)
                        if m_ud and m_ud.group(1).lower() in _UZ_DESCRIPTOR_WORDS:
                            description = description[m_ud.end():]
                            changed = True
        if description:
            return f'{p_tag}{clean} {description}'

    # ── Стратегия 2: без кавычек → первый глагол-сказуемое ───────────────────
    vm = _ANY_VERB_RE.search(content)
    if vm:
        return f'{p_tag}{clean} {content[vm.start():]}'

    return generated_text


# UZ apostrophe variants: ASCII ' U+0027, typographic ' U+2019, modifier ʻ U+02BB, ʼ U+02BC
_UZ_APOSTROPHE_RE = re.compile(r"['''ʻʼ]")

_UZ_PRODUCTION_VERBS_RE = re.compile(
    r"ishlab\s+chiqar(?:adi|ish|uvchi|moqda)|"
    r"ishlab\s+chiqar(?:adi|ish)|"
    r"shug['''ʻʼ]ullan(?:adi|moqda)|"
    r"faoliyat\s+yurit(?:adi|moqda)|"
    r"ixtisoslash(?:gan|moqda|tirilgan)|"
    r"sotadi|taklif\s+etadi|yetkazib\s+beradi",
    re.IGNORECASE,
)


def extract_facts(client: OpenAI, ru_text: str) -> str:
    """Извлекает сухие факты из RU текста для передачи в UZ/EN генерацию."""
    prompt = PROMPT_EXTRACT_FACTS.format(text=ru_text)
    result = _call_api(client, prompt, "facts", temperature=0.0) or ""
    # Убираем теги если модель их вернула
    result = re.sub(r'<[^>]+>', '', result).strip()
    return result


def translate(client: OpenAI, text: str, lang: str, has_quotes: bool = True,
              official_name: str = "", official_subject: str = "",
              facts: str = "") -> str:
    """Перевод готового русского текста на uz или en.
    Если передан facts — генерирует текст из фактов (лучше качество)."""
    if not text or not text.strip():
        return text

    # Для названий с кавычками — передаём только чистое название (без формы/города).
    if has_quotes:
        if official_name and re.search(r'[«"""]', official_name):
            clean_official = _extract_clean_official(official_name)
        elif official_name and lang == 'en':
            # EN без кавычек: нормализуем "ARIMEX JV" → JV "ARIMEX" → clean = "ARIMEX"
            _norm = _normalize_en_name(official_name)
            if '"' in _norm:
                clean_official = _extract_clean_official(_norm)
            else:
                clean_official = ''
        else:
            clean_official = ''
    else:
        clean_official = official_name

        # Для UZ: заменяем кириллические аббревиатуры материалов латинскими эквивалентами,
    # чтобы модель не теряла и не искажала их при переводе.
    _CYR_ABBR_MAP = {
        'ЛДСП': 'LDSP', 'ДСП': 'DSP', 'МДФ': 'MDF', 'ЛМДФ': 'LMDF',
        'ДВП': 'DVP', 'ОСП': 'OSB', 'ФСФ': 'FSF', 'ХДФ': 'HDF',
        'ПВХ': 'PVC', 'ПВ': 'PVC', 'ПЭ': 'PE', 'ПП': 'PP',
        'АБС': 'ABS', 'ПУ': 'PU', 'ЦСП': 'CSP',
    }
    if lang == "uz":
        for _cyr, _lat in _CYR_ABBR_MAP.items():
            text = re.sub(r'\b' + re.escape(_cyr) + r'\b', _lat, text)

    # Для UZ: выделяем объект производства/продажи в [скобки], чтобы модель его не потеряла.
    if lang == "uz":
        def _bracket_object(m):
            verb_part = m.group(1)
            obj = m.group(2)
            return f"{verb_part} [{obj}]"

        text = re.sub(
            r'(занимается\s+(?:производством(?:\s+и\s+реализацией|\s+и\s+продажей)?|'
            r'реализацией|продажей|изготовлением|поставкой|выпуском))\s+'
            r'([^.<>]{5,100}?)\s*(?=\.\s|,\s*[А-ЯЁ]|\.$)',
            _bracket_object,
            text
        )

    # Определяем форму компании в тексте для жёсткой подсказки
    form_match = _detect_form_in_text(text)

    if lang == "uz":
        # Форма из официального названия имеет приоритет над формой из русского текста
        effective_form = official_subject or (form_match[1] if form_match else None)
        if not effective_form and official_name and has_quotes:
            _m_post = re.match(r'^"[^"]*"\s+(\S+)', official_name.strip())
            if _m_post:
                _post = _m_post.group(1).strip().lower()
                if _post.upper() not in _UZ_FORM_ABBRS:
                    effective_form = _post
        system_parts = []
        if effective_form:
            system_parts.append(
                f"⚠️ КРИТИЧНО: Форма/дескриптор компании ОБЯЗАТЕЛЬНО должна быть \"{effective_form}\" "
                f"(взята из официального источника). НЕ заменяй на другую форму. "
                f"Узбекский стандарт: имя ПЕРВЫМ в кавычках, затем форма: \"{clean_official or 'NAME'}\" {effective_form} ..."
            )
        if clean_official:
            if has_quotes:
                system_parts.append(
                    f"ОФИЦИАЛЬНОЕ НАЗВАНИЕ КОМПАНИИ (только написание): \"{clean_official}\". "
                    f"Используй именно это написание в кавычках. "
                    f"Узбекский порядок: имя ПЕРВЫМ: \"{clean_official}\" MChJ/XK/AJ. "
                    f"Дескрипторы (kafesi, markazi) — ПОСЛЕ: \"{clean_official}\" kafesi."
                )
            else:
                system_parts.append(
                    f"ОФИЦИАЛЬНОЕ НАЗВАНИЕ НА УЗБЕКСКОМ (только написание, БЕЗ кавычек): {clean_official}. "
                    f"Используй это написание. НЕ добавляй кавычки вокруг названия."
                )
        system_content = PROMPT_UZ
        if system_parts:
            system_content = "\n".join(system_parts) + "\n\n" + PROMPT_UZ
        # Добавляем явный счётчик предложений чтобы модель не сокращала текст
        _src_count = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', text)))
        if _src_count > 1:
            system_content = f"⚠️ MUHIM: Tarjimada ANIQ {_src_count} ta gap bo'lishi kerak — na ko'p, na kam.\n\n" + system_content
        user_msg = text
        prompt = system_content  # kept for retry prompts that prepend to it
    elif lang == "en":
        effective_form = official_subject or (form_match[2] if form_match else None)
        system_parts = []
        if effective_form:
            system_parts.append(
                f"⚠️ CRITICAL: Write the company form as the ABBREVIATION ONLY: {effective_form} "
                f"Do NOT expand it (e.g. do NOT write 'Private Enterprise' for PE, "
                f"do NOT write 'Limited' or 'Limited Liability Company' for LTD, "
                f"do NOT write 'Joint Venture' for JV). "
                f"Write ONLY the abbreviation: {effective_form} \"NAME\". "
                f"Do NOT add any extra word before or after the quoted name."
            )
        if clean_official:
            if has_quotes:
                system_parts.append(
                    f"OFFICIAL COMPANY NAME (spelling only): \"{clean_official}\". "
                    f"Use exactly this spelling in quotes. "
                    f"Forms (JSC, LTD, IE) go FIRST: JSC \"{clean_official}\". "
                    f"Descriptors go AFTER: \"{clean_official}\" cafe."
                )
            else:
                system_parts.append(
                    f"OFFICIAL COMPANY NAME IN ENGLISH (spelling only, NO quotes): {clean_official}. "
                    f"Use exactly this spelling. Do NOT add quotes around the name."
                )
        system_content = PROMPT_EN
        if system_parts:
            system_content = "\n".join(system_parts) + "\n\n" + PROMPT_EN
        user_msg = text
        prompt = system_content
    else:
        logger.error(f"Неизвестный язык перевода: {lang}")
        return text
    result = _call_api(client, user_msg, lang, system_prompt=system_content, temperature=0.3) or text
    if lang == 'uz':
        # Strip the "MAHSULOT: ..." line, keep only the <p>...</p> part
        _p_match = re.search(r'(<p>.*</p>)', result, re.DOTALL)
        if _p_match:
            result = _p_match.group(1)
        else:
            result = re.sub(r'^MAHSULOT:.*\n?', '', result, flags=re.IGNORECASE).strip()
        # Дополнительно чистим если MAHSULOT оказался внутри тега
        result = re.sub(r'MAHSULOT:\s*[^\n<]*\n?', '', result, flags=re.IGNORECASE).strip()
        for _attempt in range(2):
            if not _has_cyrillic_uz(result):
                break
            logger.warning(f"UZ перевод содержит кириллицу, повторяю (попытка {_attempt + 1}/2)...")
            cyrillic_sys = "⚠️ КРИТИЧНО: Перевод ДОЛЖЕН быть на узбекской ЛАТИНИЦЕ. НЕ используй кириллицу. O'zbek lotin alifbosida yoz.\n\n" + system_content
            result = _call_api(client, user_msg, lang, system_prompt=cyrillic_sys, temperature=0.3) or result
        if _has_cyrillic_uz(result):
            logger.warning("UZ перевод всё ещё содержит кириллицу после 2 повторных попыток")
        # Completeness check: UZ must have same sentence count as RU source
        # Сначала чистим от рекламных предложений, потом считаем
        result = _strip_ad_sentences(result)
        src_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', text)))
        out_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', result)))
        for _comp_attempt in range(2):
            if src_sentences <= 1 or out_sentences >= src_sentences:
                break
            logger.warning(f"UZ перевод неполный ({out_sentences} предл. vs {src_sentences} в оригинале), повторяю (попытка {_comp_attempt+1}/2)...")
            completeness_sys = (
                f"⚠️ TARJIMA TO'LIQ EMAS: asl matnda {src_sentences} ta gap bor, tarjimada faqat {out_sentences} ta. "
                f"Har bir gapni to'liq tarjima qil, hech narsani o'tkazib yubora.\n\n"
                + system_content
            )
            retry_result = _call_api(client, user_msg, lang, system_prompt=completeness_sys, temperature=0.5)
            if retry_result and not _has_cyrillic_uz(retry_result):
                _rp = re.search(r'(<p>.*</p>)', retry_result, re.DOTALL)
                if _rp:
                    retry_result = _rp.group(1)
                retry_result = re.sub(r'MAHSULOT:\s*[^\n<]*\n?', '', retry_result, flags=re.IGNORECASE).strip()
                retry_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', retry_result)))
                if retry_sentences > out_sentences:
                    result = retry_result
                    out_sentences = retry_sentences
    elif lang == 'en':
        for _attempt in range(2):
            if not _has_cyrillic(result):
                break
            logger.warning(f"EN перевод содержит кириллицу, повторяю (попытка {_attempt + 1}/2)...")
            result = _call_api(client, user_msg, lang, system_prompt=system_content, temperature=0.3) or result
        if _has_cyrillic(result):
            logger.warning("EN перевод всё ещё содержит кириллицу после 2 повторных попыток")
        # Проверка полноты EN — сначала чистим, потом считаем
        result = _strip_ad_sentences(result)
        src_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', text)))
        out_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', result)))
        for _comp_attempt in range(2):
            if src_sentences <= 1 or out_sentences >= src_sentences:
                break
            logger.warning(f"EN перевод неполный ({out_sentences} предл. vs {src_sentences} в оригинале), повторяю (попытка {_comp_attempt+1}/2)...")
            completeness_sys = (
                f"⚠️ INCOMPLETE TRANSLATION: source has {src_sentences} sentences, translation has only {out_sentences}. "
                f"Translate EVERY sentence fully — do not skip any content.\n\n"
                + system_content
            )
            retry_result = _call_api(client, user_msg, lang, system_prompt=completeness_sys, temperature=0.5)
            if retry_result and not _has_cyrillic(retry_result):
                retry_sentences = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', retry_result)))
                if retry_sentences > out_sentences:
                    result = retry_result
                    out_sentences = retry_sentences
    result = _fix_false_form(text, result, lang, has_quotes)
    if lang == 'uz':
        result = _fix_uz_capslock(result)
        result = re.sub(r'\[([^\]]+)\]', r'\1', result)
        # Убираем подряд идущие одинаковые слова в первых 8 токенах после имени компании.
        # Это ловит все случаи дублирования дескриптора: galereyasi galereyasi,
        # do'koni do'koni, qandolatchilik qandolatchilik и т.п.
        _apos = r"['''ʻʻʼʼ']"
        _norm_desc_words = frozenset(re.sub(_apos, "'", w) for w in _UZ_DESCRIPTOR_WORDS)
        def _dedup_consecutive(m):
            name_part = m.group(1)
            rest = m.group(2)
            tokens = rest.split()
            result_tokens = []
            prev_norm = None
            seen_desc = set()  # дескрипторные слова — только один раз в первых 8 токенах
            window = []  # скользящее окно последних 3 нормализованных токенов
            for i, tok in enumerate(tokens):
                tok_norm = re.sub(_apos, "'", tok.rstrip('.,;').lower())
                # Подряд идущий дубль — убираем
                if i < 8 and tok_norm == prev_norm and len(tok_norm) > 1:
                    continue
                # Слово встречается в окне последних 3 токенов (tikuv sexi tikuv)
                if i < 8 and len(tok_norm) > 3 and tok_norm in window:
                    continue
                # Дескрипторное слово повторяется в первых 8 токенах
                if i < 8 and tok_norm in _norm_desc_words and tok_norm in seen_desc:
                    continue
                if i < 8 and tok_norm in _norm_desc_words:
                    seen_desc.add(tok_norm)
                result_tokens.append(tok)
                prev_norm = tok_norm
                window = (window + [tok_norm])[-3:]
            return name_part + ' ' + ' '.join(result_tokens)
        result = re.sub(r'(<p>(?:[A-Z]{2,6}\s+)?[«"""][^«"""»]*[»"""])\s+(.+)', _dedup_consecutive, result)

    result = _strip_ad_sentences(result)

    # Заменяем канцеляризмы на активные глаголы
    if lang == 'en':
        for _pat, _repl in _CANCEL_EN:
            result = _pat.sub(_repl, result)
        result = re.sub(r'(?<!is )engaged in', 'is engaged in', result)
        result = re.sub(r'<p>It\s+(?=[A-Za-z])', '<p>The company ', result)
        result = re.sub(r'(?<=\.\s)It\s+(?=[a-z])', 'The company ', result)
    elif lang == 'uz':
        for _pat, _repl in _CANCEL_UZ:
            result = _pat.sub(_repl, result)

    # Валидация переводов с одним ретраем при FAIL
    if lang == 'uz':
        is_valid, reasons = _validate_uz(client, result)
        if not is_valid:
            logger.warning(f"UZ валидация FAIL, ретрай. Нарушения: {reasons}")
            retry_sys = f"⚠️ OLDINGI TARJIMADA XATOLAR: {reasons}\nQayta yozing, bu xatolardan qoching.\n\n{system_content}"
            retry_raw = _call_api(client, user_msg, lang, system_prompt=retry_sys, temperature=0.3)
            if retry_raw and not _has_cyrillic_uz(retry_raw):
                pm = re.search(r'(<p>.*</p>)', retry_raw, re.DOTALL)
                if pm:
                    retry_raw = pm.group(1)
                retry_raw = re.sub(r'\[([^\]]+)\]', r'\1', retry_raw)
                retry_raw = _fix_false_form(text, retry_raw, lang, has_quotes)
                retry_raw = _fix_uz_capslock(retry_raw)
                retry_raw = re.sub(r'(<p>[«"""][^«"""»]*[»"""])\s+(.+)', _dedup_uz_desc, retry_raw)
                result = _strip_ad_sentences(retry_raw)
    elif lang == 'en':
        is_valid, reasons = _validate_en(client, result)
        if not is_valid:
            logger.warning(f"EN валидация FAIL, ретрай. Нарушения: {reasons}")
            retry_sys = f"⚠️ PREVIOUS VERSION HAD VIOLATIONS: {reasons}\nRewrite fixing these issues.\n\n{system_content}"
            retry_raw = _call_api(client, user_msg, lang, system_prompt=retry_sys, temperature=0.3)
            if retry_raw and not _has_cyrillic(retry_raw):
                retry_raw = _fix_false_form(text, retry_raw, lang, has_quotes)
                stripped_retry = _strip_ad_sentences(retry_raw)
                orig_count = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', result)))
                retry_count = len(re.findall(r'[.!?]', re.sub(r'<[^>]+>', '', stripped_retry)))
                if retry_count >= orig_count:
                    result = stripped_retry
                else:
                    logger.warning(f"EN валидация ретрай уменьшил кол-во предложений ({orig_count}→{retry_count}), игнорируем")

    # EN: финальный гарантированный фикс "engaged in" без "is" (после всех ретраев)
    if lang == 'en':
        result = re.sub(r'(?<!is )(?<!was )(?<!are )(?<!were )engaged in', 'is engaged in', result)

    return result
