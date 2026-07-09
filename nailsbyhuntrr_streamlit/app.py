from __future__ import annotations

import base64
import calendar
import colorsys
import hashlib
import html
import importlib
import json
import re
import secrets
import random
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "nailsbyhuntrr.db"

BRAND_PRIMARY = "#B76E79"
BRAND_PINK = "#FFB7D5"
BRAND_LAVENDER = "#C7B3E5"
BRAND_CORAL = "#FF6F61"
BRAND_EMERALD = "#2E8B57"
BRAND_NOIR = "#1B1B1B"
BRAND_DANGER = "#D2042D"
CHART_COLORS = [BRAND_PINK, BRAND_PRIMARY, BRAND_LAVENDER, BRAND_CORAL, BRAND_EMERALD, BRAND_NOIR]
ETSY_HISTORY_MONTHS = 18


st.set_page_config(
    page_title="NailsByHuntrr Dashboard",
    page_icon=".",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def compact_number(value: float | int) -> str:
    number = float(value)
    if abs(number) >= 1000:
        text = f"{number / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return f"{number:,.0f}"


def etsy_history_start() -> date:
    today = date.today()
    month = today.month - ETSY_HISTORY_MONTHS
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def load_shop_stats() -> dict:
    data_path = APP_DIR / "data" / "shop_stats.json"
    if not data_path.exists():
        return {}
    return json.loads(data_path.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS colors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hex_code TEXT NOT NULL,
                finish TEXT NOT NULL DEFAULT 'glossy',
                brand TEXT,
                swatch_id TEXT,
                in_stock INTEGER NOT NULL DEFAULT 1,
                catalog_type TEXT NOT NULL DEFAULT 'gel_polish',
                UNIQUE(name, catalog_type)
            );

            CREATE TABLE IF NOT EXISTS press_on_nails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                etsy_listing_id INTEGER UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                shape TEXT NOT NULL,
                length TEXT NOT NULL,
                color_id INTEGER,
                price REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT 'USD',
                cost REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 5,
                tags TEXT,
                materials TEXT,
                image_url TEXT,
                image_urls TEXT,
                model_file_path TEXT,
                sku TEXT,
                variation_1_name TEXT,
                variation_1_values TEXT,
                variation_2_name TEXT,
                variation_2_values TEXT,
                FOREIGN KEY (color_id) REFERENCES colors (id)
            );

            CREATE TABLE IF NOT EXISTS keychains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                etsy_listing_id INTEGER UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                style TEXT NOT NULL,
                color_id INTEGER,
                price REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT 'USD',
                cost REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 5,
                print_time TEXT,
                tags TEXT,
                materials TEXT,
                image_url TEXT,
                image_urls TEXT,
                model_file_path TEXT,
                sku TEXT,
                variation_1_name TEXT,
                variation_1_values TEXT,
                variation_2_name TEXT,
                variation_2_values TEXT,
                FOREIGN KEY (color_id) REFERENCES colors (id)
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                product_type TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                customer_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT 'USD',
                etsy_receipt_id INTEGER,
                etsy_transaction_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_date TEXT NOT NULL,
                product_name TEXT NOT NULL,
                rating INTEGER NOT NULL,
                customer_name TEXT,
                review_text TEXT,
                notes TEXT,
                order_id TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        color_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(colors)")
        }
        if "catalog_type" not in color_columns:
            conn.execute(
                "ALTER TABLE colors ADD COLUMN catalog_type TEXT NOT NULL DEFAULT 'gel_polish'"
            )
        if "brand" not in color_columns:
            conn.execute("ALTER TABLE colors ADD COLUMN brand TEXT")
        if "swatch_id" not in color_columns:
            conn.execute("ALTER TABLE colors ADD COLUMN swatch_id TEXT")
        product_columns = {
            "press_on_nails": {
                "etsy_listing_id": "INTEGER",
                "description": "TEXT",
                "currency_code": "TEXT NOT NULL DEFAULT 'USD'",
                "tags": "TEXT",
                "materials": "TEXT",
                "image_url": "TEXT",
                "image_urls": "TEXT",
                "model_file_path": "TEXT",
                "sku": "TEXT",
                "variation_1_name": "TEXT",
                "variation_1_values": "TEXT",
                "variation_2_name": "TEXT",
                "variation_2_values": "TEXT",
            },
            "keychains": {
                "etsy_listing_id": "INTEGER",
                "description": "TEXT",
                "currency_code": "TEXT NOT NULL DEFAULT 'USD'",
                "print_time": "TEXT",
                "tags": "TEXT",
                "materials": "TEXT",
                "image_url": "TEXT",
                "image_urls": "TEXT",
                "model_file_path": "TEXT",
                "sku": "TEXT",
                "variation_1_name": "TEXT",
                "variation_1_values": "TEXT",
                "variation_2_name": "TEXT",
                "variation_2_values": "TEXT",
            },
            "reviews": {
                "order_id": "TEXT",
            },
            "sales": {
                "customer_name": "TEXT",
                "currency_code": "TEXT NOT NULL DEFAULT 'USD'",
                "etsy_receipt_id": "INTEGER",
                "etsy_transaction_id": "INTEGER",
            },
        }
        for table, columns in product_columns.items():
            existing = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_press_on_nails_etsy_listing_id
            ON press_on_nails(etsy_listing_id)
            WHERE etsy_listing_id IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_keychains_etsy_listing_id
            ON keychains(etsy_listing_id)
            WHERE etsy_listing_id IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_etsy_transaction_id
            ON sales(etsy_transaction_id)
            WHERE etsy_transaction_id IS NOT NULL
            """
        )
        colors_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'colors'"
        ).fetchone()["sql"]
        if "name TEXT NOT NULL UNIQUE" in colors_sql:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(
                """
                CREATE TABLE colors_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    hex_code TEXT NOT NULL,
                    finish TEXT NOT NULL DEFAULT 'glossy',
                    brand TEXT,
                    swatch_id TEXT,
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    catalog_type TEXT NOT NULL DEFAULT 'gel_polish',
                    UNIQUE(name, catalog_type)
                );
                INSERT INTO colors_new (id, name, hex_code, finish, brand, swatch_id, in_stock, catalog_type)
                SELECT id, name, hex_code, finish, brand, swatch_id, in_stock, catalog_type FROM colors;
                DROP TABLE colors;
                ALTER TABLE colors_new RENAME TO colors;
                """
            )
            conn.execute("PRAGMA foreign_keys = ON")
        seeded = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'seeded_sample_data'"
        ).fetchone()
        if seeded is None:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ('seeded_sample_data', '1')"
            )
        ensure_bundled_nails(conn)
        ensure_bundled_reviews(conn)
        ensure_bundled_sales(conn)
        ensure_bundled_gel_polish_colors(conn)
        ensure_bundled_filament_colors(conn)
        ensure_bundled_keychains(conn)


def seed_db(conn: sqlite3.Connection) -> None:
    colors = [
        ("Cotton Candy", "#FFB7D5", "glossy", 1),
        ("Midnight Noir", "#1B1B1B", "matte", 1),
        ("Rose Gold", "#B76E79", "chrome", 1),
        ("Lavender Dream", "#C7B3E5", "glossy", 1),
        ("Sunset Coral", "#FF6F61", "glossy", 1),
        ("Emerald City", "#2E8B57", "glitter", 1),
        ("Pearl White", "#F8F6F0", "matte", 1),
        ("Cherry Pop", "#D2042D", "glossy", 0),
    ]
    conn.executemany("INSERT INTO colors (name, hex_code, finish, in_stock) VALUES (?, ?, ?, ?)", colors)
    color_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM colors")}

    nails = [
        ("Ballerina Blush", "coffin", "medium", color_ids["Cotton Candy"], 24.0, 6.5, 18, 5),
        ("Goth Glam", "stiletto", "long", color_ids["Midnight Noir"], 28.0, 7.25, 4, 5),
        ("Rose Gold Luxe", "almond", "medium", color_ids["Rose Gold"], 30.0, 8.0, 12, 5),
        ("Lavender Fields", "square", "short", color_ids["Lavender Dream"], 22.0, 5.75, 25, 6),
        ("Coral Crush", "coffin", "XL", color_ids["Sunset Coral"], 32.0, 9.0, 3, 5),
        ("Emerald Sparkle", "almond", "long", color_ids["Emerald City"], 34.0, 9.5, 9, 5),
        ("Pearl Minimalist", "oval", "short", color_ids["Pearl White"], 20.0, 5.0, 30, 8),
    ]
    conn.executemany(
        """
        INSERT INTO press_on_nails
        (name, shape, length, color_id, price, cost, quantity, reorder_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        nails,
    )

    keychains = [
        ("Beaded Bliss", "beaded", color_ids["Cotton Candy"], 12.0, 3.0, 20, 5),
        ("Acrylic Angel", "acrylic", color_ids["Pearl White"], 10.0, 2.5, 15, 5),
        ("Resin Rose", "resin", color_ids["Rose Gold"], 14.0, 3.75, 6, 5),
        ("Charm Cluster", "charm", color_ids["Lavender Dream"], 16.0, 4.25, 2, 5),
        ("Coral Charm", "charm", color_ids["Sunset Coral"], 15.0, 4.0, 11, 5),
    ]
    conn.executemany(
        """
        INSERT INTO keychains
        (name, style, color_id, price, cost, quantity, reorder_level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        keychains,
    )

    products = []
    products.extend(conn.execute("SELECT id, name, price, cost, 'press_on_nails' AS product_type FROM press_on_nails"))
    products.extend(conn.execute("SELECT id, name, price, cost, 'keychains' AS product_type FROM keychains"))
    rng = random.Random(42)
    today = date.today()
    sale_rows = []
    for days_ago in range(120, -1, -1):
        sold_on = today - timedelta(days=days_ago)
        for _ in range(rng.randint(0, 5)):
            product = rng.choice(products)
            qty = rng.randint(1, 3)
            revenue = round(qty * float(product["price"]), 2)
            sale_rows.append(
                (
                    sold_on.isoformat(),
                    product["product_type"],
                    product["id"],
                    product["name"],
                    qty,
                    product["price"],
                    product["cost"],
                    revenue,
                )
            )
    conn.executemany(
        """
        INSERT INTO sales
        (sale_date, product_type, product_id, product_name, quantity, unit_price, unit_cost, revenue)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sale_rows,
    )


def ensure_bundled_nails(conn: sqlite3.Connection) -> None:
    data_path = APP_DIR / "data" / "bundled_nails.json"
    if not data_path.exists():
        return
    nails = json.loads(data_path.read_text(encoding="utf-8"))
    for nail in nails:
        item = {
            "etsy_listing_id": nail.get("etsy_listing_id"),
            "name": nail["name"],
            "description": nail.get("description"),
            "shape": nail.get("shape") or "custom",
            "length": nail.get("length") or "varies",
            "color_id": None,
            "price": float(nail.get("price") or 0),
            "currency_code": nail.get("currency_code") or "USD",
            "cost": float(nail.get("cost") or 0),
            "quantity": int(nail.get("quantity") or 0),
            "reorder_level": int(nail.get("reorder_level") or 1),
            "tags": nail.get("tags"),
            "materials": nail.get("materials"),
            "image_url": nail.get("image_url"),
            "image_urls": nail.get("image_urls"),
            "sku": nail.get("sku"),
            "variation_1_name": nail.get("variation_1_name"),
            "variation_1_values": nail.get("variation_1_values"),
            "variation_2_name": nail.get("variation_2_name"),
            "variation_2_values": nail.get("variation_2_values"),
        }
        existing = conn.execute(
            "SELECT id FROM press_on_nails WHERE name = ?",
            (item["name"],),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE press_on_nails
                SET etsy_listing_id = COALESCE(:etsy_listing_id, etsy_listing_id),
                    description = :description,
                    shape = :shape,
                    length = :length,
                    price = :price,
                    currency_code = :currency_code,
                    cost = :cost,
                    quantity = :quantity,
                    reorder_level = :reorder_level,
                    tags = :tags,
                    materials = :materials,
                    image_url = :image_url,
                    image_urls = :image_urls,
                    sku = :sku,
                    variation_1_name = :variation_1_name,
                    variation_1_values = :variation_1_values,
                    variation_2_name = :variation_2_name,
                    variation_2_values = :variation_2_values
                WHERE id = :id
                """,
                {**item, "id": existing["id"]},
            )
        else:
            conn.execute(
                """
                INSERT INTO press_on_nails
                (
                    etsy_listing_id, name, description, shape, length, color_id,
                    price, currency_code, cost, quantity, reorder_level, tags,
                    materials, image_url, image_urls, sku, variation_1_name,
                    variation_1_values, variation_2_name, variation_2_values
                )
                VALUES (
                    :etsy_listing_id, :name, :description, :shape, :length, :color_id,
                    :price, :currency_code, :cost, :quantity, :reorder_level, :tags,
                    :materials, :image_url, :image_urls, :sku, :variation_1_name,
                    :variation_1_values, :variation_2_name, :variation_2_values
                )
                """,
                item,
            )


def ensure_bundled_reviews(conn: sqlite3.Connection) -> None:
    data_path = APP_DIR / "data" / "bundled_reviews.json"
    if not data_path.exists():
        return
    reviews = json.loads(data_path.read_text(encoding="utf-8"))
    for review in reviews:
        values = {
            "review_date": review["review_date"],
            "product_name": review.get("product_name") or "Etsy review",
            "rating": int(review.get("rating") or 5),
            "customer_name": review.get("customer_name"),
            "review_text": review.get("review_text"),
            "notes": review.get("notes"),
            "order_id": review.get("order_id"),
        }
        existing = conn.execute(
            """
            SELECT id FROM reviews
            WHERE review_date = :review_date
              AND product_name = :product_name
              AND rating = :rating
              AND IFNULL(customer_name, '') = IFNULL(:customer_name, '')
              AND IFNULL(review_text, '') = IFNULL(:review_text, '')
              AND IFNULL(order_id, '') = IFNULL(:order_id, '')
            """,
            values,
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO reviews
            (review_date, product_name, rating, customer_name, review_text, notes, order_id)
            VALUES (
                :review_date, :product_name, :rating, :customer_name,
                :review_text, :notes, :order_id
            )
            """,
            values,
        )


def ensure_bundled_sales(conn: sqlite3.Connection) -> None:
    data_path = APP_DIR / "data" / "bundled_sales.json"
    if not data_path.exists():
        return
    orders = json.loads(data_path.read_text(encoding="utf-8"))
    for order in orders:
        quantity = max(int(order.get("quantity") or 1), 1)
        revenue = round(float(order.get("revenue") or 0), 2)
        receipt_id = int(order["order_id"])
        existing_actual = conn.execute(
            """
            SELECT id FROM sales
            WHERE etsy_receipt_id = ?
              AND product_type != 'imported_etsy_order'
              AND etsy_transaction_id IS NOT NULL
            """,
            (receipt_id,),
        ).fetchone()
        if existing_actual:
            continue
        values = {
            "sale_date": order["sale_date"],
            "product_type": "imported_etsy_order",
            "product_id": 0,
            "product_name": order.get("product_name") or f"Etsy order {receipt_id}",
            "customer_name": order.get("customer_name"),
            "quantity": quantity,
            "unit_price": round(revenue / quantity, 2),
            "unit_cost": 0,
            "revenue": revenue,
            "currency_code": "USD",
            "etsy_receipt_id": receipt_id,
            "etsy_transaction_id": None,
        }
        existing = conn.execute(
            """
            SELECT id FROM sales
            WHERE etsy_receipt_id = ?
              AND product_type = 'imported_etsy_order'
              AND etsy_transaction_id IS NULL
            """,
            (receipt_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE sales
                SET sale_date = :sale_date, product_name = :product_name,
                    customer_name = :customer_name,
                    quantity = :quantity, unit_price = :unit_price,
                    unit_cost = :unit_cost, revenue = :revenue,
                    currency_code = :currency_code
                WHERE id = :id
                """,
                {**values, "id": existing["id"]},
            )
        else:
            conn.execute(
                """
                INSERT INTO sales
                (
                    sale_date, product_type, product_id, product_name, quantity,
                    customer_name, unit_price, unit_cost, revenue, currency_code,
                    etsy_receipt_id, etsy_transaction_id
                )
                VALUES (
                    :sale_date, :product_type, :product_id, :product_name,
                    :quantity, :customer_name, :unit_price, :unit_cost, :revenue,
                    :currency_code, :etsy_receipt_id, :etsy_transaction_id
                )
                """,
                values,
            )


def ensure_bundled_filament_colors(conn: sqlite3.Connection) -> None:
    colors = [
        ("ZIRO Pastel Purple Matte PLA", "#BDA9F2", "matte PLA", 1, "filament"),
        ("3DHoJor Matte Green PLA", "#9ED8A6", "matte PLA", 1, "filament"),
        ("Polymaker Celestial Light Pink PLA", "#F4A8C6", "glitter PLA", 1, "filament"),
        ("JAYO Pink PLA", "#F2A5C3", "PLA", 1, "filament"),
        ("PLA+ Matte Ice Blue", "#BFEAF7", "matte PLA", 1, "filament"),
        ("SUNLU PLA+ 2.0 White", "#F7F7F2", "PLA+", 1, "filament"),
    ]
    conn.executemany(
        """
        INSERT INTO colors (name, hex_code, finish, in_stock, catalog_type)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name, catalog_type) DO UPDATE SET
            hex_code = excluded.hex_code,
            finish = excluded.finish,
            in_stock = excluded.in_stock
        """,
        colors,
    )


def ensure_bundled_gel_polish_colors(conn: sqlite3.Connection) -> None:
    data_path = APP_DIR / "data" / "bundled_gel_polish_colors.json"
    if not data_path.exists():
        return
    colors = json.loads(data_path.read_text(encoding="utf-8"))
    rows = [
        (
            color["name"],
            color["hex_code"],
            color.get("finish") or "matte",
            color.get("brand") or "Beetles",
            color.get("swatch_id"),
            1,
            "gel_polish",
        )
        for color in colors
    ]
    conn.executemany(
        """
        INSERT INTO colors (name, hex_code, finish, brand, swatch_id, in_stock, catalog_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name, catalog_type) DO UPDATE SET
            hex_code = excluded.hex_code,
            finish = excluded.finish,
            brand = excluded.brand,
            swatch_id = excluded.swatch_id,
            in_stock = excluded.in_stock
        """,
        rows,
    )


def ensure_bundled_keychains(conn: sqlite3.Connection) -> None:
    bundled = [
        {
            "name": "Oyasumi Bakura Keychain",
            "description": "3D printed keychain design with matching thumbnail artwork.",
            "style": "3MF design",
            "color_id": None,
            "price": 0.0,
            "currency_code": "USD",
            "cost": 0.0,
            "quantity": 1,
            "reorder_level": 0,
            "print_time": "Plate 1: 2h45m\nPlate 2: 3h32m\nPlate 3: 4h10m\nPlate 4: 1h51m\nPlate 5: 1h41m",
            "tags": "keychain,3D print,3MF,kawaii",
            "materials": (
                "Plate 1: filament 1 white, 4 pink, 5 light pink | total 3.13 m / 9.49 g | 35 changes | cost 0.24\n"
                "Plate 2: filament 1 white, 4 pink, 6 blue, 7 yellow | total 4.96 m / 15.02 g\n"
                "Plate 3: filament 1 white, 4 pink, 5 light pink, 6 blue | total 5.15 m / 15.60 g | 57 changes | cost 0.39\n"
                "Plate 4: filament 2 black, 3 gray | total 2.13 m / 6.47 g | 19 changes | cost 0.16\n"
                "Plate 5: filament 1 white, 2 black, 3 gray | total 2.31 m / 6.99 g | 18 changes | cost 0.17"
            ),
            "image_url": "assets/keychains/oyasumi_bakura_keychain.png",
            "image_urls": "assets/keychains/oyasumi_bakura_keychain.png",
            "model_file_path": "assets/keychains/oyasumi_bakura_keychain.3mf",
            "sku": None,
            "variation_1_name": None,
            "variation_1_values": None,
            "variation_2_name": None,
            "variation_2_values": None,
        }
    ]
    for item in bundled:
        existing = conn.execute(
            "SELECT id FROM keychains WHERE name = ?",
            (item["name"],),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE keychains
                SET description = :description,
                    style = :style,
                    color_id = :color_id,
                    price = :price,
                    currency_code = :currency_code,
                    cost = :cost,
                    quantity = :quantity,
                    reorder_level = :reorder_level,
                    print_time = COALESCE(print_time, :print_time),
                    tags = :tags,
                    materials = COALESCE(materials, :materials),
                    image_url = :image_url,
                    image_urls = :image_urls,
                    model_file_path = :model_file_path,
                    sku = :sku,
                    variation_1_name = :variation_1_name,
                    variation_1_values = :variation_1_values,
                    variation_2_name = :variation_2_name,
                    variation_2_values = :variation_2_values
                WHERE id = :id
                """,
                {**item, "id": existing["id"]},
            )
        else:
            conn.execute(
                """
                INSERT INTO keychains
                (
                    name, description, style, color_id, price, currency_code,
                    cost, quantity, reorder_level, tags, materials, image_url,
                    print_time,
                    image_urls, model_file_path, sku, variation_1_name,
                    variation_1_values, variation_2_name, variation_2_values
                )
                VALUES (
                    :name, :description, :style, :color_id, :price, :currency_code,
                    :cost, :quantity, :reorder_level, :tags, :materials, :image_url,
                    :print_time,
                    :image_urls, :model_file_path, :sku, :variation_1_name,
                    :variation_1_values, :variation_2_name, :variation_2_values
                )
                """,
                item,
            )


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_setting(key: str, default: str | None = None) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str | None) -> None:
    with connect() as conn:
        if value is None:
            conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        else:
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )


def bambu_get_credentials() -> dict[str, str | None]:
    return {
        "ip": get_setting("bambu_ip"),
        "access_code": get_setting("bambu_access_code"),
        "serial": get_setting("bambu_serial"),
    }


def bambu_save_credentials(ip: str, access_code: str, serial: str) -> None:
    set_setting("bambu_ip", ip.strip())
    set_setting("bambu_access_code", access_code.strip())
    set_setting("bambu_serial", serial.strip())


def bambu_clear_credentials() -> None:
    for key in ["bambu_ip", "bambu_access_code", "bambu_serial"]:
        set_setting(key, None)
    st.session_state.pop("bambu_client", None)
    st.session_state.pop("bambu_status", None)
    st.session_state.pop("bambu_connected", None)


def bambu_load_printer_class():
    candidates = [
        ("bambulabs_api", "Printer"),
        ("bambulabs_api.printer", "Printer"),
        ("bambulabs_api.bambu_printer", "BambuPrinter"),
        ("bambulabs", "Printer"),
    ]
    last_error: Exception | None = None
    for module_name, class_name in candidates:
        try:
            module = importlib.import_module(module_name)
            printer_class = getattr(module, class_name, None)
            if printer_class is not None:
                return printer_class, None
        except Exception as exc:
            last_error = exc
    return None, last_error


def bambu_make_client(ip: str, access_code: str, serial: str):
    printer_class, error = bambu_load_printer_class()
    if printer_class is None:
        detail = f" Last import error: {error}" if error else ""
        raise RuntimeError(f"bambulabs-api is not installed or its Printer class was not found.{detail}")

    constructor_attempts = [
        {"hostname": ip, "access_code": access_code, "serial": serial},
        {"host": ip, "access_code": access_code, "serial": serial},
        {"ip": ip, "access_code": access_code, "serial": serial},
        {"printer_ip": ip, "access_code": access_code, "serial_number": serial},
        {"ip_address": ip, "access_code": access_code, "serial_number": serial},
    ]
    errors = []
    for kwargs in constructor_attempts:
        try:
            return printer_class(**kwargs)
        except TypeError as exc:
            errors.append(str(exc))
    try:
        return printer_class(ip, access_code, serial)
    except Exception as exc:
        errors.append(str(exc))
        raise RuntimeError("Could not create a Bambu printer client. " + " | ".join(errors[-3:])) from exc


def bambu_call_first(client, method_names: list[str]):
    for method_name in method_names:
        method = getattr(client, method_name, None)
        if callable(method):
            return method()
    return None


def bambu_connect_client(client) -> None:
    bambu_call_first(client, ["connect", "start", "login"])


def bambu_disconnect_client(client) -> None:
    bambu_call_first(client, ["disconnect", "close", "stop"])


def bambu_status_as_dict(status) -> dict:
    if status is None:
        return {}
    if isinstance(status, dict):
        return status
    if hasattr(status, "dict") and callable(status.dict):
        return status.dict()
    if hasattr(status, "model_dump") and callable(status.model_dump):
        return status.model_dump()
    if hasattr(status, "__dict__"):
        return {key: value for key, value in vars(status).items() if not key.startswith("_")}
    return {"status": str(status)}


def bambu_get_status(client) -> dict:
    status = bambu_call_first(client, ["get_current_state", "get_state", "get_status", "get_report"])
    if status is None:
        for attribute_name in ["state", "status", "report", "last_report", "printer"]:
            if hasattr(client, attribute_name):
                status = getattr(client, attribute_name)
                break
    status_data = bambu_status_as_dict(status)
    method_map = {
        "state": "get_state",
        "current_state": "get_current_state",
        "progress": "get_percentage",
        "remaining_time": "get_time",
        "file_name": "get_file_name",
        "nozzle_temperature": "get_nozzle_temperature",
        "bed_temperature": "get_bed_temperature",
        "chamber_temperature": "get_chamber_temperature",
        "print_speed": "get_print_speed",
        "current_layer": "current_layer_num",
        "total_layers": "total_layer_num",
        "wifi_signal": "wifi_signal",
        "print_type": "print_type",
        "subtask_name": "subtask_name",
    }
    for key, method_name in method_map.items():
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                value = method()
                if value not in [None, ""]:
                    status_data[key] = value
            except Exception:
                continue
    return status_data


def bambu_status_value(status: dict, keys: list[str], default: str = "-") -> str:
    for key in keys:
        value = status.get(key)
        if value not in [None, ""]:
            return str(value)
    print_data = status.get("print")
    if isinstance(print_data, dict):
        for key in keys:
            value = print_data.get(key)
            if value not in [None, ""]:
                return str(value)
    return default


def etsy_get_credentials() -> dict[str, str | None]:
    return {
        "keystring": get_setting("etsy_keystring"),
        "shared_secret": get_setting("etsy_shared_secret"),
        "redirect_uri": get_setting("etsy_redirect_uri"),
        "access_token": get_setting("etsy_access_token"),
        "refresh_token": get_setting("etsy_refresh_token"),
        "expires_at": get_setting("etsy_expires_at"),
        "user_id": get_setting("etsy_user_id"),
        "shop_id": get_setting("etsy_shop_id"),
    }


def etsy_save_credentials(keystring: str, shared_secret: str, redirect_uri: str) -> None:
    set_setting("etsy_keystring", keystring.strip())
    set_setting("etsy_shared_secret", shared_secret.strip())
    set_setting("etsy_redirect_uri", redirect_uri.strip())


def etsy_make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def etsy_build_auth_url(scopes: list[str]) -> str:
    creds = etsy_get_credentials()
    if not creds["keystring"] or not creds["redirect_uri"]:
        raise ValueError("Save your Etsy keystring and redirect URI first.")
    verifier, challenge = etsy_make_pkce_pair()
    state = secrets.token_urlsafe(24)
    set_setting("etsy_oauth_verifier", verifier)
    set_setting("etsy_oauth_state", state)
    params = {
        "response_type": "code",
        "client_id": creds["keystring"],
        "redirect_uri": creds["redirect_uri"],
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://www.etsy.com/oauth/connect?" + urlencode(params)


def etsy_extract_code(callback_text: str) -> tuple[str, str | None]:
    parsed = urlparse(callback_text.strip())
    query = parse_qs(parsed.query if parsed.query else callback_text.strip())
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [None])[0]
    if not code:
        raise ValueError("No OAuth code found. Paste the full redirected URL or the query string with code=...")
    return code, state


def etsy_store_token(token_data: dict) -> None:
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in", 3600))
    set_setting("etsy_access_token", access_token)
    if refresh_token:
        set_setting("etsy_refresh_token", refresh_token)
    set_setting("etsy_expires_at", str(int(time.time()) + expires_in - 60))
    if "." in access_token:
        set_setting("etsy_user_id", access_token.split(".", 1)[0])


def etsy_exchange_code(callback_text: str) -> None:
    creds = etsy_get_credentials()
    code, returned_state = etsy_extract_code(callback_text)
    expected_state = get_setting("etsy_oauth_state")
    verifier = get_setting("etsy_oauth_verifier")
    if expected_state and returned_state != expected_state:
        raise ValueError("The returned Etsy state did not match. Generate a fresh auth link and try again.")
    if not creds["keystring"] or not creds["redirect_uri"] or not verifier:
        raise ValueError("Missing saved Etsy credentials or PKCE verifier.")
    response = requests.post(
        "https://api.etsy.com/v3/public/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": creds["keystring"],
            "redirect_uri": creds["redirect_uri"],
            "code": code,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    response.raise_for_status()
    etsy_store_token(response.json())


def etsy_refresh_access_token() -> None:
    creds = etsy_get_credentials()
    if not creds["keystring"] or not creds["refresh_token"]:
        raise ValueError("No Etsy refresh token saved yet.")
    response = requests.post(
        "https://api.etsy.com/v3/public/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": creds["keystring"],
            "refresh_token": creds["refresh_token"],
        },
        timeout=30,
    )
    response.raise_for_status()
    etsy_store_token(response.json())


def etsy_api_headers() -> dict[str, str]:
    creds = etsy_get_credentials()
    if not creds["keystring"] or not creds["shared_secret"]:
        raise ValueError("Save your Etsy keystring and shared secret first.")
    expires_at = int(creds["expires_at"] or "0")
    if creds["refresh_token"] and expires_at < int(time.time()):
        etsy_refresh_access_token()
        creds = etsy_get_credentials()
    headers = {"x-api-key": creds["keystring"]}
    if creds["access_token"]:
        headers["Authorization"] = f"Bearer {creds['access_token']}"
    return headers


def etsy_get(path: str, params: dict | None = None) -> dict:
    response = requests.get(
        f"https://api.etsy.com/v3/application{path}",
        headers=etsy_api_headers(),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def etsy_find_shop_id() -> str:
    creds = etsy_get_credentials()
    if creds["shop_id"]:
        return creds["shop_id"]
    user_id = creds["user_id"]
    if not user_id:
        raise ValueError("Connect OAuth first so Etsy can provide your user ID.")
    data = etsy_get(f"/users/{user_id}/shops")
    shops = data.get("results", data if isinstance(data, list) else [])
    if not shops:
        raise ValueError("No Etsy shop was returned for this account.")
    shop_id = str(shops[0]["shop_id"])
    set_setting("etsy_shop_id", shop_id)
    return shop_id


def etsy_clean(value) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    return text or None


def etsy_listing_image_urls(shop_id: str, listing_id: int) -> list[str]:
    try:
        data = etsy_get(f"/shops/{shop_id}/listings/{listing_id}/images")
    except requests.HTTPError:
        return []
    images = data.get("results", data if isinstance(data, list) else [])
    urls = []
    for image in images:
        for key in ("url_fullxfull", "url_570xN", "url_170x135"):
            if image.get(key):
                urls.append(image[key])
                break
    return urls


def etsy_product_type_for(listing: dict) -> str:
    text = " ".join(
        str(listing.get(key) or "")
        for key in ("title", "description", "tags", "materials")
    ).lower()
    if "keychain" in text or "key chain" in text:
        return "keychains"
    return "press_on_nails"


def etsy_money_value(value, fallback: float = 0) -> float:
    if isinstance(value, dict):
        amount = value.get("amount", fallback)
        divisor = value.get("divisor") or 1
        return float(amount or 0) / float(divisor)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def etsy_money_currency(value, fallback: str = "USD") -> str:
    if isinstance(value, dict):
        return value.get("currency_code") or fallback
    return fallback


def etsy_receipt_date(receipt: dict, transaction: dict | None = None) -> str:
    for source in (receipt, transaction or {}):
        for key in (
            "paid_timestamp",
            "created_timestamp",
            "create_timestamp",
            "shipped_timestamp",
        ):
            timestamp = source.get(key)
            if timestamp:
                return datetime.fromtimestamp(int(timestamp)).date().isoformat()
    return date.today().isoformat()


def etsy_product_lookup(product_type: str, listing_id: int | None, title: str) -> tuple[int, float]:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    with connect() as conn:
        row = None
        if listing_id:
            row = conn.execute(
                f"SELECT id, cost FROM {table} WHERE etsy_listing_id = ?",
                (listing_id,),
            ).fetchone()
        if row is None and title:
            row = conn.execute(
                f"SELECT id, cost FROM {table} WHERE lower(name) = lower(?)",
                (title,),
            ).fetchone()
        if row:
            return int(row["id"]), float(row["cost"] or 0)
    return 0, 0


def etsy_upsert_sale_from_transaction(receipt: dict, transaction: dict) -> str:
    receipt_id = int(receipt.get("receipt_id") or transaction.get("receipt_id") or 0)
    transaction_id = int(transaction.get("transaction_id") or 0)
    listing_id = transaction.get("listing_id")
    listing_id = int(listing_id) if listing_id else None
    title = etsy_clean(transaction.get("title")) or f"Etsy transaction {transaction_id or receipt_id}"
    product_type = etsy_product_type_for({"title": title})
    product_id, unit_cost = etsy_product_lookup(product_type, listing_id, title)
    quantity = max(int(transaction.get("quantity") or 1), 1)
    unit_price = etsy_money_value(transaction.get("price"))
    if unit_price == 0 and receipt.get("grandtotal"):
        unit_price = etsy_money_value(receipt.get("grandtotal")) / quantity
    revenue = round(unit_price * quantity, 2)
    currency = etsy_money_currency(transaction.get("price"), etsy_money_currency(receipt.get("grandtotal")))
    sale_date = etsy_receipt_date(receipt, transaction)

    with connect() as conn:
        existing = None
        if transaction_id:
            existing = conn.execute(
                "SELECT id FROM sales WHERE etsy_transaction_id = ?",
                (transaction_id,),
            ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE sales
                SET sale_date = ?, product_type = ?, product_id = ?, product_name = ?,
                    quantity = ?, unit_price = ?, unit_cost = ?, revenue = ?,
                    currency_code = ?, etsy_receipt_id = ?
                WHERE id = ?
                """,
                (
                    sale_date,
                    product_type,
                    product_id,
                    title,
                    quantity,
                    unit_price,
                    unit_cost,
                    revenue,
                    currency,
                    receipt_id or None,
                    existing["id"],
                ),
            )
            return "updated"
        conn.execute(
            """
            INSERT INTO sales
            (
                sale_date, product_type, product_id, product_name, quantity,
                unit_price, unit_cost, revenue, currency_code, etsy_receipt_id,
                etsy_transaction_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                product_type,
                product_id,
                title,
                quantity,
                unit_price,
                unit_cost,
                revenue,
                currency,
                receipt_id or None,
                transaction_id or None,
            ),
        )
    return "inserted"


def etsy_import_listing(listing: dict, shop_id: str) -> str:
    product_type = etsy_product_type_for(listing)
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    listing_id = int(listing["listing_id"])
    title = etsy_clean(listing.get("title")) or f"Etsy listing {listing_id}"
    images = etsy_listing_image_urls(shop_id, listing_id)
    tags = listing.get("tags")
    materials = listing.get("materials")
    if isinstance(tags, list):
        tags = ",".join(tags)
    if isinstance(materials, list):
        materials = ",".join(materials)
    price = listing.get("price")
    if isinstance(price, dict):
        amount = price.get("amount")
        divisor = price.get("divisor") or 1
        price_value = float(amount or 0) / float(divisor)
        currency = price.get("currency_code") or "USD"
    else:
        price_value = float(price or 0)
        currency = listing.get("currency_code") or "USD"
    common = {
        "etsy_listing_id": listing_id,
        "name": title,
        "description": etsy_clean(listing.get("description")),
        "color_id": None,
        "price": price_value,
        "currency_code": currency,
        "cost": 0,
        "quantity": int(listing.get("quantity") or 0),
        "reorder_level": 1,
        "tags": etsy_clean(tags),
        "materials": etsy_clean(materials),
        "image_url": images[0] if images else None,
        "image_urls": ",".join(images) if images else None,
        "sku": etsy_clean(listing.get("sku")),
    }
    with connect() as conn:
        if table == "press_on_nails":
            values = {**common, "shape": "custom", "length": "varies"}
            existing = conn.execute(
                "SELECT id FROM press_on_nails WHERE etsy_listing_id = ? OR name = ?",
                (listing_id, title),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE press_on_nails
                    SET etsy_listing_id = :etsy_listing_id, name = :name,
                        description = :description, shape = :shape, length = :length,
                        price = :price, currency_code = :currency_code,
                        quantity = :quantity, tags = :tags, materials = :materials,
                        image_url = :image_url, image_urls = :image_urls, sku = :sku
                    WHERE id = :id
                    """,
                    {**values, "id": existing["id"]},
                )
                return "updated"
            conn.execute(
                """
                INSERT INTO press_on_nails
                (
                    etsy_listing_id, name, description, shape, length, color_id,
                    price, currency_code, cost, quantity, reorder_level, tags,
                    materials, image_url, image_urls, sku
                )
                VALUES (
                    :etsy_listing_id, :name, :description, :shape, :length, :color_id,
                    :price, :currency_code, :cost, :quantity, :reorder_level, :tags,
                    :materials, :image_url, :image_urls, :sku
                )
                """,
                values,
            )
            return "inserted"
        values = {**common, "style": "custom"}
        existing = conn.execute(
            "SELECT id FROM keychains WHERE etsy_listing_id = ? OR name = ?",
            (listing_id, title),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE keychains
                SET etsy_listing_id = :etsy_listing_id, name = :name,
                    description = :description, style = :style, price = :price,
                    currency_code = :currency_code, quantity = :quantity,
                    tags = :tags, materials = :materials, image_url = :image_url,
                    image_urls = :image_urls, sku = :sku
                WHERE id = :id
                """,
                {**values, "id": existing["id"]},
            )
            return "updated"
        conn.execute(
            """
            INSERT INTO keychains
            (
                etsy_listing_id, name, description, style, color_id, price,
                currency_code, cost, quantity, reorder_level, tags, materials,
                image_url, image_urls, sku
            )
            VALUES (
                :etsy_listing_id, :name, :description, :style, :color_id, :price,
                :currency_code, :cost, :quantity, :reorder_level, :tags, :materials,
                :image_url, :image_urls, :sku
            )
            """,
            values,
        )
        return "inserted"


def etsy_sync_listings() -> dict[str, int]:
    shop_id = etsy_find_shop_id()
    counts = {"inserted": 0, "updated": 0}
    offset = 0
    while True:
        data = etsy_get(
            f"/shops/{shop_id}/listings",
            params={"limit": 100, "offset": offset, "state": "active"},
        )
        listings = data.get("results", [])
        for listing in listings:
            counts[etsy_import_listing(listing, shop_id)] += 1
        if len(listings) < 100:
            break
        offset += 100
    return counts


def etsy_sync_revenue() -> dict[str, int]:
    shop_id = etsy_find_shop_id()
    counts = {"inserted": 0, "updated": 0, "receipts": 0}
    offset = 0
    while True:
        data = etsy_get(
            f"/shops/{shop_id}/receipts",
            params={"limit": 100, "offset": offset, "was_paid": "true"},
        )
        receipts = data.get("results", [])
        for receipt in receipts:
            receipt_id = receipt.get("receipt_id")
            if not receipt_id:
                continue
            counts["receipts"] += 1
            transaction_data = etsy_get(f"/shops/{shop_id}/receipts/{receipt_id}/transactions")
            transactions = transaction_data.get("results", [])
            if transactions:
                with connect() as conn:
                    conn.execute(
                        """
                        DELETE FROM sales
                        WHERE etsy_receipt_id = ?
                          AND product_type = 'imported_etsy_order'
                          AND etsy_transaction_id IS NULL
                        """,
                        (receipt_id,),
                    )
            for transaction in transactions:
                result = etsy_upsert_sale_from_transaction(receipt, transaction)
                counts[result] += 1
        if len(receipts) < 100:
            break
        offset += 100
    return counts


def get_colors(catalog_type: str | None = None) -> pd.DataFrame:
    if catalog_type is None:
        return query_df("SELECT * FROM colors ORDER BY name")
    return query_df(
        "SELECT * FROM colors WHERE catalog_type = ? ORDER BY name",
        (catalog_type,),
    )


def get_products(product_type: str) -> pd.DataFrame:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    descriptor = "shape || ' / ' || length" if table == "press_on_nails" else "style"
    return query_df(
        f"""
        SELECT p.*, c.name AS color_name, c.hex_code, {descriptor} AS descriptor
        FROM {table} p
        LEFT JOIN colors c ON p.color_id = c.id
        ORDER BY p.name
        """
    )


def get_sales(start: date | None = None, end: date | None = None) -> pd.DataFrame:
    where = []
    params: list[str] = []
    if start:
        where.append("sale_date >= ?")
        params.append(start.isoformat())
    if end:
        where.append("sale_date <= ?")
        params.append(end.isoformat())
    clause = "WHERE " + " AND ".join(where) if where else ""
    return query_df(f"SELECT * FROM sales {clause} ORDER BY sale_date", tuple(params))


def summarize_sales(sales: pd.DataFrame) -> dict[str, float]:
    if sales.empty:
        return {"revenue": 0, "profit": 0, "orders": 0, "units": 0, "avg_order": 0}
    revenue = float(sales["revenue"].sum())
    profit = float((sales["revenue"] - sales["quantity"] * sales["unit_cost"]).sum())
    order_sales = sales[sales["product_type"] != "manual_revenue"] if "product_type" in sales.columns else sales
    if "etsy_receipt_id" in sales.columns:
        etsy_orders = order_sales["etsy_receipt_id"].dropna()
        manual_orders = order_sales["etsy_receipt_id"].isna().sum()
        orders = int(etsy_orders.nunique() + manual_orders)
    else:
        orders = int(len(order_sales))
    units = int(order_sales["quantity"].sum()) if not order_sales.empty else 0
    return {
        "revenue": revenue,
        "profit": profit,
        "orders": orders,
        "units": units,
        "avg_order": revenue / orders if orders else 0,
    }


def inventory_restock_risk() -> pd.DataFrame:
    sales = get_sales()
    products = []
    for product_type, label in [("press_on_nails", "Press-on nails"), ("keychains", "Keychains")]:
        product_frame = get_products(product_type)
        if product_frame.empty:
            continue
        product_frame = product_frame.copy()
        product_frame["product_type"] = product_type
        product_frame["product_line"] = label
        products.append(product_frame)
    if not products:
        return pd.DataFrame()
    inventory = pd.concat(products, ignore_index=True)
    if sales.empty:
        inventory["recent_units_sold"] = 0
    else:
        recent_start = date.today() - timedelta(days=30)
        recent_sales = sales[
            (sales["product_type"].isin(["press_on_nails", "keychains"]))
            & (pd.to_datetime(sales["sale_date"]).dt.date >= recent_start)
        ]
        recent_units = (
            recent_sales.groupby(["product_type", "product_id"], as_index=False)["quantity"].sum()
            if not recent_sales.empty
            else pd.DataFrame(columns=["product_type", "product_id", "quantity"])
        )
        recent_units = recent_units.rename(columns={"quantity": "recent_units_sold"})
        inventory = inventory.merge(
            recent_units,
            how="left",
            left_on=["product_type", "id"],
            right_on=["product_type", "product_id"],
        )
        inventory["recent_units_sold"] = inventory["recent_units_sold"].fillna(0)

    inventory["daily_velocity"] = inventory["recent_units_sold"] / 30
    inventory["days_until_stockout"] = np.inf
    selling_mask = inventory["daily_velocity"] > 0
    if selling_mask.any():
        inventory.loc[selling_mask, "days_until_stockout"] = (
            inventory.loc[selling_mask, "quantity"] / inventory.loc[selling_mask, "daily_velocity"]
        )
    inventory["risk_score"] = (
        (inventory["quantity"] <= inventory["reorder_level"]).astype(int) * 2
        + (inventory["days_until_stockout"] <= 14).astype(int)
        + ((inventory["daily_velocity"] > 0) & (inventory["quantity"] <= inventory["reorder_level"] + 2)).astype(int)
    )
    inventory["risk"] = np.select(
        [inventory["risk_score"] >= 3, inventory["risk_score"] >= 1],
        ["High", "Medium"],
        default="Low",
    )
    inventory["risk_rank"] = inventory["risk"].map({"High": 0, "Medium": 1, "Low": 2})
    inventory["days_until_stockout"] = inventory["days_until_stockout"].replace(np.inf, np.nan)
    return inventory[
        [
            "product_line",
            "name",
            "quantity",
            "reorder_level",
            "recent_units_sold",
            "daily_velocity",
            "days_until_stockout",
            "risk",
            "risk_rank",
        ]
    ].sort_values(["risk_rank", "days_until_stockout", "quantity"], ascending=[True, True, True]).drop(columns=["risk_rank"])


def low_stock_df() -> pd.DataFrame:
    nails = get_products("press_on_nails").assign(product_line="Press-on nails")
    keys = get_products("keychains").assign(product_line="Keychains")
    cols = ["product_line", "name", "quantity", "reorder_level"]
    stock = pd.concat([nails[cols], keys[cols]], ignore_index=True)
    return stock[stock["quantity"] <= stock["reorder_level"]].sort_values(["quantity", "name"])


def restock(table: str, product_id: int, qty: int) -> None:
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET quantity = quantity + ? WHERE id = ?", (qty, product_id))


def add_manual_revenue(revenue_date: date, amount: float, label: str) -> None:
    clean_label = label.strip() or f"Manual Etsy revenue {revenue_date.strftime('%Y-%m')}"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sales
            (
                sale_date, product_type, product_id, product_name, quantity,
                unit_price, unit_cost, revenue, currency_code
            )
            VALUES (?, 'manual_revenue', 0, ?, 0, ?, 0, ?, 'USD')
            """,
            (revenue_date.isoformat(), clean_label, amount, amount),
        )


def delete_manual_revenue(sale_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM sales WHERE id = ? AND product_type = 'manual_revenue'",
            (sale_id,),
        )


def update_keychain_print_time(product_id: int, print_time: str | None) -> None:
    clean_time = print_time.strip() if print_time else None
    with connect() as conn:
        conn.execute("UPDATE keychains SET print_time = ? WHERE id = ?", (clean_time or None, product_id))


def update_keychain_production_details(
    product_id: int,
    print_time: str | None,
    materials: str | None,
) -> None:
    clean_time = print_time.strip() if print_time else None
    clean_materials = materials.strip() if materials else None
    with connect() as conn:
        conn.execute(
            "UPDATE keychains SET print_time = ?, materials = ? WHERE id = ?",
            (clean_time or None, clean_materials or None, product_id),
        )


def print_time_summary(print_time: str | None) -> str:
    if not print_time:
        return "Not set"
    lines = [line.strip() for line in str(print_time).splitlines() if line.strip()]
    if len(lines) > 1:
        return f"{len(lines)} plate times"
    return lines[0] if lines else "Not set"


def multiline_summary(value: str | None, item_name: str) -> str:
    if not value:
        return "Not set"
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    if len(lines) > 1:
        return f"{len(lines)} {item_name}"
    return lines[0] if lines else "Not set"


def clean_multiline_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def parse_print_time_minutes(line: str) -> int | None:
    time_text = str(line).lower().split(":", 1)[-1]
    hours = sum(int(match.group(1)) for match in re.finditer(r"(\d+)\s*h", time_text))
    minutes = sum(int(match.group(1)) for match in re.finditer(r"(\d+)\s*m", time_text))
    if not hours and not minutes:
        return None
    return hours * 60 + minutes


def format_print_time_total(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h{minutes:02d}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def total_print_time_summary(time_lines: list[str]) -> str | None:
    durations = [parse_print_time_minutes(line) for line in time_lines]
    total_minutes = sum(duration for duration in durations if duration is not None)
    if total_minutes <= 0:
        return None
    return format_print_time_total(total_minutes)


def render_keychain_production_panel(print_time: str | None, materials: str | None) -> None:
    time_lines = clean_multiline_lines(print_time)
    material_lines = clean_multiline_lines(materials)
    if not time_lines and not material_lines:
        st.caption("Production details not set.")
        return

    st.markdown("**Production details**")
    if time_lines:
        st.caption("Plate print times")
        total_time = total_print_time_summary(time_lines)
        if total_time:
            st.metric("Total print time", total_time)
        for line in time_lines:
            st.markdown(f"- {html.escape(line)}")
    if material_lines:
        st.caption("Plate colors / filament")
        for line in material_lines:
            st.markdown(f"- {html.escape(line)}")


def add_product(product_type: str, payload: dict) -> None:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    with connect() as conn:
        if table == "press_on_nails":
            conn.execute(
                """
                INSERT INTO press_on_nails
                (
                    name, description, shape, length, color_id, price,
                    currency_code, cost, quantity, reorder_level, tags,
                    materials, image_url, image_urls, sku, variation_1_name,
                    variation_1_values, variation_2_name, variation_2_values
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"],
                    payload.get("description"),
                    payload["shape"],
                    payload["length"],
                    payload["color_id"],
                    payload["price"],
                    payload.get("currency_code", "USD"),
                    payload["cost"],
                    payload["quantity"],
                    payload["reorder_level"],
                    payload.get("tags"),
                    payload.get("materials"),
                    payload.get("image_url"),
                    payload.get("image_urls"),
                    payload.get("sku"),
                    payload.get("variation_1_name"),
                    payload.get("variation_1_values"),
                    payload.get("variation_2_name"),
                    payload.get("variation_2_values"),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO keychains
                (
                    name, description, style, color_id, price, currency_code,
                    cost, quantity, reorder_level, print_time, tags, materials, image_url,
                    image_urls, model_file_path, sku, variation_1_name, variation_1_values,
                    variation_2_name, variation_2_values
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"],
                    payload.get("description"),
                    payload["style"],
                    payload["color_id"],
                    payload["price"],
                    payload.get("currency_code", "USD"),
                    payload["cost"],
                    payload["quantity"],
                    payload["reorder_level"],
                    payload.get("print_time"),
                    payload.get("tags"),
                    payload.get("materials"),
                    payload.get("image_url"),
                    payload.get("image_urls"),
                    payload.get("model_file_path"),
                    payload.get("sku"),
                    payload.get("variation_1_name"),
                    payload.get("variation_1_values"),
                    payload.get("variation_2_name"),
                    payload.get("variation_2_values"),
                ),
            )


def add_sale(product_type: str, product_id: int, qty: int, sold_on: date) -> None:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    product = query_df(f"SELECT id, name, price, cost, quantity FROM {table} WHERE id = ?", (product_id,))
    if product.empty:
        raise ValueError("Product not found")
    row = product.iloc[0]
    revenue = round(qty * float(row["price"]), 2)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sales
            (sale_date, product_type, product_id, product_name, quantity, unit_price, unit_cost, revenue)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sold_on.isoformat(), product_type, product_id, row["name"], qty, row["price"], row["cost"], revenue),
        )
        conn.execute(f"UPDATE {table} SET quantity = MAX(quantity - ?, 0) WHERE id = ?", (qty, product_id))


def get_reviews() -> pd.DataFrame:
    return query_df("SELECT * FROM reviews ORDER BY review_date DESC, id DESC")


def add_review(
    review_date: date,
    product_name: str,
    rating: int,
    customer_name: str,
    review_text: str,
    notes: str,
    order_id: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO reviews
            (review_date, product_name, rating, customer_name, review_text, notes, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_date.isoformat(),
                product_name,
                rating,
                customer_name or None,
                review_text or None,
                notes or None,
                order_id or None,
            ),
        )


def add_color(
    name: str,
    hex_code: str,
    finish: str,
    brand: str,
    swatch_id: str,
    in_stock: bool,
    catalog_type: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO colors (name, hex_code, finish, brand, swatch_id, in_stock, catalog_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, hex_code, finish, brand or None, swatch_id or None, int(in_stock), catalog_type),
        )


def update_color_stock(color_id: int, in_stock: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE colors SET in_stock = ? WHERE id = ?",
            (int(in_stock), color_id),
        )


def color_text(hex_code: str) -> str:
    clean = hex_code.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(ch * 2 for ch in clean)
    try:
        r, g, b = int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)
    except (ValueError, IndexError):
        return "#1B1B1B"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#1B1B1B" if luminance > 150 else "#FFFFFF"


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    clean = str(hex_code).strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(ch * 2 for ch in clean)
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def color_shade_sort_key(hex_code: str) -> tuple[float, float, float, float]:
    try:
        r, g, b = hex_to_rgb(hex_code)
    except (ValueError, IndexError):
        return (9, 0, 0, 0)
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    lightness = (max(r, g, b) + min(r, g, b)) / 510
    if saturation < 0.14:
        return (0, lightness, saturation, value)
    return (1, hue, saturation, value)


def style_page() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap');
        :root {{
            --brand-primary: {BRAND_PRIMARY};
            --brand-bg: #ffffff;
            --display-font: "Cormorant Garamond", Georgia, "Times New Roman", serif;
        }}
        .stApp {{
            background: #ffffff;
        }}
        [data-testid="stAppViewContainer"] {{
            background: #ffffff;
        }}
        [data-testid="stSidebar"] {{
            background: #ffffff;
        }}
        [data-testid="stHeader"] {{
            background: rgba(255, 255, 255, 0.94);
            backdrop-filter: blur(6px);
        }}
        h1, h2, h3 {{
            font-family: var(--display-font);
            letter-spacing: 0;
            font-weight: 600;
        }}
        h1 {{
            font-size: 2.5rem;
            line-height: 1.08;
        }}
        div[data-testid="stMetric"] {{
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(183, 110, 121, 0.18);
            border-radius: 8px;
            padding: 0.85rem 0.9rem;
            box-shadow: 0 1px 8px rgba(27, 27, 27, 0.05);
        }}
        .stock-card {{
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(27, 27, 27, 0.08);
            border-radius: 8px;
            padding: 0.85rem;
            margin-bottom: 0.7rem;
        }}
        .nail-grid-card {{
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(27, 27, 27, 0.08);
            border-radius: 8px;
            padding: 0.8rem;
            margin-bottom: 0.85rem;
            min-height: 150px;
        }}
        .nail-grid-card strong {{
            display: block;
            line-height: 1.22;
            margin-bottom: 0.35rem;
        }}
        .nail-grid-card small {{
            color: rgba(27, 27, 27, 0.68);
        }}
        .nail-grid-card p {{
            color: rgba(27, 27, 27, 0.74);
            font-size: 0.88rem;
            line-height: 1.35;
            margin: 0.55rem 0 0;
        }}
        .nail-image-placeholder {{
            align-items: center;
            background: rgba(255, 255, 255, 0.82);
            border: 1px dashed rgba(183, 110, 121, 0.32);
            border-radius: 8px;
            color: rgba(27, 27, 27, 0.48);
            display: flex;
            font-size: 0.9rem;
            justify-content: center;
            margin-bottom: 0.5rem;
            min-height: 160px;
        }}
        .low {{
            border-color: rgba(210, 4, 45, 0.32);
            background: rgba(255, 245, 247, 0.92);
        }}
        .swatch {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            display: inline-block;
            vertical-align: -3px;
            border: 1px solid rgba(0,0,0,0.18);
            margin-right: 8px;
        }}
        .swatch-chart {{
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(27, 27, 27, 0.08);
            border-radius: 8px;
            padding: 0.9rem;
            margin-bottom: 1rem;
        }}
        .swatch-chart-title {{
            color: rgba(27, 27, 27, 0.72);
            font-size: 0.88rem;
            font-weight: 700;
            margin: 0 0 0.65rem;
            text-transform: uppercase;
        }}
        .swatch-grid {{
            display: grid;
            gap: 0.65rem;
            grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
        }}
        .swatch-tile {{
            border: 1px solid rgba(27, 27, 27, 0.1);
            border-radius: 8px;
            overflow: hidden;
            min-height: 128px;
            background: #fff;
        }}
        .swatch-chip {{
            border-bottom: 1px solid rgba(27, 27, 27, 0.1);
            height: 58px;
        }}
        .swatch-meta {{
            padding: 0.45rem 0.5rem 0.55rem;
        }}
        .swatch-meta strong {{
            display: block;
            font-size: 0.82rem;
            line-height: 1.12;
        }}
        .swatch-meta small {{
            color: rgba(27, 27, 27, 0.62);
            display: block;
            font-size: 0.72rem;
            line-height: 1.2;
            margin-top: 0.2rem;
        }}
        .swatch-out {{
            outline: 2px solid rgba(210, 4, 45, 0.42);
        }}
        @media (max-width: 640px) {{
            .block-container {{
                padding-left: 0.85rem;
                padding-right: 0.85rem;
                padding-top: 1.1rem;
            }}
            div[data-testid="column"] {{
                width: 100% !important;
                flex: 1 1 100% !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.title("NailsByHuntrr")
    st.caption("Etsy inventory, sales, and product catalog")


def render_overview() -> None:
    sales = get_sales(etsy_history_start(), date.today())

    shop_stats = load_shop_stats()
    if shop_stats:
        st.subheader("Shop stats")
        st.caption(f"{shop_stats.get('date_range', 'All time')} | {shop_stats.get('updated_label', 'Updated')}")
        stat_cols = st.columns(6)
        stat_cols[0].metric("Etsy revenue", money(float(shop_stats.get("revenue", 0))))
        stat_cols[1].metric("Orders", f"{int(shop_stats.get('orders', 0)):,.0f}")
        stat_cols[2].metric("Sales", f"{int(shop_stats.get('sales', 0)):,.0f}")
        stat_cols[3].metric("Favorites", f"{int(shop_stats.get('favorites', 0)):,.0f}")
        stat_cols[4].metric("Total views", compact_number(shop_stats.get("total_views", 0)))
        stat_cols[5].metric("Visits", f"{int(shop_stats.get('visits', 0)):,.0f}")

    if sales.empty:
        st.info("No sales yet.")
        return

    sales["sale_date"] = pd.to_datetime(sales["sale_date"])
    daily = sales.groupby("sale_date", as_index=False)["revenue"].sum()
    st.subheader("Revenue trend")
    fig = px.line(daily, x="sale_date", y="revenue", color_discrete_sequence=[BRAND_PRIMARY])
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300, yaxis_title=None, xaxis_title=None)
    st.plotly_chart(fig, width="stretch")


def render_etsy_api() -> None:
    st.subheader("Etsy API")
    st.caption("Connects this local dashboard to your own Etsy shop through Etsy Open API v3.")
    st.info(
        "Etsy requires an app key, shared secret, OAuth approval, and an exact HTTPS redirect URI. "
        "For a private tool that only accesses your own shop, Etsy says commercial access is not required."
    )

    creds = etsy_get_credentials()
    with st.expander("1. Etsy app credentials", expanded=not bool(creds["keystring"])):
        with st.form("etsy_credentials_form"):
            keystring = st.text_input("API keystring", value=creds["keystring"] or "")
            shared_secret = st.text_input(
                "Shared secret",
                value=creds["shared_secret"] or "",
                type="password",
            )
            redirect_uri = st.text_input(
                "Redirect URI registered in Etsy",
                value=creds["redirect_uri"] or "",
                placeholder="https://your-domain.example/etsy-callback",
            )
            saved = st.form_submit_button("Save Etsy credentials", width="stretch")
        if saved:
            if not keystring.strip() or not shared_secret.strip() or not redirect_uri.strip():
                st.warning("Add the keystring, shared secret, and redirect URI.")
            elif not redirect_uri.strip().startswith("https://"):
                st.warning("Etsy requires the redirect URI to start with https:// and match exactly.")
            else:
                etsy_save_credentials(keystring, shared_secret, redirect_uri)
                st.success("Etsy credentials saved locally.")
                st.rerun()

    creds = etsy_get_credentials()
    connected = bool(creds["access_token"] and creds["refresh_token"])
    status_cols = st.columns(4)
    status_cols[0].metric("OAuth", "Connected" if connected else "Not connected")
    status_cols[1].metric("User ID", creds["user_id"] or "-")
    status_cols[2].metric("Shop ID", creds["shop_id"] or "-")
    expires_at = int(creds["expires_at"] or "0")
    status_cols[3].metric("Token", "Fresh" if expires_at > int(time.time()) else "Needs refresh")

    with st.expander("2. Connect OAuth", expanded=not connected and bool(creds["keystring"])):
        scopes = st.multiselect(
            "Scopes",
            ["listings_r", "shops_r", "transactions_r", "feedback_r"],
            default=["listings_r", "shops_r", "transactions_r"],
            key="etsy_scopes",
        )
        if st.button("Generate Etsy authorization link", width="stretch"):
            try:
                st.session_state["etsy_auth_url"] = etsy_build_auth_url(scopes)
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get("etsy_auth_url"):
            st.link_button("Open Etsy authorization", st.session_state["etsy_auth_url"], width="stretch")
            st.code(st.session_state["etsy_auth_url"], language="text")
        with st.form("etsy_callback_form"):
            callback_text = st.text_area(
                "Paste the full redirected URL from Etsy after approving access",
                placeholder="https://your-domain.example/etsy-callback?code=...&state=...",
            )
            exchanged = st.form_submit_button("Save OAuth token", width="stretch")
        if exchanged:
            try:
                etsy_exchange_code(callback_text)
                st.success("Etsy OAuth token saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander("3. Sync from Etsy", expanded=connected):
        manual_shop_id = st.text_input("Shop ID override", value=creds["shop_id"] or "")
        save_shop = st.button("Save shop ID", width="stretch")
        if save_shop:
            set_setting("etsy_shop_id", manual_shop_id.strip() or None)
            st.success("Shop ID saved.")
            st.rerun()
        sync_cols = st.columns(3)
        if sync_cols[0].button("Refresh token", width="stretch", disabled=not bool(creds["refresh_token"])):
            try:
                etsy_refresh_access_token()
                st.success("Token refreshed.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if sync_cols[1].button("Sync active listings", width="stretch", disabled=not connected):
            try:
                counts = etsy_sync_listings()
                st.success(f"Synced Etsy listings: {counts['inserted']} inserted, {counts['updated']} updated.")
            except Exception as exc:
                st.error(str(exc))
        if sync_cols[2].button("Sync revenue", width="stretch", disabled=not connected):
            try:
                counts = etsy_sync_revenue()
                st.success(
                    "Synced Etsy revenue: "
                    f"{counts['receipts']} receipts checked, "
                    f"{counts['inserted']} sales inserted, "
                    f"{counts['updated']} sales updated."
                )
            except requests.HTTPError as exc:
                st.error(
                    "Etsy did not allow the revenue sync. Reconnect OAuth with the "
                    "transactions_r scope checked, then try again. "
                    f"Details: {exc}"
                )
            except Exception as exc:
                st.error(str(exc))


def render_bambu_lab() -> None:
    st.subheader("Bambu Lab A1")
    st.caption("Connects to your A1 on your local Wi-Fi using bambulabs-api.")
    st.info(
        "This printer connection usually works only when this dashboard is running on the same local network as the A1. "
        "A Streamlit Cloud deployment normally cannot reach a printer inside your home Wi-Fi."
    )

    printer_class, import_error = bambu_load_printer_class()
    if printer_class is None:
        st.warning(
            "bambulabs-api is not available in this Python environment yet. "
            "It has been added to requirements.txt for deployment; restart the app after installing dependencies."
        )
        if import_error:
            st.caption(f"Import detail: {import_error}")

    creds = bambu_get_credentials()
    has_creds = all([creds["ip"], creds["access_code"], creds["serial"]])
    with st.expander("A1 printer credentials", expanded=not has_creds):
        st.caption("Find these on the A1 screen under Settings > WLAN.")
        with st.form("bambu_credentials_form"):
            ip = st.text_input("IP address", value=creds["ip"] or "", placeholder="192.168.1.123")
            access_code = st.text_input(
                "Access code",
                value=creds["access_code"] or "",
                type="password",
                placeholder="8-digit code from the A1",
            )
            serial = st.text_input("Serial number", value=creds["serial"] or "", placeholder="Printer serial number")
            saved = st.form_submit_button("Save Bambu credentials", width="stretch")
        if saved:
            if not ip.strip() or not access_code.strip() or not serial.strip():
                st.warning("Add the IP address, access code, and serial number.")
            else:
                bambu_save_credentials(ip, access_code, serial)
                st.success("Bambu credentials saved locally.")
                st.rerun()

        if st.button("Clear Bambu credentials", width="stretch", disabled=not has_creds):
            bambu_clear_credentials()
            st.success("Bambu credentials cleared.")
            st.rerun()

    creds = bambu_get_credentials()
    has_creds = all([creds["ip"], creds["access_code"], creds["serial"]])
    connected = bool(st.session_state.get("bambu_connected"))
    status = st.session_state.get("bambu_status") or {}

    status_cols = st.columns(4)
    status_cols[0].metric("Connection", "Connected" if connected else "Not connected")
    status_cols[1].metric("Printer state", bambu_status_value(status, ["gcode_state", "state", "status"]))
    status_cols[2].metric("Progress", bambu_status_value(status, ["mc_percent", "progress", "print_progress"]))
    status_cols[3].metric("Remaining", bambu_status_value(status, ["mc_remaining_time", "remaining_time", "time_remaining"]))

    actions = st.columns(3)
    if actions[0].button("Connect A1", width="stretch", disabled=not has_creds or printer_class is None):
        try:
            client = bambu_make_client(creds["ip"] or "", creds["access_code"] or "", creds["serial"] or "")
            bambu_connect_client(client)
            st.session_state["bambu_client"] = client
            st.session_state["bambu_connected"] = True
            st.session_state["bambu_status"] = bambu_get_status(client)
            st.success("Connected to Bambu A1.")
            st.rerun()
        except Exception as exc:
            st.session_state["bambu_connected"] = False
            st.error(f"Could not connect to the A1: {exc}")

    if actions[1].button("Refresh status", width="stretch", disabled=not connected):
        try:
            client = st.session_state.get("bambu_client")
            if client is None:
                raise RuntimeError("No active Bambu client in session. Connect first.")
            st.session_state["bambu_status"] = bambu_get_status(client)
            st.success("Printer status refreshed.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not refresh printer status: {exc}")

    if actions[2].button("Disconnect", width="stretch", disabled=not connected):
        client = st.session_state.get("bambu_client")
        if client is not None:
            try:
                bambu_disconnect_client(client)
            except Exception:
                pass
        st.session_state.pop("bambu_client", None)
        st.session_state["bambu_connected"] = False
        st.success("Disconnected from Bambu A1.")
        st.rerun()

    with st.expander("Raw printer status", expanded=bool(status)):
        if status:
            st.json(status)
        else:
            st.caption("Connect and refresh to see printer status data.")


def render_api_integrations() -> None:
    st.subheader("API")
    st.caption("External integrations for your Etsy shop and production tools.")
    render_bambu_lab()
    st.divider()
    render_etsy_api()


def render_inventory_export(table: str, products: pd.DataFrame) -> None:
    export_cols = [
        col
        for col in [
            "name",
            "description",
            "descriptor",
            "color_name",
            "price",
            "currency_code",
            "cost",
            "quantity",
            "reorder_level",
            "print_time",
            "tags",
            "materials",
            "image_url",
            "model_file_path",
            "sku",
        ]
        if col in products.columns
    ]
    st.download_button(
        "Download inventory CSV",
        products[export_cols].to_csv(index=False),
        file_name=f"{table}_inventory.csv",
        mime="text/csv",
        width="stretch",
    )


def display_image_source(image_url: str | None, image_urls: str | None = None):
    candidates = []
    if image_url:
        candidates.append(str(image_url).strip())
    if image_urls:
        candidates.extend(url.strip() for url in str(image_urls).split(",") if url.strip())
    if not candidates:
        return None
    source = candidates[0]
    if source.startswith(("http://", "https://")):
        return source.replace("il_fullxfull.", "il_570xN.")
    return APP_DIR / source


def render_nails_grid(products: pd.DataFrame) -> None:
    columns_per_row = 3
    for start in range(0, len(products), columns_per_row):
        cols = st.columns(columns_per_row)
        for col, product in zip(cols, products.iloc[start : start + columns_per_row].itertuples()):
            with col:
                description = getattr(product, "description", None) or ""
                display_image = display_image_source(
                    getattr(product, "image_url", None),
                    getattr(product, "image_urls", None),
                )
                if display_image:
                    st.image(display_image, width="stretch")
                else:
                    st.markdown('<div class="nail-image-placeholder">No image</div>', unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="nail-grid-card">
                        <strong>{html.escape(str(product.name))}</strong>
                        <small>{html.escape(str(product.descriptor))} | {html.escape(str(product.color_name or 'No color'))}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                listing_details = {
                    "Tags": getattr(product, "tags", None),
                    "Materials": getattr(product, "materials", None),
                    "Variation 1": " - ".join(
                        v
                        for v in [
                            getattr(product, "variation_1_name", None),
                            getattr(product, "variation_1_values", None),
                        ]
                        if v
                    ),
                    "Variation 2": " - ".join(
                        v
                        for v in [
                            getattr(product, "variation_2_name", None),
                            getattr(product, "variation_2_values", None),
                        ]
                        if v
                    ),
                    "Images": getattr(product, "image_urls", None),
                    "Description": description,
                }
                if any(listing_details.values()):
                    with st.expander("Etsy details", expanded=False):
                        for label, value in listing_details.items():
                            if value:
                                st.markdown(f"**{label}:** {value}")


def render_inventory_table(product_type: str) -> None:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    show_inventory_numbers = product_type != "press_on_nails"
    products = get_products(product_type)
    if products.empty:
        st.info("No products yet.")
        return

    if not show_inventory_numbers:
        render_nails_grid(products)
        render_inventory_export(table, products)
        return

    for product in products.itertuples():
        low = product.quantity <= product.reorder_level
        card_class = "stock-card low" if low else "stock-card"
        model_file_path = getattr(product, "model_file_path", None)
        print_time = getattr(product, "print_time", None)
        materials = getattr(product, "materials", None)
        display_image = display_image_source(
            getattr(product, "image_url", None),
            getattr(product, "image_urls", None),
        )
        st.markdown(
            f"""
            <div class="{card_class}">
                <strong>{product.name}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if display_image or print_time or materials:
            detail_cols = st.columns([1, 2]) if display_image else st.columns([1])
            if display_image:
                detail_cols[0].image(display_image, width=160)
                with detail_cols[1]:
                    render_keychain_production_panel(print_time, materials)
            else:
                with detail_cols[0]:
                    render_keychain_production_panel(print_time, materials)
        if model_file_path:
            model_path = APP_DIR / model_file_path
            if model_path.exists():
                st.download_button(
                    "Download 3MF",
                    model_path.read_bytes(),
                    file_name=model_path.name,
                    mime="model/3mf",
                    key=f"download_model_{table}_{product.id}",
                    width="stretch",
                )
            else:
                st.warning(f"Missing 3MF file: {model_file_path}")
    export_cols = [
        col
        for col in [
            "name",
            "description",
            "descriptor",
            "color_name",
            "price",
            "currency_code",
            "cost",
            "quantity",
            "reorder_level",
            "print_time",
            "tags",
            "materials",
            "image_url",
            "model_file_path",
            "sku",
        ]
        if col in products.columns
    ]
    st.download_button(
        "Download inventory CSV",
        products[export_cols].to_csv(index=False),
        file_name=f"{table}_inventory.csv",
        mime="text/csv",
        width="stretch",
    )


def render_add_product(product_type: str) -> None:
    is_nail = product_type == "press_on_nails"
    label = "nail set" if is_nail else "keychain"
    color_catalog = "gel_polish" if is_nail else "filament"
    colors = get_colors(color_catalog)
    color_options = {"No color selected": None}
    color_options.update({row["name"]: int(row["id"]) for _, row in colors.iterrows()})

    with st.expander(f"Add {label}", expanded=False):
        if colors.empty:
            catalog_name = "Gel Polish Catalog" if is_nail else "3D Filament Colors"
            st.info(f"Add colors in {catalog_name} first, or save this without a color.")
        with st.form(f"add_{product_type}_form", clear_on_submit=True):
            name = st.text_input("Product name", key=f"{product_type}_name")
            color_name = st.selectbox("Color", list(color_options.keys()), key=f"{product_type}_color")
            if is_nail:
                price = 0.0
                cost = 0.0
                quantity = 0
                reorder = 1
                print_time = ""
                materials = ""
            else:
                price = st.number_input("Etsy price", min_value=0.0, value=20.0, step=1.0, key=f"{product_type}_price")
                cost = st.number_input("Cost to make", min_value=0.0, value=5.0, step=0.5, key=f"{product_type}_cost")
                quantity = st.number_input("Quantity", min_value=0, value=10, step=1, key=f"{product_type}_quantity")
                reorder = st.number_input("Reorder level", min_value=0, value=5, step=1, key=f"{product_type}_reorder")
                print_time = st.text_area(
                    "Plate print times",
                    placeholder="Plate 1: 2h 10m\nPlate 2: 1h 45m\nPlate 3: 2h 05m\nPlate 4: 1h 30m",
                    key=f"{product_type}_print_time",
                    height=120,
                )
                materials = st.text_area(
                    "Plate colors / filament",
                    placeholder="Plate 1: filament 1 white, 4 pink, 5 light pink",
                    key=f"{product_type}_materials",
                    height=120,
                )
            payload = {
                "name": name.strip(),
                "color_id": color_options[color_name],
                "price": float(price),
                "cost": float(cost),
                "quantity": int(quantity),
                "reorder_level": int(reorder),
                "print_time": print_time.strip() if not is_nail and print_time.strip() else None,
                "materials": materials.strip() if not is_nail and materials.strip() else None,
            }
            if is_nail:
                payload["shape"] = st.selectbox(
                    "Shape",
                    ["coffin", "almond", "square", "stiletto", "oval"],
                    key=f"{product_type}_shape",
                )
                payload["length"] = st.selectbox(
                    "Length",
                    ["short", "medium", "long", "XL"],
                    key=f"{product_type}_length",
                )
            else:
                payload["style"] = st.selectbox(
                    "Style",
                    ["beaded", "acrylic", "resin", "charm"],
                    key=f"{product_type}_style",
                )
            submitted = st.form_submit_button("Save product", width="stretch")
        if submitted:
            if not payload["name"]:
                st.warning("Add a product name first.")
            else:
                add_product(product_type, payload)
                st.success(f"Saved {payload['name']}.")
                st.rerun()


def render_product_page(product_type: str, title: str) -> None:
    st.subheader(title)
    render_add_product(product_type)
    render_inventory_table(product_type)


def render_legacy_add_product() -> None:
    st.subheader("Add product")
    colors = get_colors()
    color_options = {"No color selected": None}
    color_options.update({row["name"]: int(row["id"]) for _, row in colors.iterrows()})
    kind = st.segmented_control(
        "Product line",
        ["Press-on nails", "Keychains"],
        default="Press-on nails",
        key="add_product_line",
    )
    with st.form("add_product_form", clear_on_submit=True):
        name = st.text_input("Product name")
        color_name = st.selectbox("Color", list(color_options.keys()))
        price = st.number_input("Etsy price", min_value=0.0, value=20.0, step=1.0)
        cost = st.number_input("Cost to make", min_value=0.0, value=5.0, step=0.5)
        quantity = st.number_input("Quantity", min_value=0, value=10, step=1)
        reorder = st.number_input("Reorder level", min_value=0, value=5, step=1)
        payload = {
            "name": name.strip(),
            "color_id": color_options[color_name],
            "price": float(price),
            "cost": float(cost),
            "quantity": int(quantity),
            "reorder_level": int(reorder),
        }
        if kind == "Press-on nails":
            payload["shape"] = st.selectbox("Shape", ["coffin", "almond", "square", "stiletto", "oval"])
            payload["length"] = st.selectbox("Length", ["short", "medium", "long", "XL"])
            product_type = "press_on_nails"
        else:
            payload["style"] = st.selectbox("Style", ["beaded", "acrylic", "resin", "charm"])
            product_type = "keychains"
        submitted = st.form_submit_button("Save product", width="stretch")
    if submitted:
        if not payload["name"]:
            st.warning("Add a product name first.")
        else:
            add_product(product_type, payload)
            st.success(f"Saved {payload['name']}.")
            st.rerun()


def render_inventory() -> None:
    tab_nails, tab_keys, tab_add = st.tabs(["Press-on nails", "Keychains", "Add"])
    with tab_nails:
        render_inventory_table("press_on_nails")
    with tab_keys:
        render_inventory_table("keychains")
    with tab_add:
        render_legacy_add_product()


def render_manual_revenue_tools(start: date, end: date, expanded: bool = False) -> None:
    with st.expander("Manual revenue", expanded=expanded):
        with st.form("manual_revenue_form", clear_on_submit=True):
            revenue_date = st.date_input(
                "Date",
                value=end,
                min_value=start,
                max_value=end,
                key="manual_revenue_date",
            )
            amount = st.number_input(
                "Revenue",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.2f",
                key="manual_revenue_amount",
            )
            label = st.text_input(
                "Label",
                value=f"Manual Etsy revenue {revenue_date.strftime('%Y-%m')}",
                key="manual_revenue_label",
            )
            submitted = st.form_submit_button("Add manual revenue", width="stretch")
        if submitted:
            if amount <= 0:
                st.warning("Enter a revenue amount above $0.")
            else:
                add_manual_revenue(revenue_date, float(amount), label)
                st.success("Manual revenue added.")
                st.rerun()

        manual = get_sales(start, end)
        manual = manual[manual["product_type"] == "manual_revenue"] if not manual.empty else manual
        if manual.empty:
            return
        st.markdown("**Manual entries**")
        for row in manual.sort_values("sale_date", ascending=False).itertuples():
            cols = st.columns([1, 2, 1, 0.7])
            cols[0].write(row.sale_date)
            cols[1].write(row.product_name)
            cols[2].write(money(float(row.revenue)))
            if cols[3].button("Remove", key=f"delete_manual_revenue_{row.id}"):
                delete_manual_revenue(int(row.id))
                st.success("Manual revenue removed.")
                st.rerun()


def render_revenue() -> None:
    bounds = query_df("SELECT MIN(sale_date) AS start_date, MAX(sale_date) AS end_date FROM sales").iloc[0]
    history_start = etsy_history_start()
    first_sale_date = pd.to_datetime(bounds["start_date"]).date() if bounds["start_date"] else None
    min_date = min(first_sale_date, history_start) if first_sale_date else history_start
    max_date = max(pd.to_datetime(bounds["end_date"]).date(), date.today()) if bounds["end_date"] else date.today()
    default_start = history_start

    filters = st.columns(2)
    start = filters[0].date_input("Start", value=default_start, min_value=min_date, max_value=max_date)
    end = filters[1].date_input("End", value=max_date, min_value=min_date, max_value=max_date)
    if start > end:
        st.warning("Start date must be before end date.")
        return

    sales = get_sales(start, end)
    summary = summarize_sales(sales)
    cols = st.columns(4)
    cols[0].metric("Revenue", money(summary["revenue"]))
    cols[1].metric("Profit", money(summary["profit"]))
    cols[2].metric("Avg. order", money(summary["avg_order"]))
    cols[3].metric("Orders", f"{summary['orders']:,.0f}")

    render_manual_revenue_tools(min_date, max_date, expanded=sales.empty)

    if sales.empty:
        st.info("No sales in this range.")
        return

    sales["sale_date"] = pd.to_datetime(sales["sale_date"])
    sales["month"] = sales["sale_date"].dt.strftime("%Y-%m")
    monthly = sales.groupby("month", as_index=False)["revenue"].sum()
    top = sales.groupby("product_name", as_index=False)["revenue"].sum().sort_values("revenue", ascending=False).head(10)

    chart_col, top_col = st.columns([1.25, 1])
    with chart_col:
        st.subheader("Monthly revenue")
        fig = px.bar(monthly, x="month", y="revenue", color_discrete_sequence=[BRAND_PRIMARY])
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320, yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
    with top_col:
        st.subheader("Top products")
        fig = px.bar(top, x="revenue", y="product_name", orientation="h", color_discrete_sequence=[BRAND_PRIMARY])
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320, yaxis_title=None, xaxis_title=None)
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch")

    st.download_button(
        "Download sales CSV",
        sales.drop(columns=["month"]).to_csv(index=False),
        file_name="etsy_sales.csv",
        mime="text/csv",
        width="stretch",
    )


def render_orders() -> None:
    st.subheader("Orders")
    orders = get_sales()
    if orders.empty:
        st.info("No orders added yet.")
        return

    orders = orders.copy()
    orders["sale_date"] = pd.to_datetime(orders["sale_date"])
    orders = orders.sort_values("sale_date", ascending=False)
    summary = summarize_sales(orders)
    cols = st.columns(4)
    cols[0].metric("Orders", f"{summary['orders']:,.0f}")
    cols[1].metric("Revenue", money(summary["revenue"]))
    cols[2].metric("Units", f"{summary['units']:,.0f}")
    cols[3].metric("Avg. order", money(summary["avg_order"]))

    order_view = orders.copy()
    if "customer_name" not in order_view.columns:
        order_view["customer_name"] = ""
    order_view["order_id"] = order_view["etsy_receipt_id"].fillna(order_view["id"]).astype(str)
    order_view["sale_date"] = order_view["sale_date"].dt.strftime("%Y-%m-%d")
    order_view["revenue"] = order_view["revenue"].map(lambda value: money(float(value)))
    order_view["unit_price"] = order_view["unit_price"].map(lambda value: money(float(value)))
    order_view = order_view[
        [
            "sale_date",
            "order_id",
            "customer_name",
            "product_name",
            "quantity",
            "unit_price",
            "revenue",
            "product_type",
        ]
    ].rename(
        columns={
            "sale_date": "Date",
            "order_id": "Order ID",
            "customer_name": "Customer",
            "product_name": "Product",
            "quantity": "Qty",
            "unit_price": "Unit price",
            "revenue": "Revenue",
            "product_type": "Source",
        }
    )
    st.dataframe(order_view, hide_index=True, width="stretch")
    st.download_button(
        "Download orders CSV",
        order_view.to_csv(index=False),
        file_name="etsy_orders.csv",
        mime="text/csv",
        width="stretch",
    )


def render_sale_entry() -> None:
    st.subheader("Log Etsy sale")
    kind = st.segmented_control(
        "Product line",
        ["Press-on nails", "Keychains"],
        default="Press-on nails",
        key="sale_product_line",
    )
    product_type = "press_on_nails" if kind == "Press-on nails" else "keychains"
    products = get_products(product_type)
    if products.empty:
        st.info("Add products before logging sales.")
        return
    options = {f"{row['name']} ({int(row['quantity'])} left)": int(row["id"]) for _, row in products.iterrows()}
    with st.form("sale_form", clear_on_submit=True):
        product_label = st.selectbox("Product", list(options.keys()))
        qty = st.number_input("Quantity sold", min_value=1, value=1, step=1)
        sold_on = st.date_input("Sale date", value=date.today())
        submitted = st.form_submit_button("Save sale", width="stretch")
    if submitted:
        add_sale(product_type, options[product_label], int(qty), sold_on)
        st.success("Sale logged and inventory updated.")
        st.rerun()


def render_reviews() -> None:
    st.subheader("Reviews")
    reviews = get_reviews()

    if reviews.empty:
        cols = st.columns(3)
        cols[0].metric("Reviews", "0")
        cols[1].metric("Average rating", "0.0")
        cols[2].metric("5-star reviews", "0")
    else:
        cols = st.columns(3)
        cols[0].metric("Reviews", f"{len(reviews):,.0f}")
        cols[1].metric("Average rating", f"{reviews['rating'].mean():.1f}")
        cols[2].metric("5-star reviews", f"{int((reviews['rating'] == 5).sum()):,.0f}")

    if reviews.empty:
        st.info("No reviews added yet.")
        return

    for review in reviews.itertuples():
        stars = "*" * int(review.rating)
        order_text = f" | Order {review.order_id}" if getattr(review, "order_id", None) else ""
        st.markdown(
            f"""
            <div class="stock-card">
                <strong>{stars} {review.product_name}</strong><br>
                <small>{review.review_date} | {review.customer_name or "Customer"}{order_text}</small><br>
                {review.review_text or ""}
                {f"<br><small>Notes: {review.notes}</small>" if review.notes else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.download_button(
        "Download reviews CSV",
        reviews.to_csv(index=False),
        file_name="etsy_reviews.csv",
        mime="text/csv",
        width="stretch",
    )


def render_gel_polish_swatch_chart(colors: pd.DataFrame) -> None:
    sorted_colors = sorted(
        list(colors.itertuples()),
        key=lambda color: (
            color_shade_sort_key(color.hex_code),
            str(getattr(color, "swatch_id", "") or ""),
            str(color.name).lower(),
        ),
    )
    st.caption("All gel polish colors sorted by shade")
    columns_per_row = 6
    for row_start in range(0, len(sorted_colors), columns_per_row):
        row_colors = sorted_colors[row_start : row_start + columns_per_row]
        columns = st.columns(columns_per_row)
        for column, color in zip(columns, row_colors):
            with column:
                hex_code = str(color.hex_code)
                if not hex_code.startswith("#"):
                    hex_code = f"#{hex_code}"
                swatch_id = getattr(color, "swatch_id", None)
                name = f"#{swatch_id} {color.name}" if swatch_id else str(color.name)
                brand = getattr(color, "brand", None)
                finish = getattr(color, "finish", None)
                stock = "OUT" if not bool(color.in_stock) else "In stock"
                st.color_picker(
                    f"Swatch {color.id}",
                    value=hex_code,
                    key=f"gel_polish_chart_color_{color.id}",
                    disabled=True,
                    label_visibility="collapsed",
                )
                st.markdown(f"**{name}**")
                details = [hex_code]
                if brand:
                    details.append(str(brand))
                if finish:
                    details.append(str(finish))
                details.append(stock)
                st.caption(" | ".join(details))


def render_catalog(catalog_type: str, title: str) -> None:
    colors = get_colors(catalog_type)
    st.subheader(title)
    if catalog_type == "gel_polish" and not colors.empty:
        out_colors = colors[colors["in_stock"] == 0]
        if not out_colors.empty:
            st.subheader("Reorder ASAP")
            for color in out_colors.itertuples():
                brand = getattr(color, "brand", None)
                brand_text = f" | {brand}" if brand else ""
                swatch_id = getattr(color, "swatch_id", None)
                swatch_text = f" | Swatch {swatch_id}" if swatch_id else ""
                st.markdown(
                    f"""
                    <div class="stock-card low">
                        <strong><span class="swatch" style="background:{color.hex_code}"></span>{color.name}</strong><br>
                        <small>{color.hex_code} | {color.finish}{brand_text}{swatch_text}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if catalog_type == "gel_polish" and not colors.empty:
        with st.expander("Open large swatch chart", expanded=False):
            render_gel_polish_swatch_chart(colors)

    for color in colors.itertuples():
        in_stock = bool(color.in_stock)
        status = "In stock" if in_stock else "OUT"
        brand = getattr(color, "brand", None)
        swatch_id = getattr(color, "swatch_id", None)
        details = [color.hex_code, color.finish, status]
        if brand:
            details.insert(2, brand)
        if swatch_id:
            details.insert(-1, f"Swatch {swatch_id}")
        card_class = "stock-card" if in_stock else "stock-card low"
        cols = st.columns([1, 0.22])
        with cols[0]:
            st.markdown(
                f"""
                <div class="{card_class}">
                    <strong><span class="swatch" style="background:{color.hex_code}"></span>{color.name}</strong><br>
                    <small>{" | ".join(str(item) for item in details)}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cols[1]:
            button_label = "Mark OUT" if in_stock else "Mark in stock"
            if st.button(button_label, key=f"stock_{catalog_type}_{color.id}", width="stretch"):
                update_color_stock(int(color.id), not in_stock)
                st.rerun()
    if colors.empty:
        st.info("No colors added yet.")

    with st.expander("Add color", expanded=False):
        with st.form(f"{catalog_type}_color_form", clear_on_submit=True):
            name_label = "Nickname" if catalog_type == "gel_polish" else "Color name"
            name = st.text_input(name_label, key=f"{catalog_type}_color_name")
            hex_code = st.text_input("Hex code", value="#FFB7D5", key=f"{catalog_type}_hex")
            if catalog_type == "gel_polish":
                finish_options = ["gel", "regular lacquer", "glossy", "matte", "chrome", "glitter", "cat eye", "jelly"]
                finish_label = "Type of polish"
            else:
                finish_options = ["PLA", "PLA+", "PETG", "TPU", "ABS", "silk PLA", "matte PLA", "glitter PLA"]
                finish_label = "Material / finish"
            finish = st.selectbox(finish_label, finish_options, key=f"{catalog_type}_finish")
            brand = st.text_input("Brand", key=f"{catalog_type}_brand")
            swatch_id = ""
            if catalog_type == "gel_polish":
                swatch_id = st.text_input("Swatch ID", key=f"{catalog_type}_swatch_id")
            in_stock = st.checkbox("In stock", value=True, key=f"{catalog_type}_in_stock")
            submitted = st.form_submit_button("Save color", width="stretch")
        if submitted:
            if not name.strip() or not hex_code.startswith("#") or len(hex_code.strip()) not in (4, 7):
                st.warning("Use a color name and a hex code like #FFB7D5.")
            else:
                try:
                    add_color(
                        name.strip(),
                        hex_code.strip(),
                        finish,
                        brand.strip(),
                        swatch_id.strip(),
                        in_stock,
                        catalog_type,
                    )
                    st.success(f"Saved {name}.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That color name already exists in this catalog.")


def main() -> None:
    init_db()
    style_page()
    render_header()
    (
        overview,
        nails,
        keychains,
        gel_polish,
        filament,
        revenue,
        orders,
        reviews,
        api,
    ) = st.tabs(
        [
            "Overview",
            "Nails",
            "Keychains",
            "Gel Polish Catalog",
            "3D Filament Colors",
            "Revenue",
            "Orders",
            "Reviews",
            "API",
        ]
    )
    with overview:
        render_overview()
    with nails:
        render_product_page("press_on_nails", "Nails")
    with keychains:
        render_product_page("keychains", "Keychains")
    with gel_polish:
        render_catalog("gel_polish", "Gel Polish Catalog")
    with filament:
        render_catalog("filament", "3D Filament Colors")
    with revenue:
        render_revenue()
    with orders:
        render_orders()
    with reviews:
        render_reviews()
    with api:
        render_api_integrations()


if __name__ == "__main__":
    main()
