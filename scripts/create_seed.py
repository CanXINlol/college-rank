"""Rebuild the small, explicitly curated launch dataset. Not a global census."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Institution identities are independently checked against the ROR registry.
institutions = json.loads((ROOT / "data/institutions.json").read_text())
institutions.append(dict(id="insitro",name="insitro",en="insitro",country="美国",code="US",
                         short="INS",url="https://www.insitro.com",kind="company",wikidata=None))
people = []


def person(id, name, field, edu, employer, role, source, extra=(), awards=(), jobs=()):
    sources = [source, *extra]
    people.append(dict(id=id, name=name, field=field, status="reviewed", checked_at="2026-10-22",
        education=[dict(institution=i, level=l, sources=sources) for i,l in edu],
        appointments=[dict(institution=employer, role=role, current=True, sources=sources), *jobs],
        awards=[dict(type=t, year=y, sources=[s]) for t,y,s in awards]))


person("fei-fei-li", "Fei-Fei Li · 李飞飞", "计算机科学", [("princeton","bachelor"),("caltech","master"),("caltech","phd")], "stanford", "faculty",
       "https://profiles.stanford.edu/fei-fei-li", ["https://www.alumni.caltech.edu/fei-fei-li/"])
person("geoffrey-hinton", "Geoffrey Hinton", "计算机科学", [("cambridge","bachelor"),("edinburgh","phd")], "toronto", "emeritus",
       "https://www.cs.toronto.edu/~hinton/shortcv.pdf", awards=[
       ("turing",2018,"https://awards.acm.org/about/2018-turing"),
       ("nobel",2024,"https://www.nobelprize.org/prizes/physics/2024/hinton/facts/")])
person("terence-tao", "Terence Tao · 陶哲轩", "数学", [("flinders","bachelor"),("flinders","master"),("princeton","phd")], "ucla", "faculty",
       "https://www.math.ucla.edu/~tao/cv.html", awards=[("fields",2006,"https://www.mathunion.org/imu-awards/fields-medal/fields-medals-2006")])
person("andrew-ng", "Andrew Ng · 吴恩达", "计算机科学", [("cmu","bachelor"),("mit","master"),("berkeley","phd")], "stanford", "adjunct",
       "https://symsys.stanford.edu/people/andrew-ng", ["https://rail.eecs.berkeley.edu/deeprlcourse-fa17/docs/ng-thesis.pdf"])
person("michael-jordan", "Michael I. Jordan", "计算机科学", [("lsu","bachelor"),("asu","master"),("ucsd","phd")], "berkeley", "emeritus",
       "https://www2.eecs.berkeley.edu/Faculty/Homepages/jordan.html")
person("sanjeev-arora", "Sanjeev Arora", "计算机科学", [("mit","bachelor"),("berkeley","phd")], "princeton", "faculty",
       "https://profsanjeevarora.github.io/bio.html", ["https://engineering.princeton.edu/faculty/sanjeev-arora"])
person("daniela-rus", "Daniela Rus", "计算机科学", [("iowa","bachelor"),("cornell","phd")], "mit", "faculty",
       "https://www.csail.mit.edu/person/daniela-rus", ["https://cap.csail.mit.edu/daniela-rus-roboticist-csail-lab-director"])
person("regina-barzilay", "Regina Barzilay", "计算机科学", [("columbia","phd"),("cornell","postdoc")], "mit", "faculty",
       "https://imes.mit.edu/people/barzilay-regina")
person("andrew-yao", "Andrew Yao · 姚期智", "计算机科学", [("harvard","phd"),("uiuc","phd")], "tsinghua", "faculty",
       "https://iiis.tsinghua.edu.cn/en/People/Faculty/yaoqizhi.htm", awards=[
       ("turing",2000,"https://aiig.tsinghua.edu.cn/en/info/1013/1091.htm")])
person("martin-odersky", "Martin Odersky", "计算机科学", [("eth","phd")], "epfl", "faculty",
       "https://people.epfl.ch/martin.odersky?lang=en")
person("stuart-russell", "Stuart Russell", "计算机科学", [("oxford","bachelor"),("stanford","phd")], "berkeley", "faculty",
       "https://www2.eecs.berkeley.edu/Faculty/Homepages/russell.html")
person("daphne-koller", "Daphne Koller", "计算机科学", [("hebrew","bachelor"),("hebrew","master"),("stanford","phd")], "insitro", "industry",
       "https://med.stanford.edu/minorconsult/daphne-koller.html")

data = dict(version="0.1.0", as_of="2026-10-23", coverage="curated-pilot",
            note="已收录 100 所经 ROR 匹配的大学与 12 位已核验人才。新增 76 所目前仅有机构信息，尚待补充人才履历；基础 PageRank 与并列名次不代表真实学术影响力。学位年份缺失时不推断。",
            institutions=institutions, people=people, milestones=[])
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data/curated.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
print(f"Created {len(people)} reviewed people, {len(institutions)} institutions")
