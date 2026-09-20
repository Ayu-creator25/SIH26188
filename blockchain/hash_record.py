"""
Blockchain Audit Trail Module
-------------------------------
Creates a SHA-256 hash of the verification result and writes it to the
local Ganache blockchain via Web3.py. No PII is ever written on-chain —
only the SHA-256 hash of a record made of a random document ID, a
timestamp and the check outcomes. Use audit_store.verify_record() to
later prove a stored record still matches the hash anchored here.

Expected contract (do not change without also updating backend/app.py):
    create_record(document_id: str, result_summary: dict) -> dict
"""

from web3 import Web3

from audit_store import compute_record_hash

# Ganache's local RPC address (shown in the Ganache app's "RPC Server" field)
GANACHE_URL = "http://127.0.0.1:7545"


def create_record(document_id, result_summary):
    """
    Hash the verification result and record it on the local blockchain.

    Args:
        document_id (str): A non-PII identifier for this scan (e.g. a
            generated UUID — never the actual document number).
        result_summary (dict): Non-sensitive summary of the verification
            outcome (e.g. {"timestamp": "2026-09-20T10:00:00+00:00",
            "decision": "Verified"}).

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

    # One exact, repeatable hash of the record. The same function is used by
    # audit_store.verify_record(), so a later re-hash always matches this one
    # unless the stored record was altered.
    record_hash = compute_record_hash(document_id, result_summary)

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