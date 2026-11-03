"""Bugs that the harness found, each with the test that keeps it fixed."""

import duckdb
import pytest

from scriptt.world import Fact, Key, World


class Night(Fact):
    id: Key[str]
    hours: float


def world() -> World:
    nights = World.new(Night)
    nights.add(Night(id="n1", hours=7.5), source="me")
    return nights


def test_sql_tells_how_to_name_a_type_without_braces() -> None:
    with pytest.raises(duckdb.CatalogException) as error:
        world().sql(t"SELECT count(*) FROM Night")
    assert "Write {Night} for the table of the type Night" in str(error.value)
    assert "pg_type" not in str(error.value)


def test_sql_errors_show_the_type_and_not_the_temporary_table() -> None:
    with pytest.raises(duckdb.BinderException) as error:
        world().sql(t"SELECT nope FROM {Night}")
    assert "{Night}" in str(error.value)
    assert "night#" not in str(error.value)


@pytest.mark.parametrize("amount", [1e16, 1.5e-7, -2e20, 0.1, 12.0])
def test_to_text_of_a_float_parses_back(amount: float) -> None:
    class Bill(Fact):
        id: Key[str]
        amount: float

    bill = Bill(id="b1", amount=amount)
    assert Bill.parse(bill.to_text()).unwrap() == bill
