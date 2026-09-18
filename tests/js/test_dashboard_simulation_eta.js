const assert = require('node:assert/strict');
const Eta = require('../../static/dashboard_simulation_eta.js');

const site = {x: 0, y: 0, radius: 100};
const near = (actual, expected, tolerance = 1e-6) => assert(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
const line = (fromSecond, toSecond, fn) => {
    const points = [];
    for (let second = fromSecond; second <= toSecond; second += 1) points.push({...fn(second), timeMs: second * 1000});
    return points;
};
const raw = (history, second, targetSite = site) => Eta.createRawSitePrediction({history, referenceTimeMs: second * 1000, site: targetSite});
const stableRaw = (referenceTimeMs, entryTimeMs) => ({valid: true, referenceTimeMs, rawEtaSeconds: (entryTimeMs-referenceTimeMs)/1000, rawEntryTimeMs: entryTimeMs, trend: 'APPROACHING', reason: 'INTERSECTS'});

// A. Straight approach: the fitted state gives the expected line-circle entry time.
const straight = line(0, 5, second => ({x: 500 - 20 * second, y: 0}));
const straightRaw = raw(straight, 5);
assert.equal(straightRaw.valid, true);
near(straightRaw.rawEtaSeconds, 15);
near(straightRaw.rawEntryTimeMs, 20000);
assert.equal(straightRaw.motion.source, 'fitted_estimated_trajectory');

// B. Noisy approach: smoothing the absolute entry timestamp reduces frame-to-frame jitter.
const noise = [0, 8, -6, 10, -9, 7, -4, 8, -7, 5, -3, 4, -2];
const noisy = line(0, 12, second => ({x: 500 - 20 * second + noise[second], y: noise[second] * .15}));
const noisyStabilizer = new Eta.EtaStabilizer();
const rawEntries = [], displayEntries = [];
for (let second = 3; second <= 12; second += 1) {
    const frameRaw = raw(noisy, second);
    const frameDisplay = noisyStabilizer.update(frameRaw, second * 1000);
    assert.notEqual(frameDisplay.state, 'CLEARED');
    if (frameRaw.rawEntryTimeMs !== null && frameDisplay.smoothedEntryTimeMs !== null) {
        rawEntries.push(frameRaw.rawEntryTimeMs);
        displayEntries.push(frameDisplay.smoothedEntryTimeMs);
    }
}
const movement = values => values.slice(1).reduce((sum, value, index) => sum + Math.abs(value - values[index]), 0);
assert(displayEntries.length >= 5);
assert(movement(displayEntries) < movement(rawEntries), 'EMA should reduce absolute entry-time jitter');

// C. A one-frame uncertain/miss result keeps the last ETA and lets its countdown continue.
const hold = new Eta.EtaStabilizer();
hold.update(stableRaw(0, 10000), 0);
const held = hold.update({valid:false, trend:'UNCERTAIN', reason:'INTERSECTION_UNCERTAIN'}, 500);
assert.equal(held.state, 'HOLDING');
near(held.displayEtaSeconds, 9.5);

// D. A sustained miss clears after the 2000 ms hold window.
const missed = hold.update({valid:false, trend:'UNCERTAIN', reason:'LIKELY_MISSES'}, 2601);
assert.equal(missed.state, 'CLEARED');
assert.equal(missed.displayEtaSeconds, null);

// E. A sustained departing trend uses its shorter confirmation hysteresis.
const departingHistory = line(0, 6, second => ({x: 200 + 20 * second, y: 0}));
assert.equal(raw(departingHistory, 5).trend, 'DEPARTING');
const departure = new Eta.EtaStabilizer();
departure.update(stableRaw(4000, 20000), 4000);
assert.equal(departure.update(raw(departingHistory, 5), 5000).state, 'HOLDING');
assert.equal(departure.update(raw(departingHistory, 6), 6000).state, 'CLEARED');

// F. A tangent path within residual-derived tolerance is marked uncertain, not a hard miss.
const tangent = line(0, 5, second => ({x: 500 - 20 * second, y: 100}));
const tangentRaw = raw(tangent, 5);
assert.equal(tangentRaw.rawIntersectionState, 'INTERSECTION_UNCERTAIN');
assert.equal(tangentRaw.valid, false);
assert.equal(tangentRaw.reason, 'INTERSECTION_UNCERTAIN');

// G. An already-inside fitted position has an immediate ETA.
const inside = line(0, 5, second => ({x: 130 - 10 * second, y: 0}));
const insideRaw = raw(inside, 5);
assert.equal(insideRaw.rawIntersectionState, 'ALREADY_INSIDE');
assert.equal(insideRaw.rawEtaSeconds, 0);
assert.equal(insideRaw.valid, true);

// H. Stationary observations never invent an arrival time.
const stationary = line(0, 5, () => ({x: 300, y: 0}));
const stationaryRaw = raw(stationary, 5);
assert.equal(stationaryRaw.valid, false);
assert.equal(stationaryRaw.mathematicalIntersection, 'LOW_SPEED');
assert.equal(stationaryRaw.rawEtaSeconds, null);

// I. Replaying the same simulated timeline yields byte-for-byte identical frames.
function replayFrames(history) {
    const stabilizer = new Eta.EtaStabilizer();
    return [3,4,5].map(second => {
        const frameRaw = raw(history, second);
        const frameDisplay = stabilizer.update(frameRaw, second * 1000);
        return {rawEtaSeconds:frameRaw.rawEtaSeconds, rawEntryTimeMs:frameRaw.rawEntryTimeMs, displayEtaSeconds:frameDisplay.displayEtaSeconds, smoothedEntryTimeMs:frameDisplay.smoothedEntryTimeMs, state:frameDisplay.state};
    });
}
assert.deepEqual(replayFrames(noisy), replayFrames(noisy));

// J. Seeking backward resets all smoothing state before accepting the older frame.
const seek = new Eta.EtaStabilizer();
seek.update(stableRaw(10000, 30000), 10000);
const afterSeek = seek.update(stableRaw(5000, 15000), 5000);
assert.equal(afterSeek.state, 'STABLE');
assert.equal(afterSeek.smoothedEntryTimeMs, 15000);
assert.deepEqual(seek.update(stableRaw(5000, 15000), 5000), afterSeek, 're-rendering one simulation frame is idempotent');

// K. Future samples are excluded, even when their coordinates would radically alter the fit.
const futurePoisoned = straight.concat([{x:9999,y:9999,timeMs:6000}]);
const withoutFuture = raw(straight, 5), withFuture = raw(futurePoisoned, 5);
near(withFuture.motion.position.x, withoutFuture.motion.position.x);
near(withFuture.motion.vx, withoutFuture.motion.vx);
near(withFuture.rawEtaSeconds, withoutFuture.rawEtaSeconds);

// L. Position and velocity both come from the fitted line rather than mixing in the latest raw point.
const finalPointNoise = line(0, 4, second => ({x:500-20*second+(second===4?10:0),y:0}));
const fitted = Eta.estimateMotion(finalPointNoise, 4000);
assert.equal(fitted.valid, true);
assert.notEqual(fitted.position.x, finalPointNoise.at(-1).x);
const fittedGeometry = Eta.siteGeometry(fitted.position, fitted.vx, fitted.vy, site);
const fittedRaw = raw(finalPointNoise, 4);
near(fittedRaw.rawEtaSeconds, fittedGeometry.etaSeconds);
near(fittedRaw.motion.position.x, fitted.position.x);

// Input hygiene: sort, de-duplicate, and reject explicitly invalid or implausible observations.
const dirty = [
    {x:460,y:0,timeMs:2000}, {x:500,y:0,timeMs:0}, {x:480,y:0,timeMs:1000},
    {x:480,y:0,timeMs:1000}, {x:1,y:1,timeMs:1500,rejected:true}, {x:9999,y:0,timeMs:3000}
];
const clean = Eta.normalizedHistory(dirty, 3000);
assert.deepEqual(clean.map(point => point.timeMs), [0,1000,2000]);

// Ground truth is a separate evaluation helper and cannot alter estimator output.
const truthA = Eta.groundTruthEta({kind:'drone',lost:false,position:{x:500,y:0},speed:20,heading:270,waypoints:[]}, site);
const truthB = Eta.groundTruthEta({kind:'drone',lost:false,position:{x:900,y:900},speed:1,heading:0,waypoints:[]}, site);
assert.notEqual(truthA, truthB);
assert.deepEqual(raw(straight,5), straightRaw, 'estimator depends only on estimated history, time, site, and configuration');

console.log('simulation ETA: A-L stability, deterministic time, no-future-leak and fitted-state tests passed');
