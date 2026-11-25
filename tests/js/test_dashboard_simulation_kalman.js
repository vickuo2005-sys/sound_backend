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


// Deterministic straight-line noise regression: Kalman should reduce position RMSE
// versus the raw measurements after the initial warm-up.
const noisy = new Kalman.ConstantVelocityKalman2D({
  processAccelerationSigmaMps2: 1,
  defaultMeasurementSigmaM: 12,
  measurementIntervalMs: 1000
});
const noisePattern = [8,-7,6,-9,7,-6,9,-8,5,-7,8,-5,6,-8,7,-6,5,-7,6,-5];
let rawSq=0, filteredSq=0, n=0;
for(let i=0;i<noisePattern.length;i++) {
  const truthX=i*10;
  const measuredX=truthX+noisePattern[i];
  const out=noisy.update({x:measuredX,y:0},i*1000,{uncertaintyM:12});
  const filteredX=out.state?.x;
  if(i>=3 && Number.isFinite(filteredX)) {
    rawSq += (measuredX-truthX)**2;
    filteredSq += (filteredX-truthX)**2;
    n++;
  }
}
const rawRmse=Math.sqrt(rawSq/n);
const filteredRmse=Math.sqrt(filteredSq/n);
assert.ok(
  filteredRmse < rawRmse,
  `Kalman should reduce straight-line position RMSE (raw=${rawRmse.toFixed(2)}, filtered=${filteredRmse.toFixed(2)})`
);

console.log(`dashboard_simulation_kalman RMSE raw=${rawRmse.toFixed(2)}m filtered=${filteredRmse.toFixed(2)}m`);
