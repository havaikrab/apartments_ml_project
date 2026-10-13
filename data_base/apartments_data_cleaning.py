import logging
from typing import cast

import pandas as pd

from data_base.orm import DBConnection

logger = logging.getLogger()
pd.set_option("display.max_columns", 33)
pd.set_option("display.width", 100)

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

    no_price = data["total_rur_price"].isna() & data["last_price"].isna()
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


def set_base_price(data: pd.DataFrame) -> pd.DataFrame:
    """Определяет последнюю цену, заявленную в объявлении"""

    uncertain_rows = (
        data["last_price"].notna()
        & (data["total_rur_price"] != data["last_price"])
        & ((data["updated_at"] < data["price_updated_at"]) | data["updated_at"].isna())
    )
    data["price"] = data["total_rur_price"]
    data.loc[uncertain_rows, "price"] = data["last_price"]
    return data.drop(["total_rur_price", "last_price", "listing_price"], axis=1)


def drop_listing_duplicates(data: pd.DataFrame) -> pd.DataFrame:
    """Удаляет дубликаты оригинальных объявлений"""

    data["last_update"] = data[["updated_at", "price_updated_at"]].agg("max", axis=1)
    data = data.sort_values(["cian_listing_id", "last_update"], ascending=[True, True])
    data = data.drop_duplicates("cian_listing_id", keep="last")
    data = data.drop(columns=["last_update"])
    return data


def detect_suspicion_price(data: pd.DataFrame) -> pd.DataFrame:
    """Проверяет историю изменения цен на наличие подозрительных записей"""

    data["recorded_at"] = pd.to_datetime(data["recorded_at"], format="mixed", utc=True)
    data = data.sort_values(["listing_id", "recorded_at"]).reset_index(drop=True)
    set_nan = data.drop_duplicates(subset="listing_id", keep="first").index
    previous_price = data["price"].shift()
    previous_price.iloc[set_nan] = None
    data["previous_price"] = previous_price
    data["total_price_diff"] = data["price"] - data["previous_price"]
    data["price_diff_grade"] = abs(data["total_price_diff"] / data[["price", "previous_price"]].agg("min", axis=1))
    data["suspicious_status"] = "valid"
    diff_stats = data["price_diff_grade"].describe()
    suspiciously = data["price_diff_grade"]
    for status in ["low", "high", "extreme"]:
        tukey_level = 2.5 * diff_stats["75%"] - 1.5 * diff_stats["25%"]
        suspiciously = suspiciously[suspiciously > tukey_level]
        data.loc[suspiciously.index, "suspicious_status"] = status
        diff_stats = suspiciously.describe()
    suspicious_listings = data[data["suspicious_status"] == "extreme"]["listing_id"].unique()
    logger.warning(
        "Обнаружено %d строк c подозрительным изменением цены, соответствующие объявления не будут учтены в расчетах.",
        len(suspicious_listings),
    )
    data = data[~data["listing_id"].isin(suspicious_listings)]
    return data


def normalize_price_history(price_history_data: pd.DataFrame) -> pd.DataFrame:
    """Упорядочивает изменение цены для каждого сохраненного объявления"""

    price_history_data = currency_cleaner(price_history_data)
    price_history_data = detect_suspicion_price(price_history_data)
    price_history_data.sort_values(by=["listing_id", "recorded_at"], inplace=True)
    result = price_history_data.groupby("listing_id").agg(
        first_price=("price", "first"),
        last_price=("price", "last"),
        price_updated_at=("recorded_at", "last"),
        price_changes_count=("recorded_at", "count"),
        min_price=("price", "min"),
        max_price=("price", "max"),
        suspicious_status=("suspicious_status", "last"),
    )
    result["price_change_percent"] = (result["last_price"] - result["first_price"]) * 100 / result["first_price"]
    result = result.reset_index()
    numeric_columns = result.select_dtypes(include="number").columns
    result[numeric_columns] = result[numeric_columns].round(2)
    return cast(pd.DataFrame, result)


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
    result["created_at"] = pd.to_datetime(result["created_at"], format="mixed", utc=True)
    result["updated_at"] = pd.to_datetime(result["updated_at"], format="mixed", utc=True)
    return result


def clean_listings_data(data: pd.DataFrame) -> pd.DataFrame:
    """Очищает исходные данные"""

    data = data.copy()
    data = currency_cleaner(data)
    data = filter_by_deal_type(data)
    data = no_price_filter(data)
    data = filter_by_property_type(data)
    data = set_base_price(data)
    data = drop_listing_duplicates(data)
    return data


def suppose_missing_cities(data: pd.DataFrame) -> pd.DataFrame:
    """Устанавливает вероятное значение в столбце "city" для объявлений с пропущенным названием города"""

    data = data.sort_values("listing_id")
    data["is_original_city"] = data["city"].notna()
    previous_city = data["city"].ffill()
    next_city = data["city"].bfill()
    same_neighbors = data["city"].isna() & (previous_city == next_city)
    data.loc[same_neighbors, "city"] = previous_city.loc[same_neighbors]
    return data
