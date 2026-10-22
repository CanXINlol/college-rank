// Same probability model as collegerank/rank.py; no dense N×N allocation.
export const defaults = {
  weights:{bachelor:.15,master:.25,phd:1,postdoc:.4}, damping:.85, award_mix:.1, industry_mix:.05,
  roles:['faculty','adjunct','researcher','postdoc'], self_hire:false, max_age_days:730,
  awards:{fields:1,abel:1,wolf_math:.8,nobel:1,turing:1,ieee_honor:.6,ieee_edison:.4,ieee_milestone:.2},
  companies:['google-deepmind','google','microsoft','nvidia','apple','meta','openai']
};
export function calculate(data, options={}) {
  const cfg={...structuredClone(defaults),...options,weights:{...defaults.weights,...options.weights},awards:{...defaults.awards,...options.awards}};
  if (![...Object.values(cfg.weights),...Object.values(cfg.awards)].every(v=>Number.isFinite(v)&&v>=0)) throw Error('权重必须为非负有限数');
  if (!(cfg.damping>0&&cfg.damping<1)||![cfg.award_mix,cfg.industry_mix].every(v=>Number.isFinite(v)&&v>=0&&v<=1)||cfg.award_mix+cfg.industry_mix>1) throw Error('无效的排名参数');
  const schools=data.institutions.filter(i=>i.kind!=='company'), ids=schools.map(i=>i.id).sort(), n=ids.length, valid=new Set(ids);
  const edgeMap=new Map(), award={}, industry={}, grads={}, staff={}, profiles={};
  const add=(obj,key,v)=>obj[key]=(obj[key]||0)+v;
  for (const p of data.people) {
    if(p.status!=='reviewed'||(Date.parse(data.as_of)-Date.parse(p.checked_at))/86400000>cfg.max_age_days) continue;
    for(const item of [...p.education,...p.appointments]) if(valid.has(item.institution)) (profiles[item.institution]??=new Set()).add(p.id);
    const edu=[...new Map(p.education.filter(e=>valid.has(e.institution)&&e.level in cfg.weights&&!e.honorary).map(e=>[e.institution+'|'+e.level,e])).values()];
    const jobs=[...new Map(p.appointments.filter(a=>a.current===true&&cfg.roles.includes(a.role)&&valid.has(a.institution)).map(a=>[a.institution,a])).values()];
    for(const a of jobs) (staff[a.institution]??=new Set()).add(p.id);
    for(const e of edu) for(const a of jobs) {
      if(!cfg.weights[e.level]||(!cfg.self_hire&&a.institution===e.institution)) continue;
      const key=a.institution+'|'+e.institution;
      if(!edgeMap.has(key)) edgeMap.set(key,{from:a.institution,to:e.institution,weight:0,evidence:[]});
      const edge=edgeMap.get(key), w=cfg.weights[e.level]/jobs.length;
      edge.weight+=w;edge.evidence.push({person:p.id,level:e.level,weight:w,sources:[...new Set([...e.sources,...a.sources])].sort()});
      (grads[e.institution]??=new Set()).add(p.id);
    }
    const total=edu.reduce((s,e)=>s+cfg.weights[e.level],0);
    if(total) {
      const events=new Map((p.awards||[]).filter(a=>a.type!=='ieee_milestone').map(a=>[a.type+'|'+a.year,cfg.awards[a.type]||0]));
      const wins=[...events.values()].reduce((a,b)=>a+b,0);
      const employed=p.appointments.some(a=>a.current===true&&a.role==='industry'&&cfg.companies.includes(a.institution));
      for(const e of edu){const share=cfg.weights[e.level]/total;add(award,e.institution,wins*share);add(industry,e.institution,Number(employed)*share);}
    }
  }
  for(const m of data.milestones||[]) if(m.status==='reviewed'&&m.sources?.length&&valid.has(m.institution)) add(award,m.institution,cfg.awards.ieee_milestone);
  const edges=[...edgeMap.values()].sort((a,b)=>(a.from+'|'+a.to).localeCompare(b.from+'|'+b.to)), out={}, incoming={};
  edges.forEach(e=>{add(out,e.from,e.weight);add(incoming,e.to,e.weight);});
  let scores=Object.fromEntries(ids.map(i=>[i,1/n])), iterations=0,residual=0;
  if(!n)return {rows:[],edges,config:cfg,iterations,residual};
  for(let step=0;step<1000;step++) {
    const dangling=ids.filter(i=>!out[i]).reduce((s,i)=>s+scores[i],0);
    const next=Object.fromEntries(ids.map(i=>[i,(1-cfg.damping)/n+cfg.damping*dangling/n]));
    edges.forEach(e=>next[e.to]+=cfg.damping*scores[e.from]*e.weight/out[e.from]);
    residual=ids.reduce((s,i)=>s+Math.abs(next[i]-scores[i]),0);scores=next;iterations=step+1;if(residual<1e-12)break;
  }
  const sum=o=>Object.values(o).reduce((a,b)=>a+b,0), at=sum(award),it=sum(industry), am=at?cfg.award_mix:0,im=it?cfg.industry_mix:0;
  const rows=schools.map(s=>({...s,pagerank:scores[s.id],award_score:at?(award[s.id]||0)/at:0,industry_score:it?(industry[s.id]||0)/it:0,
    alumni:grads[s.id]?.size||0,staff:staff[s.id]?.size||0,weighted_incoming:incoming[s.id]||0,profile_count:profiles[s.id]?.size||0,evidence_status:profiles[s.id]?.size?'profiles_available':'catalog_only'}));
  rows.forEach(r=>r.score=(1-am-im)*r.pagerank+am*r.award_score+im*r.industry_score);
  rows.sort((a,b)=>b.score-a.score||(a.id<b.id?-1:1));let previous=null,rank=0;rows.forEach((r,i)=>{if(previous===null||Math.abs(r.score-previous)>1e-12){rank=i+1;previous=r.score;}r.rank=rank;});
  return {rows,edges,config:cfg,iterations,residual,as_of:data.as_of,method_version:'0.1.0'};
}
