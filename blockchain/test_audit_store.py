"""
blockchain/test_audit_store.py

Tests for the audit store and integrity verification. No Ganache is needed:
an in-memory fake blockchain stands in for it.

Usage (from the repo root):
    pytest blockchain/test_audit_store.py -v
"""

import hashlib
import json

import pytest

import audit_store


class TransactionNotFound(Exception):
    """Same class name web3 uses when a transaction hash is unknown."""


class FakeHexBytes:
    """Mimics HexBytes in recent web3: .hex() has NO 0x prefix."""

    def __init__(self, value):
        self._value = value

    def hex(self):
        return self._value[2:]


class FakeEth:
    def __init__(self, chain):
        self._chain = chain
        self.accounts = ["0xSENDER"]

    def send_transaction(self, transaction):
        data = bytes.fromhex(transaction["data"][2:])
        tx_hash = "0x" + hashlib.sha256(data + bytes(len(self._chain))).hexdigest()
        self._chain[tx_hash] = data
        return tx_hash

    def wait_for_transaction_receipt(self, tx_hash):
        class Receipt:
            pass

        receipt = Receipt()
        receipt.transactionHash = FakeHexBytes(tx_hash)
        return receipt

    def get_transaction(self, tx_hash):
        # Real web3 wants a 0x-prefixed hash, so the fake is strict too.
        if not tx_hash.startswith("0x"):
            raise ValueError("transaction hash must be 0x-prefixed")
        if tx_hash not in self._chain:
            raise TransactionNotFound(tx_hash)
        return {"input": self._chain[tx_hash]}


def make_fake_web3(chain, connected=True):
    """Build a stand-in for the Web3 class, backed by an in-memory chain."""

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url: url)

        @staticmethod
        def to_hex(text=None):
            return "0x" + text.encode("utf-8").hex()

        def __init__(self, provider=None):
            self.eth = FakeEth(chain)

        def is_connected(self):
            return connected

    return FakeWeb3


DOCUMENT_ID = "123e4567-e89b-42d3-a456-426614174000"
SUMMARY = {
    "timestamp": "2026-09-20T10:00:00+00:00",
    "decision": "High Risk",
    "validation_status": "Valid",
    "tamper_status": "Suspicious",
    "face_match_status": "Pending",
    "liveness_status": "Pending",
}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Point the audit store at a temporary folder for each test."""
    monkeypatch.setattr(audit_store, "RECORDS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def recorded(store, monkeypatch):
    """Create a record through the REAL create_record(), then save it."""
    import hash_record

    chain = {}
    fake_web3 = make_fake_web3(chain)
    monkeypatch.setattr(hash_record, "Web3", fake_web3)

    result = hash_record.create_record(DOCUMENT_ID, SUMMARY)
    assert result["status"] == "Recorded"
    audit_store.save_record(
        DOCUMENT_ID, SUMMARY, result["tx_hash"], result["record_hash"]
    )
    return {"w3": fake_web3(), "path": store / (DOCUMENT_ID + ".json"), "result": result}


def edit_stored_record(path, change):
    """Open the stored JSON, apply a change, and save it back."""
    record = json.loads(path.read_text(encoding="utf-8"))
    change(record)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def test_hash_matches_the_original_inline_computation():
    """Refactoring must not change hashes of records written before it."""
    legacy_string = json.dumps(
        {"document_id": DOCUMENT_ID, "result_summary": SUMMARY}, sort_keys=True
    )
    legacy_hash = hashlib.sha256(legacy_string.encode("utf-8")).hexdigest()
    assert audit_store.compute_record_hash(DOCUMENT_ID, SUMMARY) == legacy_hash


def test_untouched_record_is_intact(recorded):
    result = audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])
    assert result["status"] == audit_store.INTACT
    assert result["recomputed_hash"] == result["onchain_hash"]


def test_tx_hash_without_0x_prefix_still_verifies(recorded):
    """create_record() returns a hash without 0x on recent web3 versions."""
    assert not recorded["result"]["tx_hash"].startswith("0x")
    result = audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])
    assert result["status"] == audit_store.INTACT


def test_editing_the_decision_is_detected(recorded):
    edit_stored_record(
        recorded["path"],
        lambda record: record["result_summary"].update(decision="Verified"),
    )
    result = audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])
    assert result["status"] == audit_store.TAMPERED
    assert result["recomputed_hash"] != result["onchain_hash"]


def test_editing_the_timestamp_is_detected(recorded):
    edit_stored_record(
        recorded["path"],
        lambda record: record["result_summary"].update(timestamp="2026-01-01T00:00:00+00:00"),
    )
    assert audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])["status"] == audit_store.TAMPERED


def test_attacker_who_also_edits_the_stored_hash_is_still_caught(recorded):
    """The blockchain, not the local file, is the source of truth."""

    def forge(record):
        record["result_summary"]["decision"] = "Verified"
        record["record_hash"] = audit_store.compute_record_hash(
            record["document_id"], record["result_summary"]
        )

    edit_stored_record(recorded["path"], forge)
    assert audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])["status"] == audit_store.TAMPERED


def test_pointing_the_record_at_another_transaction_is_caught(recorded):
    other = recorded["w3"].eth.send_transaction({"data": "0x" + "ab" * 32})
    edit_stored_record(recorded["path"], lambda record: record.update(tx_hash=other))
    assert audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])["status"] == audit_store.TAMPERED


def test_damaged_json_counts_as_tampered(recorded):
    recorded["path"].write_text("{ this is not json", encoding="utf-8")
    assert audit_store.verify_record(DOCUMENT_ID, w3=recorded["w3"])["status"] == audit_store.TAMPERED


def test_missing_stored_record(store):
    result = audit_store.verify_record(DOCUMENT_ID, w3=make_fake_web3({})())
    assert result["status"] == audit_store.RECORD_NOT_FOUND


def test_path_traversal_ids_are_rejected(store):
    for bad_id in ["../../etc/passwd", "..\\secret", "", None, "not-a-uuid"]:
        assert audit_store.verify_record(bad_id)["status"] == audit_store.RECORD_NOT_FOUND
    with pytest.raises(ValueError):
        audit_store.save_record("../evil", SUMMARY, "0x1", "abc")


def test_ledger_offline(recorded):
    offline = make_fake_web3({}, connected=False)()
    result = audit_store.verify_record(DOCUMENT_ID, w3=offline)
    assert result["status"] == audit_store.CHAIN_UNAVAILABLE


def test_ledger_reset_reports_missing_transaction(recorded):
    empty_chain = make_fake_web3({})()  # e.g. Ganache workspace was reset
    result = audit_store.verify_record(DOCUMENT_ID, w3=empty_chain)
    assert result["status"] == audit_store.CHAIN_RECORD_MISSING


def test_stored_record_holds_no_pii_fields(recorded):
    record = json.loads(recorded["path"].read_text(encoding="utf-8"))
    assert set(record) == {"document_id", "result_summary", "record_hash", "tx_hash"}
    assert set(record["result_summary"]) == set(SUMMARY)


def test_list_records_is_newest_first_and_shows_damaged_files(store):
    older = "11111111-1111-4111-8111-111111111111"
    newer = "22222222-2222-4222-8222-222222222222"
    broken = "33333333-3333-4333-8333-333333333333"
    audit_store.save_record(older, {"timestamp": "2026-09-20T09:00:00+00:00", "decision": "Suspicious"}, "0x1", "a")
    audit_store.save_record(newer, {"timestamp": "2026-09-20T11:00:00+00:00", "decision": "Verified"}, "0x2", "b")
    (store / (broken + ".json")).write_text("garbage", encoding="utf-8")
    (store / "notes.txt").write_text("ignored", encoding="utf-8")

    listed = audit_store.list_records()
    assert [entry["document_id"] for entry in listed] == [newer, older, broken]
    assert listed[-1]["decision"] == "Unreadable"
