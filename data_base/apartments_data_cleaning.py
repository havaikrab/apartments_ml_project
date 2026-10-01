import logging
from typing import cast

import pandas as pd

from data_base.orm import DBConnection

logger = logging.getLogger()
pd.set_option("display.max_columns", 33)
pd.set_option("display.width", 170)

EXPECTED_CURRENCY = "rur"
DEAL_TYPE = "sale"
PROPERTY_TYPE = "flat"


def show_missed(data: pd.DataFrame) -> None:
    """Показывает статистику пропущенных значений"""

    missed_total = data.isna().sum()
    missed_percent = data.isna().mean() * 100
    missed = pd.concat({"missed_total": missed_total, "missed_percent": missed_percent}, axis=1)
    missed = missed[missed["missed_total"] > 0].round(2).sort_values("missed_total", ascending=False)
    print(missed)


def currency_cleaner(data: pd.DataFrame) -> pd.DataFrame:
    """Фильтрует DataFrame в соответствии с ожидаемым кодом валюты"""

    unexpected = data["currency_code"].isna() | (data["currency_code"] != EXPECTED_CURRENCY)
    if unexpected.sum() > 0:
        logger.warning(
            "Обнаружено %d строк c несоответствующей валютой, данные строки не будут учтены в расчетах.",
            unexpected.sum(),
        )
    return cast(pd.DataFrame, data[~unexpected])


def filter_by_deal_type(data: pd.DataFrame) -> pd.DataFrame:
    """Фильтрует объявления по типу сделки. Например: продажа-sale, аренда-rent"""

    unexpected = data["listing_type"].isna() | (data["listing_type"] != DEAL_TYPE)
    if unexpected.sum() > 0:
        logger.warning(
            "Обнаружено %d строк c несоответствующим типом сделки, данные строки не будут учтены в расчетах.",
            unexpected.sum(),
        )
    return cast(pd.DataFrame, data[~unexpected])


def no_price_filter(data: pd.DataFrame) -> pd.DataFrame:
    """Очищает DataFrame от строк без указания цены сделки"""

    no_price = data["total_rur_price"].isna()
    if no_price.sum() > 0:
        logger.warning(
            "Обнаружено %d строк без указания цены сделки, данные строки не будут учтены в расчетах.",
            no_price.sum(),
        )
    return cast(pd.DataFrame, data[~no_price])


def filter_by_property_type(data: pd.DataFrame) -> pd.DataFrame:
    """Фильтрует DataFrame по типу недвижимости. Например: квартиры-flat, нежилая-commercial"""

    unexpected = data["property_type"].isna() | (data["property_type"] != PROPERTY_TYPE)
    if unexpected.sum() > 0:
        logger.warning(
            "Обнаружено %d строк c несоответствующим типом недвижимости, данные строки не будут учтены в расчетах.",
            unexpected.sum(),
        )
    return cast(pd.DataFrame, data[~unexpected])


def normalize_price_history(price_history_data: pd.DataFrame) -> pd.DataFrame:
    """Упорядочивает изменение цены для каждого уникального объявления"""

    price_history_data = currency_cleaner(price_history_data)
    price_history_data.sort_values(by=["listing_id", "recorded_at"], inplace=True)
    result = price_history_data.groupby("listing_id").agg(
        first_price=("price", "first"),
        last_price=("price", "last"),
        price_updated_at=("recorded_at", "last"),
        price_changes_count=("price", "count"),
        min_price=("price", "min"),
        max_price=("price", "max"),
    )
    result["price_change_percent"] = (result["last_price"] - result["first_price"]) * 100 / result["first_price"]
    return cast(pd.DataFrame, result.reset_index().round(2))


def get_original_listings(
    db_name: str, apartments_table: str, listings_table: str, price_history_table: str
) -> pd.DataFrame:
    """Возвращает DataFrame объект, содержащий все объявления о продаже недвижимости"""

    db_connection = DBConnection(db_name)
    with db_connection:
        apartments = db_connection.select(apartments_table)
        listings = db_connection.select(listings_table)
        price_history = db_connection.select(price_history_table)
    price_history = normalize_price_history(price_history)
    apartments.rename(columns={"id": "apartment_id"}, inplace=True)
    result = apartments.merge(listings, on="apartment_id")
    result.rename(columns={"id": "listing_id"}, inplace=True)
    result = result.merge(price_history, on="listing_id")
    return result


def clean_listings_data(data: pd.DataFrame) -> pd.DataFrame:
    """Очищает исходные данные"""

    data = currency_cleaner(data)
    data = filter_by_deal_type(data)
    data = no_price_filter(data)
    data = filter_by_property_type(data)
    return data
