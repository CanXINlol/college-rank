"""Rebuild the small, explicitly curated launch dataset. Not a global census."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
institutions = []


def school(id, name, en, country, code, short, url, kind="university", qid=None):
    institutions.append(dict(id=id, name=name, en=en, country=country, code=code, short=short,
                             url=url, kind=kind, wikidata=qid))


school("stanford", "斯坦福大学", "Stanford University", "美国", "US", "SU", "https://www.stanford.edu", qid="Q41506")
school("berkeley", "加州大学伯克利分校", "University of California, Berkeley", "美国", "US", "CAL", "https://www.berkeley.edu", qid="Q168756")
school("mit", "麻省理工学院", "Massachusetts Institute of Technology", "美国", "US", "MIT", "https://www.mit.edu", qid="Q49108")
school("princeton", "普林斯顿大学", "Princeton University", "美国", "US", "PU", "https://www.princeton.edu", qid="Q21578")
school("caltech", "加州理工学院", "California Institute of Technology", "美国", "US", "CIT", "https://www.caltech.edu", qid="Q161562")
school("toronto", "多伦多大学", "University of Toronto", "加拿大", "CA", "UT", "https://www.utoronto.ca", qid="Q180865")
school("edinburgh", "爱丁堡大学", "University of Edinburgh", "英国", "GB", "ED", "https://www.ed.ac.uk", qid="Q160302")
school("cambridge", "剑桥大学", "University of Cambridge", "英国", "GB", "CAM", "https://www.cam.ac.uk", qid="Q35794")
school("ucla", "加州大学洛杉矶分校", "University of California, Los Angeles", "美国", "US", "LA", "https://www.ucla.edu", qid="Q181644")
school("flinders", "弗林德斯大学", "Flinders University", "澳大利亚", "AU", "FL", "https://www.flinders.edu.au", qid="Q1536791")
school("cmu", "卡内基梅隆大学", "Carnegie Mellon University", "美国", "US", "CMU", "https://www.cmu.edu", qid="Q132796")
school("ucsd", "加州大学圣迭戈分校", "University of California, San Diego", "美国", "US", "SD", "https://ucsd.edu", qid="Q622664")
school("asu", "亚利桑那州立大学", "Arizona State University", "美国", "US", "ASU", "https://www.asu.edu", qid="Q670897")
school("lsu", "路易斯安那州立大学", "Louisiana State University", "美国", "US", "LSU", "https://www.lsu.edu", qid="Q716177")
school("cornell", "康奈尔大学", "Cornell University", "美国", "US", "CU", "https://www.cornell.edu", qid="Q49115")
school("iowa", "爱荷华大学", "University of Iowa", "美国", "US", "IOWA", "https://uiowa.edu", qid="Q182973")
school("columbia", "哥伦比亚大学", "Columbia University", "美国", "US", "CU", "https://www.columbia.edu", qid="Q49088")
school("tsinghua", "清华大学", "Tsinghua University", "中国", "CN", "THU", "https://www.tsinghua.edu.cn", qid="Q169959")
school("harvard", "哈佛大学", "Harvard University", "美国", "US", "HU", "https://www.harvard.edu", qid="Q13371")
school("uiuc", "伊利诺伊大学厄巴纳香槟分校", "University of Illinois Urbana-Champaign", "美国", "US", "ILL", "https://illinois.edu", qid="Q457281")
school("epfl", "洛桑联邦理工学院", "École polytechnique fédérale de Lausanne", "瑞士", "CH", "EPFL", "https://www.epfl.ch", qid="Q262760")
school("eth", "苏黎世联邦理工学院", "ETH Zürich", "瑞士", "CH", "ETH", "https://ethz.ch", qid="Q11942")
school("oxford", "牛津大学", "University of Oxford", "英国", "GB", "OX", "https://www.ox.ac.uk", qid="Q34433")
school("hebrew", "耶路撒冷希伯来大学", "Hebrew University of Jerusalem", "以色列", "IL", "HUJI", "https://en.huji.ac.il", qid="Q174570")
school("insitro", "insitro", "insitro", "美国", "US", "INS", "https://www.insitro.com", "company")
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

data = dict(version="0.1.0", as_of="2026-10-22", coverage="curated-pilot",
            note="人工核验的小型方法验证数据集，主要覆盖计算机与数学；不代表全球大学真实名次。学位年份缺失时不推断。",
            institutions=institutions, people=people, milestones=[])
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data/curated.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
print(f"Created {len(people)} reviewed people, {len(institutions)} institutions")
