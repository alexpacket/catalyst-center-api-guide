"""Rebuild index.html and package the offline companion kit: python3 src/build_kit.py (run from the repository root)."""
import os, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
subprocess.run([sys.executable, os.path.join(ROOT, "src", "gen.py"), os.path.join(ROOT, "index.html")], check=True)
OUT, TOP = os.path.join(ROOT, "catalyst-center-api-kit.zip"), "catalyst-center-api-kit"
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(ROOT, "index.html"), f"{TOP}/index.html")
    for f in ("favicon.svg", "favicon.png"):
        z.write(os.path.join(ROOT, f), f"{TOP}/{f}")
    for base, arc in (("kit", ""), ("src", "src/")):
        for d, _, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in d:
                continue
            for f in sorted(files):
                if f.endswith(".pyc"):
                    continue
                p = os.path.join(d, f)
                info = zipfile.ZipInfo.from_file(p, f"{TOP}/{arc}{os.path.relpath(p, os.path.join(ROOT, base))}")
                if f.endswith((".sh", ".py")):
                    info.external_attr = 0o100755 << 16
                with open(p, "rb") as fh:
                    z.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
print(OUT, os.path.getsize(OUT))
