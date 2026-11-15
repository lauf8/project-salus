SOURCE_URL = 'https://www.nasa.gov/wp-content/uploads/2024/09/ochmo-std-100-1a-rev-a-signed.pdf'
SOURCE_NAME = 'OCHMO-STD-100.1A, Rev. A (09/09/2024)'
APPLICABILITY = 'Selection, recertification or mission assessment as medically indicated. The medical team defines applicability and timing for each crew member. Fields and units are adapted for recording; they do not establish fitness or automatic clinical limits.'

EXAM_TYPES = [
    ('laboratory', 'Laboratory'),
    ('cardiology', 'Cardiology'),
    ('ophthalmology', 'Ophthalmology'),
    ('otolaryngology', 'Otolaryngology'),
    ('pulmonology', 'Pulmonary'),
    ('imaging', 'Diagnostic imaging'),
    ('clinical_assessment', 'Clinical assessment'),
    ('dental', 'Dental'),
    ('behavioral_health', 'Behavioral health'),
]


def number(code, label, unit, required=False):
    return dict(code=code, label=label, type='number', unit=unit, required=required)


def notes(code='findings', label='Findings and notes', required=False):
    return dict(code=code, label=label, type='textarea', required=required)


def choice(code, label, options, required=False):
    return dict(code=code, label=label, type='select', required=required, options=[dict(value=value, label=text) for value, text in options])


def exam(code, name, category, fields, page, section, specimen=None, preparation=None, description=None):
    return dict(code=code, name=name, category=category, fields=fields, source_page=page, source_section=f'{SOURCE_NAME} · {section}', source_url=SOURCE_URL, specimen=specimen, preparation=preparation, description=description or name, applicability_notes=APPLICABILITY, is_active=True)


EXAMS = [
    exam('complete_blood_count', 'Complete blood count', 'laboratory', [number('hemoglobin', 'Hemoglobin', 'g/dL', True), number('hematocrit', 'Hematocrit', '%'), number('red_blood_cells', 'Red blood cells', '10⁶/µL'), number('mcv', 'MCV', 'fL'), number('mch', 'MCH', 'pg'), number('mchc', 'MCHC', 'g/dL'), number('white_blood_cells', 'White blood cells', '/µL'), number('neutrophils', 'Neutrophils', '%'), number('lymphocytes', 'Lymphocytes', '%'), number('monocytes', 'Monocytes', '%'), number('eosinophils', 'Eosinophils', '%'), number('basophils', 'Basophils', '%'), number('platelets', 'Platelets', '10³/µL'), number('reticulocytes', 'Reticulocytes', '%')], 19, 'Tables 3 and 5', 'Blood'),
    exam('coagulation_panel', 'Coagulation panel', 'laboratory', [number('prothrombin_time', 'Prothrombin time', 's', True), number('partial_thromboplastin_time', 'Partial thromboplastin time', 's'), notes()], 19, 'Table 3', 'Blood'),
    exam('liver_function', 'Liver panel', 'laboratory', [number('ast', 'AST', 'U/L', True), number('alt', 'ALT', 'U/L'), number('ggt', 'GGT', 'U/L'), number('bilirubin', 'Total bilirubin', 'mg/dL'), number('alkaline_phosphatase', 'Alkaline phosphatase', 'U/L'), number('ldh', 'LDH', 'U/L'), number('total_protein', 'Total protein', 'g/dL'), number('albumin', 'Albumin', 'g/dL')], 19, 'Tables 3 and 5', 'Blood'),
    exam('renal_function', 'Renal panel and electrolytes', 'laboratory', [number('urea', 'Urea', 'mg/dL'), number('creatinine', 'Creatinine', 'mg/dL', True), number('sodium', 'Sodium', 'mmol/L'), number('chloride', 'Chloride', 'mmol/L'), number('potassium', 'Potassium', 'mmol/L'), number('uric_acid', 'Uric acid', 'mg/dL')], 19, 'Tables 3 and 5', 'Blood'),
    exam('thyroid_function', 'Thyroid panel', 'laboratory', [number('tsh', 'TSH', 'mIU/L', True), number('free_t4', 'Free T4', 'ng/dL'), notes('thyroid_antibodies', 'Thyroid antibodies and method')], 19, 'Tables 3 and 5', 'Blood'),
    exam('glycemic_panel', 'Fasting glucose and glycated hemoglobin', 'laboratory', [number('fasting_glucose', 'Fasting glucose', 'mg/dL', True), number('hba1c', 'Glycated hemoglobin (HbA1c)', '%'), number('fasting_hours', 'Recorded fasting time', 'h')], 19, 'Tables 3 and 5', 'Blood', 'Record the fasting conditions according to the laboratory instructions.'),
    exam('lipid_panel', 'Lipid panel', 'laboratory', [number('total_cholesterol', 'Total cholesterol', 'mg/dL', True), number('hdl', 'HDL', 'mg/dL'), number('ldl', 'LDL', 'mg/dL'), number('triglycerides', 'Triglycerides', 'mg/dL'), number('hs_crp', 'High-sensitivity C-reactive protein', 'mg/L'), number('fasting_hours', 'Recorded fasting time', 'h')], 19, 'Tables 3 and 5', 'Blood', 'Record the fasting conditions according to the laboratory instructions.'),
    exam('mineral_panel', 'Mineral panel', 'laboratory', [number('calcium', 'Total calcium', 'mg/dL', True), number('ionized_calcium', 'Ionized calcium', 'mmol/L'), number('magnesium', 'Magnesium', 'mg/dL'), number('phosphate', 'Phosphate', 'mg/dL')], 19, 'Tables 3 and 5', 'Blood'),
    exam('iron_panel', 'Iron panel', 'laboratory', [number('ferritin', 'Ferritin', 'ng/mL', True), number('iron', 'Serum iron', 'µg/dL'), number('tibc', 'Total iron-binding capacity', 'µg/dL'), number('transferrin_saturation', 'Transferrin saturation', '%')], 19, 'Tables 3 and 5', 'Blood'),
    exam('vitamin_d', 'Vitamin D (25-OH)', 'laboratory', [number('vitamin_d', '25-hydroxyvitamin D', 'ng/mL', True)], 22, 'Table 5 and section 6.7.1', 'Blood'),
    exam('urinalysis', 'Urinalysis', 'laboratory', [number('specific_gravity', 'Specific gravity', '', True), number('ph', 'pH', ''), notes('glucose', 'Glucose'), notes('protein', 'Protein'), notes('ketones', 'Ketones'), notes('blood', 'Blood'), notes('microscopy', 'Microscopy')], 20, 'Tables 3 and 5', 'Urine'),
    exam('blood_group', 'ABO and Rh blood typing', 'laboratory', [choice('abo', 'ABO group', [('a', 'A'), ('b', 'B'), ('ab', 'AB'), ('o', 'O')], True), choice('rh', 'Rh factor', [('positive', 'Positive'), ('negative', 'Negative'), ('indeterminate', 'Indeterminate')], True)], 21, 'Table 4', 'Blood'),
    exam('infectious_screening', 'Infectious disease screening', 'laboratory', [choice(code, label, [('non_reactive', 'Non-reactive'), ('reactive', 'Reactive'), ('indeterminate', 'Indeterminate'), ('not_performed', 'Not performed')]) for code, label in [('syphilis', 'Syphilis'), ('hbsag', 'Hepatitis B — HBsAg'), ('anti_hbc', 'Hepatitis B — anti-HBc'), ('anti_hbs', 'Hepatitis B — anti-HBs'), ('hepatitis_c', 'Hepatitis C'), ('hiv', 'HIV'), ('tuberculosis', 'Tuberculosis (TST/IGRA)')]] + [notes('methods', 'Laboratory methods, values and interpretation', True)], 19, 'Tables 3 and 5', 'Per test', description='Record only the indicated tests and their methods.'),
    exam('hemoglobin_electrophoresis', 'Hemoglobin electrophoresis', 'laboratory', [number(code, label, '%', code == 'hemoglobin_a') for code, label in [('hemoglobin_a', 'Hemoglobin A'), ('hemoglobin_a2', 'Hemoglobin A2'), ('hemoglobin_f', 'Hemoglobin F'), ('hemoglobin_s', 'Hemoglobin S'), ('hemoglobin_c', 'Hemoglobin C'), ('hemoglobin_e', 'Hemoglobin E')]] + [notes()], 19, 'Table 3', 'Blood'),
    exam('resting_ecg', 'Resting electrocardiogram (12-lead)', 'cardiology', [number('heart_rate', 'Heart rate', 'bpm'), number('pr_interval', 'PR interval', 'ms'), number('qrs_duration', 'QRS duration', 'ms'), number('qtc', 'Corrected QT', 'ms'), notes('rhythm', 'Rhythm'), notes('findings', 'Tracing interpretation', True)], 40, 'Section 6.1.6 and Table 6', preparation='Record position, rest and acquisition conditions of the tracing.'),
    exam('echocardiogram', 'Doppler echocardiogram', 'cardiology', [number('ejection_fraction', 'Ejection fraction', '%'), notes('structure', 'Cardiac structure and function'), notes('doppler', 'Doppler findings'), notes('findings', 'Specialist conclusion', True)], 24, 'Table 6'),
    exam('ambulatory_ecg', '24-hour Holter monitoring', 'cardiology', [number('duration', 'Recording duration', 'h', True), number('minimum_heart_rate', 'Minimum heart rate', 'bpm'), number('mean_heart_rate', 'Mean heart rate', 'bpm'), number('maximum_heart_rate', 'Maximum heart rate', 'bpm'), notes('arrhythmias', 'Recorded arrhythmias'), notes('findings', 'Conclusion', True)], 24, 'Table 6'),
    exam('cardiorespiratory_fitness', 'Cardiorespiratory fitness assessment', 'cardiology', [number('vo2_max', 'VO₂ max', 'mL/kg/min', True), number('maximum_heart_rate', 'Maximum heart rate', 'bpm'), notes('exercise_protocol', 'Exercise protocol', True), notes('findings', 'Findings and symptoms')], 24, 'Table 6'),
    exam('pulmonary_function', 'Pulmonary function test', 'pulmonology', [number('fvc', 'Forced vital capacity (FVC)', 'L', True), number('fev1', 'FEV₁', 'L'), number('fev1_fvc', 'FEV₁/FVC', '%'), notes('findings', 'Quality, reference and interpretation', True)], 24, 'Table 6'),
    exam('ophthalmologic_assessment', 'Ophthalmologic assessment', 'ophthalmology', [dict(code='visual_acuity_right', label='Visual acuity — right eye', type='text', required=True), dict(code='visual_acuity_left', label='Visual acuity — left eye', type='text', required=True), number('intraocular_pressure_right', 'Right intraocular pressure', 'mmHg'), number('intraocular_pressure_left', 'Left intraocular pressure', 'mmHg'), notes('refraction', 'Refraction and correction used'), notes('color_vision', 'Color vision and test used'), notes('fundus', 'Fundus'), notes('visual_field', 'Visual field'), notes('oct', 'Optical coherence tomography (OCT)'), notes()], 23, 'Table 6', preparation='Record the acuity scale and whether optical correction is used.'),
    exam('pure_tone_audiometry', 'Pure-tone audiometry', 'otolaryngology', [number(f'{side}_{frequency}', f'{label} — {frequency} Hz', 'dB HL') for side, label in [('right', 'Right ear'), ('left', 'Left ear')] for frequency in (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)] + [notes('findings', 'Interpretation and test conditions', True)], 41, 'Section 6.1.7 and Table 6', preparation='Record equipment, calibration and acoustic conditions in the exam method.'),
    exam('tympanometry', 'Tympanometry', 'otolaryngology', [number('right_peak_pressure', 'Right peak pressure', 'daPa'), number('left_peak_pressure', 'Left peak pressure', 'daPa'), notes('right_curve', 'Right curve'), notes('left_curve', 'Left curve'), notes('findings', 'Interpretation', True)], 23, 'Table 6 and section 6.1.7'),
    exam('dental_assessment', 'Dental assessment', 'dental', [notes('oral_exam', 'Oral exam', True), notes('panoramic_findings', 'Panoramic radiograph, when performed'), notes('treatment_status', 'Treatments and pending items'), notes('findings', 'Dentist conclusion')], 24, 'Table 6'),
    exam('bone_densitometry', 'Bone densitometry (DXA)', 'imaging', [number('lumbar_bmd', 'Lumbar bone mineral density', 'g/cm²'), number('lumbar_t_score', 'Lumbar T-score', ''), number('lumbar_z_score', 'Lumbar Z-score', ''), number('hip_bmd', 'Hip bone mineral density', 'g/cm²'), number('hip_t_score', 'Hip T-score', ''), number('hip_z_score', 'Hip Z-score', ''), notes('findings', 'Region, method and conclusion', True)], 26, 'Table 6'),
    exam('abdominal_ultrasound', 'Abdominal and pelvic ultrasound', 'imaging', [notes('liver', 'Liver and biliary tract'), notes('kidneys', 'Kidneys and urinary tract'), notes('pelvis', 'Pelvis'), notes('findings', 'Report and conclusion', True)], 26, 'Table 6'),
    exam('chest_radiography', 'Chest radiograph', 'imaging', [notes('technique', 'Technique and views'), notes('findings', 'Report and conclusion', True)], 26, 'Table 6'),
    exam('neurologic_assessment', 'Neurological assessment', 'clinical_assessment', [notes('symptoms', 'Symptoms and onset'), notes('cranial_nerves', 'Cranial nerves and eye movements'), notes('coordination', 'Coordination and cerebellar tests'), notes('balance', 'Balance, Romberg and gait'), notes('findings', 'Examiner conclusion', True)], 39, 'Section 6.1.4'),
    exam('behavioral_assessment', 'Behavioral health assessment', 'behavioral_health', [notes('history', 'History and context'), notes('assessment', 'Psychological or psychiatric assessment', True), notes('instruments', 'Instruments used'), notes('follow_up', 'Follow-up defined by the specialist')], 25, 'Table 6'),
    exam('aeromedical_assessment', 'Aeromedical clinical exam', 'clinical_assessment', [notes('medical_history', 'Medical and surgical history', True), notes('medications', 'Medications and supplements'), notes('systems_review', 'Review of systems'), notes('physical_exam', 'Physical exam', True), notes('findings', 'Conclusion and pending items')], 18, 'Table 2'),
]
