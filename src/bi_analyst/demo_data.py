"""Builds a small, deterministic e-commerce database for demos and tests."""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
from pathlib import Path

REGIONS = ["North America", "Europe", "Asia", "South America"]
CATEGORIES = {"Electronics": (50, 900), "Home": (10, 300), "Books": (5, 40), "Clothing": (15, 150)}


def create_demo_db(path: str = "data/demo.db", seed: int = 7) -> str:
    rnd = random.Random(seed)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY, name TEXT, region TEXT, signup_date TEXT);
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL);
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id));
        CREATE TABLE order_items (
            item_id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER,
            quantity INTEGER, unit_price REAL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id));
        """
    )
    for i in range(1, 201):
        d = dt.date(2023, 1, 1) + dt.timedelta(days=rnd.randint(0, 700))
        con.execute("INSERT INTO customers VALUES (?,?,?,?)", (i, f"Customer {i}", rnd.choice(REGIONS), d.isoformat()))
    pid = 0
    for cat, (lo, hi) in CATEGORIES.items():
        for n in range(1, 9):
            pid += 1
            con.execute("INSERT INTO products VALUES (?,?,?,?)",
                        (pid, f"{cat} Item {n}", cat, round(rnd.uniform(lo, hi), 2)))
    item_id = 0
    for oid in range(1, 1501):
        d = dt.date(2024, 1, 1) + dt.timedelta(days=rnd.randint(0, 600))
        status = rnd.choices(["completed", "cancelled", "refunded"], [85, 8, 7])[0]
        con.execute("INSERT INTO orders VALUES (?,?,?,?)", (oid, rnd.randint(1, 200), d.isoformat(), status))
        for _ in range(rnd.randint(1, 4)):
            item_id += 1
            p = rnd.randint(1, pid)
            price = con.execute("SELECT unit_price FROM products WHERE product_id=?", (p,)).fetchone()[0]
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)", (item_id, oid, p, rnd.randint(1, 5), price))
    con.commit()
    con.close()
    return path
