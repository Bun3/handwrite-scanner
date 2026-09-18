import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {ReportQuota} from './worker.mjs';

const payload = () => ({schema:1, report_id:crypto.randomUUID(), created_at:new Date().toISOString(),
  app_version:'0.9.0', system:{os:'Windows',release:'11',architecture:'AMD64',cpu_threads:8,ram_gb:16,disk_free_gb:10},
  model:'qwen',error_code:'unexpected',screen:'index',jobs:{error:1},events:[],contact:'',description:'synthetic test'});
const request = p => new Request('https://test/reports', {method:'POST',headers:{'content-type':'application/json','cf-connecting-ip':'192.0.2.1'},body:JSON.stringify(p)});
function environment() {
  const writes = []; let reservations = 0;
  return {writes, get reservations(){return reservations;},
    IP_LIMIT:{limit:async()=>({success:true})},
    QUOTA:{idFromName:n=>n,get:()=>({fetch:async()=>{reservations++;return new Response('ok');}})},
    REPORTS:{put:async(...args)=>writes.push(args)}};
}
test('accepted report stored once and never served publicly', async()=>{
  const env=environment(), p=payload();
  const r=await worker.fetch(request(p),env);
  assert.equal(r.status,201); assert.equal((await r.json()).receipt,p.report_id);
  assert.equal(env.writes.length,1); assert.equal(env.reservations,1);
  assert.equal((await worker.fetch(new Request('https://test/reports/'+p.report_id),env)).status,404);
});
test('oversize, malformed and unknown fields never reach quota or R2',async()=>{
  for(const p of [{...payload(),original_document:'PRIVATE'}, {...payload(),description:'x'.repeat(300000)}, {...payload(),events:[{raw:'PRIVATE'}]}]){
    const env=environment(); assert.ok((await worker.fetch(request(p),env)).status>=400);
    assert.equal(env.writes.length,0); assert.equal(env.reservations,0);
  }
});
test('rate limit, exhausted quota and broken guard fail closed',async()=>{
  for(const mode of ['rate','quota','failure']){
    const env=environment();
    if(mode==='rate')env.IP_LIMIT.limit=async()=>({success:false});
    else env.QUOTA.get=()=>({fetch:async()=>{if(mode==='failure')throw Error('down');return new Response('',{status:429});}});
    assert.ok((await worker.fetch(request(payload()),env)).status>=400);
    assert.equal(env.writes.length,0);
  }
});
test('single durable counter allows only 1000 slots across concurrent callers and restarts',async()=>{
  const values=new Map(); let tail=Promise.resolve();
  const storage={transaction: fn=>{
    const run=tail.then(()=>fn({get:async k=>values.get(k),put:async(k,v)=>values.set(k,v)}));
    tail=run.catch(()=>{});return run;
  }};
  const quota=new ReportQuota({storage},{});
  const statuses=await Promise.all(Array.from({length:1100},()=>quota.fetch(new Request('https://quota/')).then(r=>r.status)));
  assert.equal(statuses.filter(s=>s===200).length,1000);
  assert.equal((await new ReportQuota({storage},{}).fetch(new Request('https://quota/'))).status,429);
  values.set('counter',{day:'2000-01-01',count:1000});
  assert.equal((await quota.fetch()).status,200);
  assert.equal(values.get('counter').count,1);
});

test('streaming body cannot bypass length guard; pause never writes',async()=>{
  const env=environment();
  const stream=new ReadableStream({start(c){c.enqueue(new Uint8Array(200000));c.enqueue(new Uint8Array(200000));c.close();}});
  const req=new Request('https://test/reports',{method:'POST',duplex:'half',body:stream,headers:{'content-type':'application/json','cf-connecting-ip':'192.0.2.1'}});
  assert.equal((await worker.fetch(req,env)).status,400);
  assert.equal(env.reservations,0);
  env.ACCEPT_REPORTS='false';
  assert.equal((await worker.fetch(request(payload()),env)).status,503);
  assert.equal(env.writes.length,0);
});

test('R2 failure never triggers automatic retries',async()=>{
  const env=environment();let writes=0;
  env.REPORTS.put=async()=>{writes++;throw Error('down');};
  assert.equal((await worker.fetch(request(payload()),env)).status,503);
  assert.equal(writes,1);assert.equal(env.reservations,1);
});
