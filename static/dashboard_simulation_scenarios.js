'use strict';

(function attachSimulationScenarios(root) {
    const prediction = root.DashboardSimulationPrediction;
    if (!prediction) throw new Error('DashboardSimulationPrediction must load before scenarios');

    // Demo-only, arbitrary coordinates near the default map center. They are
    // not measurements and do not represent a real site, device, flight, or person.
    const demoSite = Object.freeze({
        simulation: true,
        id: 'demo_site_alpha',
        name: 'DEMO SITE ALPHA',
        lat: 25.0390,
        lng: 121.5752,
        radius_m: 100
    });

    function freezePoint(t, eastM, northM) {
        const position = prediction.localOffsetToLatLng(demoSite, eastM, northM);
        return Object.freeze({simulation:true, t, lat:position.lat, lng:position.lng});
    }

    function linearScenario({id, name, description, startEastM, startNorthM, eastMps, northMps}) {
        const points = [];
        for (let t = 0; t <= 90; t += 1) {
            points.push(freezePoint(t, startEastM + eastMps * t, startNorthM + northMps * t));
        }
        return Object.freeze({
            simulation: true,
            id,
            name,
            description,
            duration_seconds: 90,
            sample_hz: 1,
            estimator_window_sec: 5,
            position_uncertainty_m: 5,
            field_validated: false,
            source: 'static_demo_scenario',
            site: demoSite,
            points: Object.freeze(points)
        });
    }

    root.DashboardSimulationScenarios = Object.freeze({
        approach_site_demo_v1: linearScenario({
            id: 'approach_site_demo_v1',
            name: 'DIRECT APPROACH',
            description: 'Starts 1000 m west of the fixed site and travels east at 10 m/s.',
            startEastM: -1000,
            startNorthM: 0,
            eastMps: 10,
            northMps: 0
        }),
        parallel_flyby_demo_v1: linearScenario({
            id: 'parallel_flyby_demo_v1',
            name: 'PARALLEL FLY-BY',
            description: 'Starts 1000 m from the fixed site and travels north with an 800 m CPA.',
            startEastM: -800,
            startNorthM: -600,
            eastMps: 0,
            northMps: 10
        }),
        departing_demo_v1: linearScenario({
            id: 'departing_demo_v1',
            name: 'DEPARTING',
            description: 'Starts 1000 m west of the fixed site and travels farther west at 10 m/s.',
            startEastM: -1000,
            startNorthM: 0,
            eastMps: -10,
            northMps: 0
        })
    });
})(typeof window === 'object' ? window : globalThis);
