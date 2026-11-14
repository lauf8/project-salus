export function allergyStatus(record) {
  if (!record.allergy_screening_completed) return "Screening pending";
  return record.active_ingredients.length ? "Allergies recorded" : "No known allergies";
}
