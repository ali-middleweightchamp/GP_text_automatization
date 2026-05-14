import os
from playwright.sync_api import Page


def login(page: Page) -> Page:
    site_url = os.getenv("SITE_URL")
    site_login = os.getenv("SITE_LOGIN")
    site_password = os.getenv("SITE_PASSWORD")

    page.goto(f"{site_url}/site/login")
    page.wait_for_load_state("domcontentloaded")

    page.fill('#loginform-username', site_login)
    page.fill('#loginform-password', site_password)

    remember_me = page.query_selector('#loginform-rememberme')
    if remember_me and not remember_me.is_checked():
        remember_me.check()

    with page.expect_navigation():
        page.click('button[name="login-button"]')

    print("Вход выполнен успешно")
    return page
