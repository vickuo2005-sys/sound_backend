import os,json,hashlib,time,psycopg2
from pathlib import Path
T=['audio_stream_sessions','device_commands','device_connections','device_locations','device_status','event_group_observations','event_groups','events','localization_pair_results','localization_results','target_track_points','target_tracks']
F=[('event_group_observations','event_db_id','events','id'),('event_group_observations','event_id','events','event_id'),('event_group_observations','group_id','event_groups','id'),('localization_results','group_id','event_groups','id'),('localization_pair_results','group_id','event_groups','id'),('localization_pair_results','localization_result_id','localization_results','id'),('target_track_points','group_id','event_groups','id'),('target_track_points','localization_result_id','localization_results','id'),('target_track_points','track_id','target_tracks','id')]
def I(x): return '"'+x.replace('"','""')+'"'
def collect(dsn):
 c=psycopg2.connect(dsn,connect_timeout=20);c.autocommit=True;u=c.cursor();o={'captured_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'tables':{},'sequences':{},'fk_orphans':{},'relationships':{}}
 for t in T:
  tb='public.'+I(t); cols=[r[0] for r in run(u,"select column_name from information_schema.columns where table_schema='public' and table_name=%s order by ordinal_position",(t,))];d={'row_count':run(u,f'select count(*) from {tb}')[0][0],'columns':cols}
  for col in ['created_at','updated_at','event_timestamp','last_event_time','last_event_time_ms','measurement_time_ms','started_at','closed_at']:
   if col in cols:
    a,b=run(u,f'select min({I(col)}),max({I(col)}) from {tb}')[0];d[col]={'min':str(a) if a is not None else None,'max':str(b) if b is not None else None}
  pk=[r[0] for r in run(u,"select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid and a.attnum=any(i.indkey) where i.indrelid=%s::regclass and i.indisprimary order by array_position(i.indkey,a.attnum)",(f'public.{t}',))];d['primary_key']=pk
  if pk:
   p=', '.join(I(x) for x in pk);d['pk_null_count']=run(u,f'select count(*) from {tb} where '+ ' or '.join(f'{I(x)} is null' for x in pk))[0][0];d['pk_duplicate_groups']=run(u,f'select count(*) from (select {p},count(*) from {tb} group by {p} having count(*)>1) z')[0][0]
  d['row_checksum']=run(u,f"select md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' order by to_jsonb(t)::text),'')) from {tb} t")[0][0] if d['row_count'] else None
  d['gcs_reference_nonnull']=sum(run(u,f"select count(*) from {tb} where {I(col)} is not null")[0][0] for col in cols if any(k in col.lower() for k in ['gcs','storage','object_path','clip_path','audio_path']))
  o['tables'][t]=d
 for seq,last,start,inc in run(u,"select sequencename,last_value,start_value,increment_by from pg_sequences where schemaname='public' order by sequencename"):o['sequences'][seq]={'last_value':int(last) if last is not None else None,'start_value':int(start),'increment_by':int(inc)}
 for ch,col,pa,pc in F:o['fk_orphans'][f'{ch}.{col}->{pa}.{pc}']=run(u,f'select count(*) from public.{I(ch)} c left join public.{I(pa)} p on c.{I(col)}=p.{I(pc)} where c.{I(col)} is not null and p.{I(pc)} is null')[0][0]
 for ch,col in [('event_group_observations','group_id'),('target_track_points','group_id'),('target_track_points','track_id')]:
  rows=run(u,f'select {I(col)}::text,count(*) from public.{I(ch)} where {I(col)} is not null group by {I(col)} order by 1');o['relationships'][f'{ch}.{col}']=hashlib.sha256('\n'.join(f'{a}:{b}' for a,b in rows).encode()).hexdigest()
 o['smoke']={t:run(u,f'select count(*) from public.{I(t)}')[0][0] for t in T};u.close();c.close();return o
def run(c,sql,args=()):c.execute(sql,args);return c.fetchall()
s=collect(os.environ['SOURCE_DSN']);d=collect(os.environ['DEST_DSN']);
ss=json.loads(Path('outputs/tokyo_source_snapshot_data_rehearsal.json').read_text())
checks={}
for t in T: checks[t]={'source_snapshot_count':ss['tables'][t]['row_count'],'source_current_count':s['tables'][t]['row_count'],'destination_count':d['tables'][t]['row_count'],'count_match':ss['tables'][t]['row_count']==d['tables'][t]['row_count'],'checksum_match':ss['tables'][t].get('row_checksum')==d['tables'][t]['row_checksum'],'timestamp_match':all(ss['tables'][t].get(x)==d['tables'][t].get(x) for x in ['created_at','updated_at','event_timestamp','last_event_time','last_event_time_ms','measurement_time_ms','started_at','closed_at'] if x in ss['tables'][t] or x in d['tables'][t]),'pk_integrity':d['tables'][t].get('pk_null_count',0)==0 and d['tables'][t].get('pk_duplicate_groups',0)==0}
result={'captured_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_current':s,'destination':d,'table_checks':checks,'source_write_observation':{'snapshot_count_changed':any(s['tables'][t]['row_count']!=ss['tables'][t]['row_count'] for t in T)},'status':'PENDING_SEQUENCE_RESTORE'}
Path('outputs/tokyo_singapore_data_verification.json').write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+'\n');print(json.dumps({'count_matches':all(x['count_match'] for x in checks.values()),'checksum_matches':all(x['checksum_match'] for x in checks.values()),'timestamp_matches':all(x['timestamp_match'] for x in checks.values()),'pk_integrity':all(x['pk_integrity'] for x in checks.values()),'source_orphans':sum(s['fk_orphans'].values()),'destination_orphans':sum(d['fk_orphans'].values()),'source_sequences':s['sequences'],'destination_sequences':d['sequences']},indent=2))
