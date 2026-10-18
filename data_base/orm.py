import sqlite3
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


class DBConnection:
    """Класс работы с базой данных"""

    def __init__(self, db_name: str):
        """Инициализация нового соединения"""

        self.db_name = db_name
        self.connection = sqlite3.connect(self.db_name)
        self.connection.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> sqlite3.Connection:
        """Вход в менеджер контекста"""

        return self.connection

    def __exit__(self, exc_type: type, exc_value: str, traceback: str) -> None:
        """Выход из менеджера контекста"""

        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()

    def create_table(
        self,
        table_name: str,
        columns: dict[str, str],
        primary_key: Optional[tuple | list] = None,
        foreign_keys: Optional[dict[str, tuple]] = None,
        not_null: Optional[tuple | list] = None,
        unique: Optional[tuple | list] = None,
    ) -> None:
        """Универсальный метод создания таблиц. Принимает аргументы:
        - table_name - строка с названием будущей таблицы
        - columns - словарь вида {column: column_type} с названиями колонок и соответствующим типом данных
        - primary_key - опционально, кортеж или список с названиями колонок, определяющих первичный ключ таблицы
        - foreign_keys - опционально, словарь вида {column: (referenced_table, referenced_column)}
            содержащий названия ссылающихся колонок и кортежи с названиями таблицы и "старшей" колонки
        - not_null - опционально, кортеж или список с названиями колонок, для которых недопустимо отсутствие значений
        - unique - опционально, кортеж или список с названиями колонок, для которых обязательна уникальность значений
        """

        if isinstance(not_null, list | tuple):
            for n in not_null:
                columns[n] += " NOT NULL"
        elif not_null is not None:
            raise TypeError("Недопустимый тип данных для колонок с NOT NULL")

        if isinstance(unique, list | tuple):
            for u in unique:
                columns[u] += " UNIQUE"
        elif not_null is not None:
            raise TypeError("Недопустимый тип данных для колонок с UNIQUE")

        sql_string = ", ".join([f"{column} {column_type}" for column, column_type in columns.items()])

        if isinstance(primary_key, tuple | list):
            for k in primary_key:
                if not isinstance(k, str) or k not in columns:
                    raise ValueError("Недопустимое значение первичного ключа")
            primary_string = ", PRIMARY KEY (" + ", ".join(primary_key) + ")"
            sql_string += primary_string
        elif primary_key is not None:
            raise ValueError("Недопустимое значение первичного ключа")

        if isinstance(foreign_keys, dict) and len(foreign_keys) > 0:
            keys_str = ", " + ", ".join(
                [
                    f"FOREIGN KEY ({column}) REFERENCES {related[0]}({related[1]})"
                    for column, related in foreign_keys.items()
                ]
            )
            sql_string += keys_str
        self.connection.execute(f"CREATE TABLE {table_name} ({sql_string})")

    def close(self) -> None:
        """Закрывает соединение с базой данных"""

        self.connection.close()

    def insert(self, table_name: str, data: dict, return_values: Optional[tuple | list] = None) -> list:
        """Записывает строку данных в таблицу. Принимает аргументы:
        - table_name - строка с названием таблицы
        - data - словарь, в котором ключи являются названиям колонок для соответствующих значений
        - return_values - опционально, список или кортеж с названиями колонок,
            значения которых нужно вернуть, после записи новой строки в таблицу
        """

        sql_string = f"INSERT INTO {table_name} ({', '.join(list(data.keys()))}) VALUES({(len(data) * '?, ')[: -2]})"
        if isinstance(return_values, tuple | list) and len(return_values) > 0:
            return_string = " RETURNING " + ", ".join(return_values)
            sql_string += return_string
        elif return_values is not None:
            raise TypeError("Возвращаемые значения указаны некорректно")
        return self.connection.execute(sql_string, tuple(data.values())).fetchall()

    def select(self, table_name: str) -> pd.DataFrame:
        """Возвращает DataFrame объект - копию указанной таблицы"""

        query = f"SELECT * FROM {table_name}"
        return pd.read_sql_query(query, self.connection)
