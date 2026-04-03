"""
incident_task.py — "Production Database Incident Response" task definition.

This is the most novel task in the environment. The agent plays the role of
an on-call DBA who must:

  Stage 1: DIAGNOSE  — detect which tables / rows are corrupt
  Stage 2: TRIAGE    — quantify the damage (how many rows affected per issue)
  Stage 3: REPAIR    — write corrective UPDATE/DELETE SQL
  Stage 4: VERIFY    — confirm the fix with a validation query
  Stage 5: PREVENT   — write a single query that would catch this in future

Each stage unlocks after the previous one is completed correctly.
Partial credit is awarded at each stage.

This is genuinely hard for frontier models because:
  - They must reason about DB constraints AND data values simultaneously
  - Each stage's output becomes input for the next
  - Repair queries must be precise (wrong WHERE clause = more damage)
  - The verification stage requires the agent to PROVE their fix worked
"""

import random
from typing import Any, Dict, List, Optional, Tuple

# ── Schema (fixed — the randomisation is in the data corruption pattern) ──────

SCHEMA = {
    "products": (
        "CREATE TABLE products ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "category TEXT, unit_price REAL NOT NULL, stock INTEGER NOT NULL)"
    ),
    "customers": (
        "CREATE TABLE customers ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "email TEXT UNIQUE NOT NULL, tier TEXT DEFAULT 'standard', "
        "credit_limit REAL NOT NULL)"
    ),
    "orders": (
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, "
        "product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, "
        "unit_price REAL NOT NULL, order_date TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'pending')"
    ),
    "audit_log": (
        "CREATE TABLE audit_log ("
        "id INTEGER PRIMARY KEY, table_name TEXT, operation TEXT, "
        "record_id INTEGER, changed_at TEXT)"
    ),
}

# ── Clean seed data ───────────────────────────────────────────────────────────

CLEAN_DATA = [
    # products
    "INSERT INTO products VALUES (1,'Laptop','Electronics',999.99,50)",
    "INSERT INTO products VALUES (2,'Phone','Electronics',699.99,100)",
    "INSERT INTO products VALUES (3,'Desk','Furniture',299.99,30)",
    "INSERT INTO products VALUES (4,'Chair','Furniture',199.99,75)",
    "INSERT INTO products VALUES (5,'Notebook','Stationery',4.99,500)",
    "INSERT INTO products VALUES (6,'Pen Set','Stationery',12.99,200)",
    # customers
    "INSERT INTO customers VALUES (1,'Alice Smith','alice@example.com','premium',5000.00)",
    "INSERT INTO customers VALUES (2,'Bob Jones','bob@example.com','standard',1000.00)",
    "INSERT INTO customers VALUES (3,'Carol White','carol@example.com','premium',8000.00)",
    "INSERT INTO customers VALUES (4,'Dave Brown','dave@example.com','standard',1500.00)",
    "INSERT INTO customers VALUES (5,'Eve Davis','eve@example.com','gold',3000.00)",
    # valid orders
    "INSERT INTO orders VALUES (1,1,1,2,999.99,'2024-01-15','completed')",
    "INSERT INTO orders VALUES (2,2,2,1,699.99,'2024-02-20','completed')",
    "INSERT INTO orders VALUES (3,3,3,1,299.99,'2024-01-10','completed')",
    "INSERT INTO orders VALUES (4,4,5,10,4.99,'2024-03-01','completed')",
    "INSERT INTO orders VALUES (5,5,4,3,199.99,'2024-02-15','completed')",
]

# ── Corruption patterns ───────────────────────────────────────────────────────

CORRUPTIONS = {
    "negative_price": {
        "inject": [
            "INSERT INTO products VALUES (7,'Broken Widget','Electronics',-50.00,10)",
            "INSERT INTO products VALUES (8,'Ghost Item','Furniture',-1.00,0)",
        ],
        "description": "Two products have been inserted with negative unit prices.",
        "diagnosis_hint": "Check products table for unit_price < 0",
        "repair_sql": "DELETE FROM products WHERE unit_price < 0",
        "verify_sql": "SELECT COUNT(*) as bad_prices FROM products WHERE unit_price < 0",
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT id, name, unit_price FROM products WHERE unit_price <= 0 "
            "-- Add CHECK constraint: ALTER TABLE products ADD CHECK (unit_price > 0)"
        ),
        "damage_count": 2,
        "affected_table": "products",
    },
    "orphan_orders": {
        "inject": [
            "INSERT INTO orders VALUES (6,999,1,1,999.99,'2024-03-10','pending')",
            "INSERT INTO orders VALUES (7,888,2,2,699.99,'2024-03-11','pending')",
            "INSERT INTO orders VALUES (8,777,3,1,299.99,'2024-03-12','pending')",
        ],
        "description": "Three orders reference customer IDs that do not exist.",
        "diagnosis_hint": "Check orders for customer_id with no matching customers row",
        "repair_sql": (
            "DELETE FROM orders WHERE customer_id NOT IN "
            "(SELECT id FROM customers)"
        ),
        "verify_sql": (
            "SELECT COUNT(*) as orphans FROM orders o "
            "LEFT JOIN customers c ON o.customer_id = c.id WHERE c.id IS NULL"
        ),
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT o.id, o.customer_id FROM orders o "
            "LEFT JOIN customers c ON o.customer_id=c.id WHERE c.id IS NULL "
            "-- Add FK: FOREIGN KEY (customer_id) REFERENCES customers(id)"
        ),
        "damage_count": 3,
        "affected_table": "orders",
    },
    "duplicate_customers": {
        "inject": [
            "INSERT INTO customers VALUES (6,'Alice S.','alice@example.com','standard',500.00)",
            "INSERT INTO customers VALUES (7,'A. Smith','alice@example.com','standard',200.00)",
        ],
        "description": "Duplicate email addresses exist in the customers table.",
        "diagnosis_hint": "Check for duplicate emails in customers",
        "repair_sql": (
            "DELETE FROM customers WHERE id IN "
            "(SELECT id FROM customers WHERE email IN "
            "(SELECT email FROM customers GROUP BY email HAVING COUNT(*) > 1) "
            "AND id NOT IN (SELECT MIN(id) FROM customers GROUP BY email))"
        ),
        "verify_sql": (
            "SELECT COUNT(*) as dupes FROM "
            "(SELECT email FROM customers GROUP BY email HAVING COUNT(*) > 1)"
        ),
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT email, COUNT(*) as cnt FROM customers "
            "GROUP BY email HAVING COUNT(*) > 1 "
            "-- Add UNIQUE constraint on email column"
        ),
        "damage_count": 2,
        "affected_table": "customers",
    },
    "zero_quantity": {
        "inject": [
            "INSERT INTO orders VALUES (6,1,1,0,999.99,'2024-03-10','pending')",
            "INSERT INTO orders VALUES (7,2,2,-5,699.99,'2024-03-11','completed')",
        ],
        "description": "Orders exist with zero or negative quantities.",
        "diagnosis_hint": "Check orders for quantity <= 0",
        "repair_sql": "DELETE FROM orders WHERE quantity <= 0",
        "verify_sql": "SELECT COUNT(*) as bad_qty FROM orders WHERE quantity <= 0",
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT id, customer_id, quantity FROM orders WHERE quantity <= 0 "
            "-- Add CHECK constraint: quantity > 0"
        ),
        "damage_count": 2,
        "affected_table": "orders",
    },
    "future_orders": {
        "inject": [
            "INSERT INTO orders VALUES (6,1,1,1,999.99,'2099-01-01','pending')",
            "INSERT INTO orders VALUES (7,2,2,2,699.99,'2087-06-15','pending')",
            "INSERT INTO orders VALUES (8,3,3,1,299.99,'2150-12-31','completed')",
        ],
        "description": "Three orders have future-dated order_date values (after 2025-01-01).",
        "diagnosis_hint": "Check orders for order_date > '2025-01-01'",
        "repair_sql": "DELETE FROM orders WHERE order_date > '2025-01-01'",
        "verify_sql": (
            "SELECT COUNT(*) as future_orders FROM orders "
            "WHERE order_date > '2025-01-01'"
        ),
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT id, order_date FROM orders WHERE order_date > date('now') "
            "-- Add CHECK: order_date <= date('now')"
        ),
        "damage_count": 3,
        "affected_table": "orders",
    },
    "negative_stock": {
        "inject": [
            "INSERT INTO products VALUES (7,'Oversold Laptop','Electronics',999.99,-10)",
            "INSERT INTO products VALUES (8,'Ghost Phone','Electronics',699.99,-5)",
        ],
        "description": "Two products have negative stock values (oversold).",
        "diagnosis_hint": "Check products for stock < 0",
        "repair_sql": "UPDATE products SET stock = 0 WHERE stock < 0",
        "verify_sql": "SELECT COUNT(*) as bad_stock FROM products WHERE stock < 0",
        "verify_expected": 0,
        "prevent_sql": (
            "SELECT id, name, stock FROM products WHERE stock < 0 "
            "-- Add CHECK constraint: stock >= 0"
        ),
        "damage_count": 2,
        "affected_table": "products",
    },
}

# ── Incident scenarios (3 corruptions each) ───────────────────────────────────

INCIDENTS = [
    {
        "id": "incident_alpha",
        "name": "Black Friday Data Corruption",
        "narrative": (
            "🚨 PRODUCTION INCIDENT — SEVERITY: HIGH\n"
            "Time: 02:47 AM. Automated alerts firing.\n"
            "A batch import job ran with a bug during Black Friday load.\n"
            "Three separate data corruption issues have been detected.\n\n"
            "YOUR MISSION (5 stages):\n"
            "  Stage 1 DIAGNOSE  — run queries to find which rows are corrupt\n"
            "  Stage 2 TRIAGE    — submit: SELECT 'table', COUNT(*) for each issue\n"
            "  Stage 3 REPAIR    — submit UPDATE/DELETE queries to fix the data\n"
            "  Stage 4 VERIFY    — prove the fix worked (each issue should return 0)\n"
            "  Stage 5 PREVENT   — write detection queries for a monitoring dashboard\n\n"
            "Corruptions injected: negative_price, orphan_orders, zero_quantity\n\n"
            "Use run_query to explore, then submit_solution with ALL fixes combined "
            "using semicolons or a triage report query."
        ),
        "corruptions": ["negative_price", "orphan_orders", "zero_quantity"],
    },
    {
        "id": "incident_beta",
        "name": "ETL Pipeline Gone Wrong",
        "narrative": (
            "🚨 PRODUCTION INCIDENT — SEVERITY: CRITICAL\n"
            "An ETL pipeline synced bad data from a legacy system.\n"
            "Customer deduplication failed and order validation was skipped.\n\n"
            "YOUR MISSION: Diagnose, triage, repair, verify, and prevent "
            "three data quality issues.\n\n"
            "Corruptions injected: duplicate_customers, future_orders, negative_stock\n\n"
            "Work through the data systematically. Use examine_schema and run_query "
            "to investigate, then submit_solution with your repair queries."
        ),
        "corruptions": ["duplicate_customers", "future_orders", "negative_stock"],
    },
]


def get_incident_task(incident_id: str = "incident_alpha") -> Dict[str, Any]:
    """Return the full task definition for an incident scenario."""
    scenario = next((i for i in INCIDENTS if i["id"] == incident_id), INCIDENTS[0])
    corruptions = [CORRUPTIONS[c] for c in scenario["corruptions"]]

    seed_data = list(CLEAN_DATA)
    for c in corruptions:
        seed_data.extend(c["inject"])

    description = (
        f"INCIDENT: {scenario['name']}\n\n"
        f"{scenario['narrative']}\n\n"
        "TABLES: products, customers, orders, audit_log\n\n"
        "KNOWN CORRUPTION TYPES IN THIS INCIDENT:\n"
    )
    for i, c in enumerate(corruptions, 1):
        description += f"  Issue {i}: {c['description']}\n"

    return {
        "id": f"incident_response_{incident_id}",
        "name": f"Incident Response: {scenario['name']}",
        "difficulty": "expert",
        "description": description,
        "schema": SCHEMA,
        "seed_data": seed_data,
        "corruptions": corruptions,
        "scenario": scenario,
        "expected": {
            "total_corrupt_rows": sum(c["damage_count"] for c in corruptions),
            "issues": [
                {
                    "table": c["affected_table"],
                    "count": c["damage_count"],
                    "verify_sql": c["verify_sql"],
                    "verify_expected": c["verify_expected"],
                }
                for c in corruptions
            ],
        },
    }
