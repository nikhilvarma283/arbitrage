"""
Real swap transaction construction (Tinyman V2 + Pact), single-leg only.

Built for the "maker flip" strategy's hedge leg: given a specific pool and
a desired asset_in -> asset_out swap, build a REAL, correctly ABI-encoded
transaction group using the official tinyman-py-sdk / pactsdk libraries --
not hand-rolled encoding. This deliberately does NOT touch the existing
multi-hop CycleSimulator (src/simulator.py); a maker-flip hedge only ever
needs one swap at a time, which is a much smaller, better-scoped problem
than fixing the full N-hop atomic-arb builder.

Still zero capital, zero signing: build_swap_transaction() only constructs
an unsigned transaction group. Nothing here signs or broadcasts anything.
verify_swap_via_simulate() checks the encoding via algod.simulate() with
empty-signature stubs, same as the existing (placeholder-address) approach
in simulator.py -- useful even with no funded account: a "logic eval
error" / "underflow on asset holding" / "account X hasn't opted in"
response means the encoding reached real contract logic correctly; a
generic "invalid Args"/decode error means the encoding itself is wrong.
"""

import logging
from typing import Dict, List

from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.models.simulate_request import (
    SimulateRequest,
    SimulateRequestTransactionGroup,
)
from algosdk import transaction

logger = logging.getLogger(__name__)


def build_swap_transaction(
    algod_client: AlgodClient,
    pool_info: Dict,
    asset_in_id: int,
    amount_in: int,
    sender: str,
    min_amount_out: int = 0,
    slippage_pct: float = 1.0,
) -> List[transaction.Transaction]:
    """
    Build a real, unsigned swap transaction group for one specific pool.

    Args:
        algod_client: Algorand client (mainnet)
        pool_info: pool entry from pools.lock.json -- must have "protocol",
            "asset_a"/"asset_b", and protocol-specific fields ("validator_app"
            + "address" for tinyman_v2, "app_id" for pact)
        asset_in_id: asset being sent in (0 for ALGO)
        amount_in: amount of asset_in_id to swap, in raw base units
        sender: address performing the swap (transactions are unsigned --
            caller is responsible for signing before ever broadcasting)
        min_amount_out: minimum acceptable output, used directly by the
            Tinyman branch (its native fixed-input interface)
        slippage_pct: max acceptable slippage as a percent, used by the
            Pact branch (its native interface computes a minimum output
            internally from this rather than accepting one directly)

    Returns:
        List of unsigned Transaction objects, already assigned a group id.
    """
    protocol = pool_info.get("protocol", "pact")

    if protocol == "tinyman_v2":
        return _build_tinyman_swap(
            algod_client, pool_info, asset_in_id, amount_in, min_amount_out, sender
        )
    else:
        return _build_pact_swap(
            algod_client, pool_info, asset_in_id, amount_in, slippage_pct, sender
        )


def _build_tinyman_swap(
    algod_client: AlgodClient,
    pool_info: Dict,
    asset_in_id: int,
    amount_in: int,
    min_amount_out: int,
    sender: str,
) -> List[transaction.Transaction]:
    from tinyman.v2.swap import prepare_swap_transactions
    from tinyman.v2.constants import FIXED_INPUT_APP_ARGUMENT

    asset_a = int(pool_info["asset_a"])
    asset_b = int(pool_info["asset_b"])
    validator_app_id = int(pool_info["validator_app"])

    txn_group = prepare_swap_transactions(
        validator_app_id=validator_app_id,
        asset_1_id=max(asset_a, asset_b),
        asset_2_id=min(asset_a, asset_b),
        asset_in_id=asset_in_id,
        asset_in_amount=amount_in,
        asset_out_amount=min_amount_out,
        swap_type=FIXED_INPUT_APP_ARGUMENT,
        sender=sender,
        suggested_params=algod_client.suggested_params(),
    )
    return list(txn_group.transactions)


def _build_pact_swap(
    algod_client: AlgodClient,
    pool_info: Dict,
    asset_in_id: int,
    amount_in: int,
    slippage_pct: float,
    sender: str,
) -> List[transaction.Transaction]:
    import pactsdk

    pact = pactsdk.PactClient(algod_client, network="mainnet")
    pool = pact.fetch_pool_by_id(int(pool_info["app_id"]))
    asset_in = pact.fetch_asset(asset_in_id)

    swap = pool.prepare_swap(
        asset=asset_in, amount=amount_in, slippage_pct=slippage_pct
    )
    txn_group = pool.prepare_swap_tx_group(swap, sender)
    return list(txn_group.transactions)


def verify_swap_via_simulate(
    algod_client: AlgodClient, txn_group: List[transaction.Transaction]
) -> Dict:
    """
    Run a built swap transaction group through algod.simulate() using
    empty-signature stubs -- no signing, no broadcast, no funds required.

    Returns a dict with "success" (bool) and "detail" (the algod response
    or error message), so the caller can distinguish "reached real
    contract logic" (e.g. balance/opt-in errors) from "encoding itself is
    malformed" (e.g. invalid Args, decode errors).
    """
    try:
        signed_stub: List[transaction.GenericSignedTransaction] = [
            transaction.SignedTransaction(transaction=t, signature=None)
            for t in txn_group
        ]
        request = SimulateRequest(
            txn_groups=[SimulateRequestTransactionGroup(txns=signed_stub)],
            allow_empty_signatures=True,
        )
        result = algod_client.simulate_transactions(request)
        assert isinstance(result, dict)
        txn_result = result.get("txn-groups", [{}])[0]
        return {"success": True, "detail": txn_result}
    except Exception as e:
        return {"success": False, "detail": str(e)}
