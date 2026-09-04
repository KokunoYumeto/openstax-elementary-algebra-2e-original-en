"""Independent semantic/readback validator for the original-English reader."""
from __future__ import annotations

import csv, hashlib, io, json, re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit
from lxml import etree, html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/html-en"
CN = "http://cnx.rice.edu/cnxml"; MD = "http://cnx.rice.edu/mdml"; MATH = "http://www.w3.org/1998/Math/MathML"
ORIGINAL = "https://openstax.org/details/books/elementary-algebra-2e"
PROGRAM = "https://kokunoyumeto.github.io/program-matematika-indonesia/en/"

def sha(data): return hashlib.sha256(data).hexdigest()
def stable(value): return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+"\n").encode()
def confined(base, raw):
    parts=urlsplit(raw)
    if parts.scheme or parts.netloc or raw.startswith("//"): return None
    candidate=(base/unquote(parts.path)).resolve()
    try: candidate.relative_to(OUT.resolve())
    except ValueError: return False
    return candidate
def math_signature(node):
    def sig(x):
        q=etree.QName(x); attrs=[]
        for k,v in x.attrib.items():
            aq=etree.QName(k); attrs.append((aq.namespace or "",aq.localname,v))
        return (q.namespace or "",q.localname,tuple(sorted(attrs)),x.text or "",tuple((sig(c),c.tail or "") for c in x))
    return sig(node)
def serialized_math_signatures(data):
    fragments=re.findall(rb"<math(?=[\s>]).*?</math>",data,re.DOTALL)
    return [math_signature(etree.fromstring(fragment,etree.XMLParser(resolve_entities=False,no_network=True))) for fragment in fragments]
def normalized_text(node): return " ".join("".join(node.itertext()).split())
def remove_element_preserve_tail(node):
    parent=node.getparent(); tail=node.tail or ""; previous=node.getprevious()
    if previous is not None: previous.tail=(previous.tail or "")+tail
    else: parent.text=(parent.text or "")+tail
    parent.remove(node)
def source_visible_text(root):
    parts=[]
    def walk(node, allowed=True):
        q=etree.QName(node)
        if q.namespace==CN and q.localname=="metadata":
            for child in node:
                if etree.QName(child).namespace==MD and etree.QName(child).localname=="abstract": walk(child)
            return
        if allowed and node.text: parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail: parts.append(child.tail)
    walk(root)
    return " ".join("".join(parts).split())

def main():
    manifest_bytes=(OUT/"volume.manifest.json").read_bytes(); manifest=json.loads(manifest_bytes)
    assert manifest["schema"]=="openstax-deterministic-semantic-html-reader" and manifest["schema_version"]=="1.1.0"
    declared={r["path"]:(r["bytes"],r["sha256"]) for r in manifest["outputs"]["files_excluding_manifest"]}
    actual={p.relative_to(OUT).as_posix():p for p in OUT.rglob("*") if p.is_file() and p.name!="volume.manifest.json"}
    assert set(actual)==set(declared) and len(actual)==4107
    for name,path in actual.items():
        data=path.read_bytes(); assert (len(data),sha(data))==declared[name],name

    sources=list(csv.DictReader((ROOT/"authority/source-manifest.tsv").read_text(encoding="utf-8").splitlines(),delimiter="\t"))
    source_ids=[]; source_roots={}; titles={}
    for row in sources:
        mid=row["module"]; raw=(ROOT/"modules"/mid/"index.cnxml").read_bytes()
        assert len(raw)==int(row["bytes"]) and sha(raw)==row["sha256"]
        tree=etree.fromstring(raw,etree.XMLParser(resolve_entities=False,no_network=True,remove_comments=True,remove_pis=True,huge_tree=True)); source_roots[mid]=tree
        titles[mid]=" ".join("".join(tree.find(f"{{{CN}}}title").itertext()).split())
        source_ids.append(mid)
    assert source_ids==manifest["collection"]["ordered_module_ids"] and len(source_ids)==82
    labels={}
    for mid,root in source_roots.items():
        count=Counter()
        for n in root.iter():
            tag=etree.QName(n).localname
            if tag in {"example","exercise","figure","note","table"}:
                count[tag]+=1
                if n.get("id"): labels[(mid,n.get("id"))]=f"{tag.title()} {count[tag]}"

    html_files=[OUT/"index.html",OUT/"print.html",*[OUT/"modules"/mid/"index.html" for mid in source_ids]]
    parsed={p:html.fromstring(p.read_bytes(),parser=html.HTMLParser(encoding="utf-8",recover=True)) for p in html_files}
    ids={p:set(doc.xpath("//*[@id]/@id")) for p,doc in parsed.items()}
    unresolved=[]; external=Counter(); paired=[]; forbidden=[]
    for path,doc in parsed.items():
        actions=doc.xpath("//nav[@class='paired-access']/a")
        paired.append((path.relative_to(OUT).as_posix(),[(a.get("href"),a.get("hreflang"),normalized_text(a)) for a in actions]))
        assert doc.get("lang")=="en" and sum(a.get("href")==ORIGINAL for a in actions)==1 and sum(a.get("href")==PROGRAM for a in actions)==1
        forbidden.extend((path.relative_to(OUT).as_posix(),etree.QName(x).localname) for x in doc.xpath("//script|//iframe|//object|//embed"))
        for node,attribute in [(n,"href") for n in doc.xpath("//a[@href]")]+[(n,"src") for n in doc.xpath("//img[@src]")]+[(n,"href") for n in doc.xpath("//link[@rel='stylesheet']")]:
            raw=node.get(attribute); parts=urlsplit(raw)
            if parts.scheme in {"http","https","mailto","tel"} or raw.startswith("//"):
                external[parts.netloc or parts.scheme]+=1; continue
            target=path if not parts.path else confined(path.parent,raw)
            if target is False or target is None: unresolved.append((str(path),raw)); continue
            if target.is_dir():target=target/"index.html"
            if attribute=="href" and etree.QName(node).localname=="a":
                if target not in parsed or parts.fragment and unquote(parts.fragment) not in ids[target]:unresolved.append((str(path),raw))
            elif not target.is_file():unresolved.append((str(path),raw))
    assert not unresolved and not forbidden
    print_doc=parsed[OUT/"print.html"]
    assert len(print_doc.xpath("//section[@class='print-front']/nav[@class='paired-access'][following-sibling::h2]"))==1

    xref_total=0; source_counts=Counter(); output_counts=Counter(); source_lists=Counter(); output_lists=Counter()
    for mid,source in source_roots.items():
        page=parsed[OUT/"modules"/mid/"index.html"]
        article=page.xpath("//article[@data-module-id=$m]",m=mid)[0]
        native=[x.get("id") for x in source.iter() if x.get("id")]
        assert article.xpath(".//*[@id]/@id")==native
        source_math=[math_signature(x) for x in source.iter() if etree.QName(x).namespace==MATH and etree.QName(x).localname=="math"]
        output_math=serialized_math_signatures((OUT/"modules"/mid/"index.html").read_bytes())
        assert source_math==output_math,mid
        expected=[]
        for link in source.iter(f"{{{CN}}}link"):
            if "".join(link.itertext()).strip():continue
            target_module=link.get("document") or mid; target_id=link.get("target-id")
            text=labels[(target_module,target_id)]+(f" in {titles[target_module]}" if target_module!=mid else "")
            expected.append(text)
        observed=[normalized_text(x) for x in article.xpath(".//a[@data-generated-cross-reference-label='true']")]
        assert observed==expected and all(observed),(mid,observed,expected); xref_total+=len(observed)
        prose=deepcopy(article)
        for generated in prose.xpath(".//aside[contains(concat(' ',normalize-space(@class),' '),' module-abstract ')]/h2[normalize-space(.)='Learning Objectives'] | .//details/summary[normalize-space(.)='Solution']"):
            remove_element_preserve_tail(generated)
        for generated in prose.xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' sr-only ')]"):
            remove_element_preserve_tail(generated)
        for generated in prose.xpath(".//a[@data-generated-cross-reference-label='true']"):
            generated.text=""
        assert re.sub(r"\s+", "", normalized_text(prose))==re.sub(r"\s+", "", source_visible_text(source)),f"Visible prose mismatch: {mid}"
        for x in source.iter(): source_counts[etree.QName(x).localname]+=1
        for x in article.iter(): output_counts[(x.get("class") or "").split()[0] if (x.get("class") or "") else etree.QName(x).localname]+=1
        for x in source.iter(f"{{{CN}}}list"):
            source_lists[(x.get("number-style") or None,x.get("list-type") or None,x.get("bullet-style") or None,"circled" in (x.get("class") or ""))]+=1
        for x in article.xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' cnxml-list ')]"):
            output_lists[(x.get("data-number-style"),x.get("data-list-type"),x.get("data-bullet-style"),bool({'source-circled','source--circled'}&set(x.get('class','').split())))]+=1
    assert xref_total==455 and source_lists==output_lists
    for source_tag,output_class in {"exercise":"cnxml-exercise","figure":"cnxml-figure","list":"cnxml-list","media":"cnxml-media","problem":"cnxml-problem","solution":"cnxml-solution","table":"cnxml-table"}.items():
        assert source_counts[source_tag]==output_counts[output_class],source_tag
    css=(OUT/"reader-id.css").read_bytes()
    for token in [b'[data-number-style="lower-alpha"]',b'list-style-type: lower-alpha',b'.cnxml-list.source-circled',b'list-style-type: none']:
        assert token in css
    credits=json.loads((OUT/"metadata/original-component-credits.json").read_bytes())["components"]
    assert len(credits)==2
    for row in credits:
        captions=[" ".join("".join(x.itertext()).split()) for x in source_roots[row["module_id"]].iter(f"{{{CN}}}caption")]
        assert " ".join(row["source_caption_text"].split()) in captions
    provenance=json.loads((OUT/"metadata/source-provenance.json").read_bytes())
    assert provenance["original_website"]==ORIGINAL and provenance["native_source_bytes_unchanged"] is True
    assert provenance["offline"]["javascript_required"] is False and (OUT/"LICENSE.txt").read_bytes()==(ROOT/"LICENSE").read_bytes()
    receipt={"schema":"openstax-original-reader-independent-validation/1","status":"pass",
      "output":{"files":len(actual)+1,"bytes":sum(p.stat().st_size for p in actual.values())+len(manifest_bytes),"manifest_bytes":len(manifest_bytes),"manifest_sha256":sha(manifest_bytes),"output_inventory_sha256_excluding_manifest":manifest["outputs"]["inventory_stream_sha256"]},
      "source":{"modules":82,"bytes":sum(int(r["bytes"]) for r in sources),"native_ids":sum(len([x for x in root.iter() if x.get("id")]) for root in source_roots.values())},
      "content":{"mathml":sum(len(root.xpath("//*[local-name()='math']")) for root in source_roots.values()),"generated_cross_references":xref_total,"lists":sum(source_lists.values()),"component_credits":len(credits)},
      "access":{"paired_pages":len(paired),"original_website":ORIGINAL,"program_website":PROGRAM,"unresolved_local_references":0,"remote_rendering_dependencies":0,"external_hyperlinks_not_network_checked":sum(external.values())},
      "checks":["exact output inventory bytes and hashes","source manifest and order","native ID order","independent normalized visible-prose equality","semantic element counts","MathML expanded-name/attribute/text signatures","generated cross-reference labels and destinations","list presentation contract","paired access on every page","original component credits and license","local resource closure and no remote rendering runtime"],
      "limitations":["No browser visual or assistive-technology certification","External hyperlinks not network checked","Independent prose comparison normalizes whitespace; builder separately preserves every exact source text-slot byte signature"],
    }
    data=stable(receipt); path=ROOT/"INDEPENDENT_READER_VALIDATION_V2.json"
    if path.exists():assert path.read_bytes()==data
    else:path.write_bytes(data)
    print(json.dumps(receipt,ensure_ascii=False,sort_keys=True));print(f"Receipt {len(data)} bytes SHA-256 {sha(data)}")
if __name__=="__main__":main()

