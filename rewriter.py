import os
import re
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─── Определение формы компании (Python, точно) ──────────────────────────────

# Все известные формы → (ru, uz, en)
_FORM_MAP = {
    'ООО':  ('ООО',  'MCHJ', 'LLC'),
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
    'ТМ':   ('ТМ',   'TM',   'TM'),
    'АО':   ('АО',   'AJ',   'JSC'),
    'УП':   ('УП',   'KK',   'UE'),
    'ГУП':  ('ГУП',  'DUK',  'SUE'),
    'САВДО БЕЛГИСИ': ('ТМ',  'Savdo belgisi', 'TM'),
    'MCHJ': ('ООО',  'MCHJ', 'LLC'),
    'OAJ':  ('ОАО',  'OAJ',  'OJSC'),
    'YoAJ': ('ЗАО',  'YoAJ', 'CJSC'),
    'YT':   ('ИП',   'YT',   'IE'),
    'XK':   ('ЗАО',  'XK',   'PE'),
    'AJ':   ('АО',   'AJ',   'JSC'),
    'KK':   ('УП',   'KK',   'UE'),
    'DUK':  ('ГУП',  'DUK',  'SUE'),
    'LLC':  ('ООО',  'MCHJ', 'LLC'),
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
    'PE':   ('ЧП',   'XK',   'PE'),
    'SUE':  ('ГУП',  'DUK',  'SUE'),
    # ── Новые формы ──────────────────────────────────────────
    'ПКП':  ('ПКП',  'PKK',  'CCP'),
    'МП':   ('МП',   'MK',   'ME'),
    'КПП':  ('КПП',  'QXK',  'CME'),
    'ПП':   ('ПП',   'IK',   'PE'),
    'ТЗБ':  ('ТЗБ',  'TZB',  'CTB'),
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


def _detect_unknown_form(company_name: str) -> tuple[str, str, bool] | None:
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


def detect_subject(company_name: str, lang: str) -> tuple[str, str, bool]:
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

    # Если в названии есть кавычки — берём только их содержимое
    m = re.search(r'[«"""]([^«"""»]+)[»"""]', company_name)
    clean = m.group(1).strip() if m else company_name.strip('«»"""\'"').strip()
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
  НЕПРАВИЛЬНО: Завод "КОКАНДСКИЙ СУПЕРФОСФАТНЫЙ" / Организация ШАХРИСАБЗСКОЕ ПЭС / "ФЕРГАНСКИЙ..." занимается...
  ПРАВИЛЬНО: КОКАНДСКИЙ СУПЕРФОСФАТНЫЙ ЗАВОД занимается... / ШАХРИСАБЗСКОЕ ГОРОДСКОЕ ПЭС осуществляет...

Если {has_quotes} = True и СУБЪЕКТ ≠ AUTO → начни точно так: {subject} "{clean_name}"
  Примеры: ООО "AMEKS TRAVEL" / Кафе "ARIANA" / Центр "ASTIGMATI-SERVIS"

Если {has_quotes} = True и СУБЪЕКТ = AUTO → КРИТИЧНО: пиши слово по {alt_idx}, затем название В КАВЫЧКАХ:
  0 = Организация "{clean_name}"
  1 = Компания "{clean_name}"
  2 = Предприятие "{clean_name}"
  КАВЫЧКИ ВОКРУГ НАЗВАНИЯ ОБЯЗАТЕЛЬНЫ. Пример: clean_name=MONTELLA DAILY, alt_idx=0 → Организация "MONTELLA DAILY" занимается...

ПРАВИЛА ТЕКСТА:
- 3-5 предложений, сохраняй объём исходного текста — не урезай
- Только факты: чем занимается, какие услуги, что производит
- ЗАПРЕЩЕНО рекламные слова и фразы: "широкий спектр", "высокое качество", "качественный/качественные/качественными", "комфортный", "динамично развивается", "является лидером", "квалифицированные специалисты", "что позволяет удовлетворить", "разнообразные", "различные", "уникальный", "особый", "индивидуальный подход", "эффективный/эффективно", "надёжный/надёжно", "профессиональный", "для улучшения", "на высоком уровне", "в сфере", "в области", "современный", "передовой", "инновационный", "оптимальный"
- ЗАПРЕЩЕНО: сайт, веб-ресурс, соцсети, контакты
- ЗАПРЕЩЕНО: Ташкент и Узбекистан (кроме случаев когда компания работает по всей стране)
- ЗАПРЕЩЕНО: повторять одну информацию дважды
- ЗАПРЕЩЕНО: местоимения — она, он, они, оно, её, его, их. Вместо местоимения повтори название или используй "Также выполняет...", "Дополнительно оказывает..."
- ⚠️ ЧЕРЕДОВАНИЕ ГЛАГОЛОВ КРИТИЧНО: каждое предложение должно начинаться с РАЗНОГО глагола.
  ЗАПРЕЩЕНО использовать слово «занимается» более одного раза.
  Варианты для первого предложения:
  специализируется на / осуществляет / предоставляет / оказывает / выполняет / производит / реализует / ведёт деятельность
  Варианты для второго предложения (связка + глагол):
  Также выполняет / Дополнительно осуществляет / В сферу деятельности входит / Среди направлений работы — / К основным услугам относятся / Реализует также / Помимо этого оказывает / Кроме того предоставляет
- Сохрани теги <p> в начале и </p> в конце
- Если в названии есть слово ФИЛИАЛ/FILIALI/BRANCH — упоминай его только если это важная информация. Не добавляй географический филиал если он не меняет суть деятельности компании
- Верни только текст, без комментариев"""

PROMPT_UZ = """⚠️ КРИТИЧНО: Пиши ТОЛЬКО на узбекской ЛАТИНИЦЕ (lotin alifbosi). НЕ используй кириллицу. Только латинские буквы и апострофы (o', g', sh, ch).

⚠️ КРИТИЧНО: Переводи ВЕСЬ текст полностью — каждое предложение, каждую мысль. НЕ сокращай, НЕ пропускай предложения, сохраняй объём оригинала.

Переведи на узбекский язык.
1. Переводи естественно, не дословно.
2. Формы компаний: ООО→MCHJ, ИП→YT, ЧП→XK, ЧПФ→XKF, ТМ→Savdo belgisi (TM), МЧП→MCHX, ГП→DK, КФХ→DXK, АО→AJ, УП→KK, ГУП→DUK.
3. Если название БЕЗ кавычек — переводи название полностью на узбекский по смыслу. Само название пиши ЗАГЛАВНЫМИ буквами, остальной текст — обычным регистром:
   - ШАХРИСАБЗСКОЕ ГОРОДСКОЕ ПЭС → SHAHRISABZ SHAHAR ETK energiya ta'minoti bilan shug'ullanadi...
   - КОКАНДСКИЙ СУПЕРФОСФАТНЫЙ ЗАВОД → QO'QON SUPERFOSFAT ZAVODI mineral o'g'itlar ishlab chiqaradi...
   - ФЕРГАНСКИЙ НЕФТЕПЕРЕРАБАТЫВАЮЩИЙ ЗАВОД → FARG'ONA NEFTNI QAYTA ISHLASH ZAVODI...
   Аббревиатуры: ПЭС→ETK, ТЭС→IES, ГЭС→GES, РЭС→RETK
   Писать БЕЗ кавычек, БЕЗ tashkiloti/kompaniyasi в конце.
4. Сохрани <p> и </p>.
5. ⚠️ СТРУКТУРА ДЛЯ НАЗВАНИЙ С КАВЫЧКАМИ — ОБЯЗАТЕЛЬНО:
   Название ПЕРВОЕ в кавычках, дескриптор ПОСЛЕ с суффиксом -i/-si. БЕЗ ИСКЛЮЧЕНИЙ:
   Кафе "ARIANA" → "ARIANA" kafesi
   Ресторан "AMUDARYA" → "AMUDARYA" restorani
   Компания "ALX.UZ" → "ALX.UZ" kompaniyasi
   Организация "NAME" → "NAME" tashkiloti
   Предприятие "NAME" → "NAME" korxonasi
   Стоматология "ALVA-DENT" → "ALVA-DENT" stomatologiyasi
   Центр "ASTIGMATI-SERVIS" → "ASTIGMATI-SERVIS" markazi
   Клиника "НАЗВАНИЕ" → "НАЗВАНИЕ" klinikasi
   Адвокатская фирма "НАЗВАНИЕ" → "НАЗВАНИЕ" advokatlik firmasi
   Торговый центр "НАЗВАНИЕ" → "НАЗВАНИЕ" savdo markazi
   Банк "НАЗВАНИЕ" → "НАЗВАНИЕ" banki
   Агрофирма "НАЗВАНИЕ" → "НАЗВАНИЕ" agrofirmasi
   Завод "НАЗВАНИЕ" → "НАЗВАНИЕ" zavodi
   Фабрика "НАЗВАНИЕ" → "НАЗВАНИЕ" fabrikasi
   ИСКЛЮЧЕНИЕ: формы компаний (MCHJ, XKF, TM, YT, XK, AJ, KK, DUK) идут В НАЧАЛЕ: MCHJ "НАЗВАНИЕ", XKF "НАЗВАНИЕ", TM "НАЗВАНИЕ"
   Пример: ТМ "АВТОМИР" → TM "AVTOMIR" (НЕ "AVTOMIR" kompaniyasi)
6. ПРАВИЛО ДЛЯ НАЗВАНИЯ В КАВЫЧКАХ:
   - Латиница (GOLDEN PAGES, AQUALAND, ALX.UZ) → НЕ переводить, оставить как есть
   - Кириллица, коммерческий бренд (АЛТЫН БЕТ) → транслитерировать (ALTYN BET)
   - Кириллица, описательное/государственное название (НАУЧНО-ПРОИЗВОДСТВЕННОЕ ОБЪЕДИНЕНИЕ, РЕСПУБЛИКАНСКИЙ ЦЕНТР) → переводить на узбекский
   Примеры: MCHJ "GOLDEN PAGES" (не переводим) / AJ "ILMIY-ISHLAB CHIQARISH BIRLASHMASI..." (переводим)
7. РЕГИСТР: Пиши текст в нормальном регистре — первая буква заглавная, остальные строчные. ЗАПРЕЩЕНО писать весь текст заглавными буквами. Исключение: название организации без кавычек пиши ЗАГЛАВНЫМИ, остальной текст — обычным регистром.
8. ⚠️ FE'LLARNI ALMASHTIRISH SHART: har bir gap turli fe'l bilan boshlanishi MAJBURIY.
   'shug'ullanadi' so'zini bir martadan ko'p ishlatish TAQIQLANGAN.
   Birinchi gap uchun: ixtisoslashgan / amalga oshiradi / taqdim etadi / ko'rsatadi / bajaradi / ishlab chiqaradi / faoliyat yuritadi
   Ikkinchi gap uchun (bog'lovchi + fe'l):
   Bundan tashqari amalga oshiradi / Qo'shimcha ravishda taqdim etadi / Asosiy faoliyatdan tashqari bajaradi / Shuningdek ko'rsatadi
9. ⚠️ ISMLAR VA FAMILIYALAR — o'zgartirmang.
   Agar nomda shaxs familiyasi yoki initiallari bo'lsa (QO'CHQOROV A.E., TOSHMATOV B.) — aynan shunday qoldiring. Tarjima qilmang va transkripsiyani o'zgartirmang.
10. TAQIQLANGAN: shahar nomlari (Toshkent, Samarqand, Farg'ona va boshqalar) va O'zbekiston deb yozish (agar kompaniya butun mamlakat bo'ylab faoliyat ko'rsatmasa).
Только перевод:
{text}"""

PROMPT_EN = """⚠️ CRITICAL: Translate the ENTIRE text to English. Every single word must be in English.
NEVER leave any Russian words in the output. Translate the FULL body, not just the company name.
⚠️ CRITICAL: Translate EVERY sentence completely — do NOT shorten, do NOT skip sentences, preserve the volume of the original.

WRONG: FERGANA PETROLEUM REFINERY PLANT занимается производством битума...
RIGHT: FERGANA PETROLEUM REFINERY PLANT is engaged in the production of bitumen...

Translate to English. Replace forms: ООО→LLC, ИП→IE, ЧП→PE, ЧПФ→PE, ТМ→TM, МЧП→SPE, ГП→SE, КФХ→PFE, АО→JSC, УП→UE, ГУП→SUE. Keep <p> and </p>.
If the name has NO quotes — translate the full name into English by meaning. Write the name in ALL CAPS, the rest of the text in normal case:
- ШАХРИСАБЗСКОЕ ГОРОДСКОЕ ПЭС → SHAKHRISABZ CITY ELECTRIC NETWORKS ENTERPRISE provides energy supply...
- КОКАНДСКИЙ СУПЕРФОСФАТНЫЙ ЗАВОД → KOKAND SUPERPHOSPHATE PLANT produces mineral fertilizers...
- ФЕРГАНСКИЙ НЕФТЕПЕРЕРАБАТЫВАЮЩИЙ ЗАВОД → FERGANA OIL REFINERY PLANT...
Abbreviations: ПЭС→Electric Networks Enterprise, ТЭС→Thermal Power Station, ГЭС→Hydroelectric Power Station, РЭС→Regional Electric Networks, ПТС→Heat Supply Enterprise
Write WITHOUT quotes, WITHOUT adding "The organization/The company" before it.
RULE FOR QUOTED NAMES:
- Latin script (GOLDEN PAGES, AQUALAND, ALX.UZ) → do NOT translate, keep as is
- Cyrillic, commercial brand (АЛТЫН БЕТ) → transliterate (ALTYN BET)
- Cyrillic, descriptive/state name (НАУЧНО-ПРОИЗВОДСТВЕННОЕ ОБЪЕДИНЕНИЕ, РЕСПУБЛИКАНСКИЙ ЦЕНТР) → translate to English
Examples: LLC "GOLDEN PAGES" (keep) / JSC "SCIENTIFIC-PRODUCTION ASSOCIATION..." (translate)
WORD ORDER: company form ALWAYS goes FIRST, then the name in DOUBLE QUOTES.
RIGHT: LLC "GOLDEN PAGES", IE "QO'CHQOROV A.E.", LLC "DELUXE FABRIC", ME "OSIYO BAZIS"
WRONG: "GOLDEN PAGES" LLC / GOLDEN PAGES LLC / GOLDEN PAGES LTD. / DELUXE FABRIC LTD.
REGISTER: Write text in normal case — first letter uppercase, rest lowercase. NEVER write the entire text in ALL CAPS. Exception: organization name without quotes must be in ALL CAPS, the rest of the text in normal case.
⚠️ VARY VERBS — CRITICAL: each sentence must start with a DIFFERENT verb.
Using 'is engaged in' more than once is FORBIDDEN.
First sentence variants: specializes in / carries out / provides / offers / performs / produces / operates / focuses on
Second sentence variants (connector + verb):
In addition, provides / Additionally, carries out / Furthermore, offers / Beyond its core activities, performs / It also produces
⚠️ NAMES AND SURNAMES IN THE COMPANY NAME — do NOT translate or change transliteration.
If the name contains a person's surname or initials (e.g. QO'CHQOROV A.E., TOSHMATOV B.) — leave them EXACTLY as written.
WRONG: KUCHKAROV A.E.
RIGHT: QO'CHQOROV A.E.
Only translation:
{text}"""


def init_openai():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r'[а-яА-Я]', text))


def _has_cyrillic_uz(text: str) -> bool:
    text_no_quotes = re.sub(r'"[^"]*"', '', text)
    return bool(re.search(r'[а-яА-ЯёЁ]', text_no_quotes))


def _call_api(client: OpenAI, prompt: str, lang_label: str) -> str | None:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            time.sleep(2)
            return response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                wait = 30
                logger.warning(f"Rate limit, жду {wait} сек (попытка {attempt+1}/3)...")
                time.sleep(wait)
            else:
                logger.error(f"Ошибка OpenAI API ({lang_label}): {e}")
                return None
    logger.error(f"OpenAI API не ответил после 3 попыток ({lang_label})")
    return None


def _fix_ru_subject(result: str, clean_name: str, has_quotes: bool, subject: str, alt_idx: int) -> str:
    """Постобработка RU: восстанавливает субъект и кавычки если модель их потеряла."""
    if not has_quotes or not clean_name:
        return result

    def _name_quoted(text: str) -> bool:
        return bool(re.search(r'[«""]' + re.escape(clean_name) + r'[»""]', text))

    def _normalize_quotes(text: str) -> str:
        """Заменяет «NAME» → "NAME" для единообразной дальнейшей обработки."""
        return re.sub(r'[«"](' + re.escape(clean_name) + r')[»"]', r'"\1"', text)

    # Случай 1: subject != AUTO, но кавычки потерялись вокруг clean_name
    if subject != 'AUTO':
        if _name_quoted(result):
            return _normalize_quotes(result)
        if clean_name in result:
            result = result.replace(clean_name, f'"{clean_name}"', 1)
        return result

    # Случай 2: subject == AUTO — должно быть Компания/Организация/Предприятие "NAME"
    words = ['Организация', 'Компания', 'Предприятие']
    word = words[alt_idx % 3]

    # Нормализуем гильометры → прямые кавычки
    result = _normalize_quotes(result)

    has_subject_word = bool(re.search(
        r'(?:Организация|Компания|Предприятие)',
        result[:80], re.IGNORECASE
    ))
    has_quoted = f'"{clean_name}"' in result

    # Уже правильно
    if has_subject_word and has_quoted:
        return result

    # Субъект есть, но имя без кавычек: <p>Компания NAVRUZ ...
    # (?!\w) вместо \b чтобы работало для имён заканчивающихся на . или - (R.A., CLEAN-WORK)
    subj_bare = re.compile(
        r'(<p>\s*(?:Организация|Компания|Предприятие)\s+)' + re.escape(clean_name) + r'(?!\w)',
        re.IGNORECASE
    )
    m = subj_bare.search(result)
    if m:
        return subj_bare.sub(lambda x: x.group(1) + f'"{clean_name}"', result, count=1)

    # Кавычки есть, но субъекта нет: <p>"NAVRUZ" ...
    quoted_pattern = re.compile(r'<p>\s*"' + re.escape(clean_name) + r'"')
    if quoted_pattern.search(result):
        return quoted_pattern.sub(f'<p>{word} "{clean_name}"', result, count=1)

    # Ни кавычек, ни субъекта: <p>NAVRUZ ...
    name_pattern = re.compile(r'<p>\s*' + re.escape(clean_name) + r'(?!\w)', re.IGNORECASE)
    if name_pattern.search(result):
        result = name_pattern.sub(f'<p>{word} "{clean_name}"', result, count=1)

    return result


def rewrite(client: OpenAI, text: str, company_name: str = "", subject: str = "AUTO", clean_name: str = "", alt_idx: int = 0, has_quotes: bool = True) -> str:
    """Рерайт на русском."""
    if not text or not text.strip():
        return text
    prompt = PROMPT_RU.format(text=text, company_name=company_name, subject=subject, clean_name=clean_name or company_name, alt_idx=alt_idx, has_quotes=has_quotes)
    result = _call_api(client, prompt, "ru") or text
    result = _fix_ru_subject(result, clean_name or company_name, has_quotes, subject, alt_idx)
    return result


def _fix_false_form(original_ru: str, translated: str, lang: str, has_quotes: bool = True) -> str:
    """Убирает форму компании из перевода, если её не было в оригинале."""
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

        def _fix_uz_subject(m):
            name = m.group(1)
            after = m.group(2)
            first_word = after.strip().split()[0].rstrip('.,;') if after.strip() else ''
            if first_word.lower() in _UZ_DESCRIPTOR_WORDS:
                return f'<p>{name} {after}'
            desc = uz_desc or 'kompaniyasi'
            return f'<p>{name} {desc} {after}'

        translated = re.sub(r'<p>(".*?")\s*(.*)', _fix_uz_subject, translated)

    elif lang == 'en' and re.match(r'<p>\s*"', translated):
        translated = re.sub(r'<p>\s*"', '<p>The company "', translated, count=1)

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
    for abbr in sorted(_UZ_FORM_ABBRS, key=len, reverse=True):
        result = re.sub(r'\b' + re.escape(abbr.lower()) + r'\b', abbr, result, flags=re.IGNORECASE)
    return result


def _detect_form_in_text(text: str) -> tuple | None:
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
        return m.group(1).strip()
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
    r'specializes|carries|provides|offers|performs|produces|operates|focuses|engaged|delivers|'
    r'manufactures|supplies|ixtisoslashgan|faoliyat|taqdim|bajaradi|ishlab)\b',
    re.IGNORECASE,
)


def _normalize_uz_name(name: str) -> str:
    """'"NAME" FORM' → 'FORM "NAME"' если FORM — известная UZ-аббревиатура (MCHJ, QK, AJ…)."""
    m = re.match(r'^("[^"]*")\s+([A-Za-z][A-Za-z0-9]*)\s*$', name)
    if m and m.group(2).upper() in _UZ_FORM_ABBRS:
        return f'{m.group(2)} {m.group(1)}'
    return name


_EN_FORM_SUFFIX_RE = re.compile(
    r'\s+(LLC|LTD|OJSC|CJSC|JSC|IE|PE|ME|SUE|JV|ALC|SP|MUE|UE|SE|PCB|JISB|JSB)\s*$',
    re.IGNORECASE,
)


def _normalize_en_name(name: str) -> str:
    """Преобразует goldenpages EN формат 'NAME FORM.' или 'NAME. FORM DESC' в 'FORM "NAME"'."""
    name = name.rstrip('.')
    # Pattern: "NAME. FORM DESCRIPTOR" (точка отделяет имя от дескриптора)
    dot_m = re.match(r'^(.*?)\.\s+([A-Z].+)$', name)
    if dot_m:
        base = dot_m.group(1).strip()
        # Восстанавливаем точку если base заканчивается на одиночную заглавную букву (инициал: R.A → R.A.)
        if re.search(r'(?<![A-Z])[A-Z]$', base):
            base += '.'
        form_part = dot_m.group(2).strip().rstrip('.')
        form_part = re.sub(r'\s+on\s+[\w.][\w\s,.]+$', '', form_part, flags=re.IGNORECASE).strip()
        form_part = re.sub(r'\s+in\s+[\w.][\w\s,.]+$', '', form_part, flags=re.IGNORECASE).strip()
        return f'{form_part} "{base}"'
    # Pattern: "NAME FORM" или "NAME FORM."
    form_m = _EN_FORM_SUFFIX_RE.search(name)
    if form_m:
        form = form_m.group(1)
        base = name[:form_m.start()].strip()
        return f'{form} "{base}"'
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
    clean = re.sub(r'\s+in\s+[\w.][\w\s,.]+$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s+on\s+[\w.][\w\s,.]+$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s+-\s+[\w.][\w\s,.]+$', '', clean).strip()
    clean = re.sub(r"\s+\w+\s+ko[''']chasida\b.*$", '', clean, flags=re.IGNORECASE).strip()
    clean = clean.rstrip('.')
    if not clean:
        return generated_text

    # Если clean — имя без кавычек, но в generated_text оно стоит в кавычках — сохраняем кавычки.
    # Делаем ДО AUTO-check, чтобы AUTO-check видел уже обёрнутое "ИМЯ".
    if not re.search(r'[«"""]', clean):
        if re.search(r'[«"""]' + re.escape(clean) + r'[»"""]', generated_text[:200]):
            clean = f'"{clean}"'

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

    # RU: '"NAME" ФОРМА/ДЕСКРИПТОР' → 'ФОРМА/ДЕСКРИПТОР "NAME"'
    if lang == 'ru' and re.search(r'[«"""]', clean):
        for label in _RU_ALL_LABELS_SORTED:
            m = re.match(r'^("[^"]*")\s+(' + re.escape(label) + r')\s*$', clean, re.IGNORECASE)
            if m:
                clean = f'{m.group(2)} {m.group(1)}'
                break

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
                    clean = f'{m_post.group(1)} {post.lower()}'

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
        if vm and vm.start() < 40:
            description = after_quote[vm.start():]
            if description:
                return f'{p_tag}{clean} {description}'

        # UZ / EN: убираем trailing ALL-CAPS слова (форма/дескриптор из сгенерированного)
        description = re.sub(r'^\s*(?:[A-ZА-ЯЁ]{2,}\'?\s*)+', '', after_quote).lstrip()
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
                m_ud = re.match(r'^(\w[\w\']*)\s+', description)
                if m_ud and m_ud.group(1).lower() in _UZ_DESCRIPTOR_WORDS:
                    description = description[m_ud.end():]
        if description:
            return f'{p_tag}{clean} {description}'

    # ── Стратегия 2: без кавычек → первый глагол-сказуемое ───────────────────
    vm = _ANY_VERB_RE.search(content)
    if vm:
        return f'{p_tag}{clean} {content[vm.start():]}'

    return generated_text


def translate(client: OpenAI, text: str, lang: str, has_quotes: bool = True,
              official_name: str = "", official_subject: str = "") -> str:
    """Перевод готового русского текста на uz или en."""
    if not text or not text.strip():
        return text

    # Для названий с кавычками — передаём только чистое название (без формы/города).
    # Если has_quotes=True, но официальное название не содержит кавычек — не используем его
    # как spelling hint (иначе _extract_clean_official обрежет инициалы по точке).
    if has_quotes:
        if official_name and re.search(r'[«"""]', official_name):
            clean_official = _extract_clean_official(official_name)
        else:
            clean_official = ''
    else:
        clean_official = official_name

    # Определяем форму компании в тексте для жёсткой подсказки
    form_match = _detect_form_in_text(text)

    if lang == "uz":
        prompt = PROMPT_UZ.format(text=text)
        # Форма из официального названия имеет приоритет над формой из русского текста
        effective_form = official_subject or (form_match[1] if form_match else None)
        # Если форма не определена — пробуем извлечь дескриптор из официального UZ названия
        # (например "NAME" AGROFIRMASI → effective_form = 'agrofirmasi')
        if not effective_form and official_name and has_quotes:
            _m_post = re.match(r'^"[^"]*"\s+(\S+)', official_name.strip())
            if _m_post:
                _post = _m_post.group(1).strip().lower()
                if _post.upper() not in _UZ_FORM_ABBRS:
                    effective_form = _post
        if effective_form:
            form_hint = (
                f"⚠️ КРИТИЧНО: Форма/дескриптор компании ОБЯЗАТЕЛЬНО должна быть \"{effective_form}\" "
                f"(взята из официального источника). НЕ заменяй на MCHJ, AJ или другую форму. "
                f"Пример: \"NAME\" {effective_form} (название ПЕРВЫМ в кавычках, затем {effective_form}).\n\n"
            )
            prompt = form_hint + prompt
        if clean_official:
            if has_quotes:
                hint = (
                    f"ОФИЦИАЛЬНОЕ НАЗВАНИЕ КОМПАНИИ (только написание): \"{clean_official}\"\n"
                    f"Используй именно это написание в кавычках. "
                    f"Правила субъекта соблюдай: формы (AJ, MCHJ, YT) идут ПЕРВЫМИ: AJ \"{clean_official}\". "
                    f"Дескрипторы (kafesi, markazi) — ПОСЛЕ: \"{clean_official}\" kafesi.\n"
                )
            else:
                hint = (
                    f"ОФИЦИАЛЬНОЕ НАЗВАНИЕ НА УЗБЕКСКОМ (только написание, БЕЗ кавычек): {clean_official}\n"
                    f"Используй это написание. НЕ добавляй кавычки вокруг названия.\n"
                )
            prompt = hint + prompt
    elif lang == "en":
        prompt = PROMPT_EN.format(text=text)
        effective_form = official_subject or (form_match[2] if form_match else None)
        if effective_form:
            form_hint = (
                f"⚠️ CRITICAL: The company form MUST be {effective_form} "
                f"(from official source). Do NOT replace with LLC, JSC or any other form. "
                f"Use exactly {effective_form}.\n\n"
            )
            prompt = form_hint + prompt
        if clean_official:
            if has_quotes:
                hint = (
                    f"OFFICIAL COMPANY NAME (spelling only): \"{clean_official}\"\n"
                    f"Use exactly this spelling in quotes. "
                    f"Keep subject rules: forms (JSC, LLC, IE) go FIRST: JSC \"{clean_official}\". "
                    f"Descriptors go AFTER: \"{clean_official}\" cafe.\n"
                )
            else:
                hint = (
                    f"OFFICIAL COMPANY NAME IN ENGLISH (spelling only, NO quotes): {clean_official}\n"
                    f"Use exactly this spelling. Do NOT add quotes around the name.\n"
                )
            prompt = hint + prompt
    else:
        logger.error(f"Неизвестный язык перевода: {lang}")
        return text
    result = _call_api(client, prompt, lang) or text
    if lang == 'uz':
        for _attempt in range(2):
            if not _has_cyrillic_uz(result):
                break
            logger.warning(f"UZ перевод содержит кириллицу, повторяю (попытка {_attempt + 1}/2)...")
            retry_prompt = "⚠️ КРИТИЧНО: Перевод ДОЛЖЕН быть на узбекской ЛАТИНИЦЕ. НЕ используй кириллицу. O'zbek lotin alifbosida yoz.\n\n" + prompt
            result = _call_api(client, retry_prompt, lang) or result
        if _has_cyrillic_uz(result):
            logger.warning("UZ перевод всё ещё содержит кириллицу после 2 повторных попыток")
    elif lang == 'en':
        for _attempt in range(2):
            if not _has_cyrillic(result):
                break
            logger.warning(f"EN перевод содержит кириллицу, повторяю (попытка {_attempt + 1}/2)...")
            result = _call_api(client, prompt, lang) or result
        if _has_cyrillic(result):
            logger.warning("EN перевод всё ещё содержит кириллицу после 2 повторных попыток")
    result = _fix_false_form(text, result, lang, has_quotes)
    if lang == 'uz':
        result = _fix_uz_capslock(result)
    return result
