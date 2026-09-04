"""Create a deterministic, self-contained HTML-reader release ZIP."""
from pathlib import Path
import hashlib, json, zipfile

ROOT=Path(__file__).resolve().parents[1]; READER=ROOT/"output/html-en"; RELEASE=ROOT/"release/v1.0.0"
NAME="openstax-elementary-algebra-2e-original-en-html-v1.0.0.zip"; PREFIX="openstax-elementary-algebra-2e-original-en-html/"
def sha(b):return hashlib.sha256(b).hexdigest()
def stable(v):return (json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
def immutable(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert path.read_bytes()==data,f"Refusing to replace different bytes: {path}"
    else:path.write_bytes(data)
def main():
    manifest=json.loads((READER/"volume.manifest.json").read_bytes())
    facts={r["path"]:(r["bytes"],r["sha256"]) for r in manifest["outputs"]["files_excluding_manifest"]}
    vm=(READER/"volume.manifest.json").read_bytes();facts["volume.manifest.json"]=(len(vm),sha(vm))
    actual={p.relative_to(READER).as_posix():p for p in READER.rglob("*") if p.is_file()}
    assert set(actual)==set(facts)==set(facts)
    for name,path in actual.items():
        b=path.read_bytes();assert (len(b),sha(b))==facts[name],name
    RELEASE.mkdir(parents=True,exist_ok=True);target=RELEASE/NAME
    if not target.exists():
        with zipfile.ZipFile(target,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,path in sorted(actual.items()):
                info=zipfile.ZipInfo(PREFIX+name,(2026,9,4,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                z.writestr(info,path.read_bytes())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(actual) and len(z.namelist())==len(set(z.namelist()))
        for name,path in actual.items():assert z.read(PREFIX+name)==path.read_bytes(),name
    zb=target.read_bytes();receipt={"schema":"openstax-original-reader-release/1","version":"1.0.0","source_revision":"38cae454e644abf9f0a623e876994553881597c9","reader":{"files":len(actual),"bytes":sum(p.stat().st_size for p in actual.values()),"manifest_sha256":facts["volume.manifest.json"][1]},"archive":{"name":NAME,"bytes":len(zb),"sha256":sha(zb),"entries":len(actual),"root":PREFIX},"entry_bytes_exact":True,"zip_crc_pass":True,"offline_scope":"book text, MathML, CSS and images included; external hyperlinks and publisher services require internet"}
    rb=stable(receipt);immutable(RELEASE/"RELEASE_RECEIPT.json",rb)
    print(json.dumps(receipt,sort_keys=True));print(f"Receipt {len(rb)} bytes SHA-256 {sha(rb)}")
if __name__=="__main__":main()
