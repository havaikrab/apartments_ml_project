import os

from dotenv import load_dotenv

from .orm import DBConnection

load_dotenv()
DATA_BASE_NAME = os.getenv("DB_NAME", "../apartments.db")


def save_cian_data(cian_data: dict) -> None:
    """Сохраняет в базу данных информацию из объявлений с сайта cian.ru"""

    connection = DBConnection(DATA_BASE_NAME)
    with connection:
        apartment = cian_data.get("apartments", dict())
        apartment_id = connection.insert("apartments", apartment, return_values=("id",))[0][0]
        listing = cian_data.get("listings", dict())
        listing["apartment_id"] = apartment_id
        listing_id = connection.insert("listings", listing, return_values=("id",))[0][0]
        price_history = cian_data.get("price_history", list())
        for change in price_history:
            change["listing_id"] = listing_id
            connection.insert("price_history", change)
    connection.close()
