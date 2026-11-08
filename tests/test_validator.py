import pytest

from bi_analyst.agents.validator import validate_sql


@pytest.fixture()
def schema(db):
    return db.schema()


def test_valid_query_passes(schema, db):
    sql = "SELECT region, COUNT(*) AS n FROM customers GROUP BY region"
    assert validate_sql(sql, schema, db) is None


def test_cte_passes(schema, db):
    sql = "WITH t AS (SELECT customer_id FROM orders) SELECT COUNT(*) FROM t"
    assert validate_sql(sql, schema, db) is None


@pytest.mark.parametrize("sql", [
    "DROP TABLE customers",
    "DELETE FROM orders",
    "UPDATE customers SET name='x'",
    "SELECT 1; DROP TABLE customers",
    "INSERT INTO customers VALUES (1,'a','b','c')",
])
def test_writes_are_blocked(sql, schema, db):
    err = validate_sql(sql, schema, db)
    assert err and err.startswith(("unsafe", "syntax"))


def test_hallucinated_column(schema, db):
    err = validate_sql("SELECT revenue FROM orders", schema, db)
    assert err and err.startswith("unknown_column")


def test_hallucinated_table(schema, db):
    err = validate_sql("SELECT * FROM sales", schema, db)
    assert err and err.startswith("unknown_table")


def test_database_is_read_only(db):
    with pytest.raises(Exception):
        db.run("DELETE FROM customers")
