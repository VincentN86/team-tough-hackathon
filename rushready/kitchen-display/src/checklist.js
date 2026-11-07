// Derive the confirmation checklist from an order.
// Every allergy and every modifier becomes one row. Allergies always come first.

export const modKey = (modifierId) => `mod:${modifierId}`;
export const allergyKey = (allergyId) => `allergy:${allergyId}`;

export function allergyText(allergy) {
  const base = `${allergy.allergen} allergy`;
  return allergy.note ? `${base} — ${allergy.note}` : base;
}

/** @returns {import('./model.js').ChecklistItem[]} */
export function buildChecklist(order) {
  const itemName = new Map(order.items.map((it) => [it.id, it.name]));
  const rows = [];
  for (const a of order.allergies ?? []) {
    rows.push({
      key: allergyKey(a.id),
      type: 'allergy',
      orderId: order.id,
      itemId: a.itemId ?? null,
      itemName: a.itemId ? itemName.get(a.itemId) ?? 'Unknown item' : 'Whole order',
      text: allergyText(a),
      matchText: `${a.allergen} allergy`, // what staff will say out loud
      allergen: a.allergen,
      severity: a.severity ?? 'standard',
    });
  }
  for (const item of order.items) {
    for (const m of item.modifiers ?? []) {
      rows.push({
        key: modKey(m.id),
        type: 'modifier',
        orderId: order.id,
        itemId: item.id,
        itemName: item.name,
        text: m.text,
        matchText: m.text,
      });
    }
  }
  return rows;
}
