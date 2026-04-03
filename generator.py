"""
generator.py — Procedural task generation.

Every call to generate_variant() produces a *unique* schema/data combination
for a given task family.  This means agents cannot memorise solutions —
they must generalise, which is exactly what the RL community needs.
"""

import random
import string
from typing import Any, Dict, List, Tuple


# ── Name pools ────────────────────────────────────────────────────────────────

_FIRST = ["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Hank",
          "Iris","Jack","Kim","Leo","Mia","Noah","Olivia","Paul",
          "Quinn","Rose","Sam","Tina","Uma","Victor","Wendy","Xander","Yara","Zoe"]

_LAST  = ["Smith","Jones","White","Brown","Davis","Miller","Wilson",
          "Moore","Taylor","Anderson","Thomas","Jackson","Harris","Martin"]

_CITIES   = ["New York","Los Angeles","Chicago","Houston","Phoenix",
             "Seattle","Boston","Denver","Atlanta","Miami","Austin","Portland"]

_PRODUCTS = ["Laptop","Phone","Tablet","Monitor","Keyboard","Mouse",
             "Headphones","Webcam","Printer","Scanner","Router","SSD",
             "RAM","GPU","CPU","Cable","Hub","Dock","Speaker","Camera"]

_CATEGORIES = ["Electronics","Furniture","Clothing","Books","Sports",
               "Garden","Kitchen","Toys","Automotive","Health"]

_DEPARTMENTS = ["Engineering","Marketing","Finance","HR","Sales",
                "Operations","Legal","Design","Product","Research"]

_STATUSES_ORDER = ["pending","processing","completed","cancelled","refunded"]
_STATUSES_PROJ  = ["active","completed","on_hold","cancelled"]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"


def _email(name: str, suffix: int = 0) -> str:
    parts = name.lower().replace(" ", ".")
    return f"{parts}{suffix if suffix else ''}@example.com"


def _date(rng: random.Random, year_range=(2022, 2024)) -> str:
    y = rng.randint(*year_range)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


# ═══════════════════════════════════════════════════════════════════════════
# Variant generators — one per task family
# ═══════════════════════════════════════════════════════════════════════════

def generate_fix_broken_query(seed: int) -> Dict[str, Any]:
    """
    Produce a new variant of the 'fix_broken_query' task.
    The broken query always has exactly 4 bugs (same bug *types*, different names).
    """
    rng = _rng(seed)

    # Pick 3-5 customers
    n_customers = rng.randint(3, 5)
    customers   = []
    for i in range(1, n_customers + 1):
        name  = _name(rng)
        email = _email(name, i if i > 1 else 0)
        city  = rng.choice(_CITIES)
        customers.append((i, name, email, city))

    # Pick orders — ensure at least one 'completed' per customer
    orders = []
    oid    = 1
    for cust in customers:
        n_orders = rng.randint(1, 3)
        for _ in range(n_orders):
            amt    = round(rng.uniform(20, 500), 2)
            status = rng.choice(_STATUSES_ORDER)
            date   = _date(rng)
            orders.append((oid, cust[0], amt, status, date))
            oid += 1
    # Ensure at least 2 customers have 'completed' orders
    for cust in customers[:3]:
        amt  = round(rng.uniform(50, 300), 2)
        date = _date(rng)
        orders.append((oid, cust[0], amt, "completed", date))
        oid += 1

    # Intentional bugs
    wrong_table_alias  = rng.choice(["custmer", "cust_r", "custm", "cstomer"])
    wrong_col_alias    = rng.choice(["custmer_id", "cust_id_wrong", "customerid"])
    wrong_status_col   = rng.choice(["statue", "statu", "statuss", "sttaus"])
    wrong_order_dir    = rng.choice(["DESK", "DESCC", "DECS", "DESC DESC"])

    broken_sql = (
        f"SELECT {wrong_table_alias}.name, {wrong_table_alias}.email, "
        f"SUM(ord.total_amount) as total_spent\n"
        f"FROM customers {wrong_table_alias}\n"
        f"INNER JOIN orders ord ON {wrong_table_alias}.id = ord.{wrong_col_alias}\n"
        f"WHERE ord.{wrong_status_col} = 'completed'\n"
        f"GROUP BY {wrong_table_alias}.id\n"
        f"ORDER BY total_spent {wrong_order_dir}"
    )

    # Expected: customers with completed orders, ordered by total DESC
    totals = {}
    for o in orders:
        if o[3] == "completed":
            totals[o[1]] = totals.get(o[1], 0) + o[2]
    expected_rows = []
    for cid, total in sorted(totals.items(), key=lambda x: -x[1]):
        cust = next(c for c in customers if c[0] == cid)
        expected_rows.append({"name": cust[1], "email": cust[2],
                               "total_spent": round(total, 2)})

    seed_data = []
    for c in customers:
        seed_data.append(
            f"INSERT INTO customers VALUES ({c[0]}, '{c[1]}', '{c[2]}', '{c[3]}')"
        )
    for o in orders:
        seed_data.append(
            f"INSERT INTO orders VALUES ({o[0]}, {o[1]}, {o[2]}, '{o[3]}', '{o[4]}')"
        )

    bugs = [
        f"Table alias '{wrong_table_alias}' should be a valid alias (e.g. 'c')",
        f"Column 'ord.{wrong_col_alias}' should be 'ord.customer_id'",
        f"Column 'ord.{wrong_status_col}' should be 'ord.status'",
        f"ORDER BY direction '{wrong_order_dir}' should be 'DESC'",
    ]

    return {
        "seed": seed,
        "broken_sql": broken_sql,
        "bugs": bugs,
        "seed_data": seed_data,
        "expected": {
            "row_count": len(expected_rows),
            "data": expected_rows,
        },
        "description_suffix": (
            f"\nTHE BROKEN QUERY:\n```sql\n{broken_sql}\n```\n\n"
            f"Fix all 4 bugs and submit the corrected query.\n"
            f"Expected: {len(expected_rows)} rows ordered by total_spent DESC."
        ),
    }


def generate_business_query(seed: int) -> Dict[str, Any]:
    """Vary the HR schema: different dept names, salaries, employee counts."""
    rng = _rng(seed)

    depts = rng.sample(_DEPARTMENTS, 4)
    dept_rows = []
    for i, name in enumerate(depts, 1):
        budget   = round(rng.uniform(200_000, 1_200_000), 0)
        location = rng.choice(_CITIES)
        dept_rows.append((i, name, budget, location))

    employees = []
    eid = 1
    # Ensure 3 depts have >1 employee (1 dept has exactly 1)
    single_dept = rng.randint(1, 4)
    for did, dname, _, _ in dept_rows:
        count = 1 if did == single_dept else rng.randint(2, 4)
        for _ in range(count):
            name   = _name(rng)
            salary = round(rng.uniform(60_000, 200_000), 0)
            date   = _date(rng, (2017, 2023))
            employees.append((eid, name, did, salary, date))
            eid += 1

    seed_data = []
    for d in dept_rows:
        seed_data.append(
            f"INSERT INTO departments VALUES ({d[0]}, '{d[1]}', {d[2]}, '{d[3]}')"
        )
    for e in employees:
        seed_data.append(
            f"INSERT INTO employees VALUES ({e[0]}, '{e[1]}', {e[2]}, {e[3]}, '{e[4]}')"
        )

    # Pre-compute expected answers
    from collections import defaultdict
    dept_emps = defaultdict(list)
    for e in employees:
        dept_emps[e[2]].append(e)

    expected = []
    for did, dname, _, _ in dept_rows:
        emps = dept_emps[did]
        if len(emps) > 1:
            avg_sal  = round(sum(e[3] for e in emps) / len(emps), 2)
            top_name = max(emps, key=lambda x: x[3])[1]
            expected.append({
                "dept": dname,
                "emp_count": len(emps),
                "avg_salary": avg_sal,
                "top_earner": top_name,
            })
    expected.sort(key=lambda x: -x["avg_salary"])

    return {
        "seed": seed,
        "seed_data": seed_data,
        "expected": expected,
        "single_dept_name": depts[single_dept - 1],
    }


def generate_incident_response(seed: int) -> Dict[str, Any]:
    """Generate a production-DB incident with randomised corruption patterns."""
    rng  = _rng(seed)

    products  = rng.sample(_PRODUCTS, 6)
    customers = [_name(rng) for _ in range(5)]

    # Decide which corruptions to inject (always exactly 3 types)
    corruption_pool = [
        "negative_price", "orphan_fk", "duplicate_primary",
        "null_required", "future_date", "wrong_currency"
    ]
    chosen = rng.sample(corruption_pool, 3)

    return {
        "seed": seed,
        "corruptions": chosen,
        "products": products,
        "customers": customers,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def get_variant(task_id: str, seed: int) -> Dict[str, Any]:
    """Return a procedurally generated variant for *task_id* using *seed*."""
    generators = {
        "fix_broken_query":    generate_fix_broken_query,
        "write_business_query": generate_business_query,
    }
    fn = generators.get(task_id)
    if fn:
        return fn(seed)
    return {}
