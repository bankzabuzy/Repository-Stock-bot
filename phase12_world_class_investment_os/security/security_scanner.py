from pathlib import Path

class SecurityScanner:
    DANGEROUS = ["eval(", "exec(", "os.system(", "subprocess.call(", "rm -rf", "pickle.loads("]

    def scan_text(self, text):
        return [p for p in self.DANGEROUS if p in text]

    def scan_path(self, root):
        hits = []
        for f in Path(root).rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for p in self.scan_text(text):
                hits.append({"file": str(f), "pattern": p})
        return hits
