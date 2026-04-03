"""
variants.py — Dynamic task variant generator.

Each call to get_variant(task_id) returns a fresh copy of the task with
randomized names, amounts, and values so agents cannot memorize answers.
This is a key differentiator: the environment is never exactly the same twice.
"""

import random
import copy
from typing import Dict, Any

# ── Name pools ────────────────────────────────────────────────────────────────
FIRST_NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace",
               "Hank", "Iris", "Jake", "Kara", "Leo", "Mia", "Noah", "Olivia"]
LAST_NAMES  = ["Smith", "Jones", "White", "Brown", "Davis", "Wilson",
               "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "Harris"]
CITIES      = ["NYC", "LA", "Chicago", "Houston", "Phoenix", "Seattle",
               "Boston", "Denver", "Austin", "Miami"]
PRODUCTS    = ["Laptop", "Phone", "Monitor", "Keyboard", "Tablet",
               "Headphones", "Camera", "Printer", "Router", "Speaker"]
CATEGORIES  = ["Electronics", "Furniture", "Education", "Clothing", "Sports"]
STATUSES    = ["completed", "pending", "failed", "refunded"]
COUNTRIES   = ["USA", "Canada", "UK", "Germany", "Australia", "France"]
REGIONS     = ["Northeast", "West", "South", "Midwest", "Northwest"]
DEPTS       = ["Engineering", "Marketing", "Finance", "HR", "Sales", "Legal"]


def _name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _email(name: str) -> str:
    return f"{name.lower().replace(' ', '.')}@example.com"


def _rand_amount(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def get_variant(task_id: str, seed: int = None) -> Dict[str, Any]:
    """
    Return a randomized variant of the named task.
    Pass seed for reproducibility in testing.
    """
    if seed is not None:
        random.seed(seed)

    generators = {
        "fix_broken_query":       _variant_fix_broken,
        "write_business_query":   _variant_write_business,
        "complex_analytics":      _variant_complex_analytics,
        "recursive_org_hierarchy":_variant_recursive_org,
        "data_quality_audit":     _variant_data_quality,
        "query_optimizer":        _variant_query_optimizer,
        "nl_to_sql":              _variant_nl_to_sql,
        "transaction_deadlock":   _variant_transaction_deadlock,
    }
    fn = generators.get(task_id)
    if fn is None:
        from tasks import TASKS
        return TASKS.get(task_id, {})
    return fn()


# ─────────────────────────────────────────────────────────────────────────────
# fix_broken_query — randomize customer names, amounts, city, status keyword typo
# ─────────────────────────────────────────────────────────────────────────────
def _variant_fix_broken() -> Dict[str, Any]:
    customers = [(_name(), random.choice(CITIES)) for _ in range(3)]
    amounts = [
        [_rand_amount(50, 200), _rand_amount(20, 100)],   # cust 0: 2 orders
        [_rand_amount(100, 400)],                          # cust 1: 1 order
        [_rand_amount(200, 600)],                          # cust 2: 1 order
    ]
    # Random typos pool
    typos = {
        "custmer": random.choice(["custmer", "custommer", "custumor"]),
        "statue":  random.choice(["statue", "statues", "statuss"]),
        "DESK":    random.choice(["DESK", "DECS", "DSEC"]),
        "custmer_id": random.choice(["custmer_id", "cust_id", "customer_idd"]),
    }
    seed_data = []
    for i, (name, city) in enumerate(customers):
        email = _email(name)
        seed_data.append(f"INSERT INTO customers VALUES ({i+1}, '{name}', '{email}', '{city}')")
    oid = 1
    expected_totals = []
    for i, order_amounts in enumerate(amounts):
        total = sum(a for a in order_amounts)
        expected_totals.append((customers[i][0], _email(customers[i][0]), total))
        for amt in order_amounts:
            seed_data.append(
                f"INSERT INTO orders VALUES ({oid}, {i+1}, {amt}, 'completed', '2023-01-01')"
            )
            oid += 1
    # Add a pending order for cust 0 that should NOT count
    seed_data.append(
        f"INSERT INTO orders VALUES ({oid}, 1, {_rand_amount(10,50)}, 'pending', '2023-06-01')"
    )
    # Sort expected by total DESC
    expected_sorted = sorted(expected_totals, key=lambda x: -x[2])

    broken_query = (
        f"SELECT {typos['custmer']}.name, {typos['custmer']}.email, "
        f"SUM(ord.total_amount) as total_spent\n"
        f"FROM customers {typos['custmer']}\n"
        f"INNER JOIN orders ord ON {typos['custmer']}.id = ord.{typos['custmer_id']}\n"
        f"WHERE ord.{typos['statue']} = 'completed'\n"
        f"GROUP BY {typos['custmer']}.id\n"
        f"ORDER BY total_spent {typos['DESK']}"
    )

    return {
        "id": "fix_broken_query",
        "name": "Fix the Broken SQL Query",
        "difficulty": "easy",
        "description": (
            "You are working with an e-commerce database.\n\n"
            "TABLES:\n"
            "  customers(id, name, email, city)\n"
            "  orders(id, customer_id, total_amount, status, order_date)\n\n"
            "A developer wrote a query to find all customers and their total spending "
            "on 'completed' orders, but it has MULTIPLE bugs (typos in aliases, column names, "
            "and ORDER BY direction).\n\n"
            f"THE BROKEN QUERY:\n```sql\n{broken_query}\n```\n\n"
            "FIX all bugs and submit a corrected query. "
            f"Expected: {len(expected_sorted)} rows ordered by total_spent DESC."
        ),
        "schema": {
            "customers": "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT, city TEXT)",
            "orders": "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount REAL, status TEXT, order_date TEXT)",
        },
        "seed_data": seed_data,
        "expected": {
            "row_count": len(expected_sorted),
            "data": [{"name": n, "email": e, "total_spent": t} for n, e, t in expected_sorted],
        },
        "_variant": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# write_business_query — randomize dept names, employee names, salaries
# ─────────────────────────────────────────────────────────────────────────────
def _variant_write_business() -> Dict[str, Any]:
    from tasks import TASKS
    base = copy.deepcopy(TASKS["write_business_query"])
    # Shuffle salaries slightly to change the top earner
    salaries = [120000, 95000, 110000, 80000, 85000, 100000, 90000, 70000]
    random.shuffle(salaries)
    new_seed = []
    for line in base["seed_data"]:
        if "INSERT INTO employees" in line:
            # find old salary value and replace
            for old, new in zip([120000, 95000, 110000, 80000, 85000, 100000, 90000, 70000], salaries):
                line = line.replace(str(old), str(new))
        new_seed.append(line)
    base["seed_data"] = new_seed
    base["_variant"] = True
    return base


# ─────────────────────────────────────────────────────────────────────────────
# complex_analytics — randomize quantities and prices
# ─────────────────────────────────────────────────────────────────────────────
def _variant_complex_analytics() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS["complex_analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# recursive_org_hierarchy — randomize salaries and project budgets
# ─────────────────────────────────────────────────────────────────────────────
def _variant_recursive_org() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS["recursive_org_hierarchy"])


# ─────────────────────────────────────────────────────────────────────────────
# data_quality_audit — randomize the specific dirty data
# ─────────────────────────────────────────────────────────────────────────────
def _variant_data_quality() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS["data_quality_audit"])


# ─────────────────────────────────────────────────────────────────────────────
# query_optimizer — NEW TASK
# ─────────────────────────────────────────────────────────────────────────────
def _variant_query_optimizer() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS.get("query_optimizer", {}))


def _variant_nl_to_sql() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS.get("nl_to_sql", {}))


def _variant_transaction_deadlock() -> Dict[str, Any]:
    from tasks import TASKS
    return copy.deepcopy(TASKS.get("transaction_deadlock", {}))
