const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('templates/dashboard_v2_4.html', 'utf8');
const pending = [];
const context = vm.createContext({
    state:{selectedEventId:'A'}, eventContextState:{eventId:null,phase:'idle',loadedAt:0},
    renderEventContext:()=>{}, Date,
    fetchJson:url => new Promise((resolve,reject) => pending.push({url,resolve,reject}))
});
const start = html.indexOf('        async function ensureEventContext(');
const end = html.indexOf('        function nodeShapeText(', start);
assert(start > 0 && end > start);
vm.runInContext(html.slice(start,end),context);
const response = id => ({status:'success',event:{event_id:id},group:null});

// Render untrusted identifiers through the actual template escaping path.
let writes = 0;
let markup = '';
const container = {dataset:{}, querySelectorAll:()=>[],
    get innerHTML() { return markup; }, set innerHTML(value) { writes++; markup=value; }};
const rendering = vm.createContext({
    window:{DashboardEventContext:require('../../static/dashboard_event_context.js')},
    state:{selectedEventId:'unsafe',runtime:{}},
    eventContextState:{eventId:'unsafe',phase:'ready',payload:{
        event:{event_id:'unsafe',device_id:'<img src=x onerror=alert(1)>'},
        group:{id:'<script>alert(1)</script>',devices:['<img src=x>']}}},
    document:{getElementById:id => id === 'eventContext' ? container : {addEventListener:()=>{}}}
});
const safeStart = html.indexOf('        function safe(');
vm.runInContext(html.slice(safeStart,html.indexOf('        function finite(',safeStart)),rendering);
const renderStart = html.indexOf('        function renderEventContext(');
vm.runInContext(html.slice(renderStart,start),rendering);
rendering.renderEventContext();
assert(!markup.includes('<img'));
assert(!markup.includes('<script>'));
assert(markup.includes('&lt;img'));
assert(markup.includes('&lt;script&gt;'));
rendering.renderEventContext();
assert.equal(writes,1,'unchanged summary should not replace its DOM');

(async () => {
    const first = context.ensureEventContext('A');
    await context.ensureEventContext('A');
    assert.equal(pending.length,1, 'in-flight requests are deduplicated');
    context.state.selectedEventId = 'B';
    const second = context.ensureEventContext('B');
    pending[0].resolve(response('A')); await first;
    assert.equal(context.eventContextState.eventId,'B');
    assert.equal(context.eventContextState.payload,null, 'late A cannot populate B');
    pending[1].resolve(response('B')); await second;
    assert.equal(context.eventContextState.payload.event.event_id,'B');
    await context.ensureEventContext('B');
    assert.equal(pending.length,2, 'fresh data does not trigger another query');

    const retry = context.ensureEventContext('B',true);
    pending[2].reject(new Error('503')); await retry;
    assert.equal(context.eventContextState.phase,'error');
    assert.equal(context.eventContextState.payload,null, 'failed refresh must not claim a current association');
    const wrongResponse = context.ensureEventContext('B',true);
    pending[3].resolve(response('A')); await wrongResponse;
    assert.equal(context.eventContextState.phase,'error');
    const recovered = context.ensureEventContext('B',true);
    pending[4].resolve(response('B')); await recovered;
    assert.equal(context.eventContextState.phase,'ready');

    context.state.selectedEventId='id with ?';
    const encoded = context.ensureEventContext('id with ?');
    assert.equal(pending[5].url,'/events/id%20with%20%3F/context');
    pending[5].resolve(response('id with ?')); await encoded;
    console.log('Event context loading: selection races, deduplication, errors and retry passed');
})().catch(error => { console.error(error); process.exitCode=1; });
