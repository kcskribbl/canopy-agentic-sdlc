"""Verify offline reviewer signatures; Canopy never receives the reviewer's private key."""
import base64
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from sdlc_store import encode, sha

NAMESPACE = "canopy-local-review-v1"


def enroll(store, principal, public_key):
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}",principal):
        raise ValueError("Invalid reviewer identifier")
    fields = public_key.strip().split()
    if len(fields)<2 or fields[0]!="ssh-ed25519":
        raise ValueError("Expected an OpenSSH Ed25519 public key")
    raw=base64.b64decode(fields[1],validate=True)
    if len(raw)!=51 or raw[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
        raise ValueError("Invalid Ed25519 public key")
    with store.tx():
        if store.db.execute("SELECT 1 FROM runs LIMIT 1").fetchone() or store.trust():
            raise ValueError("Reviewer enrollment requires a fresh workspace")
        trust={"workspace_nonce":secrets.token_hex(32),"principal":principal,"public_key":" ".join(fields[:2])}
        store.db.execute("INSERT INTO trust VALUES(1,?)",(store.put(trust),))
    return {"principal":principal,"key_hash":sha(trust["public_key"]),"required_for":"all approval gates in this workspace"}


def payload(store, state, decision, reason):
    trust=store.trust()
    if not trust or state["state"]!="awaiting_approval" or decision not in {"approve","reject"} or not reason.strip():
        raise ValueError("A signed decision requires an enrolled reviewer and a pending gate")
    return (encode(dict(namespace=NAMESPACE,workspace=trust["workspace_nonce"],reviewer=trust["principal"],
                        run=state["run"],revision=state["revision"],gate=state["gate"],digest=state["digest"],
                        decision=decision,reason=reason))+"\n").encode()


def authenticate(store, state, decision, reason, signature):
    trust=store.trust()
    if not trust:
        if signature is not None:
            raise ValueError("No enrolled trust root; signature not used")
        return None
    if signature is None:
        raise ValueError("This workspace requires an enrolled reviewer's signature")
    if len(signature)>8192:
        raise ValueError("Unexpected signature size")
    data=payload(store,state,decision,reason)
    with tempfile.TemporaryDirectory(prefix="canopy-verify-sig-") as directory:
        allowed=Path(directory,"allowed")
        allowed.write_text(f"{trust['principal']} {trust['public_key']}\n",encoding="ascii")
        sig=Path(directory,"decision.sig")
        sig.write_bytes(signature)
        p=subprocess.run(["ssh-keygen","-Y","verify","-f",str(allowed),"-I",trust["principal"],
                          "-n",NAMESPACE,"-s",str(sig)],input=data,capture_output=True,timeout=10)
        if p.returncode:
            raise ValueError("Reviewer signature does not verify for this exact decision")
    return {"principal":trust["principal"],"key":trust["public_key"],"payload":data.decode(),"signature":signature.decode("ascii")}
