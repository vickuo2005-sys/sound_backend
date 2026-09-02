'use strict';

// Demo-only, arbitrary coordinates near the default map center. They are not
// measurements and do not represent a real site, device, flight, or person.
window.DashboardSimulationScenarios = Object.freeze({
    approach_site_demo_v1: Object.freeze({
        simulation: true,
        id: 'approach_site_demo_v1',
        name: 'Approach Site Demo V1',
        duration_seconds: 75,
        field_validated: false,
        source: 'static_demo_scenario',
        site: Object.freeze({
            simulation: true,
            id: 'demo_site_alpha',
            name: 'Demo Site Alpha',
            lat: 25.0390,
            lng: 121.5752
        }),
        points: Object.freeze([
            Object.freeze({simulation:true, t:0,  lat:25.0282, lng:121.5560}),
            Object.freeze({simulation:true, t:12, lat:25.0305, lng:121.5600}),
            Object.freeze({simulation:true, t:24, lat:25.0332, lng:121.5650}),
            Object.freeze({simulation:true, t:36, lat:25.0360, lng:121.5696}),
            Object.freeze({simulation:true, t:48, lat:25.0380, lng:121.5731}),
            Object.freeze({simulation:true, t:60, lat:25.0391, lng:121.5750}),
            Object.freeze({simulation:true, t:66, lat:25.0398, lng:121.5775}),
            Object.freeze({simulation:true, t:75, lat:25.0412, lng:121.5812})
        ])
    })
});
