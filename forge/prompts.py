"""The AI's own instructions, stored as editable .md files with a version history.

Self-improvement may rewrite these; every replaced version is kept in
prompts/history/<name>/ and can be restored from the UI.
The judge prompt is deliberately NOT self-improved: if the system could rewrite
the thing that grades it, it would learn to flatter itself.
"""
import os
from datetime import datetime

from .common import PROMPTS

FROZEN = {"judge", "judge_pair"}


class Prompts:
    def get(self, name):
        with open(os.path.join(PROMPTS, name + ".md")) as f:
            return f.read().strip()

    def names(self):
        return sorted(f[:-3] for f in os.listdir(PROMPTS) if f.endswith(".md"))

    def history(self, name):
        d = os.path.join(PROMPTS, "history", name)
        return sorted(os.listdir(d), reverse=True) if os.path.isdir(d) else []

    def replace(self, name, text, reason=""):
        if name in FROZEN:
            raise ValueError("%s is frozen" % name)
        d = os.path.join(PROMPTS, "history", name)
        os.makedirs(d, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(d, stamp + ".md"), "w") as f:
            f.write(self.get(name) + "\n\n<!-- replaced %s: %s -->\n" % (stamp, reason))
        with open(os.path.join(PROMPTS, name + ".md"), "w") as f:
            f.write(text.strip() + "\n")

    def rollback(self, name, version):
        path = os.path.join(PROMPTS, "history", name, os.path.basename(version))
        with open(path) as f:
            text = f.read().split("\n\n<!-- replaced")[0]
        self.replace(name, text, reason="rollback to " + version)
