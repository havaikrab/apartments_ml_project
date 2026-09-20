import asyncio
import json
import logging

import zendriver as zd
from curl_cffi import AsyncSession, requests

logger = logging.getLogger()

REGION = "novosibirsk"
START_URL = f"https://{REGION}.cian.ru/"
CHECK_WORD = "Купить квартиру"
COOKIES_FILE = "data/cookies.json"
HEADERS_FILE = "data/headers.json"


async def get_browser_attributes() -> None:
    """Сохраняет куки и заголовки браузера"""

    browser = await zd.start()
    current_tab = browser.tabs[0]
    async with current_tab.expect_response(START_URL) as response:
        page = await current_tab.get(START_URL)
        await asyncio.sleep(5)
        page_content = await page.get_content()
        if CHECK_WORD in page_content:
            cookies = await browser.cookies.get_all()
            cookies_list = [cookie.to_json() for cookie in cookies]  # type: ignore
            cookies_dict = {c["name"]: c["value"] for c in cookies_list}
            logger.info("Куки сохранены")
            with open(COOKIES_FILE, "w", encoding="utf-8") as cookie_file:
                json.dump(cookies_dict, cookie_file, indent=4, ensure_ascii=False)
                logger.info("Куки сохранены")
            event = await response.request
            headers = dict(event.headers)
            with open(HEADERS_FILE, "w", encoding="utf-8") as headers_file:
                json.dump(headers, headers_file, ensure_ascii=False, indent=4)
                logger.info("Заголовки сохранены")
        else:
            logger.error("Не удалось получить куки и заголовки браузера")
    await asyncio.sleep(1)
    await browser.stop()


async def get_session() -> requests.AsyncSession:
    """Создает объект асинхронной сессии пользователя"""

    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as cookies_file:
            cookies = json.load(cookies_file)
        with open(HEADERS_FILE, "r", encoding="utf-8") as headers_file:
            headers = json.load(headers_file)
    except FileNotFoundError:
        await get_browser_attributes()
        with open(COOKIES_FILE, "r", encoding="utf-8") as cookies_file:
            cookies = json.load(cookies_file)
        with open(HEADERS_FILE, "r", encoding="utf-8") as headers_file:
            headers = json.load(headers_file)
    session = AsyncSession(impersonate="chrome")
    session.cookies.update(cookies)
    session.headers = headers
    return session


async def get_response() -> None:
    current_session = await get_session()
    async with current_session:
        response = await current_session.get("https://novosibirsk.cian.ru/sale/flat/333679548")
        with open("qwert.html", "w", encoding="utf-8") as file:
            file.write(response.text)


asyncio.run(get_response())
