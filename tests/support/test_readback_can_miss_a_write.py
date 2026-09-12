"""the fake backend can model a write the read-back
does not reflect.

The one thing the MCP server's own `{success: true}` cannot prove is that
the cart actually changed (`CLAUDE.md`'s fourth invariant). The offline
fixture had no way to produce that case: every write it accepted, it also
applied, so a read-back always showed exactly what was written and the
`unverified` branch could only be reached by killing the read-back
entirely (`crash_readback_once`).

`silent_write_rounds` closes that: the write tool returns success and the
cart does NOT move. The graph's read-back then finds its consented product
missing, refuses to call it a success, and reports `unverified` -- which is
DR-12 in its intended form, a completed read-back that disagrees, rather
than a read-back that never happened.

Needed for GD-06's own bundle: its declared rubric ends `unverified`, and
that must come from a modelled failure rather than from a fixture running
out of recorded cart states.
"""

from tests.support.write_backend import (
    FakeWriteBackend,
    WriteBackendFixture,
    default_fixture,
)


def _fixture(**overrides: object) -> WriteBackendFixture:
    import dataclasses

    return dataclasses.replace(default_fixture(), **overrides)


def test_by_default_a_write_still_moves_the_cart() -> None:
    """The existing behaviour, unchanged -- every other case depends on
    it."""
    backend = FakeWriteBackend(_fixture())
    before = len(backend.fixture.raw_cart["shipments"][0]["products"])

    backend.call_write_tool(
        "silpo_add_or_update_cart_products",
        {"shoppingCartId": "c", "products": [{"productId": "p1", "quantity": 1}]},
    )
    after = backend.fetch_cart_by_id_after_write("c")["cart"]

    assert len(after["shipments"][0]["products"]) == before + 1


def test_a_silent_round_reports_success_and_moves_nothing() -> None:
    backend = FakeWriteBackend(_fixture(silent_write_rounds=(1,)))
    before = len(backend.fixture.raw_cart["shipments"][0]["products"])

    response = backend.call_write_tool(
        "silpo_add_or_update_cart_products",
        {"shoppingCartId": "c", "products": [{"productId": "p1", "quantity": 1}]},
    )
    after = backend.fetch_cart_by_id_after_write("c")["cart"]

    assert response["success"] is True, "the server's own success flag still says yes"
    assert (
        len(after["shipments"][0]["products"]) == before
    ), "the cart moved -- then this models nothing the read-back could catch"


def test_only_the_named_round_is_silent() -> None:
    """GD-06 needs a first round that lands and a second that does not."""
    backend = FakeWriteBackend(_fixture(silent_write_rounds=(2,)))
    before = len(backend.fixture.raw_cart["shipments"][0]["products"])

    backend.call_write_tool(
        "silpo_add_or_update_cart_products",
        {"shoppingCartId": "c", "products": [{"productId": "p1", "quantity": 1}]},
    )
    assert (
        len(
            backend.fetch_cart_by_id_after_write("c")["cart"]["shipments"][0][
                "products"
            ]
        )
        == before + 1
    )

    backend.call_write_tool(
        "silpo_add_or_update_cart_products",
        {"shoppingCartId": "c", "products": [{"productId": "p2", "quantity": 1}]},
    )
    assert (
        len(
            backend.fetch_cart_by_id_after_write("c")["cart"]["shipments"][0][
                "products"
            ]
        )
        == before + 1
    ), "the second round moved the cart despite being declared silent"


def test_the_write_is_still_recorded_as_attempted() -> None:
    """A silent write is not an absent write: the journal claim and the
    write call both happened, and the metrics' denominators must see
    them."""
    backend = FakeWriteBackend(_fixture(silent_write_rounds=(1,)))

    backend.call_write_tool(
        "silpo_add_or_update_cart_products",
        {"shoppingCartId": "c", "products": [{"productId": "p1", "quantity": 1}]},
    )

    assert len(backend.write_calls) == 1
