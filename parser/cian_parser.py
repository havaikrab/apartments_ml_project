import asyncio
import json
import logging
from random import randint
from typing import cast

import zendriver as zd
from bs4 import BeautifulSoup
from curl_cffi import AsyncSession, requests

logger = logging.getLogger()

REGION = "novosibirsk"
START_URL = f"https://{REGION}.cian.ru/"
CHECK_WORD = "Купить квартиру"
COOKIES_FILE = "browser/cookies.json"
HEADERS_FILE = "browser/headers.json"
LISTING_TYPE = "sale"
PROPERTY_TYPE = "flat"
RANDOM_RANGE_START = 300000000
RANDOM_RANGE_END = 400000000
START_ID = 329497673
MAX_WAIT = 10


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


async def get_listing_data(session: AsyncSession, listing_id: int) -> dict:
    """Возвращает информацию из объявления в виде словаря"""

    url = f"https://{REGION}.cian.ru/{LISTING_TYPE}/{PROPERTY_TYPE}/{listing_id}"
    response = await session.get(url)
    if response.status_code == 403:
        logger.error("Запрос с id=%d был отклонен сервером cian.ru. Статус-код 403", listing_id)
        return {"parsing_status": "forbidden"}
    soup = BeautifulSoup(response.text, "html.parser")
    scripts = soup.find_all("script")
    for script in scripts:
        text = script.get_text()
        if "offerData" in text:
            try:
                additional_response = await session.post(
                    "https://api.cian.ru/search-engine/v3/get-similar-offers/", json={"cianOfferId": listing_id}
                )
                additional_offers = [offer.get("cianId") for offer in additional_response.json().get("offers", list())]
                script_tail = [part for part in text.split(".concat(") if "offerData" in part][0].split('offerData":')[
                    1
                ]
                depth = 0
                for i, char in enumerate(script_tail):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            json_body = script_tail[: i + 1]
                            result = cast(dict, json.loads(json_body))
                            result["parsing_status"] = "success"
                            result["additional_offers"] = additional_offers
                            return result
            except Exception as exc:
                logger.critical("Возникла ошибка при извлечении данных:\n%s", exc)
                return {"parsing_status": "internal_error"}
    return {"parsing_status": "empty_response"}


def clean_listing_data(listing_data: dict) -> None:
    """Извлекает необходимую информацию из словаря-объявления"""

    status = listing_data.get("parsing_status")
    if status == "success":
        print(listing_data.keys())


async def get_data() -> None:
    """Собирает информацию об объектах недвижимости с сайта cian.ru"""

    session = await get_session()
    explored = set()
    to_explore = list()
    async with session:
        data = await get_listing_data(session, START_ID)
        clean_listing_data(data)
        additional_ids = data.get("additional_offers", list())
        to_explore.extend(additional_ids)
        random_sleep = randint(1, MAX_WAIT)
        await asyncio.sleep(random_sleep)
        while len(to_explore) > 0:
            next_id = to_explore.pop(-1)
            explored.add(next_id)
            data = await get_listing_data(session, next_id)
            status = data.get("parsing_status")
            if status == "forbidden":
                break
            clean_listing_data(data)
            additional_ids = set(data.get("additional_offers", list())).difference(explored)
            to_explore.extend(list(additional_ids))
            random_sleep = randint(1, MAX_WAIT)
            await asyncio.sleep(random_sleep)


if __name__ == "__main__":
    asyncio.run(get_data())
