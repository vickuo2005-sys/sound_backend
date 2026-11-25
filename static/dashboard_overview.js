(function(root) {
    'use strict';
    // Inputs are normalized live snapshots. Simulation state never enters this model.
    function summarize(input) {
        const {now, devices=[], events=[]} = input;
        const nodesFresh = Boolean(input.backendConnected && !input.devicesFailed && input.devicesAt && now-input.devicesAt <= 20000);
        const eventsFresh = Boolean(input.backendConnected && !input.eventsFailed && input.eventsAt && now-input.eventsAt <= 45000);
        const recent = events.filter(e => e.time > 0 && e.time <= now && now-e.time <= 60000);
        return {
            nodesFresh, eventsFresh,
            online: nodesFresh ? devices.filter(d=>d.online).length : null,
            listening: nodesFresh ? devices.filter(d=>d.online && d.listening).length : null,
            offline: nodesFresh ? devices.filter(d=>!d.online).length : null,
            missingLocation: devices.filter(d=>!d.located).length,
            recentDroneCount: eventsFresh ? recent.filter(e=>e.drone).length : null,
            recentEvents: events.slice().sort((a,b)=>b.time-a.time).slice(0,5),
            devices: devices.slice().sort((a,b)=>Number(a.online)-Number(b.online) || a.id.localeCompare(b.id))
        };
    }
    const api={summarize};
    if(typeof module!=='undefined' && module.exports) module.exports=api;
    else root.DashboardOverview=api;
})(typeof window!=='undefined'?window:globalThis);
