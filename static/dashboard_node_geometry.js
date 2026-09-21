(function (root) {
    'use strict';
    const FRESH_MS = 15000;
    const FUTURE_TOLERANCE_MS = 2000;
    const number = value => (typeof value === 'number' || typeof value === 'string' && value.trim() !== '') && Number.isFinite(Number(value)) ? Number(value) : null;
    function coordinate(lat, lng) {
        lat = number(lat); lng = number(lng);
        return lat !== null && lng !== null && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? {lat, lng} : null;
    }
    function nodePosition(node) {
        for (const [lat, lng] of [['marker_latitude','marker_longitude'], ['effective_latitude','effective_longitude'], ['fixed_latitude','fixed_longitude'], ['latitude','longitude']]) {
            const result = coordinate(node?.[lat], node?.[lng]);
            if (result) return result;
        }
        return null;
    }
    function rows(value) {
        if (value instanceof Map) return [...value.values()];
        if (Array.isArray(value)) return value;
        if (Array.isArray(value?.device_locations)) return value.device_locations;
        return [];
    }
    function mergeFixedLocations(devices, fixedLocations) {
        const merged = new Map(rows(devices).filter(node => node?.device_id).map(node => [String(node.device_id), {...node}]));
        for (const location of rows(fixedLocations)) {
            const id = typeof location?.device_id === 'string' ? location.device_id.trim() : '';
            const point = coordinate(location?.latitude, location?.longitude);
            if (!id || !point || location.enabled === false || location.is_active === false) continue;
            // A saved map position is configuration, never proof of a connected or listening node.
            const node = merged.get(id) || {device_id:id, status:'offline', reported:false, is_listening:false};
            merged.set(id, {...node,
                fixed_latitude:point.lat, fixed_longitude:point.lng,
                marker_latitude:point.lat, marker_longitude:point.lng,
                effective_latitude:point.lat, effective_longitude:point.lng,
                fixed_location_source:location.location_source || 'manual_map',
                fixed_accuracy_m:number(location.accuracy_m),
                fixed_location_accuracy_m:number(location.accuracy_m),
                effective_location_source:'fixed', marker_location_source:'fixed',
                fixed_location:{...location}, configured_fixed:true
            });
        }
        return [...merged.values()];
    }
    function mergeFixedNodes(devices, fixedLocations, canonicalIds=[]) {
        const merged = new Map(mergeFixedLocations(devices, fixedLocations).map(node => [String(node.device_id),node]));
        const ids = [...new Set([...canonicalIds.map(String),...merged.keys()])];
        return ids.map(id => merged.get(id) || {device_id:id,status:'offline',reported:false,is_listening:false});
    }
    function timestamp(value) {
        if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : null;
        if (typeof value !== 'string' || !value.trim()) return null;
        const parsed = Date.parse(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
    const eventTime = event => timestamp(event?.timestamp ?? event?.event_timestamp ?? event?.measurement_timestamp ?? event?.created_at) ?? timestamp(event?.alert_sequence_ms);
    const groupTime = group => timestamp(group?.last_event_time ?? group?.end_time ?? group?.region_updated_at ?? group?.updated_at ?? group?.created_at);
    const groupId = group => String(group?.id ?? group?.group_id ?? '');
    function fresh(time, now, duration) { return time !== null && Number.isFinite(now) && now-time >= -FUTURE_TOLERANCE_MS && now-time <= duration; }
    function isDrone(event) {
        const label = event?.classification?.model_label ?? event?.dashboard_presentation?.model_label ?? event?.model_label ?? event?.label;
        return typeof label === 'string' && label.trim().toLowerCase() === 'drone';
    }
    function parseIds(value) {
        if (typeof value === 'string') {
            try { value = JSON.parse(value); }
            catch (_) { value = value.split(','); }
        }
        if (!Array.isArray(value)) return null;
        return [...new Set(value.map(item => typeof item === 'string' ? item.trim() : typeof item?.device_id === 'string' ? item.device_id.trim() : '').filter(Boolean))];
    }
    function memberIds(group) {
        for (const key of ['active_device_ids','reporting_device_ids','device_ids','member_device_ids','devices']) {
            const ids = parseIds(group?.[key]);
            if (ids !== null) return ids; // An explicit empty active set must not fall back to historical members.
        }
        return parseIds(group?.events) || [];
    }
    function eventGroupId(event) { return String(event?.group_id ?? event?.fusion_group_id ?? event?.event_group_id ?? ''); }
    function belongsToGroup(event, group) {
        const explicit = eventGroupId(event);
        if (explicit) return explicit === groupId(group);
        const included = Array.isArray(group.events) && group.events.some(item => item === event || item?.event_id && item.event_id === event.event_id);
        if (included) return true;
        // Group membership supplies the association. Event time bounds prevent a later,
        // unrelated Drone report from activating an older group for the same node.
        const start = timestamp(group.first_event_time ?? group.start_time ?? group.created_at);
        const end = timestamp(group.last_event_time ?? group.end_time);
        const time = eventTime(event);
        return start !== null && end !== null && time !== null && time >= start && time <= end;
    }
    function convexHull(points) {
        const unique = new Map();
        for (const value of points || []) {
            const point = coordinate(value?.lat, value?.lng);
            if (point) unique.set(`${point.lat},${point.lng}`, point);
        }
        const valid = [...unique.values()];
        if (valid.length < 3) return valid;
        // Unwrap longitude around the first point so a local site across the date line
        // does not become a polygon spanning nearly the entire world.
        const anchor = valid[0].lng;
        const projected = valid.map(point => ({...point, x:anchor + ((point.lng-anchor+540)%360-180)})).sort((a,b) => a.x-b.x || a.lat-b.lat);
        const cross = (a,b,c) => (b.x-a.x)*(c.lat-a.lat)-(b.lat-a.lat)*(c.x-a.x);
        const build = list => {
            const chain = [];
            for (const point of list) {
                while (chain.length >= 2 && cross(chain.at(-2),chain.at(-1),point) <= 1e-12) chain.pop();
                chain.push(point);
            }
            return chain;
        };
        const lower = build(projected), upper = build([...projected].reverse());
        return lower.slice(0,-1).concat(upper.slice(0,-1)).map(({lat,lng}) => ({lat,lng}));
    }
    function geometry(id, participants, expiresAt) {
        const path = convexHull(participants.map(item => item.position));
        return {id, kind:path.length >= 3 ? 'polygon' : path.length === 2 ? 'line' : 'point', path,
            participants, deviceIds:participants.map(item => item.device_id), expiresAt,
            label:'無人機事件回報節點連線／範圍（非無人機定位）'};
    }
    function buildGeometries({nodes=[], groups=[], events=[], now=Date.now(), freshMs=FRESH_MS, enabled=true} = {}) {
        if (!enabled) return [];
        const duration = number(freshMs) !== null && freshMs > 0 ? Number(freshMs) : FRESH_MS;
        const positions = new Map(rows(nodes).map(node => [String(node.device_id || ''), nodePosition(node)]).filter(([id,point]) => id && point));
        const recent = rows(events).filter(event => isDrone(event) && fresh(eventTime(event), now, duration));
        const output = [], representedEvents = new Set();
        for (const group of rows(groups)) {
            const id = groupId(group), updated = groupTime(group);
            if (!id || ['closed','expired','ended','inactive'].includes(String(group.status || '').toLowerCase()) || !fresh(updated, now, duration)) continue;
            const embedded = rows(group.events).filter(event => isDrone(event) && fresh(eventTime(event), now, duration));
            const evidence = [...recent, ...embedded].filter(event => belongsToGroup(event, group));
            const participants = memberIds(group).map(device_id => {
                const reports = evidence.filter(event => String(event.device_id || '') === device_id);
                const position = positions.get(device_id);
                if (!position || !reports.length) return null;
                reports.forEach(event => representedEvents.add(event.event_id || event));
                return {device_id, position, time:Math.max(...reports.map(eventTime))};
            }).filter(Boolean);
            if (participants.length) output.push(geometry(`group:${id}`, participants, Math.min(updated,...participants.map(item => item.time))+duration));
        }
        const solo = new Map();
        for (const event of recent) {
            const id = String(event.device_id || ''), position = positions.get(id);
            if (!position || representedEvents.has(event.event_id || event)) continue;
            const time = eventTime(event);
            if (!solo.has(id) || time > solo.get(id).time) solo.set(id,{device_id:id,position,time});
        }
        for (const participant of solo.values()) output.push(geometry(`node:${participant.device_id}`, [participant], participant.time+duration));
        return output;
    }
    function createRenderer(options={}) {
        const overlays = new Map();
        const clock = options.clock || (() => Date.now());
        const requestFrame = options.requestAnimationFrame || root.requestAnimationFrame?.bind(root);
        const cancelFrame = options.cancelAnimationFrame || root.cancelAnimationFrame?.bind(root);
        const schedule = options.setTimeout || root.setTimeout?.bind(root);
        const unschedule = options.clearTimeout || root.clearTimeout?.bind(root);
        let frame = null, expiryTimer = null, current = null, epoch = 0, baseNow = 0;
        function remove(entry) { entry.objects.forEach(object => object.setMap(null)); }
        function stopTimers() {
            if (frame !== null) cancelFrame?.(frame);
            if (expiryTimer !== null) unschedule?.(expiryTimer);
            frame = null; expiryTimer = null;
        }
        function activeDeviceIds() { return new Set([...overlays.values()].flatMap(entry => entry.deviceIds || [])); }
        function publishPulse(pulse) { if (typeof current?.onPulse === 'function') current.onPulse(activeDeviceIds(),pulse); }
        function clear() { stopTimers();publishPulse(0);overlays.forEach(remove); overlays.clear(); current = null; }
        function animate() {
            if (!current || !overlays.size) return;
            const pulse = (Math.sin(clock()/650)+1)/2;
            for (const entry of overlays.values()) {
                entry.rings.forEach(ring => ring.setOptions({radius:24+28*pulse,fillOpacity:.1-.07*pulse,strokeOpacity:.9-.75*pulse}));
                entry.shape?.setOptions(entry.kind === 'polygon' ? {fillOpacity:.12,strokeOpacity:.85} : {strokeOpacity:.95});
            }
            publishPulse(pulse);
            frame = requestFrame?.(animate) ?? null;
        }
        function update(input={}) {
            stopTimers();
            const api = input.google?.maps || input.google || root.google?.maps;
            if (!input.map || !api || input.enabled === false) { clear(); return []; }
            current = input; epoch = clock(); baseNow = number(input.now) ?? epoch;
            const items = buildGeometries({...input, now:baseNow});
            const active = new Set(items.map(item => item.id));
            overlays.forEach((entry,id) => { if (!active.has(id)) { remove(entry); overlays.delete(id); } });
            for (const item of items) {
                const signature = JSON.stringify([item.kind,item.participants.map(p => [p.device_id,p.position.lat,p.position.lng])]);
                let entry = overlays.get(item.id);
                if (entry && (entry.signature !== signature || entry.map !== input.map || entry.api !== api)) { remove(entry); overlays.delete(item.id); entry = null; }
                if (!entry) {
                    const shared = {map:input.map,clickable:false,strokeColor:'#f97316',fillColor:'#f97316',zIndex:4};
                    const rings = item.participants.map(node => new api.Circle({...shared,center:node.position,radius:24,strokeWeight:3,strokeOpacity:.9,fillOpacity:.1}));
                    const shape = item.kind === 'polygon'
                        ? new api.Polygon({...shared,paths:item.path,geodesic:true,strokeWeight:3,strokeOpacity:.85,fillOpacity:.12})
                        : item.kind === 'line'
                            ? new api.Polyline({...shared,path:item.path,geodesic:true,strokeWeight:5,strokeOpacity:.95})
                            : null;
                    entry = {signature, map:input.map, api, rings, shape, kind:item.kind, deviceIds:item.deviceIds, objects:shape ? [...rings,shape] : rings};
                    overlays.set(item.id,entry);
                } else entry.deviceIds=item.deviceIds;
            }
            publishPulse(.5);
            const reduced = input.reducedMotion ?? options.reducedMotion ?? root.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
            // Static rings remain visible with reduced motion. Expiration still runs.
            if (!reduced && input.animate !== false && requestFrame && overlays.size) frame = requestFrame(animate);
            if (items.length && schedule) {
                const remaining = Math.max(1,Math.min(...items.map(item => item.expiresAt))-baseNow+1);
                expiryTimer = schedule(() => { if (current) update({...current, now:baseNow+Math.max(0,clock()-epoch)}); }, remaining);
                expiryTimer?.unref?.();
            }
            return items;
        }
        return Object.freeze({update,clear});
    }
    const api = Object.freeze({FRESH_MS,coordinate,nodePosition,mergeFixedLocations,mergeFixedNodes,memberIds,isDrone,convexHull,buildGeometries,createRenderer});
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.DashboardNodeGeometry = api;
})(typeof window !== 'undefined' ? window : globalThis);
