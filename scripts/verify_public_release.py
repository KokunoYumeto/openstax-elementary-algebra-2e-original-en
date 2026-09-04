"""Anonymous, bounded public-byte verification for source, release, and Pages."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import hashlib,json,subprocess,tempfile,time,zipfile
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"output/html-en";REPO="KokunoYumeto/openstax-elementary-algebra-2e-original-en"
COMMIT="b56ead2d7114356a03a46cb64ffb8f592eb07dcd";TAG="v1.0.0"
PAGES_COMMIT=COMMIT;RUN=33911671836
PAGES="https://kokunoyumeto.github.io/openstax-elementary-algebra-2e-original-en/"
UA={"User-Agent":"anonymous-original-reader-verifier/1"};SESSION=requests.Session();SESSION.headers.update(UA)
def sha(b):return hashlib.sha256(b).hexdigest()
def stable(v):return (json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
def get(url,stream=False):
    last=None
    for delay in (0,1,3):
        if delay:time.sleep(delay)
        try:
            r=SESSION.get(url,timeout=(15,90),stream=stream);r.raise_for_status();return r
        except requests.RequestException as exc:last=exc
    raise last
def main():
    repo=get(f"https://api.github.com/repos/{REPO}").json();assert repo["private"] is False and repo["default_branch"]=="main"
    release=get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}").json();assert release["draft"] is False and release["prerelease"] is False
    tag_ref=get(f"https://api.github.com/repos/{REPO}/git/ref/tags/{TAG}").json();assert tag_ref["object"]["type"]=="commit" and tag_ref["object"]["sha"]==COMMIT
    expected_assets={
      "openstax-elementary-algebra-2e-original-en-html-v1.0.0.zip":ROOT/"release/v1.0.0/openstax-elementary-algebra-2e-original-en-html-v1.0.0.zip",
      "RELEASE_RECEIPT.json":ROOT/"release/v1.0.0/RELEASE_RECEIPT.json",
      "INDEPENDENT_READER_VALIDATION_V2.json":ROOT/"INDEPENDENT_READER_VALIDATION_V2.json",
      "ISOLATED_READER_REPLAY.json":ROOT/"ISOLATED_READER_REPLAY.json"}
    assert {x["name"] for x in release["assets"]}==set(expected_assets)
    asset_facts=[]
    for remote in release["assets"]:
        expected=expected_assets[remote["name"]].read_bytes();public=get(remote["browser_download_url"]).content
        assert public==expected and remote["size"]==len(expected)
        asset_facts.append({"name":remote["name"],"url":remote["browser_download_url"],"bytes":len(public),"sha256":sha(public)})

    # Compare the public codeload archive directly to exact Git blob bytes.  Do
    # not use ``git archive`` here: archive filters and newline attributes can
    # transform an otherwise exact committed blob during local ZIP creation.
    with tempfile.TemporaryDirectory(prefix="a10-public-source-") as d:
        d=Path(d);remote=d/"remote.zip"
        with get(f"https://codeload.github.com/{REPO}/zip/{COMMIT}",stream=True) as response,remote.open("wb") as stream:
            for chunk in response.iter_content(1024*1024):stream.write(chunk)
        tree_raw=subprocess.run(
            ["git","ls-tree","-r","-z","--full-tree",COMMIT],cwd=ROOT,
            check=True,capture_output=True).stdout
        tree={}
        for entry in tree_raw.split(b"\0"):
            if not entry:continue
            header,path=entry.split(b"\t",1);mode,kind,object_id=header.split(b" ")
            assert kind==b"blob"
            tree[path.decode("utf-8")]=object_id.decode("ascii")
        with zipfile.ZipFile(remote) as right:
            assert right.testzip() is None
            prefix=right.namelist()[0].split("/",1)[0]+"/"
            rnames={x[len(prefix):] for x in right.namelist() if x.startswith(prefix) and not x.endswith("/")}
            assert set(tree)==rnames
            reader=subprocess.Popen(
                ["git","cat-file","--batch"],cwd=ROOT,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert reader.stdin is not None and reader.stdout is not None
            try:
                for name in sorted(tree):
                    object_id=tree[name]
                    reader.stdin.write((object_id+"\n").encode("ascii"));reader.stdin.flush()
                    header=reader.stdout.readline().decode("ascii").strip().split()
                    assert header==[object_id,"blob",header[2]] and header[2].isdigit(),name
                    size=int(header[2]);blob=reader.stdout.read(size);separator=reader.stdout.read(1)
                    assert len(blob)==size and separator==b"\n",name
                    assert blob==right.read(prefix+name),name
            finally:
                reader.stdin.close();return_code=reader.wait(timeout=30)
                stderr=reader.stderr.read() if reader.stderr is not None else b""
            assert return_code==0,stderr.decode("utf-8",errors="replace")
        codeload={"url":f"https://codeload.github.com/{REPO}/zip/{COMMIT}","bytes":remote.stat().st_size,"sha256":sha(remote.read_bytes()),"files":len(tree),"all_bytes_equal_exact_git_blobs":True}

    manifest=json.loads((OUT/"volume.manifest.json").read_bytes());expected={r["path"]:(r["bytes"],r["sha256"]) for r in manifest["outputs"]["files_excluding_manifest"]}
    vm=(OUT/"volume.manifest.json").read_bytes();expected["volume.manifest.json"]=(len(vm),sha(vm))
    def verify_page(item):
        name,(size,digest)=item;data=get(PAGES+quote(name,safe="/")).content
        assert len(data)==size and sha(data)==digest,name
        return {"path":name,"url":PAGES+quote(name,safe="/"),"bytes":len(data),"sha256":sha(data)}
    pages=[]
    with ThreadPoolExecutor(max_workers=6) as executor:
        for i,fact in enumerate(executor.map(verify_page,sorted(expected.items())),1):
            pages.append(fact)
            if i%250==0:print(f"Anonymous Pages readback {i}/{len(expected)}",flush=True)
    workflow=get(f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}").json()
    assert workflow["status"]=="completed" and workflow["conclusion"]=="success" and workflow["head_sha"]==PAGES_COMMIT
    receipt={"schema":"openstax-original-reader-publication/1","status":"published_and_anonymously_verified","repository":{"url":repo["html_url"],"public":True,"release_commit":COMMIT,"pages_workflow_commit":PAGES_COMMIT,"tag":TAG,"codeload":codeload},"github_release":{"url":release["html_url"],"assets":asset_facts},"pages":{"url":PAGES,"workflow_run":RUN,"workflow_attempt":1,"deployment_source":"byte-exact_release_zip","files":pages,"file_count":len(pages),"bytes":sum(x["bytes"] for x in pages),"all_exact":True},"source_revision":"38cae454e644abf9f0a623e876994553881597c9","original_publisher":"https://openstax.org/details/books/elementary-algebra-2e","indonesian_edition":"https://doi.org/10.5281/zenodo.22236314","public_access":"open","browser_visual_qa_claimed":False,"credentials_recorded":False}
    data=stable(receipt);path=ROOT/"PUBLICATION_RECEIPT.json"
    if path.exists():assert path.read_bytes()==data
    else:path.write_bytes(data)
    print(json.dumps({"status":receipt["status"],"pages_files":len(pages),"pages_bytes":receipt["pages"]["bytes"],"release_assets":len(asset_facts),"source_files":codeload["files"]},sort_keys=True));print(f"Receipt {len(data)} bytes SHA-256 {sha(data)}")
if __name__=="__main__":main()
