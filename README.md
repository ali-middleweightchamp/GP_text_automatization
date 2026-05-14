# GP Rewriter 

Автоматическое переписывание описаний компаний на 3 языках (RU/UZ/EN) с помощью AI.

## Технологии

- Python 3.13, Playwright, OpenAI GPT-4o-mini

## Что делает

- Авторизуется на admin.gpa.uz
- Берёт компании со статусом "Сгенерирована"
- Переписывает описания через GPT на русском
- Переводит на узбекский (латиница) и английский
- Берёт официальные названия с goldenpages.uz
- Сохраняет со статусом "Отмодерирована"

## Установка

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Заполни `.env` своими данными и запускай:

```bash
python main.py
```
