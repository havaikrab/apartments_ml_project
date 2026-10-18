import os

from data_base.orm import DBConnection

if __name__ == "__main__":
    data_base_name = os.getenv("DB_NAME", "apartments.db")
    db_connection = DBConnection(data_base_name)
    with db_connection:
        db_connection.create_table(
            "apartments",
            {
                "id": "INTEGER",
                "property_type": "TEXT",
                "flat_type": "TEXT",
                "total_area": "REAL",
                "rooms_count": "INTEGER",
                "floor_number": "INTEGER",
                "total_floors": "INTEGER",
                "building_material": "TEXT",
                "ceiling_height": "REAL",
                "year_built": "INTEGER",
                "is_from_builder": "BOOL",
                "is_complete_building": "BOOL",
                "builder_name": "TEXT",
                "cian_builder_id": "INTEGER",
                "city": "TEXT",
                "district": "TEXT",
                "street": "TEXT",
                "building_number": "TEXT",
                "cian_building_code": "INTEGER",
            },
            primary_key=("id",),
            not_null=("id", "total_area"),
            unique=("id",),
        )
        db_connection.create_table(
            "listings",
            {
                "id": "INTEGER",
                "cian_listing_id": "INTEGER",
                "apartment_id": "INTEGER",
                "listing_type": "TEXT",
                "total_rur_price": "REAL",
                "listing_price": "REAL",
                "currency_code": "TEXT",
                "source": "TEXT",
                "url": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "photos_count": "INTEGER",
            },
            primary_key=("id",),
            foreign_keys={"apartment_id": ("apartments", "id")},
            not_null=("id", "cian_listing_id", "apartment_id"),
            unique=("id",),
        )
        db_connection.create_table(
            "price_history",
            {
                "id": "INTEGER",
                "listing_id": "INTEGER",
                "price": "REAL",
                "currency_code": "TEXT",
                "recorded_at": "TEXT",
            },
            primary_key=("id",),
            foreign_keys={"listing_id": ("listings", "id")},
            not_null=("id", "listing_id"),
            unique=("id",),
        )
        db_connection.create_table(
            "city_recovery_testing",
            {
                "id": "INTEGER",
                "start_date": "TEXT",
                "data_size": "INTEGER",
                "test_data_part": "REAL",
                "launches_count": "INTEGER",
                "efficiency_by_cian_building_code": "REAL",
                "accuracy_by_cian_building_code": "REAL",
                "efficiency_by_cian_builder_id": "REAL",
                "accuracy_by_cian_builder_id": "REAL",
                "efficiency_by_builder_name": "REAL",
                "accuracy_by_builder_name": "REAL",
                "efficiency_by_district": "REAL",
                "accuracy_by_district": "REAL",
                "efficiency_by_street": "REAL",
                "accuracy_by_street": "REAL",
                "efficiency_by_building_number": "REAL",
                "accuracy_by_building_number": "REAL",
                "base_efficiency": "REAL",
                "base_accuracy": "REAL",
            },
            primary_key=("id",),
            not_null=(
                "id",
                "start_date",
                "data_size",
                "test_data_part",
                "launches_count",
                "base_efficiency",
                "base_accuracy",
            ),
            unique=("id",),
        )
