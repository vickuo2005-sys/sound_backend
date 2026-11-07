"""Verify the running local server with an explicitly synthetic node and event."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import time
import uuid
from pathlib import Path
import httpx
import websockets


async def run(port, data_dir, hold_seconds=0):
    base = f'http://127.0.0.1:{port}'
    wsbase = f'ws://127.0.0.1:{port}'
    # CHECK/TEST/SMOKE IDs are deliberately filtered by the production dashboard.
    device = 'LOCAL_DEMO'
    event_id = f'local-check-{uuid.uuid4()}'

    def envelope(kind, payload):
        return json.dumps({'protocol_version':1, 'message_type':kind,
                           'device_id':device, 'message_id':str(uuid.uuid4()),
                           'sent_at_ms':int(time.time()*1000), 'payload':payload})

    async def receive_until(socket, predicate):
        async with asyncio.timeout(10):
            while True:
                item = json.loads(await socket.recv())
                if predicate(item):
                    return item

    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        token = (data_dir / 'upload-token.txt').read_text(encoding='utf-8').strip()
        for route in ('/health','/runtime-status','/device-status','/events','/event-groups','/tracks','/device-locations','/dashboard'):
            response = await client.get(route)
            response.raise_for_status()
        response=await client.put('/device-locations/'+device,json={'latitude':25.039,'longitude':121.5752,'location_source':'manual_map'})
        response.raise_for_status()
        async with websockets.connect(wsbase+'/ws/dashboard') as dashboard:
            async with websockets.connect(wsbase+'/ws/node/'+device) as node:
                await node.send(envelope('hello',{'app_version':'LOCAL_TEST','recording':True,'detection_enabled':True}))
                await receive_until(node,lambda x:x.get('message_type')=='hello_ack')
                await node.send(envelope('heartbeat',{'recording':True,'detection_enabled':True,'latitude':25.039,'longitude':121.5752}))
                await receive_until(dashboard,lambda x:x.get('type')=='node_heartbeat')
                devices=(await client.get('/device-status')).json()['devices']
                active=next(d for d in devices if d['device_id']==device)
                assert active['is_listening'] is True, active
                response = await client.post('/events',headers={'x-upload-token':token},json={
                    'event_id':event_id,'device_id':device,'timestamp':datetime.now(timezone.utc).isoformat(),
                    'latitude':25.039,'longitude':121.5752,'label':'Drone','note':'Synthetic localhost integration check',
                    'classification':{'schema_version':'classification.v1','model_id':'local-test','model_version':'1',
                        'model_label':'Drone','confidence':0.9,'class_scores':{'Drone':0.9,'Car':0.1,'Rainfall':0,'Airplane':0,'Electric_saw':0},
                        'operational_class':'drone','is_target':True,'aircraft_probability':0.9}
                })
                response.raise_for_status()
                await receive_until(dashboard,lambda x:x.get('type')=='event_trigger' and x.get('event_id',x.get('event',{}).get('event_id'))==event_id)
                events = (await client.get('/events?limit=100')).json()['events']
                assert any(e['event_id']==event_id for e in events), 'event was not persisted'
                response=await client.post('/device-command',json={'device_id':device,'command':'stop_listening','issued_by':'local-smoke'})
                response.raise_for_status()
                command=response.json()
                assert command['delivery']=='websocket', command
                delivered=await receive_until(node,lambda x:x.get('message_type')=='command')
                command_id=delivered['payload']['command_id']
                assert int(command_id)==command['command_id']
                await node.send(envelope('command_ack',{'command_id':command_id}))
                await receive_until(dashboard,lambda x:x.get('type')=='device_command_ack')
                await node.send(envelope('command_result',{'command_id':command_id,'status':'completed'}))
                await receive_until(dashboard,lambda x:x.get('type')=='device_command_result')
                persisted=(await client.get('/device-command/'+device,params={'command_id':command['command_id']})).json()
                assert 'completed' in json.dumps(persisted), persisted
                for _ in range(hold_seconds):
                    await node.send(envelope('heartbeat',{'recording':True,'detection_enabled':True}))
                    await asyncio.sleep(1)
            await receive_until(dashboard,lambda x:x.get('type')=='node_disconnected')
        fixed=(await client.get('/device-locations')).json()['device_locations']
        assert any(d['device_id']==device for d in fixed), 'fixed offline node was lost'
    print('PASS: API, node hello/heartbeat/disconnect, event persistence + dashboard WebSocket, command delivery/ack/result')
    print('Synthetic event retained only in the local database:',event_id)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8786)
    parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'.local-runtime')
    parser.add_argument('--hold-seconds',type=int,default=0,choices=range(0,61))
    args=parser.parse_args()
    asyncio.run(run(args.port,args.data_dir,args.hold_seconds))
