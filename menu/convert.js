'use strict';

const fs   = require('fs');
const path = require('path');

// Usage: node convert.js [input.json] [output.json]
// Defaults: scanned-menu.json → menu.json (relative to this script's directory)
const args    = process.argv.slice(2);
const menuPath = path.resolve(args[0] || path.join(__dirname, 'scanned-menu.json'));
const outPath  = path.resolve(args[1] || path.join(__dirname, 'menu.json'));

// ── Timing parser ────────────────────────────────────────────────────────────

function parseHalf(raw) {
  const s = raw.trim().toLowerCase();
  if (s === '12 noon' || s === 'noon') return '12:00';
  const m = s.match(/^(\d+)(?:[.:,](\d+))?\s*(am|pm)$/);
  if (!m) return null;
  let h = parseInt(m[1], 10);
  const min = m[2] ? parseInt(m[2], 10) : 0;
  const meridiem = m[3];
  if (meridiem === 'am') {
    if (h === 12) h = 0;
  } else {
    if (h !== 12) h += 12;
  }
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function parseTiming(raw) {
  if (!raw) return { startTime: '00:00', endTime: '23:59' };

  // Some sections have two shifts: "12 noon to 3.30 pm - 7 pm to 10.30 pm"
  // Use widest window: first shift start → last shift end
  const shifts = raw.split(/\s*-\s*/);
  const parsed = shifts.map(shift => {
    const parts = shift.split(/\s+to\s+/i);
    if (parts.length !== 2) return null;
    const start = parseHalf(parts[0]);
    const end   = parseHalf(parts[1]);
    return (start && end) ? { start, end } : null;
  }).filter(Boolean);

  if (!parsed.length) {
    console.warn(`  WARN: could not parse timing "${raw}", defaulting to 00:00-23:59`);
    return { startTime: '00:00', endTime: '23:59' };
  }

  return { startTime: parsed[0].start, endTime: parsed[parsed.length - 1].end };
}

// Convert an all-uppercase string to title case. Leaves already-mixed-case
// strings (e.g. item names like "Coffee / Tea") untouched.
function toMixedCase(s) {
  if (!s || !/[a-zA-Z]/.test(s) || s !== s.toUpperCase()) return s;
  return s.toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase());
}

// ── Main ─────────────────────────────────────────────────────────────────────

const menu = JSON.parse(fs.readFileSync(menuPath, 'utf8')).menu;

const languages = [
  { code: 'en', name: 'English' },
  { code: 'kn', name: 'Kannada' },
];

let idSeq = 0;
function nextId() { return ++idSeq; }

let slashSplitCount = 0;

// Items whose English name contains " / " represent a customer choice between
// two equivalent variants priced the same. Split them into separate items so
// each variant can be ordered or displayed independently.
function splitSlashVariants(src) {
  const SEP_EN = ' / ';
  const SEP_KN = ' /';

  if (!src.name.includes(SEP_EN)) return [src];

  slashSplitCount++;
  const enParts = src.name.split(SEP_EN);
  const knParts = src.name_kannada ? src.name_kannada.split(SEP_KN) : [];

  return enParts.map((enName, i) => ({
    ...src,
    name: enName.trim(),
    name_kannada: (knParts[i] || '').trim() || null,
  }));
}

function buildItems(itemsArray) {
  const result = [];
  (itemsArray || []).forEach((src, idx) => {
    const timing = parseTiming(src.timings || null);
    const displayOrder = idx + 1;

    if (src.price_dry != null && src.price_gravy != null) {
      // Item offered in two preparation styles at different prices
      for (const [preparationType, price] of [['dry', src.price_dry], ['gravy', src.price_gravy]]) {
        for (const variant of splitSlashVariants(src)) {
          const enName = toMixedCase(variant.name);
          const knName = variant.name_kannada;
          result.push({
            id: nextId(),
            name: enName,
            displayOrder,
            preparationType,
            startTime: timing.startTime,
            endTime: timing.endTime,
            itemText: [
              { langCode: 'en', name: enName },
              ...(knName ? [{ langCode: 'kn', name: knName }] : []),
            ],
            price,
          });
        }
      }
    } else {
      // Single price; may still be a slash-separated choice
      for (const variant of splitSlashVariants(src)) {
        const enName = toMixedCase(variant.name);
        const knName = variant.name_kannada;
        result.push({
          id: nextId(),
          name: enName,
          displayOrder,
          preparationType: null,
          startTime: timing.startTime,
          endTime: timing.endTime,
          itemText: [
            { langCode: 'en', name: enName },
            ...(knName ? [{ langCode: 'kn', name: knName }] : []),
          ],
          price: src.price,
        });
      }
    }
  });
  return result;
}

function buildSection(key, src, displayOrder, parentId) {
  const id     = nextId();
  const timing = parseTiming(src.timings || null);

  const enName = toMixedCase(src.section_name || src.sub_section_name || key);
  const knName = src.section_name_kannada || src.sub_section_name_kannada || null;

  const sectionText = [{ langCode: 'en', name: enName }];
  if (knName) sectionText.push({ langCode: 'kn', name: knName });

  const childSections = src.sub_sections
    ? Object.entries(src.sub_sections).map(([subKey, subSrc], subIdx) =>
        buildSection(subKey, subSrc, subIdx + 1, id))
    : [];

  return {
    id,
    parentId,
    sectionKey: key,
    name: enName,
    displayOrder,
    startTime: timing.startTime,
    endTime: timing.endTime,
    sectionText,
    item: buildItems(src.items),
    section: childSections,
  };
}

const section = Object.entries(menu).map(([key, src], idx) =>
  buildSection(key, src, idx + 1, null));

fs.writeFileSync(outPath, JSON.stringify({ languages, section }, null, 2), 'utf8');

let totalSections = 0, totalItems = 0;
function countSection(s) {
  totalSections++;
  totalItems += s.item.length;
  s.section.forEach(countSection);
}
section.forEach(countSection);

console.log('Input  :', menuPath);
console.log('Output :', outPath);
console.log('  languages   :', languages.length);
console.log('  sections    :', totalSections, '(all levels)');
console.log('  items       :', totalItems);
console.log('  slash splits:', slashSplitCount, 'source items expanded into pairs');
