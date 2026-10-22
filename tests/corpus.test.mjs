import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {calculate} from '../site/core.js';

test('published full corpus matches the Python ranking and retains real source shards',{skip:!existsSync('site/data.json.gz')},()=>{
  const data=JSON.parse(gunzipSync(readFileSync('site/data.json.gz')));
  if(data.coverage!=='collected-wikidata')return;
  const python=JSON.parse(readFileSync('site/ranking.json','utf8'));
  const js=calculate(data);
  assert.ok(js.rows.length>=100);
  assert.equal(js.edges.length,python.edges.length);
  assert.deepEqual(js.rows.map(r=>r.id),python.rows.map(r=>r.id));
  for(let i=0;i<js.rows.length;i++)for(const key of ['score','pagerank','award_score','industry_score','alumni','staff','profile_count','rank'])
    assert.ok(Math.abs(js.rows[i][key]-python.rows[i][key])<1e-10,`${js.rows[i].id}/${key}`);
  assert.ok(Math.abs(js.rows.reduce((s,r)=>s+r.score,0)-1)<1e-9);
  assert.ok(js.rows.slice(0,100).every(r=>r.alumni||r.staff||r.award_score||r.industry_score));
  for(const compact of [data.people[0],data.people[Math.floor(data.people.length/2)],data.people.at(-1)]){
    const shard=JSON.parse(gunzipSync(readFileSync(`site/profiles/${compact.profile_shard}.json.gz`)));
    const person=shard[compact.id];assert.ok(person);
    for(const item of [...person.education,...person.appointments,...person.awards])
      assert.ok(item.sources?.length&&item.sources.every(s=>s.startsWith('https://')));
  }
});
