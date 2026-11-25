import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import control
import reviewer
from reviewed_patch import load
from sdlc_store import sha


class DeliveryTests(unittest.TestCase):
    def test_pinned_build_change_denies_drift_and_unregistered_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            pack=root/"scenarios"/"fixture"/"proposal"
            pack.mkdir(parents=True)
            path=pack/"pom.xml"
            path.write_text("<project/>",encoding="utf-8")
            base={"pom.xml":"previous"}
            entry={"baseline":sha(base),"directory":"scenarios/fixture/proposal","files":{"pom.xml":sha("<project/>")}}
            self.assertEqual({"pom.xml":"<project/>"},load(root,entry,base,1024))
            with self.assertRaisesRegex(ValueError,"baseline mismatch"):
                load(root,entry,{},1024)
            path.write_text("changed",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"file changed"):
                load(root,entry,base,1024)
            path.write_text("<project/>",encoding="utf-8")
            (pack/"control.json").write_text("{}",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Unreviewed"):
                load(root,entry,base,1024)

    @unittest.skipUnless(shutil.which("ssh-keygen"),"OpenSSH required for signed approval mode")
    def test_signed_review_is_scoped_to_workspace_gate_rationale_and_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            key=root/"ephemeral"
            subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True,capture_output=True)
            stores=[control.Store(root/x) for x in ("one","two")]
            try:
                for store in stores:
                    reviewer.enroll(store,"fixture",key.with_suffix(".pub").read_text())
                    control.create(store,"demo",dict(project="links",kind="greenfield",request="Create a short link",criteria=["Return 201"]))
                    s=control.resume(store,"demo")
                s=stores[0].load("demo")
                reason="Synthetic unit test"
                payload=root/"message"
                payload.write_bytes(reviewer.payload(stores[0],s,"approve",reason))
                subprocess.run(["ssh-keygen","-Y","sign","-f",str(key),"-n",reviewer.NAMESPACE,str(payload)],check=True,capture_output=True)
                sig=payload.with_suffix(".sig").read_bytes()
                for store,why,reject,signature in [(stores[0],reason,False,None),(stores[0],"Different reason",False,sig),
                                                    (stores[0],reason,True,sig),(stores[1],reason,False,sig)]:
                    with self.assertRaises(ValueError):
                        control.approve(store,"demo",s["digest"],why,reject=reject,signature=signature)
                accepted=control.approve(stores[0],"demo",s["digest"],reason,signature=sig)
                proof=stores[0].get(accepted["done"]["requirements_approval"])
                self.assertEqual("ssh:fixture",proof["actor"])
                self.assertEqual(sig.decode(),stores[0].get(proof["signed_decision"])["signature"])
            finally:
                for store in stores:
                    store.db.close()
