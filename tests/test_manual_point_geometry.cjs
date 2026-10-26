const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../inserter_platform/static/app.js'), 'utf8');
const names = ['normalizeBoardCalibration', 'storedBoardCalibration', 'boardBaseMetrics', 'boardMapMetrics',
  'applyBoardCalibrationToNormalizedPoint', 'invertBoardCalibrationFromNormalizedPoint',
  'boardPointPosition', 'manualCoordinatesFromClick', 'manualPointContext'];
const context = vm.createContext({});
for (const name of names) {
  const match = source.match(new RegExp(`function ${name}\\([^]*?\\n\\}`));
  assert.ok(match, name);
  vm.runInContext(match[0], context);
}

function project(calibration = {}) {
  return { board_width: 100, board_height: 50, board_image_path: 'pcb.svg', updated_at: 't',
    board_calibration: calibration, points: [{ id: 1, designator: 'R1', x: 5, y: 40, source: 'pp' }] };
}

for (const rotation of [0, 90, 180, 270]) {
  test(`click round-trip, rotation ${rotation}, mirrors, scales, offsets and zoom`, () => {
    for (const flipX of [false, true]) for (const flipY of [false, true]) for (const zoom of [1, 2.4]) {
      const p = project({ rotation, flipX, flipY, scaleX: .8, scaleY: 1.1, offsetX: 3, offsetY: -2 });
      const metrics = context.boardMapMetrics(p, p.points);
      const point = { x: 32, y: 21 };
      const position = context.boardPointPosition(point, metrics);
      const rect = { left: -150, top: -80, width: 800 * zoom, height: 400 * zoom };
      const actual = context.manualCoordinatesFromClick({ currentTarget: { getBoundingClientRect: () => rect },
        clientX: rect.left + position.x / 100 * rect.width, clientY: rect.top + position.y / 100 * rect.height }, p);
      assert.ok(Math.abs(actual.x - point.x) < 1e-9);
      assert.ok(Math.abs(actual.y - point.y) < 1e-9);
    }
  });
}

test('click outside calibrated board is rejected, not silently clamped to an edge', () => {
  const p = project({ scaleX: .5, scaleY: .5 });
  assert.throws(() => context.manualCoordinatesFromClick({ currentTarget: { getBoundingClientRect: () => ({left: 0, top: 0, width: 100, height: 50}) },
    clientX: 1, clientY: 1 }, p), /poza skalibrowanym/);
});

test('new manual point cannot move frame, swap axes, or alter geometry reference snapshot', () => {
  const p = project();
  const before = JSON.stringify(context.boardBaseMetrics(p, p.points));
  const beforeContext = JSON.stringify(context.manualPointContext(p));
  p.points.push({ id: 2, designator: 'Z_K5K6', x: -900, y: 800, source: 'manual' });
  assert.equal(JSON.stringify(context.boardBaseMetrics(p, p.points)), before);
  assert.equal(JSON.stringify(context.manualPointContext(p)), beforeContext);
});

test('offset Gerber origin maps clicks back to source coordinates', () => {
  const p = project({ rotation: 270 });
  p.board_contours = { profile: { fromProfile: true, x: 200, y: 300, width: 100, height: 50 } };
  p.points = [{ id: 1, designator: 'R1', x: 205, y: 340 }];
  const metrics = context.boardMapMetrics(p, p.points);
  assert.equal(metrics.originX, 200);
  const position = context.boardPointPosition({ x: 232, y: 321 }, metrics);
  const actual = context.manualCoordinatesFromClick({ currentTarget: { getBoundingClientRect: () => ({left: 0, top: 0, width: 500, height: 1000}) },
    clientX: position.x * 5, clientY: position.y * 10 }, p);
  assert.ok(Math.abs(actual.x - 232) < 1e-9);
  assert.ok(Math.abs(actual.y - 321) < 1e-9);
});
