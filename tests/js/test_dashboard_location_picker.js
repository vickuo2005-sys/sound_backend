const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('templates/dashboard_v2_4.html', 'utf8');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value:'', dataset:{}, textContent:''});
  return elements.get(id);
};
const context = vm.createContext({
  locationTokenRequired:true,
  document:{getElementById:element},
  state:{locationBusy:false, locationEditDeviceId:'node_A01', locationClearArmed:true},
  syncLocationPickerMarker:()=>{},
});
function include(name, next) {
  const start = html.indexOf(`        function ${name}(`);
  const end = html.indexOf(`        ${next}`, start);
  assert(start >= 0 && end > start);
  vm.runInContext(html.slice(start,end), context);
}
include('finite', 'function parseTime');
include('chooseLocationPoint', 'function openLocationPicker');
include('validateLocationEditor', 'async function saveFixedLocation');
element('locationWriteToken').value = 'test-only-token';
element('locationAccuracy').value = '26';
context.chooseLocationPoint({lat:()=>25.0441234,lng:()=>121.5412345});
let payload = context.validateLocationEditor();
assert.equal(payload.latitude,25.044123);
assert.equal(payload.longitude,121.541235);
assert.equal(payload.location_source,'manual_map');
assert.equal(payload.accuracy_m,null); // Never reuse GPS accuracy for a map click.
assert.equal(context.state.locationClearArmed,false);
context.state.locationBusy = true;
context.chooseLocationPoint({lat:()=>0,lng:()=>0});
assert.equal(element('locationLatitude').value,'25.044123');
element('locationLatitude').value = '';
assert.throws(()=>context.validateLocationEditor(), /緯度/);
element('locationLatitude').value = '91';
assert.throws(()=>context.validateLocationEditor(), /緯度/);
console.log('Location picker coordinates, request source and busy guard passed');

context.locationTokenRequired = false;
element('locationLatitude').value = '25';
element('locationWriteToken').value = '';
assert.equal(context.validateLocationEditor().latitude,25);
context.locationTokenRequired = true;
assert.throws(()=>context.validateLocationEditor(), /授權碼/);

context.state.locationBusy = false;
context.manualLocationInput('locationLatitude');
assert.equal(element('locationAccuracy').value, '');
element('locationAccuracy').value = '7';
context.manualLocationInput('locationAccuracy');
assert.equal(element('locationAccuracy').value, '7');
assert.equal(element('locationEditorModal').dataset.locationSource, 'manual_map');

context.locationEditorDevice = () => ({raw_latitude:25, raw_longitude:121, gps_accuracy_m:null});
context.locationPickerMap = null;
include('useCurrentGpsForLocation', 'function locationRequestHeaders');
context.useCurrentGpsForLocation();
assert.equal(element('locationAccuracy').value, '');
assert.equal(element('locationEditorModal').dataset.locationSource, 'current_gps');

context.state.devices = new Map([['node_A01', {fixed_latitude:26, fixed_longitude:122,
  fixed_location_accuracy_m:null, gps_accuracy_m:3, fixed_location_source:'manual_map'}]]);
context.shortNodeId = value => value;
context.displayLocationSource = () => '固定位置';
context.setLocationBusy = () => {};
context.openLocationPicker = () => {};
element('locationLatitude').focus = () => {};
include('openLocationEditor', 'function closeLocationEditor');
context.openLocationEditor('node_A01');
assert.equal(element('locationAccuracy').value, '');
assert.equal(element('locationLatitude').value, 26);
assert.equal(element('locationEditorModal').dataset.locationSource, 'manual_map');
