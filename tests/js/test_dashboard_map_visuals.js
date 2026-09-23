const assert=require('node:assert/strict');
const V=require('../../static/dashboard_map_visuals.js');

assert.equal(typeof V.pulseAt,'function');
assert.equal(typeof V.nodeVisual,'function');
assert.equal(typeof V.regionStyle,'function');
assert.equal(typeof V.sampleMotion,'function');

const inactive=V.nodeVisual(true,false,.5);
const active=V.nodeVisual(true,true,.5);
assert.equal(inactive.shape,'circle');
assert.equal(active.shape,'circle');
assert.equal(active.fill,V.COLORS.active);
assert(active.scale>inactive.scale);

const line=V.regionStyle('line');
const polygon=V.regionStyle('polygon');
assert.equal(line.strokeWeight,5);
assert.equal(line.strokeOpacity,.95);
assert.equal(polygon.strokeWeight,3);
assert.equal(polygon.strokeOpacity,.85);
assert.equal(polygon.fillOpacity,.12);

const p0=V.pulseAt(0),p1=V.pulseAt(180);
assert(p0>=0&&p0<=1);
assert(p1>=0&&p1<=1);
assert.notEqual(p0,p1);

const motion={
  start:{lat:25,lng:121},
  target:{lat:25.001,lng:121.002},
  startHeading:350,
  targetHeading:10,
  startedAt:0,
  durationMs:1000
};
const mid=V.sampleMotion(motion,500);
assert(mid.position.lat>25&&mid.position.lat<25.001);
assert(mid.position.lng>121&&mid.position.lng<121.002);
assert(mid.heading<15||mid.heading>345,'heading should interpolate through 0 degrees');
assert.equal(V.sampleMotion(motion,1000).done,true);

console.log('shared dashboard map visuals passed');


const maps={SymbolPath:{CIRCLE:'circle'}};
const siteMarker=V.siteMarkerStyle(maps);
const siteZone=V.siteZoneStyle();
assert.equal(siteMarker.icon.path,'circle');
assert.equal(siteMarker.icon.scale,16);
assert.equal(siteMarker.icon.fillColor,'#5EEAD4');
assert.equal(siteMarker.icon.strokeColor,'#0B1220');
assert.equal(siteMarker.label.text,'據點');
assert.equal(siteZone.strokeColor,'#FBBF24');
assert.equal(siteZone.fillColor,'#FBBF24');
assert.equal(siteZone.fillOpacity,.1);
