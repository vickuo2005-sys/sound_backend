const assert = require('node:assert/strict');
const Tracking = require('../../static/dashboard_simulation_tracker.js');

const tracker = new Tracking.AlphaBetaTracker({measurementIntervalMs:1000});
let first = tracker.update({x:0,y:0}, 0);
assert.equal(first.accepted, true);
assert.equal(first.state.x, 0);
assert.equal(first.state.vx, 0);

// A changed localization measurement is a correction, not a teleport.
let second = tracker.update({x:100,y:0}, 1000);
assert.equal(second.accepted, true);
assert(second.state.x > 0 && second.state.x < 100);
assert(second.state.vx > 0);

// Between measurements the track predicts continuously.
const mid = tracker.predict(1500);
assert(mid.x > second.state.x);
assert.equal(mid.source, 'simulation_alpha_beta_track');

// Same timestamp cannot rewrite the track.
const before = tracker.predict(1000);
const duplicate = tracker.update({x:500,y:0}, 1000);
assert.equal(duplicate.accepted, false);
assert.equal(duplicate.reason, 'NON_INCREASING_MEASUREMENT_TIME');
assert.equal(tracker.predict(1000).x, before.x);

// Physically implausible measurement is rejected.
const gated = new Tracking.AlphaBetaTracker({measurementIntervalMs:1000,maxSpeedMps:80,baseGateM:10});
gated.update({x:0,y:0}, 0);
const jump = gated.update({x:1000,y:0}, 1000);
assert.equal(jump.accepted, false);
assert.equal(jump.reason, 'INNOVATION_GATE_EXCEEDED');

// Stale prediction expires instead of drifting forever.
const stale = new Tracking.AlphaBetaTracker({maxPredictionAgeMs:2000});
stale.update({x:0,y:0}, 0);
assert(stale.predict(1999));
assert.equal(stale.predict(2001), null);

console.log('simulation alpha-beta tracker tests passed');
