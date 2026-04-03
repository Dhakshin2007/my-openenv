"""
Task definitions for the SQL Debug Environment.
Each task has a schema, seed data, description, and grading criteria.
"""

TASKS = {
    "recursive_org_hierarchy": {
        "id": "recursive_org_hierarchy",
        "name": "Recursive Org-Chart Query",
        "difficulty": "hard",
        "description": (
            "You have a company org-chart database.\n\n"
            "TABLES:\n"
            "  employees(id, name, title, manager_id, department, salary, hire_date)\n"
            "    — manager_id is NULL for the CEO; all others point to their direct manager.\n"
            "  projects(id, name, lead_id, budget, status)\n"
            "    — lead_id references employees.id\n\n"
            "TASK: Write a SINGLE SQL query (using a recursive CTE) that:\n"
            "  1. Starts from employee id=1 (the CTO — NOT the CEO)\n"
            "  2. Traverses the full reporting chain downward (direct + indirect reports)\n"
            "  3. Returns for EACH person in the CTO's org:\n"
            "       - employee name\n"
            "       - title\n"
            "       - depth  (CTO = 0, direct reports = 1, their reports = 2, …)\n"
            "       - manager_name (name of their direct manager)\n"
            "       - num_active_projects (count of 'active' projects they lead; 0 if none)\n"
            "  4. ORDER BY depth ASC, name ASC\n\n"
            "CONSTRAINTS:\n"
            "  - Must use a recursive CTE (WITH RECURSIVE)\n"
            "  - Must include the CTO themselves (depth=0)\n"
            "  - Must handle employees with NO active projects (show 0, not NULL)\n"
            "  - The CEO (id=2) must NOT appear in results\n\n"
            "HINT: SQLite supports WITH RECURSIVE. "
            "Use LEFT JOIN to projects to handle employees with no projects.\n\n"
            "Expected: 7 rows (CTO + 6 people in their org), ordered by depth then name."
        ),
        "schema": {
            "employees": (
                "CREATE TABLE employees ("
                "id INTEGER PRIMARY KEY, name TEXT, title TEXT, "
                "manager_id INTEGER, department TEXT, salary REAL, hire_date TEXT)"
            ),
            "projects": (
                "CREATE TABLE projects ("
                "id INTEGER PRIMARY KEY, name TEXT, lead_id INTEGER, "
                "budget REAL, status TEXT)"
            ),
        },
        "seed_data": [
            # CEO (id=2, manager=NULL) — must NOT appear in results
            "INSERT INTO employees VALUES (2, 'Sarah CEO',   'CEO',              NULL, 'Executive',   500000, '2015-01-01')",
            # CTO (id=1, reports to CEO) — depth=0, anchor of recursion
            "INSERT INTO employees VALUES (1, 'Alice CTO',   'CTO',              2,    'Engineering', 350000, '2016-03-15')",
            # Depth 1: direct reports of CTO
            "INSERT INTO employees VALUES (3, 'Bob VP Eng',  'VP Engineering',   1,    'Engineering', 220000, '2017-06-01')",
            "INSERT INTO employees VALUES (4, 'Carol VP ML', 'VP ML',            1,    'ML',          210000, '2018-02-20')",
            # Depth 2: reports of Bob VP
            "INSERT INTO employees VALUES (5, 'Dave SWE',    'Senior Engineer',  3,    'Engineering', 150000, '2019-04-10')",
            "INSERT INTO employees VALUES (6, 'Eve SWE',     'Senior Engineer',  3,    'Engineering', 145000, '2020-01-15')",
            # Depth 2: reports of Carol VP
            "INSERT INTO employees VALUES (7, 'Frank ML',    'ML Engineer',      4,    'ML',          160000, '2019-08-20')",
            "INSERT INTO employees VALUES (8, 'Grace ML',    'ML Engineer',      4,    'ML',          155000, '2021-03-01')",
            # CFO — NOT in CTO org, must not appear
            "INSERT INTO employees VALUES (9, 'Henry CFO',   'CFO',              2,    'Finance',     300000, '2016-07-01')",
            # Projects
            "INSERT INTO projects VALUES (1, 'Platform Rewrite',  1, 500000, 'active')",   # Alice leads
            "INSERT INTO projects VALUES (2, 'ML Pipeline',       4, 300000, 'active')",   # Carol leads
            "INSERT INTO projects VALUES (3, 'API Gateway',       3, 200000, 'active')",   # Bob leads
            "INSERT INTO projects VALUES (4, 'Data Lake',         4, 400000, 'active')",   # Carol leads (2 active)
            "INSERT INTO projects VALUES (5, 'Legacy Migration',  3, 150000, 'completed')", # Bob — not active
            "INSERT INTO projects VALUES (6, 'GPU Cluster',       7, 250000, 'active')",   # Frank leads
            "INSERT INTO projects VALUES (7, 'Old Infra',         5, 100000, 'archived')", # Dave — not active
        ],
        "expected": {
            "row_count": 7,
            "cto_depth": 0,
            "max_depth": 2,
            "carol_projects": 2,  # Carol leads 2 active projects
            "dave_projects": 0,   # Dave leads 0 active projects
            "no_ceo": True,       # id=2 must not appear
            "no_henry": True,     # id=9 must not appear
        },
    },

    "data_quality_audit": {
        "id": "data_quality_audit",
        "name": "Data Quality Audit Pipeline",
        "difficulty": "hard",
        "description": (
            "You are a data engineer auditing a messy customer database.\n\n"
            "TABLES:\n"
            "  customers(id, name, email, phone, signup_date, country)\n"
            "  transactions(id, customer_id, amount, currency, txn_date, status)\n\n"
            "The database has KNOWN DATA QUALITY ISSUES you must surface.\n\n"
            "TASK: Write a SINGLE SQL query that returns a data quality report "
            "with exactly these rows (one issue per row):\n\n"
            "  issue_type        | issue_count | example_ids\n"
            "  ─────────────────────────────────────────────\n"
            "  duplicate_email   | 2           | (ids of dupes, comma-separated)\n"
            "  null_name         | 1           | (id of the NULL-name customer)\n"
            "  invalid_amount    | 3           | (txn ids where amount <= 0)\n"
            "  orphan_txn        | 2           | (txn ids with no matching customer)\n"
            "  future_txn        | 1           | (txn id dated after 2024-12-31)\n\n"
            "REQUIREMENTS:\n"
            "  - Exactly 5 rows, one per issue_type (listed above)\n"
            "  - Columns: issue_type (TEXT), issue_count (INTEGER), example_ids (TEXT)\n"
            "  - example_ids: comma-separated string of IDs (can be in any order)\n"
            "  - Use UNION ALL to combine the 5 checks into one result\n"
            "  - issue_count must be correct for each issue\n\n"
            "HINT: Use GROUP_CONCAT for example_ids, subqueries for each check, "
            "UNION ALL to combine. LEFT JOIN for orphan detection."
        ),
        "schema": {
            "customers": (
                "CREATE TABLE customers ("
                "id INTEGER PRIMARY KEY, name TEXT, email TEXT, "
                "phone TEXT, signup_date TEXT, country TEXT)"
            ),
            "transactions": (
                "CREATE TABLE transactions ("
                "id INTEGER PRIMARY KEY, customer_id INTEGER, "
                "amount REAL, currency TEXT, txn_date TEXT, status TEXT)"
            ),
        },
        "seed_data": [
            # Good customers
            "INSERT INTO customers VALUES (1, 'Alice Smith',  'alice@example.com', '555-0001', '2022-01-15', 'USA')",
            "INSERT INTO customers VALUES (2, 'Bob Jones',    'bob@example.com',   '555-0002', '2022-02-20', 'UK')",
            "INSERT INTO customers VALUES (3, 'Carol White',  'carol@example.com', '555-0003', '2022-03-10', 'CA')",
            # Duplicate email (customers 4 & 5 share email with customer 1)
            "INSERT INTO customers VALUES (4, 'Alice S.',     'alice@example.com', '555-0004', '2023-01-01', 'USA')",
            "INSERT INTO customers VALUES (5, 'A. Smith',     'alice@example.com', '555-0005', '2023-06-01', 'USA')",
            # NULL name
            "INSERT INTO customers VALUES (6, NULL,           'unknown@example.com','555-0006','2023-07-01', 'USA')",
            # Good customer
            "INSERT INTO customers VALUES (7, 'Dave Brown',   'dave@example.com',  '555-0007', '2022-04-15', 'AUS')",
            # Good transactions
            "INSERT INTO transactions VALUES (1,  1, 100.00, 'USD', '2023-01-15', 'completed')",
            "INSERT INTO transactions VALUES (2,  2, 250.50, 'GBP', '2023-02-20', 'completed')",
            "INSERT INTO transactions VALUES (3,  3,  75.00, 'CAD', '2023-03-10', 'completed')",
            # Invalid amounts (amount <= 0)
            "INSERT INTO transactions VALUES (4,  1,   0.00, 'USD', '2023-04-01', 'pending')",
            "INSERT INTO transactions VALUES (5,  2,  -50.00,'GBP', '2023-04-02', 'failed')",
            "INSERT INTO transactions VALUES (6,  3,  -1.00, 'CAD', '2023-04-03', 'failed')",
            # Orphan transactions (customer_id 99 and 100 don't exist)
            "INSERT INTO transactions VALUES (7,  99, 500.00,'USD', '2023-05-01', 'completed')",
            "INSERT INTO transactions VALUES (8,  100,300.00,'EUR', '2023-06-01', 'completed')",
            # Future transaction
            "INSERT INTO transactions VALUES (9,  7, 150.00, 'USD', '2025-03-15', 'pending')",
        ],
        "expected": {
            "row_count": 5,
            "issue_types": {"duplicate_email", "null_name", "invalid_amount",
                            "orphan_txn", "future_txn"},
            "duplicate_email_count": 2,  # ids 4 and 5 are duplicates (match id 1's email)
            "null_name_count": 1,
            "invalid_amount_count": 3,
            "orphan_txn_count": 2,
            "future_txn_count": 1,
        },
    },

    "fix_broken_query": {
        "id": "fix_broken_query",
        "name": "Fix the Broken SQL Query",
        "difficulty": "easy",
        "description": (
            "You are working with an e-commerce database.\n\n"
            "TABLES:\n"
            "  customers(id, name, email, city)\n"
            "  orders(id, customer_id, total_amount, status, order_date)\n\n"
            "A developer wrote a query to find all customers and their total spending on "
            "'completed' orders, but it has MULTIPLE bugs (typos, wrong column names, bad syntax).\n\n"
            "THE BROKEN QUERY:\n"
            "```sql\n"
            "SELECT custmer.name, custmer.email, SUM(ord.total_amount) as total_spent\n"
            "FROM customers custmer\n"
            "INNER JOIN orders ord ON custmer.id = ord.custmer_id\n"
            "WHERE ord.statue = 'completed'\n"
            "GROUP BY custmer.id\n"
            "ORDER BY total_spent DESK\n"
            "```\n\n"
            "FIX all bugs and submit a corrected query. "
            "Expected output: 3 rows with columns (name, email, total_spent), ordered by total_spent DESC."
        ),
        "schema": {
            "customers": (
                "CREATE TABLE customers "
                "(id INTEGER PRIMARY KEY, name TEXT, email TEXT, city TEXT)"
            ),
            "orders": (
                "CREATE TABLE orders "
                "(id INTEGER PRIMARY KEY, customer_id INTEGER, "
                "total_amount REAL, status TEXT, order_date TEXT)"
            ),
        },
        "seed_data": [
            "INSERT INTO customers VALUES (1, 'Alice Smith',  'alice@example.com', 'NYC')",
            "INSERT INTO customers VALUES (2, 'Bob Jones',    'bob@example.com',   'LA')",
            "INSERT INTO customers VALUES (3, 'Carol White',  'carol@example.com', 'Chicago')",
            "INSERT INTO orders VALUES (1, 1, 150.00, 'completed', '2023-01-15')",
            "INSERT INTO orders VALUES (2, 1,  75.50, 'completed', '2023-02-20')",
            "INSERT INTO orders VALUES (3, 2, 200.00, 'completed', '2023-01-10')",
            "INSERT INTO orders VALUES (4, 2,  50.00, 'pending',   '2023-03-01')",
            "INSERT INTO orders VALUES (5, 3, 300.00, 'completed', '2023-02-15')",
        ],
        "expected": {
            "row_count": 3,
            "data": [
                {"name": "Carol White",  "email": "carol@example.com", "total_spent": 300.00},
                {"name": "Alice Smith",  "email": "alice@example.com", "total_spent": 225.50},
                {"name": "Bob Jones",    "email": "bob@example.com",   "total_spent": 200.00},
            ],
        },
    },

    "write_business_query": {
        "id": "write_business_query",
        "name": "Write a Business Analytics Query",
        "difficulty": "medium",
        "description": (
            "You have an HR database.\n\n"
            "TABLES:\n"
            "  employees(id, name, department_id, salary, hire_date)\n"
            "  departments(id, name, budget, location)\n\n"
            "TASK: Write a single SQL query that returns, for each department:\n"
            "  - department name\n"
            "  - number of employees\n"
            "  - average salary (round to 2 decimal places)\n"
            "  - name of the highest-paid employee\n\n"
            "CONSTRAINTS:\n"
            "  - Only include departments with MORE THAN 1 employee\n"
            "  - Order results by average salary DESCENDING\n\n"
            "Expected output: 3 rows (Engineering, Finance, Marketing — HR has only 1 employee)."
        ),
        "schema": {
            "employees": (
                "CREATE TABLE employees "
                "(id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER, "
                "salary REAL, hire_date TEXT)"
            ),
            "departments": (
                "CREATE TABLE departments "
                "(id INTEGER PRIMARY KEY, name TEXT, budget REAL, location TEXT)"
            ),
        },
        "seed_data": [
            "INSERT INTO departments VALUES (1, 'Engineering', 1000000, 'NYC')",
            "INSERT INTO departments VALUES (2, 'Marketing',    500000, 'LA')",
            "INSERT INTO departments VALUES (3, 'Finance',      750000, 'Chicago')",
            "INSERT INTO departments VALUES (4, 'HR',           300000, 'NYC')",
            "INSERT INTO employees VALUES (1, 'Alice',   1, 120000, '2020-01-15')",
            "INSERT INTO employees VALUES (2, 'Bob',     1,  95000, '2021-03-20')",
            "INSERT INTO employees VALUES (3, 'Carol',   1, 110000, '2019-06-10')",
            "INSERT INTO employees VALUES (4, 'Dave',    2,  80000, '2022-01-05')",
            "INSERT INTO employees VALUES (5, 'Eve',     2,  85000, '2020-11-15')",
            "INSERT INTO employees VALUES (6, 'Frank',   3, 100000, '2018-07-20')",
            "INSERT INTO employees VALUES (7, 'Grace',   3,  90000, '2021-09-01')",
            "INSERT INTO employees VALUES (8, 'Hank',    4,  70000, '2023-01-10')",
        ],
        "expected": {
            "row_count": 3,
            "dept_names": ["Engineering", "Finance", "Marketing"],
            "engineering_top_earner": "Alice",
            "engineering_emp_count": 3,
            "ordered_by_avg_desc": True,
        },
    },

    "complex_analytics": {
        "id": "complex_analytics",
        "name": "Complex Multi-table Analytics",
        "difficulty": "hard",
        "description": (
            "You have a sales analytics database.\n\n"
            "TABLES:\n"
            "  products(id, name, category, unit_price)\n"
            "  sales(id, product_id, quantity, sale_date, region_id)\n"
            "  regions(id, name, country)\n\n"
            "TASK: Write a SQL query that:\n"
            "  1. Computes total revenue (quantity * unit_price) per category per country\n"
            "  2. Only includes sales from 2023 (sale_date LIKE '2023-%')\n"
            "  3. Returns the TOP 2 categories by total_revenue FOR EACH country\n"
            "  4. Columns: country, category, total_revenue, total_units_sold, num_transactions\n"
            "  5. Ordered by country ASC, total_revenue DESC\n\n"
            "HINT: You will need window functions (RANK/ROW_NUMBER) or a correlated subquery "
            "to get the top 2 per country. SQLite supports window functions.\n\n"
            "Expected: 4 rows (top 2 for USA, top 2 for Canada)."
        ),
        "schema": {
            "products": (
                "CREATE TABLE products "
                "(id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL)"
            ),
            "sales": (
                "CREATE TABLE sales "
                "(id INTEGER PRIMARY KEY, product_id INTEGER, "
                "quantity INTEGER, sale_date TEXT, region_id INTEGER)"
            ),
            "regions": (
                "CREATE TABLE regions "
                "(id INTEGER PRIMARY KEY, name TEXT, country TEXT)"
            ),
        },
        "seed_data": [
            # regions
            "INSERT INTO regions VALUES (1, 'Northeast', 'USA')",
            "INSERT INTO regions VALUES (2, 'West',      'USA')",
            "INSERT INTO regions VALUES (3, 'Ontario',   'Canada')",
            "INSERT INTO regions VALUES (4, 'Quebec',    'Canada')",
            # products
            "INSERT INTO products VALUES (1, 'Laptop',  'Electronics', 999.99)",
            "INSERT INTO products VALUES (2, 'Phone',   'Electronics', 699.99)",
            "INSERT INTO products VALUES (3, 'Desk',    'Furniture',   299.99)",
            "INSERT INTO products VALUES (4, 'Chair',   'Furniture',   199.99)",
            "INSERT INTO products VALUES (5, 'Book',    'Education',    29.99)",
            "INSERT INTO products VALUES (6, 'Course',  'Education',   199.99)",
            # sales 2023
            "INSERT INTO sales VALUES  (1, 1, 10, '2023-01-15', 1)",  # Laptop x10 USA
            "INSERT INTO sales VALUES  (2, 2, 20, '2023-02-20', 1)",  # Phone  x20 USA
            "INSERT INTO sales VALUES  (3, 3,  5, '2023-01-10', 2)",  # Desk   x5  USA
            "INSERT INTO sales VALUES  (4, 4, 15, '2023-03-01', 2)",  # Chair  x15 USA
            "INSERT INTO sales VALUES  (5, 1,  8, '2023-01-15', 3)",  # Laptop x8  Canada
            "INSERT INTO sales VALUES  (6, 5, 50, '2023-02-20', 3)",  # Book   x50 Canada
            "INSERT INTO sales VALUES  (7, 6, 30, '2023-03-10', 4)",  # Course x30 Canada
            "INSERT INTO sales VALUES  (8, 3, 10, '2023-04-15', 4)",  # Desk   x10 Canada
            "INSERT INTO sales VALUES  (9, 2, 15, '2023-05-20', 1)",  # Phone  x15 USA
            "INSERT INTO sales VALUES (10, 4, 20, '2023-06-10', 2)",  # Chair  x20 USA
            # sales 2022 — must be excluded
            "INSERT INTO sales VALUES (11, 1, 100, '2022-12-15', 1)",
            "INSERT INTO sales VALUES (12, 2, 200, '2022-11-20', 2)",
        ],
        "expected": {
            "row_count": 4,  # top 2 per country, 2 countries
            "countries": ["Canada", "USA"],
            "no_2022_data": True,
            "top_2_per_country": True,
        },
    },

    # ── NEW: Query Optimizer ──────────────────────────────────────────────────
    "query_optimizer": {
        "id": "query_optimizer",
        "name": "SQL Query Optimizer",
        "difficulty": "expert",
        "description": (
            "You are a database performance engineer. A critical production query is "
            "running in 8+ seconds on a 100k-row table. Your job: rewrite it to run fast.\n\n"
            "TABLES:\n"
            "  users(id, name, email, country, signup_date, status)\n"
            "  orders(id, user_id, product_id, amount, order_date, status)\n"
            "  products(id, name, category, price, inventory_count)\n\n"
            "INDEXES AVAILABLE (created for you):\n"
            "  idx_orders_user_id     ON orders(user_id)\n"
            "  idx_orders_date        ON orders(order_date)\n"
            "  idx_orders_status      ON orders(status)\n"
            "  idx_users_country      ON users(country)\n"
            "  idx_products_category  ON products(category)\n\n"
            "THE SLOW QUERY (avoid this pattern — it does a full table scan + correlated subquery):\n"
            "```sql\n"
            "SELECT u.name, u.email, u.country,\n"
            "       (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id AND o.status = 'completed') AS order_count,\n"
            "       (SELECT SUM(o.amount) FROM orders o WHERE o.user_id = u.id AND o.status = 'completed') AS total_spent,\n"
            "       (SELECT MAX(o.order_date) FROM orders o WHERE o.user_id = u.id) AS last_order_date\n"
            "FROM users u\n"
            "WHERE u.status = 'active'\n"
            "  AND u.country IN ('USA', 'Canada')\n"
            "  AND (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id AND o.status = 'completed') > 2\n"
            "ORDER BY total_spent DESC\n"
            "LIMIT 10\n"
            "```\n\n"
            "REWRITE REQUIREMENTS:\n"
            "  1. Replace correlated subqueries with a single JOIN + GROUP BY\n"
            "  2. Use HAVING instead of a WHERE with a subquery for the count filter\n"
            "  3. Must return identical results: name, email, country, order_count, total_spent, last_order_date\n"
            "  4. Must still filter: status='active', country IN ('USA','Canada'), order_count > 2\n"
            "  5. Same ORDER BY total_spent DESC LIMIT 10\n\n"
            "SCORING: Correctness of results (60%) + elimination of correlated subqueries (40%)"
        ),
        "schema": {
            "users": (
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, name TEXT, email TEXT, "
                "country TEXT, signup_date TEXT, status TEXT)"
            ),
            "orders": (
                "CREATE TABLE orders ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, "
                "amount REAL, order_date TEXT, status TEXT)"
            ),
            "products": (
                "CREATE TABLE products ("
                "id INTEGER PRIMARY KEY, name TEXT, category TEXT, "
                "price REAL, inventory_count INTEGER)"
            ),
        },
        "seed_data": [
            # Users
            "INSERT INTO users VALUES (1,  'Alice Smith',   'alice@x.com',   'USA',    '2021-01-10', 'active')",
            "INSERT INTO users VALUES (2,  'Bob Jones',     'bob@x.com',     'Canada', '2021-02-15', 'active')",
            "INSERT INTO users VALUES (3,  'Carol White',   'carol@x.com',   'USA',    '2021-03-20', 'active')",
            "INSERT INTO users VALUES (4,  'Dave Brown',    'dave@x.com',    'UK',     '2021-04-25', 'active')",    # excluded: UK
            "INSERT INTO users VALUES (5,  'Eve Davis',     'eve@x.com',     'USA',    '2021-05-30', 'inactive')",  # excluded: inactive
            "INSERT INTO users VALUES (6,  'Frank Wilson',  'frank@x.com',   'Canada', '2021-06-05', 'active')",
            "INSERT INTO users VALUES (7,  'Grace Moore',   'grace@x.com',   'USA',    '2021-07-10', 'active')",
            # Products
            "INSERT INTO products VALUES (1, 'Laptop',  'Electronics', 999.99, 50)",
            "INSERT INTO products VALUES (2, 'Phone',   'Electronics', 699.99, 100)",
            "INSERT INTO products VALUES (3, 'Desk',    'Furniture',   299.99, 30)",
            # Orders — Alice: 3 completed (qualifies)
            "INSERT INTO orders VALUES  (1, 1, 1, 999.99, '2023-01-10', 'completed')",
            "INSERT INTO orders VALUES  (2, 1, 2, 699.99, '2023-02-15', 'completed')",
            "INSERT INTO orders VALUES  (3, 1, 3, 299.99, '2023-03-20', 'completed')",
            # Bob: 4 completed (qualifies)
            "INSERT INTO orders VALUES  (4, 2, 1, 999.99, '2023-01-05', 'completed')",
            "INSERT INTO orders VALUES  (5, 2, 2, 699.99, '2023-02-10', 'completed')",
            "INSERT INTO orders VALUES  (6, 2, 3, 299.99, '2023-03-15', 'completed')",
            "INSERT INTO orders VALUES  (7, 2, 1, 999.99, '2023-04-20', 'completed')",
            # Carol: 2 completed (does NOT qualify — needs >2)
            "INSERT INTO orders VALUES  (8, 3, 1, 999.99, '2023-01-20', 'completed')",
            "INSERT INTO orders VALUES  (9, 3, 2, 699.99, '2023-02-25', 'completed')",
            # Frank: 3 completed (qualifies)
            "INSERT INTO orders VALUES (10, 6, 1, 999.99, '2023-02-01', 'completed')",
            "INSERT INTO orders VALUES (11, 6, 2, 699.99, '2023-03-05', 'completed')",
            "INSERT INTO orders VALUES (12, 6, 3, 299.99, '2023-04-10', 'completed')",
            # Grace: 1 completed + 2 pending (does NOT qualify)
            "INSERT INTO orders VALUES (13, 7, 1, 999.99, '2023-01-15', 'completed')",
            "INSERT INTO orders VALUES (14, 7, 2, 699.99, '2023-02-20', 'pending')",
            "INSERT INTO orders VALUES (15, 7, 3, 299.99, '2023-03-25', 'pending')",
            # Dave (UK): 5 completed but excluded by country filter
            "INSERT INTO orders VALUES (16, 4, 1, 999.99, '2023-01-01', 'completed')",
            "INSERT INTO orders VALUES (17, 4, 2, 699.99, '2023-02-01', 'completed')",
            "INSERT INTO orders VALUES (18, 4, 3, 299.99, '2023-03-01', 'completed')",
            "INSERT INTO orders VALUES (19, 4, 1, 999.99, '2023-04-01', 'completed')",
            "INSERT INTO orders VALUES (20, 4, 2, 699.99, '2023-05-01', 'completed')",
        ],
        "expected": {
            "row_count": 3,       # Alice, Bob, Frank
            "top_user": "Bob Jones",   # highest total_spent
            "no_correlated_subquery": True,
            "has_join_group_by": True,
        },
    },

    # ── NEW: NL → SQL Report Builder ─────────────────────────────────────────
    "nl_to_sql": {
        "id": "nl_to_sql",
        "name": "Natural Language → SQL Report Builder",
        "difficulty": "expert",
        "description": (
            "You are a data analyst. A business stakeholder has sent you the following "
            "request in plain English. Translate it into a single SQL query.\n\n"
            "TABLES:\n"
            "  employees(id, name, department, salary, hire_date, manager_id, is_remote)\n"
            "  performance_reviews(id, employee_id, review_year, score, reviewer_id)\n"
            "  projects(id, name, department, start_date, end_date, budget_usd)\n"
            "  project_assignments(employee_id, project_id, role, hours_billed)\n\n"
            "BUSINESS REQUEST:\n"
            "\"I need a report for our Q4 board meeting. Show me each department's "
            "talent health. For each department I want to know:\n"
            "  1. Department name\n"
            "  2. Total headcount\n"
            "  3. Number of remote employees\n"
            "  4. Average performance score in 2023 (round to 1 decimal place)\n"
            "  5. Number of employees who scored ABOVE the company-wide average in 2023\n"
            "  6. Total hours billed across all projects\n"
            "  7. Budget utilization: total salary cost vs total project budget "
            "(salary_cost = sum of all employee salaries in dept; "
            "project_budget = sum of all project budgets for that dept)\n\n"
            "Only show departments with at least 3 employees. "
            "Sort by average performance score descending. "
            "If a department has no performance reviews, show NULL for score columns.\"\n\n"
            "COLUMNS EXPECTED: department, headcount, remote_count, avg_score_2023, "
            "above_avg_count, total_hours_billed, total_salary_cost, total_project_budget\n\n"
            "HINT: You will need multiple JOINs, a subquery for the company-wide average, "
            "COALESCE for NULLs, and careful GROUP BY. This is a hard multi-table aggregation."
        ),
        "schema": {
            "employees": (
                "CREATE TABLE employees ("
                "id INTEGER PRIMARY KEY, name TEXT, department TEXT, "
                "salary REAL, hire_date TEXT, manager_id INTEGER, is_remote INTEGER)"
            ),
            "performance_reviews": (
                "CREATE TABLE performance_reviews ("
                "id INTEGER PRIMARY KEY, employee_id INTEGER, review_year INTEGER, "
                "score REAL, reviewer_id INTEGER)"
            ),
            "projects": (
                "CREATE TABLE projects ("
                "id INTEGER PRIMARY KEY, name TEXT, department TEXT, "
                "start_date TEXT, end_date TEXT, budget_usd REAL)"
            ),
            "project_assignments": (
                "CREATE TABLE project_assignments ("
                "employee_id INTEGER, project_id INTEGER, role TEXT, hours_billed REAL)"
            ),
        },
        "seed_data": [
            # Employees
            "INSERT INTO employees VALUES (1,  'Alice',   'Engineering', 120000, '2019-01-10', NULL, 0)",
            "INSERT INTO employees VALUES (2,  'Bob',     'Engineering',  95000, '2020-03-15', 1,    1)",
            "INSERT INTO employees VALUES (3,  'Carol',   'Engineering', 110000, '2018-06-20', 1,    1)",
            "INSERT INTO employees VALUES (4,  'Dave',    'Engineering', 105000, '2021-01-05', 1,    0)",
            "INSERT INTO employees VALUES (5,  'Eve',     'Marketing',    80000, '2020-04-10', NULL, 1)",
            "INSERT INTO employees VALUES (6,  'Frank',   'Marketing',    75000, '2021-07-15', 5,    0)",
            "INSERT INTO employees VALUES (7,  'Grace',   'Marketing',    78000, '2019-11-20', 5,    1)",
            "INSERT INTO employees VALUES (8,  'Hank',    'Finance',     100000, '2018-02-28', NULL, 0)",
            "INSERT INTO employees VALUES (9,  'Iris',    'Finance',      92000, '2019-09-10', 8,    0)",
            "INSERT INTO employees VALUES (10, 'Jake',    'Finance',      88000, '2020-05-15', 8,    1)",
            "INSERT INTO employees VALUES (11, 'Kara',    'HR',           70000, '2021-03-01', NULL, 0)",
            "INSERT INTO employees VALUES (12, 'Leo',     'HR',           68000, '2022-01-15', 11,   1)",
            # HR only has 2 employees → should be excluded (need ≥3)
            # Performance reviews (2023)
            "INSERT INTO performance_reviews VALUES (1,  1,  2023, 4.5, NULL)",
            "INSERT INTO performance_reviews VALUES (2,  2,  2023, 3.8, 1)",
            "INSERT INTO performance_reviews VALUES (3,  3,  2023, 4.2, 1)",
            "INSERT INTO performance_reviews VALUES (4,  4,  2023, 3.5, 1)",
            "INSERT INTO performance_reviews VALUES (5,  5,  2023, 4.0, NULL)",
            "INSERT INTO performance_reviews VALUES (6,  6,  2023, 3.2, 5)",
            "INSERT INTO performance_reviews VALUES (7,  7,  2023, 3.9, 5)",
            "INSERT INTO performance_reviews VALUES (8,  8,  2023, 4.8, NULL)",
            "INSERT INTO performance_reviews VALUES (9,  9,  2023, 4.1, 8)",
            "INSERT INTO performance_reviews VALUES (10, 10, 2023, 3.7, 8)",
            # Projects
            "INSERT INTO projects VALUES (1, 'Platform v2',     'Engineering', '2023-01-01', '2023-12-31', 800000)",
            "INSERT INTO projects VALUES (2, 'Mobile App',      'Engineering', '2023-06-01', '2024-06-01', 400000)",
            "INSERT INTO projects VALUES (3, 'Brand Refresh',   'Marketing',   '2023-02-01', '2023-08-31', 200000)",
            "INSERT INTO projects VALUES (4, 'Q4 Campaign',     'Marketing',   '2023-09-01', '2023-12-31', 150000)",
            "INSERT INTO projects VALUES (5, 'Audit 2023',      'Finance',     '2023-01-01', '2023-06-30', 100000)",
            "INSERT INTO projects VALUES (6, 'Tax Compliance',  'Finance',     '2023-07-01', '2023-12-31', 120000)",
            # Assignments
            "INSERT INTO project_assignments VALUES (1,  1, 'Lead',        800)",
            "INSERT INTO project_assignments VALUES (2,  1, 'Developer',   600)",
            "INSERT INTO project_assignments VALUES (3,  1, 'Developer',   550)",
            "INSERT INTO project_assignments VALUES (4,  2, 'Developer',   400)",
            "INSERT INTO project_assignments VALUES (5,  3, 'Lead',        300)",
            "INSERT INTO project_assignments VALUES (6,  3, 'Coordinator', 250)",
            "INSERT INTO project_assignments VALUES (7,  4, 'Lead',        200)",
            "INSERT INTO project_assignments VALUES (8,  5, 'Analyst',     350)",
            "INSERT INTO project_assignments VALUES (9,  6, 'Analyst',     320)",
            "INSERT INTO project_assignments VALUES (10, 6, 'Analyst',     280)",
        ],
        "expected": {
            "row_count": 3,       # Engineering, Marketing, Finance (HR excluded — 2 employees)
            "departments": ["Engineering", "Finance", "Marketing"],
            "engineering_headcount": 4,
            "finance_top_scorer": True,   # Finance avg ~4.2, highest
            "hr_excluded": True,
        },
    },

    # ── NEW: Transaction Deadlock Detector ───────────────────────────────────
    "transaction_deadlock": {
        "id": "transaction_deadlock",
        "name": "Transaction Deadlock & Anomaly Detector",
        "difficulty": "expert",
        "description": (
            "You are a database reliability engineer analyzing a transaction log "
            "from a banking system. The system had an incident and you need to "
            "surface all anomalies using SQL.\n\n"
            "TABLES:\n"
            "  accounts(id, owner_name, account_type, balance, created_at)\n"
            "  transactions(id, from_account, to_account, amount, txn_timestamp, status, session_id)\n"
            "  locks(id, session_id, account_id, lock_type, acquired_at, released_at)\n"
            "    — lock_type: 'READ' or 'WRITE'\n"
            "    — released_at is NULL if lock is still held\n\n"
            "TASK: Write a SINGLE SQL query using UNION ALL that detects ALL of "
            "these anomalies and returns a report:\n\n"
            "  anomaly_type        | count | details\n"
            "  ──────────────────────────────────────\n"
            "  overdraft           | N     | accounts where balance < total outgoing (balance - SUM(outgoing) < 0)\n"
            "  unreleased_lock     | N     | sessions still holding locks\n"
            "  duplicate_txn       | N     | same from/to/amount within 60 seconds\n"
            "  self_transfer       | N     | transactions where from=to account\n"
            "  large_transfer      | N     | transfers > 10000 (potential fraud)\n\n"
            "COLUMNS: anomaly_type (TEXT), count (INTEGER), details (TEXT — describe affected IDs)\n\n"
            "This requires: multiple self-joins, timestamp arithmetic, UNION ALL, "
            "window functions or correlated subqueries. The hardest task in this environment.\n\n"
            "Expected: exactly 5 rows, one per anomaly type."
        ),
        "schema": {
            "accounts": (
                "CREATE TABLE accounts ("
                "id INTEGER PRIMARY KEY, owner_name TEXT, account_type TEXT, "
                "balance REAL, created_at TEXT)"
            ),
            "transactions": (
                "CREATE TABLE transactions ("
                "id INTEGER PRIMARY KEY, from_account INTEGER, to_account INTEGER, "
                "amount REAL, txn_timestamp TEXT, status TEXT, session_id INTEGER)"
            ),
            "locks": (
                "CREATE TABLE locks ("
                "id INTEGER PRIMARY KEY, session_id INTEGER, account_id INTEGER, "
                "lock_type TEXT, acquired_at TEXT, released_at TEXT)"
            ),
        },
        "seed_data": [
            # Accounts — Carol/Bob have large balances so only Dave overdrafts
            "INSERT INTO accounts VALUES (1, 'Alice',  'checking',  5000.00, '2020-01-01')",
            "INSERT INTO accounts VALUES (2, 'Bob',    'checking', 20000.00, '2020-02-01')",
            "INSERT INTO accounts VALUES (3, 'Carol',  'savings',  25000.00, '2020-03-01')",
            "INSERT INTO accounts VALUES (4, 'Dave',   'checking',   500.00, '2021-01-01')",
            "INSERT INTO accounts VALUES (5, 'System', 'internal',     0.00, '2019-01-01')",
            # Transactions — normal
            "INSERT INTO transactions VALUES (1,  1, 2,  500.00, '2024-01-15 10:00:00', 'completed', 101)",
            "INSERT INTO transactions VALUES (2,  2, 3,  300.00, '2024-01-15 10:05:00', 'completed', 102)",
            "INSERT INTO transactions VALUES (3,  3, 1, 1000.00, '2024-01-15 10:10:00', 'completed', 103)",
            # Overdraft: Dave (id=4, balance=500) sends 600 → overdraft
            "INSERT INTO transactions VALUES (4,  4, 1,  600.00, '2024-01-15 11:00:00', 'completed', 104)",
            # Self transfer: account 2 → account 2
            "INSERT INTO transactions VALUES (5,  2, 2,  100.00, '2024-01-15 11:30:00', 'completed', 105)",
            # Duplicate: same from/to/amount within 60s (txns 6 and 7)
            "INSERT INTO transactions VALUES (6,  1, 3,  250.00, '2024-01-15 12:00:00', 'completed', 106)",
            "INSERT INTO transactions VALUES (7,  1, 3,  250.00, '2024-01-15 12:00:45', 'completed', 107)",
            # Large transfer (fraud alert): > 10000
            "INSERT INTO transactions VALUES (8,  3, 1, 15000.00, '2024-01-15 13:00:00', 'completed', 108)",
            "INSERT INTO transactions VALUES (9,  2, 4, 12000.00, '2024-01-15 13:30:00', 'completed', 109)",
            # Locks
            "INSERT INTO locks VALUES (1, 101, 1, 'WRITE', '2024-01-15 10:00:00', '2024-01-15 10:00:05')",
            "INSERT INTO locks VALUES (2, 102, 2, 'WRITE', '2024-01-15 10:05:00', '2024-01-15 10:05:04')",
            "INSERT INTO locks VALUES (3, 103, 3, 'WRITE', '2024-01-15 10:10:00', '2024-01-15 10:10:06')",
            # Unreleased locks (released_at IS NULL)
            "INSERT INTO locks VALUES (4, 110, 1, 'WRITE', '2024-01-15 14:00:00', NULL)",
            "INSERT INTO locks VALUES (5, 111, 2, 'READ',  '2024-01-15 14:05:00', NULL)",
            "INSERT INTO locks VALUES (6, 111, 3, 'WRITE', '2024-01-15 14:05:01', NULL)",
        ],
        "expected": {
            "row_count": 5,
            "anomaly_types": {"overdraft", "unreleased_lock", "duplicate_txn",
                              "self_transfer", "large_transfer"},
            "overdraft_count": 1,      # Dave
            "unreleased_lock_count": 3, # sessions 110 and 111 (3 lock records)
            "duplicate_txn_count": 1,   # txns 6+7 form 1 duplicate pair
            "self_transfer_count": 1,   # txn 5
            "large_transfer_count": 2,  # txns 8 and 9
        },
    },
}

