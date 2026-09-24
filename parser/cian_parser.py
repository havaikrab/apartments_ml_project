import asyncio
import json
import logging
from random import randint
from typing import cast

import zendriver as zd
from bs4 import BeautifulSoup
from curl_cffi import AsyncSession, requests

from data_base.cian_data_manager import save_cian_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


REGION = "novosibirsk"
START_URL = f"https://{REGION}.cian.ru/"
CHECK_WORD = "Купить квартиру"
COOKIES_FILE = "browser/cookies.json"
HEADERS_FILE = "browser/headers.json"
LISTING_TYPE = "sale"
PROPERTY_TYPE = "flat"
START_ID = 333226424
MAX_WAIT = 20


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
    logger.info("Сессия обновлена")
    return session


async def get_listing_data(session: AsyncSession, listing_id: int, update: bool) -> dict:
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
                            result["additional_offers"] = list()
                            result["source"] = f"https://{REGION}.cian.ru"
                            result["url"] = url
                            if update:
                                additional_response = await session.post(
                                    "https://api.cian.ru/search-engine/v3/get-similar-offers/",
                                    json={"cianOfferId": listing_id},
                                )
                                additional_ids = [
                                    offer.get("cianId") for offer in additional_response.json().get("offers", list())
                                ]
                                similar_listings = result.get("similarNewObjects", list())
                                similar_ids = [
                                    offer.get("id") for offer in similar_listings if isinstance(offer.get("id"), int)
                                ]
                                result["additional_offers"].extend(additional_ids)
                                result["additional_offers"].extend(similar_ids)
                            logger.info("Данные успешно получены")
                            return result
            except Exception as exc:
                logger.critical("Возникла ошибка при извлечении данных:\n%s", exc)
                return {"parsing_status": "internal_error"}
    logger.error("Запрос не вернул ожидаемых данных")
    return {"parsing_status": "empty_response"}


def clean_listing_data(listing_data: dict) -> dict:
    """Извлекает необходимую информацию из словаря-объявления"""

    status = listing_data.get("parsing_status")
    if status == "success":
        result: dict = {"apartments": dict(), "listings": dict(), "price_history": list()}
        result["apartments"]["property_type"] = listing_data.get("offer", dict()).get("offerType", "")
        result["apartments"]["flat_type"] = listing_data.get("offer", dict()).get("flatType", "")
        result["apartments"]["total_area"] = float(listing_data.get("offer", dict()).get("totalArea", 0))
        result["apartments"]["rooms_count"] = listing_data.get("offer", dict()).get("roomsCount", 1)
        result["apartments"]["floor_number"] = listing_data.get("offer", dict()).get("floorNumber", 1)
        result["apartments"]["total_floors"] = (
            listing_data.get("offer", dict()).get("building", dict()).get("floorsCount")
        )
        specifications = listing_data.get("newObject", dict()).get("specifications", list())
        result["apartments"]["building_material"] = None
        for spec in specifications:
            material_key = spec.get("title").lower()
            if material_key in ["тип дома"]:
                result["apartments"]["building_material"] = spec.get("value")
        ceiling_height = listing_data.get("offer", dict()).get("building", dict()).get("ceilingHeight")
        if ceiling_height is not None:
            result["apartments"]["ceiling_height"] = float(ceiling_height)
        else:
            result["apartments"]["ceiling_height"] = ceiling_height
        result["apartments"]["year_built"] = (
            listing_data.get("offer", dict()).get("building", dict()).get("deadline", dict()).get("year")
        )
        result["apartments"]["is_from_builder"] = (
            str(listing_data.get("offer", dict()).get("isFromBuilder")).lower() == "true"
        )
        result["apartments"]["is_complete_building"] = (
            str(
                listing_data.get("offer", dict()).get("building", dict()).get("deadline", dict()).get("isComplete")
            ).lower()
            == "true"
        )

        result["apartments"]["builder_name"] = None  # Пришло None в "company"
        result["apartments"]["cian_builder_id"] = None  # Пришло None в "company"
        company = listing_data.get("company", dict())  # Пришло None в "company"
        if company is not None:  # Пришло None в "company"
            result["apartments"]["builder_name"] = company.get("name")  # Пришло None в "company"
            result["apartments"]["cian_builder_id"] = company.get("id")  # Пришло None в "company"

        address_list = listing_data.get("offer", dict()).get("geo", dict()).get("address", list())
        for index in address_list:
            if index.get("type") == "location" and index.get("locationTypeId") == 1:
                result["apartments"]["city"] = index.get("name")
            elif index.get("type") == "raion":
                result["apartments"]["district"] = index.get("name")
            elif index.get("type") == "street":
                result["apartments"]["street"] = index.get("name")
            elif index.get("type") == "house":
                result["apartments"]["building_number"] = index.get("name")
                result["apartments"]["cian_building_code"] = index.get("id")

        result["listings"]["listing_type"] = listing_data.get("offer", dict()).get("dealType", "")
        result["listings"]["cian_listing_id"] = listing_data.get("offer", dict()).get("id")
        result["listings"]["total_rur_price"] = listing_data.get("offer", dict()).get("priceTotalRur")
        result["listings"]["listing_price"] = (
            listing_data.get("offer", dict()).get("bargainTerms", dict()).get("price")
        )
        result["listings"]["currency_code"] = (
            listing_data.get("offer", dict()).get("bargainTerms", dict()).get("currency")
        )
        result["listings"]["source"] = listing_data.get("source")
        result["listings"]["url"] = listing_data.get("url")
        result["listings"]["created_at"] = listing_data.get("offer", dict()).get("creationDate")
        result["listings"]["updated_at"] = listing_data.get("offer", dict()).get("editDate")
        result["listings"]["photos_count"] = len(listing_data.get("offer", dict()).get("photos", list()))

        result["price_history"] = [
            {
                "price": change.get("priceData", dict()).get("price"),
                "currency_code": change.get("priceData", dict()).get("currency"),
                "recorded_at": change.get("changeTime"),
            }
            for change in listing_data.get("priceChanges", list())
        ]
        logger.info("Данные успешно очищены")
        return result
    return dict()


async def get_data() -> None:
    """Собирает информацию об объектах недвижимости с сайта cian.ru"""

    session = await get_session()
    explored = set()
    to_explore = list()
    async with session:
        data = await get_listing_data(session, START_ID, True)
        cleaned_data = clean_listing_data(data)
        save_cian_data(cleaned_data)
        additional_ids = data.get("additional_offers", list())
        to_explore.extend(additional_ids)
        random_sleep = randint(1, MAX_WAIT)
        logger.info("Произвольное время ожидания перед следующим запросом %d секунд", random_sleep)
        await asyncio.sleep(random_sleep)
        while len(to_explore) > 0:
            if len(to_explore) < 10:
                next_id = to_explore.pop(0)
                update = True
            else:
                next_id = to_explore.pop(-1)
                update = False
            explored.add(next_id)
            data = await get_listing_data(session, next_id, update)
            status = data.get("parsing_status")
            if status == "forbidden":
                break
            cleaned_data = clean_listing_data(data)
            save_cian_data(cleaned_data)
            if update:
                additional_ids = set(data.get("additional_offers", list())).difference(explored)
                to_explore.extend(list(additional_ids))
            random_sleep = randint(1, MAX_WAIT)
            logger.info("Произвольное время ожидания перед следующим запросом %d секунд", random_sleep)
            await asyncio.sleep(random_sleep)


if __name__ == "__main__":
    asyncio.run(get_data())
