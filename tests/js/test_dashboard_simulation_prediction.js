'use strict';

const assert = require('node:assert/strict');
require('../../static/dashboard_simulation_prediction.js');

const prediction = globalThis.DashboardSimulationPrediction;
const site = Object.freeze({simulation:true, id:'test_site', name:'TEST SITE', lat:25.039, lng:121.5752, radius_m:100});

function near(actual, expected, tolerance, label) {
    assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} != ${expected} ± ${tolerance}`);
}

function historyEndingAt(currentEastM, currentNorthM, eastMps, northMps, count = 6) {
    const points = [];
    const endTime = count - 1;
    for (let t = 0; t <= endTime; t += 1) {
        const point = prediction.localOffsetToLatLng(
            site,
            currentEastM - eastMps * (endTime - t),
            currentNorthM - northMps * (endTime - t)
        );
        points.push({simulation:true, t, lat:point.lat, lng:point.lng});
    }
    return points;
}

function tick(history, extra = {}) {
    return prediction.computeSimulationPredictionTick({
        simulation:true,
        history,
        current_position:history[history.length - 1],
        site,
        position_uncertainty_m:1,
        ...extra
    });
}

for (const [heading, expectedEast, expectedNorth] of [
    [0, 0, 100], [90, 100, 0], [180, 0, -100], [270, -100, 0]
]) {
    const velocity = prediction.velocityFromSpeedHeading(10, heading);
    const projected = prediction.projectConstantVelocity(site, velocity, [10])[0];
    const offset = prediction.localOffsetMeters(site, projected);
    near(offset.east_m, expectedEast, .01, `heading ${heading} east`);
    near(offset.north_m, expectedNorth, .01, `heading ${heading} north`);
}

near(prediction.haversineDistanceM(site, site), 0, 1e-9, 'same point');
near(prediction.haversineDistanceM({lat:0,lng:0}, {lat:0,lng:1}), 111194.93, .1, 'equator degree');
near(prediction.haversineDistanceM({lat:0,lng:179.9}, {lat:0,lng:-179.9}), 22238.99, .2, 'antimeridian');

const directHistory = historyEndingAt(-1000, 0, 10, 0);
const direct = tick(directHistory);
assert.equal(direct.status, 'OK');
assert.equal(direct.motion.trend, 'APPROACHING');
near(direct.current.speed_mps, 10, .02, 'direct speed');
near(direct.motion.radial_closing_speed_mps, 10, .02, 'direct closing');
near(direct.site_metrics.predicted_closest_distance_m, 0, .2, 'direct CPA distance');
near(direct.site_metrics.predicted_closest_time_sec, 100, .1, 'direct CPA time');
near(direct.site_metrics.simulated_eta_sec, 90, .1, 'direct ETA');

const repeated = tick(directHistory);
assert.deepEqual(repeated, direct, 'same input must be deterministic');

const movedSite = {...site, lat:site.lat + .02, lng:site.lng - .03};
const movedSiteResult = tick(directHistory, {site:movedSite});
assert.deepEqual(
    movedSiteResult.predictions.map(({lat,lng,horizon_sec}) => ({lat,lng,horizon_sec})),
    direct.predictions.map(({lat,lng,horizon_sec}) => ({lat,lng,horizon_sec})),
    'moving the assessment site must not alter predicted positions'
);
assert.notEqual(movedSiteResult.site.current_distance_m, direct.site.current_distance_m);

const parallel = tick(historyEndingAt(-800, -600, 0, 10));
assert.equal(parallel.motion.trend, 'APPROACHING');
near(parallel.site_metrics.predicted_closest_distance_m, 800, .3, 'parallel CPA distance');
near(parallel.site_metrics.predicted_closest_time_sec, 60, .1, 'parallel CPA time');
assert.equal(parallel.site_metrics.simulated_eta_sec, null);
assert.equal(parallel.site_metrics.eta_reason, 'NO_SITE_INTERSECTION');

const departing = tick(historyEndingAt(-1000, 0, -10, 0));
assert.equal(departing.motion.trend, 'DEPARTING');
near(departing.motion.radial_closing_speed_mps, -10, .02, 'departing closing');
assert.equal(departing.site_metrics.simulated_eta_sec, null);

const inside = tick(historyEndingAt(50, 0, 10, 0));
assert.equal(inside.site_metrics.simulated_eta_sec, 0);
assert.equal(inside.site_metrics.eta_reason, 'AT_SITE');

const tangent = tick(historyEndingAt(-1000, 100, 10, 0));
near(tangent.site_metrics.predicted_closest_distance_m, 100, .3, 'tangent CPA distance');
near(tangent.site_metrics.simulated_eta_sec, 100, .5, 'tangent ETA');
assert.ok(Number.isFinite(tangent.site_metrics.simulated_eta_sec));

const lowSpeed = tick(historyEndingAt(-1000, 0, .49, 0), {position_uncertainty_m:0});
assert.equal(lowSpeed.status, 'DATA_INSUFFICIENT');
assert.deepEqual(lowSpeed.status_reasons, ['LOW_SPEED']);
assert.equal(lowSpeed.display.show_heading, false);
assert.equal(lowSpeed.site_metrics.simulated_eta_sec, null);

const unwrapped = prediction.unwrapHeadings([
    {t:0,heading_deg:358}, {t:1,heading_deg:359}, {t:2,heading_deg:0}, {t:3,heading_deg:1}, {t:4,heading_deg:2}
]);
assert.deepEqual(unwrapped.map(item => item.heading_deg), [358,359,360,361,362]);
near(prediction.estimateTurnRate(unwrapped), 1, 1e-9, 'turn wrap rate');

const tooFew = tick(directHistory.slice(-2));
assert.equal(tooFew.status, 'DATA_INSUFFICIENT');
assert.ok(tooFew.status_reasons.includes('TOO_FEW_POINTS'));

const withGap = [directHistory[0], {...directHistory[4], t:4}, {...directHistory[5], t:5}];
const gap = tick(withGap);
assert.equal(gap.status, 'DATA_INSUFFICIENT');
assert.ok(gap.status_reasons.includes('HISTORY_GAP'));

const duplicate = prediction.normalizeSimulationHistory([...directHistory, {...directHistory[5], lat:directHistory[5].lat}]);
assert.equal(duplicate.points.length, directHistory.length);

const invalid = tick([...directHistory, {t:'bad',lat:25,lng:121}]);
assert.equal(invalid.status, 'DATA_INSUFFICIENT');
assert.ok(invalid.status_reasons.includes('INVALID_TIME'));

const uncertain = tick(directHistory, {position_uncertainty_m:1000});
assert.equal(uncertain.status, 'DATA_INSUFFICIENT');
assert.ok(uncertain.status_reasons.includes('UNCERTAINTY_EXCEEDS_MOTION'));

require('../../static/dashboard_simulation_scenarios.js');
const scenarios = globalThis.DashboardSimulationScenarios;
function scenarioAtFive(id) {
    const scenario = scenarios[id];
    const history = scenario.points.filter(point => point.t <= 5);
    return prediction.computeSimulationPredictionTick({
        simulation:true,
        history,
        current_position:history[history.length - 1],
        site:scenario.site,
        position_uncertainty_m:scenario.position_uncertainty_m,
        options:{estimator_window_sec:scenario.estimator_window_sec}
    });
}
near(prediction.haversineDistanceM(scenarios.approach_site_demo_v1.points[0], site), 1000, .2, 'direct scenario initial distance');
near(prediction.haversineDistanceM(scenarios.parallel_flyby_demo_v1.points[0], site), 1000, .2, 'parallel scenario initial distance');
near(prediction.haversineDistanceM(scenarios.departing_demo_v1.points[0], site), 1000, .2, 'departing scenario initial distance');
const directScenario = scenarioAtFive('approach_site_demo_v1');
assert.equal(directScenario.motion.trend, 'APPROACHING');
assert.ok(directScenario.site_metrics.predicted_closest_distance_m < site.radius_m);
near(directScenario.site_metrics.simulated_eta_sec, 85, .2, 'direct scenario ETA at t=5');
const parallelScenario = scenarioAtFive('parallel_flyby_demo_v1');
assert.ok(parallelScenario.site_metrics.predicted_closest_distance_m > site.radius_m);
assert.equal(parallelScenario.site_metrics.simulated_eta_sec, null);
const departingScenario = scenarioAtFive('departing_demo_v1');
assert.equal(departingScenario.motion.trend, 'DEPARTING');
assert.ok(departingScenario.motion.radial_closing_speed_mps < 0);
assert.equal(departingScenario.site_metrics.simulated_eta_sec, null);
assert.equal(scenarios.approach_site_demo_v1.site, scenarios.parallel_flyby_demo_v1.site);
assert.equal(scenarios.approach_site_demo_v1.site, scenarios.departing_demo_v1.site);

console.log('dashboard_simulation_prediction: all assertions passed');
