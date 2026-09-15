const assert = require('node:assert/strict');
const lab = require('../../static/dashboard_simulation_lab.js');

// Exercise the production controller and its rendered HTML without a browser.
// This host implements only the DOM methods used by Workspace; it does not
// replace handleClick, mapClick, rendering, or any model behavior.
function createHost() {
    const elements = new Map();
    const host = {
        focused: null,
        contains() { return true; },
        addEventListener() {}, removeEventListener() {},
        querySelector(selector) { return elements.get(selector) ?? null; }
    };

    function registerHTML(owner, html) {
        // Index only elements actually present in production HTML. Missing slots
        // must return null, as they do in a browser, rather than be invented by
        // the host and hide errors during mounting or a later rerender.
        for (const [selector, element] of elements) {
            for (let ancestor = element.owner; ancestor; ancestor = ancestor.owner) {
                if (ancestor === owner) { elements.delete(selector); break; }
            }
        }
        for (const tag of html.matchAll(/<([a-z][\w-]*)\b([^>]*)>/gi)) {
            const attributes = new Map(Array.from(tag[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g), match => [match[1], match[2] ?? '']));
            const selectors = ['field', 'slot', 'action'].filter(type => attributes.has(`data-${type}`)).map(type => `[data-${type}="${attributes.get(`data-${type}`)}"]`);
            if (!selectors.length) continue;
            const classes = new Set((attributes.get('class') || '').split(/\s+/));
            const element = {
                owner, value: attributes.get('value') ?? '', textContent: '', hidden: attributes.has('hidden'),
                dataset: Object.fromEntries(Array.from(attributes).filter(([name]) => name.startsWith('data-')).map(([name, value]) => [name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase()), value])),
                classList: {
                    add(...names) { names.forEach(name => classes.add(name)); },
                    remove(...names) { names.forEach(name => classes.delete(name)); },
                    toggle(name, force) { const on = force ?? !classes.has(name); if (on) classes.add(name); else classes.delete(name); return on; },
                    contains(name) { return classes.has(name); }
                },
                setAttribute(name, value) { attributes.set(name, String(value)); },
                getAttribute(name) { return attributes.get(name) ?? null; },
                removeAttribute(name) { attributes.delete(name); },
                focus() { host.focused = element; },
                scrollIntoView() {},
                setCustomValidity(message) { element.validationMessage = message; },
                reportValidity() { return !element.validationMessage; }
            };
            if (tag[1].toLowerCase() === 'select') {
                const selectHTML = html.slice(tag.index + tag[0].length).split('</select>')[0];
                const options = Array.from(selectHTML.matchAll(/<option\b([^>]*)>/gi));
                const chosen = options.find(option => /\bselected\b/.test(option[1])) ?? options[0];
                element.value = chosen?.[1].match(/value="([^"]*)"/)?.[1] ?? '';
            }
            addHTMLProperty(element);
            for (const selector of selectors) if (!elements.has(selector)) elements.set(selector, element);
        }
    }
    function addHTMLProperty(element) {
        let current = '';
        Object.defineProperty(element, 'innerHTML', {
            get() { return current; },
            set(value) { current = String(value); registerHTML(element, current); }
        });
    }
    addHTMLProperty(host);
    return host;
}

function setup() {
    const host = createHost();
    const workspace = lab.mount(host);
    return {
        host, workspace, model: workspace.model,
        field(name) { return workspace.field(name); },
        slot(name) { return host.querySelector(`[data-slot="${name}"]`); },
        click(action, id) {
            const button = { dataset: { action, id } };
            workspace.handleClick({ target: { closest(selector) { return selector === '[data-action]' ? button : null; } }, preventDefault() {}, stopPropagation() {} });
        }
    };
}

let failures = 0;
function test(name, run) {
    try { run(); console.log(`PASS ${name}`); }
    catch (error) { failures += 1; console.error(`FAIL ${name}\n${error.stack}`); }
    finally { lab.destroy(); }
}

for (const phase of ['idle', 'playing', 'replaying', 'paused replay']) {
    for (const clear of ['clear-targets', 'clear-all', 'clear-nodes', 'clear-history']) {
        test(`${phase}: ${clear} permits two consecutive additions and map placements`, () => {
            const ui = setup();
            ui.model.preset('approach');
            ui.model.step(3);
            ui.model.playing = phase === 'playing';
            if (phase.includes('replay')) {
                ui.model.replayEvent(ui.model.events[0].id);
                ui.model.replay.playing = phase === 'replaying';
            }
            ui.workspace.mode = 'move-target';
            ui.workspace.editTarget = ui.model.selectedId;
            ui.workspace.editNode = ui.model.nodes[0].id;
            ui.click(clear);
            assert.equal(ui.workspace.mode, 'inspect');
            assert.equal(ui.workspace.editTarget, null, 'clear removes a pending target edit');
            assert.equal(ui.workspace.editNode, null, 'clear removes a pending node edit');
            assert.equal(ui.model.replay, null, 'clearing returns to the editable current scene');

            for (let i = 0; i < 2; i += 1) {
                const previous = new Set(ui.model.targets.map(target => target.id));
                ui.click('create');
                const created = ui.model.targets.find(target => !previous.has(target.id));
                assert(created, 'the create button must add a target before any map click');
                assert(ui.slot('fleet').innerHTML.includes(created.id), 'the added target must immediately have a visible setup row');
                assert.equal(created.position, null);
                assert.equal(ui.workspace.editTarget, created.id);
                assert.equal(ui.model.selectedId, created.id);
                assert.equal(ui.model.playing, false);
                const position = { x: 1000 + i * 100, y: 300 + i * 50 };
                ui.workspace.mapClick(position);
                assert.deepEqual(created.position, position);
                assert(ui.slot('fleet').innerHTML.includes('起點 已設定'));
            }
        });
    }
}

for (const clear of ['clear-targets', 'clear-all']) {
    test(`${clear} resets stale sound and invalid motion inputs`, () => {
        const ui = setup();
        ui.field('kind').value = 'car';
        ui.field('speed').value = '101';
        ui.field('heading').value = '360';
        ui.click(clear);
        assert.equal(ui.field('kind').value, 'drone');
        assert.equal(Number(ui.field('speed').value), 25);
        assert.equal(Number(ui.field('heading').value), 90);
        ui.click('create');
        assert.equal(ui.model.targets.length, 1);
        assert.equal(ui.model.targets[0].kind, 'drone');
        assert(ui.slot('fleet').innerHTML.includes(ui.model.targets[0].id));
    });
}

for (const kind of ['drone', 'car', 'airplane', 'rainfall', 'electric_saw']) {
    test(`creating ${kind} never produces a hidden setup target`, () => {
        const ui = setup();
        ui.click('clear-targets');
        ui.field('kind').value = kind;
        ui.click('create');
        const target = ui.model.targets[0];
        assert(target);
        assert.equal(target.kind, kind);
        assert(ui.slot('fleet').innerHTML.includes(target.id), 'every supported sound type remains editable in the setup list');
        ui.workspace.mapClick({ x: 1000, y: 250 });
        assert.deepEqual(target.position, { x: 1000, y: 250 });
    });
}

for (const [name, value] of [['speed', '-1'], ['speed', '101'], ['heading', '-1'], ['heading', '360']]) {
    test(`invalid ${name}=${value} shows nearby feedback and focuses the invalid field`, () => {
        const ui = setup();
        ui.field(name).value = value;
        ui.click('create');
        assert.equal(ui.model.targets.length, 0);
        assert(ui.slot('create-message').textContent.trim(), 'validation feedback must appear beside the create controls');
        assert.equal(ui.host.focused, ui.field(name));
        assert.equal(ui.field(name).getAttribute('aria-invalid'), 'true');
        ui.field(name).value = name === 'speed' ? '25' : '90';
        ui.click('create');
        assert.equal(ui.model.targets.length, 1, 'correcting the value allows immediate creation');
        assert(ui.slot('fleet').innerHTML.includes(ui.model.targets[0].id));
    });
}

test('newly added drone stays selected despite an existing warning', () => {
    const ui = setup();
    ui.model.preset('inside');
    assert(ui.model.alerts.length);
    const warningTarget = ui.model.selectedId;
    ui.model.playing = true;
    ui.click('create');
    const target = ui.model.targets.at(-1);
    assert.notEqual(target.id, warningTarget);
    assert.equal(ui.model.selectedId, target.id);
    assert.equal(ui.workspace.editTarget, target.id);
    assert.equal(ui.model.playing, false);
    assert(ui.slot('fleet').innerHTML.includes(`data-id="${target.id}"`));
});

test('editing a start position exits active replay and updates the visible current scene', () => {
    const ui = setup();
    ui.model.preset('approach');
    ui.model.step(3);
    const target = ui.model.selected();
    ui.model.replayEvent(ui.model.events[0].id);
    assert(ui.model.replay.playing);
    ui.click('edit-target-start', target.id);
    assert.equal(ui.model.replay, null);
    assert.equal(ui.model.playing, false);
    ui.workspace.mapClick({ x: 1200, y: 350 });
    assert.deepEqual(target.position, { x: 1200, y: 350 });
    assert(ui.slot('map').innerHTML.includes(`#${target.id.replace('SIM-TARGET-', '')}`));
});

test('route points stay attached to the edited drone when alert selection changes', () => {
    const ui = setup();
    const other = ui.model.createEvent({ position: { x: 0, y: 0 }, speed: 0 });
    const edited = ui.model.createEvent({ position: { x: 1000, y: 0 }, speed: 25 });
    ui.model.playing = true;
    ui.click('edit-target-route', edited.id);
    assert.equal(ui.model.playing, false);
    assert.equal(ui.workspace.editTarget, edited.id);
    ui.model.selectedId = other.id;
    ui.workspace.mapClick({ x: 1200, y: 100 });
    assert.deepEqual(edited.waypoints, [{ x: 1200, y: 100 }]);
    assert.deepEqual(other.waypoints, []);
});

test('a removed target cannot produce a false successful placement', () => {
    const ui = setup();
    const target = ui.model.createEvent({ position: null });
    ui.click('edit-target-start', target.id);
    ui.model.clearTargets();
    ui.slot('message').textContent = '';
    ui.workspace.mapClick({ x: 1000, y: 200 });
    const feedback = `${ui.slot('message').textContent} ${ui.slot('create-message').textContent}`;
    assert.equal(ui.model.targets.length, 0);
    assert(feedback.trim(), 'missing target should be explained to the user');
    assert(!feedback.includes('已設定這台目標的起點'), 'failed placement must not claim success');
});

test('node placement continues past twelve and enforces the new 100-node capacity', () => {
    const ui = setup();
    ui.click('clear-all');
    ui.click('place-node');
    for (let i = 0; i < 100; i += 1) ui.workspace.mapClick({ x: i * 3, y: i * 2 });
    assert.equal(ui.model.nodes.length, 100);
    assert.equal(lab.LIMITS.nodes, 100);
    assert(ui.slot('nodes').innerHTML.includes('節點 100'));
    ui.workspace.mapClick({ x: 500, y: 400 });
    assert.equal(ui.model.nodes.length, 100);
    assert(ui.slot('message').textContent.includes('100'));
});

if (failures) process.exitCode = 1;
else console.log('simulation lab controls: clear/recreate, visible targets, validation, edit isolation and node capacity passed');
