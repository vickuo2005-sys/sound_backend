const assert = require('assert');
const Kalman = require('../../static/dashboard_simulation_kalman.js');

const k = new Kalman.ConstantVelocityKalman2D({
  processAccelerationSigmaMps2: 1,
  defaultMeasurementSigmaM: 10,
  measurementIntervalMs: 1000
});

let r = k.update({x:0,y:0},0,{uncertaintyM:10});
assert.equal(r.accepted,true);
assert.equal(r.reason,'INITIALIZED');
assert.equal(k.shouldAcceptMeasurement(500),false);
assert.equal(k.shouldAcceptMeasurement(1000),true);

r = k.update({x:12,y:0},1000,{uncertaintyM:10});
assert.equal(r.accepted,true);
assert.equal(r.reason,'UPDATED');
assert.ok(Number.isFinite(r.state.x));
assert.ok(Number.isFinite(r.state.vx));
assert.ok(r.state.x > 0 && r.state.x < 12);

for(let i=2;i<=8;i++) {
  const noise = i % 2 === 0 ? 3 : -3;
  k.update({x:i*10+noise,y:0},i*1000,{uncertaintyM:10});
}
const state=k.predict(8000);
assert.ok(Math.abs(state.vx-10)<5, 'velocity should converge near constant-velocity truth');
assert.ok(Math.abs(state.y)<1);
assert.equal(state.source,'simulation_kalman_cv');
assert.ok(state.uncertaintyM>0);

const invalid=k.update({x:NaN,y:0},9000);
assert.equal(invalid.accepted,false);
assert.equal(invalid.reason,'INVALID_MEASUREMENT');

const duplicate=k.update({x:90,y:0},8000);
assert.equal(duplicate.accepted,false);
assert.equal(duplicate.reason,'NON_INCREASING_MEASUREMENT_TIME');

console.log('dashboard_simulation_kalman: all assertions passed');
