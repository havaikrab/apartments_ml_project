import datetime
import os
import random
from statistics import mean
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from data_base.apartments_data_cleaning import add_city_candidates_groups, clean_listings_data, get_original_listings

load_dotenv()

TEST_LAUNCHES_COUNT = int(os.getenv("TEST_LAUNCHES_COUNT", 5))
SIGNS_LIST = ["cian_building_code", "cian_builder_id", "district", "street", "building_number"]
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")


def predict_city_test(data: pd.DataFrame):

    start_time = datetime.datetime.now(tz=ZoneInfo(TIME_ZONE))
    city_exists = data["city"].notna()
    test_data = data[city_exists].copy().reset_index(drop=True)
    test_data["original_city"] = test_data["city"]
    selection_part = data["city"].isna().sum() / len(data)
    selection_size = int(len(test_data) * selection_part)
    report = {
        "start_date": start_time.isoformat(),
        "data_size": len(test_data),
        "test_data_part": float(selection_part),
        "launches_count": TEST_LAUNCHES_COUNT,
    }
    metrics_dict = {f"efficiency_by_{key}": list() for key in SIGNS_LIST}
    metrics_dict.update({f"accuracy_by_{key}": list() for key in SIGNS_LIST})

    for launch in range(TEST_LAUNCHES_COUNT):
        launch_test_data = test_data.copy()
        selected_indexes = random.sample(list(test_data.index), selection_size)
        launch_test_data.loc[selected_indexes, "city"] = None
        launch_test_data = add_city_candidates_groups(launch_test_data, SIGNS_LIST)

        for sign in SIGNS_LIST:
            column_name = f"candidate_by_{sign}"
            rows_with_candidate = launch_test_data[column_name].notna().sum()
            sign_efficiency = float(rows_with_candidate / len(launch_test_data))
            sign_accuracy = float(
                (launch_test_data[column_name] == launch_test_data["original_city"]).sum() / rows_with_candidate
            )
            metrics_dict[f"efficiency_by_{sign}"].append(sign_efficiency)
            metrics_dict[f"accuracy_by_{sign}"].append(sign_accuracy)

    average_metrics = {key: mean(value) for key, value in metrics_dict.items()}
    print(average_metrics)


original_data = get_original_listings("../apartments.db", "apartments", "listings", "price_history")
cleaned_data = clean_listings_data(original_data)

predict_city_test(cleaned_data)
