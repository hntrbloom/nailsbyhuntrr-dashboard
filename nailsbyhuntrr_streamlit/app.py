from __future__ import annotations

import base64
import hashlib
import html
import secrets
import random
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

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


st.set_page_config(
    page_title="NailsByHuntrr Dashboard",
    page_icon=".",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def money(value: float) -> str:
    return f"${value:,.2f}"


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
                tags TEXT,
                materials TEXT,
                image_url TEXT,
                image_urls TEXT,
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
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0
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
        product_columns = {
            "press_on_nails": {
                "etsy_listing_id": "INTEGER",
                "description": "TEXT",
                "currency_code": "TEXT NOT NULL DEFAULT 'USD'",
                "tags": "TEXT",
                "materials": "TEXT",
                "image_url": "TEXT",
                "image_urls": "TEXT",
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
                "tags": "TEXT",
                "materials": "TEXT",
                "image_url": "TEXT",
                "image_urls": "TEXT",
                "sku": "TEXT",
                "variation_1_name": "TEXT",
                "variation_1_values": "TEXT",
                "variation_2_name": "TEXT",
                "variation_2_values": "TEXT",
            },
            "reviews": {
                "order_id": "TEXT",
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
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    catalog_type TEXT NOT NULL DEFAULT 'gel_polish',
                    UNIQUE(name, catalog_type)
                );
                INSERT INTO colors_new (id, name, hex_code, finish, in_stock, catalog_type)
                SELECT id, name, hex_code, finish, in_stock, catalog_type FROM colors;
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
    headers = {"x-api-key": f"{creds['keystring']}:{creds['shared_secret']}"}
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
    orders = int(len(sales))
    units = int(sales["quantity"].sum())
    return {
        "revenue": revenue,
        "profit": profit,
        "orders": orders,
        "units": units,
        "avg_order": revenue / orders if orders else 0,
    }


def low_stock_df() -> pd.DataFrame:
    nails = get_products("press_on_nails").assign(product_line="Press-on nails")
    keys = get_products("keychains").assign(product_line="Keychains")
    cols = ["product_line", "name", "quantity", "reorder_level"]
    stock = pd.concat([nails[cols], keys[cols]], ignore_index=True)
    return stock[stock["quantity"] <= stock["reorder_level"]].sort_values(["quantity", "name"])


def restock(table: str, product_id: int, qty: int) -> None:
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET quantity = quantity + ? WHERE id = ?", (qty, product_id))


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
                    cost, quantity, reorder_level, tags, materials, image_url,
                    image_urls, sku, variation_1_name, variation_1_values,
                    variation_2_name, variation_2_values
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    in_stock: bool,
    catalog_type: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO colors (name, hex_code, finish, in_stock, catalog_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, hex_code, finish, int(in_stock), catalog_type),
        )


def style_page() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap');
        :root {{
            --brand-primary: {BRAND_PRIMARY};
            --brand-bg: #fff8fa;
            --display-font: "Cormorant Garamond", Georgia, "Times New Roman", serif;
        }}
        .stApp {{
            background: var(--brand-bg);
        }}
        [data-testid="stHeader"] {{
            background: rgba(255, 248, 250, 0.88);
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
            background: #ffffff;
            border: 1px solid rgba(183, 110, 121, 0.18);
            border-radius: 8px;
            padding: 0.85rem 0.9rem;
            box-shadow: 0 1px 8px rgba(27, 27, 27, 0.05);
        }}
        .stock-card {{
            background: #ffffff;
            border: 1px solid rgba(27, 27, 27, 0.08);
            border-radius: 8px;
            padding: 0.85rem;
            margin-bottom: 0.7rem;
        }}
        .low {{
            border-color: rgba(210, 4, 45, 0.32);
            background: #fff5f7;
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
    sales = get_sales(date.today() - timedelta(days=90), date.today())
    summary = summarize_sales(sales)
    cols = st.columns(4)
    cols[0].metric("Revenue", money(summary["revenue"]))
    cols[1].metric("Profit", money(summary["profit"]))
    cols[2].metric("Orders", f"{summary['orders']:,.0f}")
    cols[3].metric("Units sold", f"{summary['units']:,.0f}")

    low_stock = low_stock_df()
    if not low_stock.empty:
        labels = ", ".join(f"{r.name} ({r.quantity})" for r in low_stock.itertuples())
        st.error(f"Low stock: {labels}")

    if sales.empty:
        st.info("No sales yet.")
        return

    sales["sale_date"] = pd.to_datetime(sales["sale_date"])
    daily = sales.groupby("sale_date", as_index=False)["revenue"].sum()
    by_type = sales.groupby("product_type", as_index=False)["revenue"].sum()
    by_type["product_type"] = by_type["product_type"].map(
        {"press_on_nails": "Press-on nails", "keychains": "Keychains"}
    )

    chart_col, pie_col = st.columns([1.35, 1])
    with chart_col:
        st.subheader("Revenue trend")
        fig = px.line(daily, x="sale_date", y="revenue", color_discrete_sequence=[BRAND_PRIMARY])
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300, yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
    with pie_col:
        st.subheader("Product-line split")
        fig = px.pie(
            by_type,
            names="product_type",
            values="revenue",
            hole=0.48,
            color_discrete_sequence=CHART_COLORS,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
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
            default=["listings_r", "shops_r"],
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
        sync_cols = st.columns(2)
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


def render_inventory_table(product_type: str) -> None:
    table = "press_on_nails" if product_type == "press_on_nails" else "keychains"
    show_inventory_numbers = product_type != "press_on_nails"
    products = get_products(product_type)
    if products.empty:
        st.info("No products yet.")
        return

    if show_inventory_numbers:
        cost_value = float((products["quantity"] * products["cost"]).sum())
        retail_value = float((products["quantity"] * products["price"]).sum())
        cols = st.columns(3)
        cols[0].metric("SKUs", f"{len(products):,.0f}")
        cols[1].metric("Cost value", money(cost_value))
        cols[2].metric("Retail value", money(retail_value))

    for product in products.itertuples():
        low = product.quantity <= product.reorder_level
        card_class = "stock-card low" if low else "stock-card"
        status = "Low stock" if low else "In stock"
        sku_text = f" | SKU: {product.sku}" if show_inventory_numbers and getattr(product, "sku", None) else ""
        description = getattr(product, "description", None) or ""
        image_url = getattr(product, "image_url", None)
        card_meta = f"{product.descriptor} | {product.color_name or 'No color'}"
        if show_inventory_numbers:
            card_meta = f"{card_meta} | {money(product.price)} | {status}{sku_text}"
        st.markdown(
            f"""
            <div class="{card_class}">
                <strong><span class="swatch" style="background:{product.hex_code or BRAND_PRIMARY}"></span>{product.name}</strong><br>
                <small>{card_meta}</small>
                {f"<br><strong>{product.quantity}</strong> units on hand, reorder at {product.reorder_level}" if show_inventory_numbers else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if image_url or description:
            detail_cols = st.columns([1, 2]) if image_url else st.columns([1])
            if image_url:
                detail_cols[0].image(image_url, width=160)
                detail_cols[1].caption(description)
            else:
                detail_cols[0].caption(description)
        listing_details = {
            "Tags": getattr(product, "tags", None),
            "Materials": getattr(product, "materials", None),
            "Variation 1": " - ".join(
                v for v in [getattr(product, "variation_1_name", None), getattr(product, "variation_1_values", None)] if v
            ),
            "Variation 2": " - ".join(
                v for v in [getattr(product, "variation_2_name", None), getattr(product, "variation_2_values", None)] if v
            ),
            "Images": getattr(product, "image_urls", None),
        }
        if any(listing_details.values()):
            with st.expander(f"Etsy listing details for {product.name}", expanded=False):
                for label, value in listing_details.items():
                    if value:
                        st.markdown(f"**{label}:** {value}")
        if show_inventory_numbers:
            with st.expander(f"Restock {product.name}", expanded=False):
                qty = st.number_input("Units to add", min_value=1, max_value=999, value=10, key=f"restock_{table}_{product.id}")
                if st.button("Add stock", key=f"btn_restock_{table}_{product.id}", width="stretch"):
                    restock(table, int(product.id), int(qty))
                    st.success(f"Added {qty} units to {product.name}.")
                    st.rerun()

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
            "tags",
            "materials",
            "image_url",
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
            else:
                price = st.number_input("Etsy price", min_value=0.0, value=20.0, step=1.0, key=f"{product_type}_price")
                cost = st.number_input("Cost to make", min_value=0.0, value=5.0, step=0.5, key=f"{product_type}_cost")
                quantity = st.number_input("Quantity", min_value=0, value=10, step=1, key=f"{product_type}_quantity")
                reorder = st.number_input("Reorder level", min_value=0, value=5, step=1, key=f"{product_type}_reorder")
            payload = {
                "name": name.strip(),
                "color_id": color_options[color_name],
                "price": float(price),
                "cost": float(cost),
                "quantity": int(quantity),
                "reorder_level": int(reorder),
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


def render_revenue() -> None:
    bounds = query_df("SELECT MIN(sale_date) AS start_date, MAX(sale_date) AS end_date FROM sales").iloc[0]
    min_date = pd.to_datetime(bounds["start_date"]).date() if bounds["start_date"] else date.today() - timedelta(days=90)
    max_date = pd.to_datetime(bounds["end_date"]).date() if bounds["end_date"] else date.today()
    default_start = max(min_date, max_date - timedelta(days=90))

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

    product_names = []
    nails = get_products("press_on_nails")
    keychains = get_products("keychains")
    if not nails.empty:
        product_names.extend(nails["name"].tolist())
    if not keychains.empty:
        product_names.extend(keychains["name"].tolist())
    product_names = sorted(set(product_names))

    with st.expander("Add review", expanded=reviews.empty):
        with st.form("review_form", clear_on_submit=True):
            review_date = st.date_input("Review date", value=date.today(), key="review_date")
            if product_names:
                selected_product = st.selectbox("Product", ["Type manually", *product_names], key="review_product_select")
                manual_product = st.text_input("Product name", key="review_product_manual") if selected_product == "Type manually" else ""
                product_name = manual_product.strip() if selected_product == "Type manually" else selected_product
            else:
                product_name = st.text_input("Product name", key="review_product_name").strip()
            rating = st.slider("Rating", min_value=1, max_value=5, value=5, key="review_rating")
            customer_name = st.text_input("Customer name", key="review_customer")
            review_text = st.text_area("Review text", key="review_text")
            notes = st.text_area("Private notes", key="review_notes")
            submitted = st.form_submit_button("Save review", width="stretch")
        if submitted:
            if not product_name:
                st.warning("Add a product name first.")
            else:
                add_review(review_date, product_name, int(rating), customer_name.strip(), review_text.strip(), notes.strip())
                st.success("Review saved.")
                st.rerun()

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


def render_catalog(catalog_type: str, title: str) -> None:
    colors = get_colors(catalog_type)
    st.subheader(title)
    for color in colors.itertuples():
        status = "In stock" if color.in_stock else "Out of stock"
        st.markdown(
            f"""
            <div class="stock-card">
                <strong><span class="swatch" style="background:{color.hex_code}"></span>{color.name}</strong><br>
                <small>{color.hex_code} | {color.finish} | {status}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if colors.empty:
        st.info("No colors added yet.")

    with st.expander("Add color", expanded=False):
        with st.form(f"{catalog_type}_color_form", clear_on_submit=True):
            name = st.text_input("Color name", key=f"{catalog_type}_color_name")
            hex_code = st.text_input("Hex code", value="#FFB7D5", key=f"{catalog_type}_hex")
            if catalog_type == "gel_polish":
                finish_options = ["glossy", "matte", "chrome", "glitter", "cat eye", "jelly"]
                finish_label = "Finish"
            else:
                finish_options = ["PLA", "PETG", "TPU", "ABS", "silk PLA", "matte PLA", "glitter PLA"]
                finish_label = "Material / finish"
            finish = st.selectbox(finish_label, finish_options, key=f"{catalog_type}_finish")
            in_stock = st.checkbox("In stock", value=True, key=f"{catalog_type}_in_stock")
            submitted = st.form_submit_button("Save color", width="stretch")
        if submitted:
            if not name.strip() or not hex_code.startswith("#") or len(hex_code.strip()) not in (4, 7):
                st.warning("Use a color name and a hex code like #FFB7D5.")
            else:
                try:
                    add_color(name.strip(), hex_code.strip(), finish, in_stock, catalog_type)
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
        reviews,
        sales,
        etsy_api,
    ) = st.tabs(
        [
            "Overview",
            "Nails",
            "Keychains",
            "Gel Polish Catalog",
            "3D Filament Colors",
            "Revenue",
            "Reviews",
            "Log Sales",
            "Etsy API",
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
    with reviews:
        render_reviews()
    with sales:
        render_sale_entry()
    with etsy_api:
        render_etsy_api()


if __name__ == "__main__":
    main()
