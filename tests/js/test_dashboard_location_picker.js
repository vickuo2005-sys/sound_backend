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
assert.throws(()=>context.validateLocationEditor(), /Latitude/);
element('locationLatitude').value = '91';
assert.throws(()=>context.validateLocationEditor(), /Latitude/);
console.log('Location picker coordinates, request source and busy guard passed');
