// Public, unauthenticated intake. No client-side secret is a security boundary.
export const MAX_BYTES = 256 * 1024;
export const DAILY_LIMIT = 1000;
const json = (data, status = 200) => Response.json(data, {status, headers:{'Cache-Control':'no-store'}});
const symbol = v => typeof v === 'string' && /^[A-Za-z0-9_.-]{1,80}$/.test(v);
const text = (v, max) => typeof v === 'string' && v.length <= max;
const number = v => Number.isFinite(v) && v >= 0 && v <= 1e9;
function keys(o, allowed) {
  return o !== null && typeof o === 'object' && !Array.isArray(o)
    && Object.keys(o).every(k=>allowed.includes(k));
}
export function validReport(p) {
  return keys(p,['schema','report_id','created_at','app_version','system','model','error_code','screen','jobs','job_progress','events','contact','description'])
    && p.schema===1 && typeof p.report_id==='string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(p.report_id)
    && text(p.created_at,40) && /^[0-9T:+.Z-]+$/.test(p.created_at) && Number.isFinite(Date.parse(p.created_at))
    && symbol(p.app_version) && symbol(p.model) && symbol(p.error_code)
    && ['index','template','review','transfer','unknown'].includes(p.screen)
    && keys(p.system,['os','release','architecture','cpu','os_build','cpu_threads','ram_gb','disk_free_gb'])
    && ['os','release','architecture'].every(k=>text(p.system[k],120))
    && ['cpu','os_build'].every(k=>p.system[k]===undefined || text(p.system[k],120))
    && ['cpu_threads','ram_gb','disk_free_gb'].every(k=>p.system[k]===null || number(p.system[k]))
    && keys(p.jobs,['queued','running','done','cancelled','error']) && Object.values(p.jobs).every(number)
    && (p.job_progress===undefined || (Array.isArray(p.job_progress) && p.job_progress.length<=10
      && p.job_progress.every(j=>keys(j,['state','phase','page','total_pages'])
        && ['queued','running','cancelled','error'].includes(j.state)
        && ['preparing','recognizing','starting_engine','loading_model','unknown'].includes(j.phase)
        && ['page','total_pages'].every(k=>j[k]===undefined || (Number.isInteger(j[k]) && number(j[k]))))))
    && Array.isArray(p.events) && p.events.length<=100 && p.events.every(e=>
      keys(e,['time','code','source','exception','frames']) && text(e.time,40) && /^[0-9T:+.Z-]*$/.test(e.time)
      && symbol(e.code) && symbol(e.source) && symbol(e.exception)
      && Array.isArray(e.frames) && e.frames.length<=8 && e.frames.every(f=>
        keys(f,['module','line']) && symbol(f.module) && Number.isInteger(f.line) && number(f.line)))
    && text(p.contact,200) && text(p.description,4000);
}

async function readBounded(request) {
  if (Number(request.headers.get('content-length')) > MAX_BYTES) throw new Error('size');
  if (!request.body) throw new Error('body');
  const reader=request.body.getReader(), chunks=[];
  let total=0;
  try {
    while(true) {
      const {done,value}=await reader.read(); if(done)break;
      total+=value.byteLength;
      if(total>MAX_BYTES) { await reader.cancel(); throw new Error('size'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes=new Uint8Array(total); let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}

export default {
  async fetch(request, env) {
    const url=new URL(request.url);
    if(url.pathname==='/health' && request.method==='GET')return json({service:'handwrite-error-reports',schema:1});
    if(url.pathname!=='/reports')return json({error:'not_found'},404);
    if(request.method!=='POST')return json({error:'method_not_allowed'},405);
    if(env.ACCEPT_REPORTS==='false')return json({error:'paused'},503);
    if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/json'
      || request.headers.has('content-encoding'))return json({error:'content_type'},415);
    // Rate limits execute before parsing, quota access or any R2 operations.
    try {
      const ip=request.headers.get('CF-Connecting-IP');
      if(!ip || !(await env.IP_LIMIT.limit({key:ip})).success)return json({error:'rate_limited'},429);
      let report;
      try { report=await readBounded(request); }
      catch { return json({error:'invalid_or_oversized_report'},400); }
      if(!validReport(report))return json({error:'invalid_report'},400);
      const reservation=await env.QUOTA.get(env.QUOTA.idFromName('global')).fetch('https://quota/reserve');
      if(!reservation.ok)return json({error:'daily_limit'},reservation.status===429?429:503);
      // One write per reservation. No retries or reads; failed writes also consume a slot.
      await env.REPORTS.put('reports/'+report.report_id+'.json',JSON.stringify(report),{
        httpMetadata:{contentType:'application/json'},onlyIf:{etagDoesNotMatch:'*'}
      });
      return json({receipt:report.report_id},201);
    } catch { return json({error:'temporarily_unavailable'},503); }
  }
};

export class ReportQuota {
  constructor(ctx, env) { this.storage=ctx.storage; }
  async fetch() {
    // One stable object, persistent transactional state across all regions/instances.
    const accepted=await this.storage.transaction(async tx=>{
      const day=new Date().toISOString().slice(0,10);
      const previous=await tx.get('counter');
      const count=previous?.day===day?previous.count:0;
      if(!Number.isInteger(count) || count<0 || count>=DAILY_LIMIT)return false;
      await tx.put('counter',{day,count:count+1});return true;
    });
    return new Response(null,{status:accepted?200:429});
  }
}
