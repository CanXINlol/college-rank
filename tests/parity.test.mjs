import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {calculate} from '../site/core.js';

const data=JSON.parse(readFileSync(new URL('../data/curated.json',import.meta.url)));
const configs=[{}, {roles:['faculty','adjunct','researcher','postdoc','emeritus'],companies:['insitro'],self_hire:true},
  {weights:{bachelor:0,master:.7,phd:1.8,postdoc:.1},award_mix:.3,industry_mix:.2},
  {weights:{bachelor:0,master:0,phd:0,postdoc:0},award_mix:0,industry_mix:0}];
for(const [index,config] of configs.entries())test(`Python/browser parity, configuration ${index+1}`,()=>{
  const python=JSON.parse(execFileSync('python3',['-c',
    'import json,sys; from collegerank.rank import calculate; d=json.load(open("data/curated.json")); print(json.dumps(calculate(d,json.loads(sys.argv[1]))))',JSON.stringify(config)],{encoding:'utf8'}));
  const js=calculate(data,config);
  assert.deepEqual(js.rows.map(r=>r.id),python.rows.map(r=>r.id));
  assert.deepEqual(js.edges,python.edges);
  for(let i=0;i<js.rows.length;i++) for(const k of ['score','pagerank','award_score','industry_score','alumni','staff'])
    assert.ok(Math.abs(js.rows[i][k]-python.rows[i][k])<1e-10,`${js.rows[i].id} ${k}`);
});
