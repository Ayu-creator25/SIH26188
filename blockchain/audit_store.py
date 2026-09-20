"""
Audit Store and Integrity Verification
--------------------------------------
Completes the blockchain audit trail so that "tamper-evident" is something
you can actually demonstrate, not just claim.

How it works
    1. hash_record.create_record() hashes a scan's result record with SHA-256
       and writes ONLY that hash to the blockchain.
    2. save_record() (this module) keeps the exact record that was hashed in a
       local JSON file. It holds no PII: a random document ID, a timestamp and
       the check outcomes.
    3. verify_record() later re-hashes the stored record and compares the
       result with the hash found on the blockchain. If anyone edited the
       stored record, the two hashes differ and it is reported as tampered.

What this proves: the record was not altered after it was written.
What it does NOT prove: that the scanned document itself is genuine.
"""

import hashlib
import json
import os
import re

# Where the off-chain records live (data/ is not committed to git).
RECORDS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "audit_records")

# Document IDs are UUID4 strings. Checking the format before touching the
# filesystem blocks path-traversal input such as "../../secret".
_DOCUMENT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Every verification ends in exactly one of these statuses.
INTACT = "INTACT"
TAMPERED = "TAMPERED"
RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
CHAIN_RECORD_MISSING = "CHAIN_RECORD_MISSING"
CHAIN_UNAVAILABLE = "CHAIN_UNAVAILABLE"

# Short labels shown on the dashboard.
STATUS_LABELS = {
    INTACT: "Integrity Verified",
    TAMPERED: "Tamper Detected",
    RECORD_NOT_FOUND: "No Stored Record",
    CHAIN_RECORD_MISSING: "Not Found On Chain",
    CHAIN_UNAVAILABLE: "Ledger Offline",
}


def compute_record_hash(document_id, result_summary):
    """
    Return the SHA-256 hash (hex string) of a canonical record.

    This is the single place where a record is turned into bytes, and both
    create_record() and verify_record() use it. sort_keys=True makes the same
    record always produce the same string, whatever order its keys are in.
    """
    record_string = json.dumps(
        {"document_id": document_id, "result_summary": result_summary},
        sort_keys=True,
    )
    return hashlib.sha256(record_string.encode("utf-8")).hexdigest()


def _record_path(document_id):
    """Return the JSON path for a document ID, or None if the ID is invalid."""
    if not isinstance(document_id, str) or not _DOCUMENT_ID_PATTERN.match(document_id):
        return None
    return os.path.join(RECORDS_DIR, document_id + ".json")


def save_record(document_id, result_summary, tx_hash, record_hash):
    """
    Save the exact record that was hashed, next to its blockchain reference.

    Raises ValueError if document_id is not a valid UUID string.
    """
    path = _record_path(document_id)
    if path is None:
        raise ValueError("document_id must be a UUID string")

    os.makedirs(RECORDS_DIR, exist_ok=True)
    record = {
        "document_id": document_id,
        "result_summary": result_summary,
        "record_hash": record_hash,
        "tx_hash": tx_hash,
    }
    # Pretty-printed on purpose, so the record is easy to open and edit by
    # hand when demonstrating tamper detection.
    with open(path, "w", encoding="utf-8") as record_file:
        json.dump(record, record_file, indent=2, sort_keys=True)


def get_w3():
    """Connect to the local Ganache node (imports are lazy so tests need no web3)."""
    from web3 import Web3
    from hash_record import GANACHE_URL

    return Web3(Web3.HTTPProvider(GANACHE_URL))


def _normalize_tx_hash(tx_hash):
    """Make sure a transaction hash carries the 0x prefix web3 expects."""
    tx_hash = str(tx_hash)
    return tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash


def _result(status, message, **extra):
    """Build the dict returned by verify_record()."""
    result = {
        "status": status,
        "label": STATUS_LABELS[status],
        "message": message,
        "recomputed_hash": None,
        "onchain_hash": None,
        "tx_hash": None,
    }
    result.update(extra)
    return result


def verify_record(document_id, w3=None):
    """
    Re-hash the stored record and compare it with the hash on the blockchain.

    Args:
        document_id (str): The scan's UUID.
        w3: Optional Web3 connection (a fresh one is created if omitted).

    Returns:
        dict with keys: status (one of INTACT, TAMPERED, RECORD_NOT_FOUND,
        CHAIN_RECORD_MISSING, CHAIN_UNAVAILABLE), label, message,
        recomputed_hash, onchain_hash, tx_hash.
    """
    path = _record_path(document_id)
    if path is None or not os.path.exists(path):
        return _result(RECORD_NOT_FOUND, "No stored record exists for this document ID.")

    # Step 1: read the stored record and re-hash it.
    try:
        with open(path, encoding="utf-8") as record_file:
            record = json.load(record_file)
        recomputed_hash = compute_record_hash(
            record["document_id"], record["result_summary"]
        )
        tx_hash = _normalize_tx_hash(record["tx_hash"])
    except (OSError, ValueError, KeyError, TypeError):
        return _result(
            TAMPERED, "The stored record is unreadable or has been damaged."
        )

    # Step 2: fetch the hash that was written to the blockchain.
    try:
        if w3 is None:
            w3 = get_w3()
        if not w3.is_connected():
            return _result(
                CHAIN_UNAVAILABLE,
                "The local blockchain (Ganache) is not reachable, so the record "
                "cannot be verified right now.",
                recomputed_hash=recomputed_hash,
                tx_hash=tx_hash,
            )
        transaction = w3.eth.get_transaction(tx_hash)
    except Exception as error:  # noqa: BLE001 - any failure here means "cannot verify"
        if type(error).__name__ == "TransactionNotFound":
            return _result(
                CHAIN_RECORD_MISSING,
                "The blockchain has no transaction for this record. If Ganache "
                "was restarted or its workspace reset, older records are gone.",
                recomputed_hash=recomputed_hash,
                tx_hash=tx_hash,
            )
        return _result(
            CHAIN_UNAVAILABLE,
            "The blockchain could not be queried right now.",
            recomputed_hash=recomputed_hash,
            tx_hash=tx_hash,
        )

    # The transaction's data field holds the ASCII text of the SHA-256 hash.
    try:
        onchain_hash = bytes(transaction["input"]).decode("utf-8")
    except (KeyError, TypeError, UnicodeDecodeError):
        onchain_hash = None

    # Step 3: compare.
    if onchain_hash == recomputed_hash:
        return _result(
            INTACT,
            "The stored record matches the hash anchored on the blockchain. "
            "It has not been altered since it was written.",
            recomputed_hash=recomputed_hash,
            onchain_hash=onchain_hash,
            tx_hash=tx_hash,
        )
    return _result(
        TAMPERED,
        "The stored record no longer matches the hash anchored on the "
        "blockchain. It has been altered since it was written.",
        recomputed_hash=recomputed_hash,
        onchain_hash=onchain_hash,
        tx_hash=tx_hash,
    )


def list_records(limit=25):
    """
    Return the most recent stored records (newest first) for the audit page.

    Each entry: document_id, timestamp, decision, tx_hash. Unreadable files are
    still listed so that damage is visible rather than silently skipped.
    """
    if not os.path.isdir(RECORDS_DIR):
        return []

    entries = []
    for name in os.listdir(RECORDS_DIR):
        document_id, extension = os.path.splitext(name)
        if extension != ".json" or not _DOCUMENT_ID_PATTERN.match(document_id):
            continue

        entry = {
            "document_id": document_id,
            "timestamp": "",
            "decision": "Unreadable",
            "tx_hash": None,
        }
        try:
            with open(os.path.join(RECORDS_DIR, name), encoding="utf-8") as record_file:
                record = json.load(record_file)
            summary = record.get("result_summary", {})
            entry["timestamp"] = str(summary.get("timestamp", ""))
            entry["decision"] = str(summary.get("decision", "Unknown"))
            entry["tx_hash"] = record.get("tx_hash")
        except (OSError, ValueError, AttributeError):
            pass
        entries.append(entry)

    # ISO timestamps sort correctly as plain strings.
    entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
    return entries[:limit]
