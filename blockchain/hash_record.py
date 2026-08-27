"""
Blockchain Audit Trail Module
-------------------------------
Creates a SHA-256 hash of the verification result and writes it to the
local Ganache blockchain via Web3.py. No PII is ever written on-chain —
only a document ID, timestamp, risk score, and outcome hash.

Expected contract (do not change without also updating backend/app.py):
    create_record(document_id: str, result_summary: dict) -> dict
"""


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
    # TODO: implement SHA-256 hashing + Web3.py/Ganache integration
    return {
        "tx_hash": None,
        "record_hash": None,
        "status": "Pending"
    }


if __name__ == "__main__":
    result = create_record("doc-0001", {"decision": "Pending Review"})
    print(result)