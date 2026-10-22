import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculate} from '../site/core.js';

const dataset={coverage:'collected-wikidata',as_of:'2026-10-23',institutions:['x','y','catalog'].map(id=>({id,kind:'university'})),people:[{
  id:'wd:Q10',wikidata:'Q10',status:'source_verified',checked_at:'2026-10-23',source_url:'https://www.wikidata.org/wiki/Q10',
  education:[{institution:'x',level:'phd'}],appointments:[{institution:'y',role:'faculty',current:null,observed:true}],awards:[]
}]};
test('source-cited historical employment is observed without inventing current status',()=>{
  const result=calculate(dataset);
  assert.equal(result.edges.length,1);
  assert.deepEqual(result.rows.map(r=>r.id).sort(),['x','y']);
  assert.ok(result.edges[0].evidence[0].sources.every(u=>u.startsWith('https://www.wikidata.org/wiki/Q10#')));
  assert.equal(calculate(dataset,{appointment_scope:'current'}).rows.length,0);
});
test('unknown degree and unsupported catalogs never pad a Top 100',()=>{
  const data=structuredClone(dataset);data.people[0].education[0].level='unknown';
  assert.equal(calculate(data).rows.length,0);
});
test('a tiny current-company sample does not consume the entire five-percent channel',()=>{
  const data=structuredClone(dataset);data.institutions.push({id:'google',kind:'company'});
  data.people[0].appointments.push({institution:'google',role:'industry',current:true});
  const r=calculate(data);
  assert.equal(r.signal_counts.current_company_people,1);
  assert.equal(r.effective_mix.industry,.05/1000);
  assert.ok(Math.abs(r.rows.reduce((s,r)=>s+r.score,0)-1)<1e-10);
});
