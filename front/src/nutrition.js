export const nutritionUnits = ['g', 'ml', 'serving', 'package', 'piece'];
export const nutritionBases = ['stored', 'prepared'];
export const nutrientNames = { energy_kcal: 'Calories (kcal)', protein_g: 'Protein (g)', carbohydrate_g: 'Carbohydrates (g)', fat_g: 'Fat (g)', fiber_g: 'Fiber (g)', sodium_mg: 'Sodium (mg)' };
export const label = value => String(value || '').replaceAll('_', ' ').replace(/^./, value => value.toUpperCase());
export const displayNumber = value => value == null ? 'Unknown' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 6 });
export const utcDay = value => new Date(value).toISOString().slice(0, 10);
export const localDateTime = value => { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
export function equivalents(product) {
  if (!product) return [];
  return [{ unit: product.reference_unit, basis: product.reference_basis, quantity_per_reference: product.reference_quantity }, ...product.unit_equivalences];
}
export function referenceAmount(product, unit, basis) {
  const found = equivalents(product).find(entry => entry.unit === unit && entry.basis === basis);
  if (!found) throw Error(`No registered equivalence for ${product?.name || 'this product'}: ${basis} ${unit}`);
  return Number(found.quantity_per_reference);
}
export function usableLots(lots, productId, consumedAt) {
  let day;
  try { day = utcDay(consumedAt); } catch { return []; }
  return lots.filter(lot => lot.food_product_id === Number(productId) && Number(lot.remaining_quantity) > 0 && lot.expiration_date >= day).sort((a, b) => a.expiration_date.localeCompare(b.expiration_date) || a.id - b.id);
}
export async function nutritionPages(request, path, filters = {}) {
  const rows = [];
  for (let page = 1; ; page++) {
    const result = await request(`${path}?${new URLSearchParams({ ...filters, page: String(page), per_page: '100' })}`);
    rows.push(...result.data);
    if (!result.pagination.has_next) return rows;
  }
}
export function previewNutrition(items, products) {
  const nutrients = Object.fromEntries(Object.keys(nutrientNames).map(key => [key, 0]));
  const partial = Object.fromEntries(Object.keys(nutrientNames).map(key => [key, false]));
  let beverage = 0, water = 0, preparation = 0, beveragePartial = false, waterPartial = false;
  const errors = [];
  for (const item of items) {
    const product = item.id && item._snapshot ? item._snapshot : products.find(row => row.id === Number(item.food_product_id));
    if (!product || !(Number(item.consumed_quantity) > 0)) continue;
    try {
      const factor = Number(item.consumed_quantity) / referenceAmount(product, item.consumed_unit, item.consumed_basis);
      for (const key of Object.keys(nutrients)) {
        if (product[key] == null) partial[key] = true;
        else nutrients[key] += Number(product[key]) * factor;
      }
      if (product.category === 'beverage') {
        try {
          const volume = referenceAmount(product, 'ml', item.consumed_basis) * factor;
          beverage += volume;
          if (product.is_plain_water) water += volume;
        } catch {
          beveragePartial = true;
          if (product.is_plain_water) waterPartial = true;
        }
      }
      preparation += Number(item.preparation_water_used_ml || 0);
    } catch (error) { errors.push(error.message); }
  }
  return { nutrients, partial, beverage_volume_ml: beverage, plain_water_volume_ml: water, preparation_water_used_ml: preparation, beverage_volume_partial: beveragePartial, plain_water_volume_partial: waterPartial, errors };
}
