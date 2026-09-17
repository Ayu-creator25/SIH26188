"""
Blockchain Audit Trail Module
-------------------------------
Creates a SHA-256 hash of the verification result and writes it to the
local Ganache blockchain via Web3.py. No PII is ever written on-chain —
only a document ID, timestamp, risk score, and outcome hash.

Expected contract (do not change without also updating backend/app.py):
    create_record(document_id: str, result_summary: dict) -> dict
"""

import hashlib
import json

from web3 import Web3

# Ganache's local RPC address (shown in the Ganache app's "RPC Server" field)
GANACHE_URL = "http://127.0.0.1:7545"


def create_record(document_id, result_summary):
    """
    Hash the verification result and record it on the local blockchain.

    Args:
        document_id (str): A non-PII identifier for this scan (e.g. a
            generated UUID — never the actual document number).
        result_summary (dict): Non-sensitive summary of the verification
            outcome (e.g. {"decision": "Verified", "risk_score": 0.1}).

    Returns:
        dict: {
            "tx_hash": str | None,
            "record_hash": str | None,
            "status": "Recorded" | "Pending"
        }
    """
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

    # If Ganache isn't reachable, fail gracefully instead of crashing the
    # whole scan pipeline just because the audit-trail step couldn't run.
    if not w3.is_connected():
        return {
            "tx_hash": None,
            "record_hash": None,
            "status": "Pending"
        }

    # Build one exact, repeatable string from the inputs. sort_keys=True
    # guarantees the same dict always produces the same string, no matter
    # what order its keys happen to be in — which means the same input
    # always produces the same hash.
    record_string = json.dumps(
        {"document_id": document_id, "result_summary": result_summary},
        sort_keys=True
    )
    record_hash = hashlib.sha256(record_string.encode("utf-8")).hexdigest()

    # Ganache pre-funds 10 test accounts for us; use the first one both
    # to send from and send to — we're not transferring value to anyone,
    # just using the transaction as a vehicle to carry our hash.
    sender = w3.eth.accounts[0]

    tx_hash = w3.eth.send_transaction({
        "from": sender,
        "to": sender,
        "value": 0,
        "data": Web3.to_hex(text=record_hash),
    })

    # Block until the transaction is actually mined, so we only report
    # "Recorded" once it's really on the chain, not just submitted.
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return {
        "tx_hash": receipt.transactionHash.hex(),
        "record_hash": record_hash,
        "status": "Recorded"
    }


if __name__ == "__main__":
    result = create_record("doc-0001", {"decision": "Pending Review"})
    print(result)