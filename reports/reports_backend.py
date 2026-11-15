import datetime
import os

import pandas as pd
from dotenv import load_dotenv
from IPython.display import Markdown, display

from data_base.apartments_data_cleaning import (
    DEAL_TYPE,
    EXPECTED_CURRENCY,
    GEOGRAPHIC_SIGNS,
    PROPERTY_TYPE,
    clean_listings_data,
    detect_suspicion_price,
    get_original_listings,
    show_missed,
)
from data_base.orm import DBConnection

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "apartments.db")
PATH_TO_DB = f"../{DB_NAME}"


def show_markdown_missing(data: pd.DataFrame) -> None:
    """Формирует Markdown-таблицу с отчетом о пропусках для отображения в Jupyter notebook"""

    missed = show_missed(data)
    md_lines = [
        "## Статистика пропущенных значений",
        "| Признак | Всего пропусков | Процент пропусков |",
        "|:---|:---:|:---:|",
    ]
    for row in missed.index:
        md_lines.append(f"| {row} | {missed.loc[row, missed.columns[0]]} | {missed.loc[row, missed.columns[1]]} % |")
    display(Markdown("\n".join(md_lines)))


def show_cbc_profit(data: pd.DataFrame) -> None:
    """Формирует Markdown-таблицу с отчетом о пользе поля "cian_building_code"
    при восстановлении пропущенных значений географических признаков"""

    now = datetime.datetime.now().date()
    md_lines = [
        f"### Польза cian_building_code при восстановлении географических признаков на {now}",
        "| Признак | Указанных значений | Пропусков | Можно восстановить |",
        "| :--- | :---: | :---: | :---: |",
    ]
    known_code_data = data[data["cian_building_code"].notna()].copy()
    for sign in GEOGRAPHIC_SIGNS:
        signed_data = known_code_data.copy()
        signed_data = signed_data[signed_data[sign].notna()]
        codes_with_sign = signed_data["cian_building_code"].unique()
        unsigned_data = known_code_data.copy()
        unsigned_data = unsigned_data[unsigned_data[sign].isna()]
        able_to_recover_data = unsigned_data[unsigned_data["cian_building_code"].isin(codes_with_sign)]
        md_lines.append(f"| {sign} | {len(signed_data)} | {len(unsigned_data)} | {len(able_to_recover_data)} |")
    md_lines.append("\n*Для расчета показателей используются строки с указанными значениями **cian_building_code***")
    display(Markdown("\n".join(md_lines)))


if __name__ == "__main__":

    # Получение сырых данных из БД
    db_connection = DBConnection(PATH_TO_DB)
    with db_connection:
        apartments = db_connection.select("apartments")
        listings = db_connection.select("listings")
        price_history = db_connection.select("price_history")
    print(
        f"Количество строк в таблице apartments: {len(apartments)}\n"
        f"Количество строк в таблице listings: {len(listings)}\n"
        f"Количество строк в таблице price_history: {len(price_history)}\n"
    )

    # Определение количества объявлений с неподходящей валютой сделки
    invalid_currency_from_listings = listings[listings["currency_code"] != "rur"]["id"]
    invalid_currency_from_history = price_history[price_history["currency_code"] != "rur"]["listing_id"]
    total_invalid_currency = pd.concat([invalid_currency_from_listings, invalid_currency_from_history]).unique().size
    print(f"Количество объявлений c валютой сделки, отличающейся от <{EXPECTED_CURRENCY}>: {total_invalid_currency}")

    # Определение количества объявлений с неподходящим типом сделки
    invalid_type = (listings["listing_type"] != DEAL_TYPE).sum()
    print(f"Количество объявлений c типом сделки, отличающимся от <{DEAL_TYPE}>: {invalid_type}")

    # Определение количества объявлений без указанной цены сделки
    invalid_price = listings["total_rur_price"].isna().sum()
    print(f"Количество объявлений без указанной цены сделки: {invalid_price}")

    # Определение количества объявлений с неподходящим типом недвижимости
    invalid_property = (apartments["property_type"] != PROPERTY_TYPE).sum()
    print(f"Количество объявлений c типом недвижимости, отличающимся от <{PROPERTY_TYPE}>: {invalid_property}")

    # Определение общего количества повторных записей одних и тех же объявлений
    unique_listings = listings.drop_duplicates(subset="cian_listing_id")
    print(f"Общее количество повторных записей объявлений: {len(listings) - len(unique_listings)}")

    # Извлечение данных и их предварительная очистка
    original_data = get_original_listings(PATH_TO_DB, "apartments", "listings", "price_history")
    cleaned_data = clean_listings_data(original_data).copy()
    print(cleaned_data.shape)

    # Определение количества объявлений, соответствующих различным уровням подозрительности изменения цены
    for level in ["single_record", "valid", "low", "high"]:
        level_count = (cleaned_data["suspicious_status"] == level).sum()
        print(f"Количество объявлений с уровнем подозрительности изменения цены <{level}>: {level_count}")
    approved_listings = detect_suspicion_price(price_history)["listing_id"].unique()
    extreme_price_change_listings = price_history[~(price_history["listing_id"].isin(approved_listings))]["listing_id"]
    print(f"Количество объявлений с экстремально-резкими изменениями цен: {extreme_price_change_listings.nunique()}")

    # Самая ранняя и самая поздняя даты публикации объявлений
    dates = cleaned_data["created_at"].agg(["min", "max"])
    print(f"Самая ранняя дата публикации: {dates["min"]}")
    print(f"Самая поздняя дата публикации: {dates["max"]}")

    # Статистика пропущенных значений
    print(show_missed(cleaned_data))
