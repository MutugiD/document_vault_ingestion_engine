"""Prove that answering a question about a matter reaches no network.

JurisNuru is sold to firms that already pay a subscription for it. A hosted LLM
layer on top would be a second per-firm bill for something the product does not
need, so "no LLM" is a commercial commitment as much as a technical one.

It is currently true. It has never been *provable*, and a claim in a document
degrades the moment someone adds a convenient import. The dynamic check below is
the part that matters: sockets are made to raise, and the whole retrieval and
summary path is then run for real. Anything reaching the network fails with a
stack trace naming the caller, which survives refactors, indirection and
transitive imports in a way a grep for "openai" does not.

The static check is the cheap complement, catching an import before it is ever
called.
"""

from __future__ import annotations

import ast
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Modules that answer questions about a matter. Nothing here may open a socket.
OFFLINE_PACKAGES = ("rag", "search", "vault", "intake", "backup")
OFFLINE_MODULES = (Path("core") / "manual_app.py",)

# Two groups, because they fail differently. A provider client is a deliberate
# decision someone made; a bare `import socket` is usually an accident that
# opens the door for the next person.
PROVIDER_CLIENTS = {
    "openai",
    "anthropic",
    "google",
    "google.generativeai",
    "cohere",
    "mistralai",
    "transformers",
    "litellm",
    "ollama",
}
NETWORK_MODULES = {
    "urllib.request",
    "urllib3",
    "http.client",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "ftplib",
    "smtplib",
    "telnetlib",
}


def imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def check_static() -> int:
    sources: list[Path] = []
    for package in OFFLINE_PACKAGES:
        sources.extend(sorted((ROOT / package).rglob("*.py")))
    sources.extend(ROOT / module for module in OFFLINE_MODULES)

    failures: list[str] = []
    for source in sources:
        if not source.exists():
            continue
        names = imported_names(source)
        for name in sorted(names):
            root_name = name.split(".")[0]
            if root_name in PROVIDER_CLIENTS or name in PROVIDER_CLIENTS:
                failures.append(f"{source.relative_to(ROOT)} imports the LLM client {name}")
            if name in NETWORK_MODULES or root_name in {"socket", "ssl"}:
                failures.append(f"{source.relative_to(ROOT)} imports the network module {name}")
    if failures:
        raise AssertionError(
            "the offline path gained a network dependency:\n  " + "\n  ".join(failures)
        )
    return len(sources)


def check_dynamic() -> None:
    """Run the real path with the network unplugged.

    A grep can be satisfied by indirection. This cannot: if anything below
    opens a connection, it raises here and names itself.
    """
    from rag import build_answer_packet, build_rag_index
    from search import add_document_version, create_document, create_matter, initialize_search_store
    from vault import initialize_vault
    from wakilios.core import initialize_firm_backend

    judgment = (
        "IN THE HIGH COURT OF KENYA AT MERU\n"
        "CIVIL CASE NO. E214 OF 2026\n"
        "The plaintiff seeks damages for breach of a supply agreement dated "
        "4 March 2025. Liability was apportioned 70 per cent to the defendant "
        "and 30 per cent to the plaintiff. The court awarded KES 4,000,000 in "
        "general damages together with costs and interest at court rates."
    )

    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def refuse(*args, **kwargs):
        raise AssertionError(
            "the offline path opened a network connection. "
            "Read the stack above: something in retrieval or summarising is "
            "calling out, which is exactly what this product promises not to do."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        backend = initialize_firm_backend(
            root / "firm",
            firm_name="Offline Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="offline vault passphrase",
        )
        token = backend.login("admin", "admin-pass").token
        matter = backend.create_litigation_matter(
            token,
            internal_reference="MTR-OFF-1",
            client_name="Kiunga Holdings",
            parties="Kiunga v Supplier",
            court="High Court",
            station="Meru",
            case_number="HCCC/E214/2026",
            practice_area="Commercial",
            responsible_advocate="A. Advocate",
            filing_status="filed",
            filing_date="2026-08-01",
        )
        matter_id = str(matter["matter_id"])
        document = backend.upload_document(
            token,
            matter_id,
            title="Judgment",
            document_type="judgment",
            content=judgment.encode("utf-8"),
            original_name="judgment.txt",
            content_type="text/plain",
            extracted_text=judgment,
        )

        # A standalone vault and index too, so the check covers the path a
        # single-machine install takes as well as the firm backend's.
        standalone = root / "standalone"
        initialize_vault(standalone, "standalone passphrase")
        initialize_search_store(standalone)
        solo_matter = create_matter(
            standalone,
            internal_reference="MTR-OFF-2",
            client_name="Kiunga Holdings",
            parties="Kiunga v Supplier",
            court="High Court",
            station="Meru",
            case_number="HCCC/E215/2026",
            practice_area="Commercial",
            responsible_advocate="A. Advocate",
            status="active",
        )
        solo_document = create_document(
            standalone,
            matter_id=solo_matter.matter_id,
            title="Judgment",
            document_type="judgment",
            lifecycle_status="filed",
        )
        add_document_version(
            standalone,
            document_id=solo_document.document_id,
            object_id="obj-1",
            source_sha256="0" * 64,
            extracted_text=judgment,
            lifecycle_status="filed",
        )

        socket.socket.connect = refuse
        socket.create_connection = refuse
        try:
            # Prove the trap is armed before trusting what it does not catch.
            # Without this, a typo in the patching would make every assertion
            # below pass forever while testing nothing at all.
            try:
                socket.create_connection(("127.0.0.1", 9))
            except AssertionError:
                pass
            else:
                raise SystemExit("the socket guard is not active; this test proves nothing")

            build_rag_index(standalone, matter_id=solo_matter.matter_id)
            packet = build_answer_packet(
                standalone,
                "How was liability apportioned?",
                matter_id=solo_matter.matter_id,
            )
            assert packet.citations, "the offline path returned nothing to assert on"
            # Retrieval, not generation. There is no answer field, because
            # nothing composes one -- which is the architectural reason no LLM
            # is needed rather than merely not used.
            assert not hasattr(packet, "answer"), (
                "RagAnswerPacket grew an 'answer' field; something is now generating "
                "prose rather than returning passages, and that is where an LLM enters"
            )
            assert packet.grounded_context.strip()
            assert packet.safety_notice

            summary = backend.generate_ai_summary(
                token, matter_id, document_id=str(document["document_id"])
            )
            assert summary, summary
        finally:
            socket.socket.connect = original_connect
            socket.create_connection = original_create


def check_hosted_boundary() -> None:
    """The one hosted path ships no client, no key, and is gated."""
    from ai.hosted import HostedAIDecision

    hosted_source = (ROOT / "ai" / "hosted.py").read_text(encoding="utf-8")
    names = imported_names(ROOT / "ai" / "hosted.py")
    for name in sorted(names):
        assert name.split(".")[0] not in PROVIDER_CLIENTS, f"ai/hosted.py imports {name}"
        assert name not in NETWORK_MODULES, f"ai/hosted.py imports {name}"
    # The transport is injected, which is why this module can carry no provider
    # and no endpoint: a caller has to supply one, and nothing in the shipped
    # product does.
    assert "HostedAITransport = Callable" in hosted_source, hosted_source[:200]
    for marker in ("api.openai.com", "api.anthropic.com", "sk-", "Bearer "):
        assert marker not in hosted_source, f"ai/hosted.py carries a provider detail: {marker}"

    # Both switches are required: the licence has to include it *and* the user
    # has to have approved it. Either alone is not enough.
    for entitled, approved in ((False, True), (True, False), (False, False)):
        try:
            HostedAIDecision(hosted_ai_enabled=entitled, user_approved=approved).require_allowed()
        except Exception:
            pass
        else:
            raise AssertionError(
                f"hosted AI was permitted with entitlement={entitled}, approval={approved}"
            )
    HostedAIDecision(hosted_ai_enabled=True, user_approved=True).require_allowed()

    from ui.app import ENTITLEMENT_CONTROLS

    assert "hosted_ai" in ENTITLEMENT_CONTROLS, ENTITLEMENT_CONTROLS
    assert ENTITLEMENT_CONTROLS["hosted_ai"], "the hosted_ai entitlement governs no control"


def main() -> None:
    checked = check_static()
    check_hosted_boundary()
    check_dynamic()
    print(f"NO-LLM EGRESS VALIDATION PASS: {checked} offline modules, network refused end to end")


if __name__ == "__main__":
    main()
