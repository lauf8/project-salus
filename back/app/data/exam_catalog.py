SOURCE_URL = 'https://www.nasa.gov/wp-content/uploads/2024/09/ochmo-std-100-1a-rev-a-signed.pdf'
SOURCE_NAME = 'OCHMO-STD-100.1A, Rev. A (09/09/2024)'
APPLICABILITY = 'Seleção, recertificação ou avaliação da missão conforme indicação médica. A equipe médica define aplicabilidade e prazo para cada tripulante. Os campos e unidades são uma adaptação para registro; não estabelecem aptidão nem limites clínicos automáticos.'

EXAM_TYPES = [
    ('laboratory', 'Laboratorial'),
    ('cardiology', 'Cardiológico'),
    ('ophthalmology', 'Oftalmológico'),
    ('otolaryngology', 'Otorrinolaringológico'),
    ('pulmonology', 'Pulmonar'),
    ('imaging', 'Diagnóstico por imagem'),
    ('clinical_assessment', 'Avaliação clínica'),
    ('dental', 'Odontológico'),
    ('behavioral_health', 'Saúde comportamental'),
]


def number(code, label, unit, required=False):
    return dict(code=code, label=label, type='number', unit=unit, required=required)


def notes(code='findings', label='Achados e observações', required=False):
    return dict(code=code, label=label, type='textarea', required=required)


def choice(code, label, options, required=False):
    return dict(code=code, label=label, type='select', required=required, options=[dict(value=value, label=text) for value, text in options])


def exam(code, name, category, fields, page, section, specimen=None, preparation=None, description=None):
    return dict(code=code, name=name, category=category, fields=fields, source_page=page, source_section=f'{SOURCE_NAME} · {section}', source_url=SOURCE_URL, specimen=specimen, preparation=preparation, description=description or name, applicability_notes=APPLICABILITY, is_active=True)


EXAMS = [
    exam('complete_blood_count', 'Hemograma completo', 'laboratory', [number('hemoglobin', 'Hemoglobina', 'g/dL', True), number('hematocrit', 'Hematócrito', '%'), number('red_blood_cells', 'Hemácias', '10⁶/µL'), number('mcv', 'VCM', 'fL'), number('mch', 'HCM', 'pg'), number('mchc', 'CHCM', 'g/dL'), number('white_blood_cells', 'Leucócitos', '/µL'), number('neutrophils', 'Neutrófilos', '%'), number('lymphocytes', 'Linfócitos', '%'), number('monocytes', 'Monócitos', '%'), number('eosinophils', 'Eosinófilos', '%'), number('basophils', 'Basófilos', '%'), number('platelets', 'Plaquetas', '10³/µL'), number('reticulocytes', 'Reticulócitos', '%')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('coagulation_panel', 'Coagulograma', 'laboratory', [number('prothrombin_time', 'Tempo de protrombina', 's', True), number('partial_thromboplastin_time', 'Tempo de tromboplastina parcial', 's'), notes()], 19, 'Tabela 3', 'Sangue'),
    exam('liver_function', 'Perfil hepático', 'laboratory', [number('ast', 'AST (TGO)', 'U/L', True), number('alt', 'ALT (TGP)', 'U/L'), number('ggt', 'GGT', 'U/L'), number('bilirubin', 'Bilirrubina total', 'mg/dL'), number('alkaline_phosphatase', 'Fosfatase alcalina', 'U/L'), number('ldh', 'LDH', 'U/L'), number('total_protein', 'Proteínas totais', 'g/dL'), number('albumin', 'Albumina', 'g/dL')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('renal_function', 'Perfil renal e eletrólitos', 'laboratory', [number('urea', 'Ureia', 'mg/dL'), number('creatinine', 'Creatinina', 'mg/dL', True), number('sodium', 'Sódio', 'mmol/L'), number('chloride', 'Cloreto', 'mmol/L'), number('potassium', 'Potássio', 'mmol/L'), number('uric_acid', 'Ácido úrico', 'mg/dL')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('thyroid_function', 'Perfil tireoidiano', 'laboratory', [number('tsh', 'TSH', 'mIU/L', True), number('free_t4', 'T4 livre', 'ng/dL'), notes('thyroid_antibodies', 'Anticorpos antitireoidianos e método')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('glycemic_panel', 'Glicemia de jejum e hemoglobina glicada', 'laboratory', [number('fasting_glucose', 'Glicemia de jejum', 'mg/dL', True), number('hba1c', 'Hemoglobina glicada (HbA1c)', '%'), number('fasting_hours', 'Tempo de jejum registrado', 'h')], 19, 'Tabelas 3 e 5', 'Sangue', 'Registrar as condições de jejum conforme orientação do laboratório.'),
    exam('lipid_panel', 'Perfil lipídico', 'laboratory', [number('total_cholesterol', 'Colesterol total', 'mg/dL', True), number('hdl', 'HDL', 'mg/dL'), number('ldl', 'LDL', 'mg/dL'), number('triglycerides', 'Triglicerídeos', 'mg/dL'), number('hs_crp', 'Proteína C reativa ultrassensível', 'mg/L'), number('fasting_hours', 'Tempo de jejum registrado', 'h')], 19, 'Tabelas 3 e 5', 'Sangue', 'Registrar as condições de jejum conforme orientação do laboratório.'),
    exam('mineral_panel', 'Perfil de minerais', 'laboratory', [number('calcium', 'Cálcio total', 'mg/dL', True), number('ionized_calcium', 'Cálcio ionizado', 'mmol/L'), number('magnesium', 'Magnésio', 'mg/dL'), number('phosphate', 'Fosfato', 'mg/dL')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('iron_panel', 'Perfil de ferro', 'laboratory', [number('ferritin', 'Ferritina', 'ng/mL', True), number('iron', 'Ferro sérico', 'µg/dL'), number('tibc', 'Capacidade total de ligação do ferro', 'µg/dL'), number('transferrin_saturation', 'Saturação de transferrina', '%')], 19, 'Tabelas 3 e 5', 'Sangue'),
    exam('vitamin_d', 'Vitamina D (25-OH)', 'laboratory', [number('vitamin_d', '25-hidroxivitamina D', 'ng/mL', True)], 22, 'Tabela 5 e seção 6.7.1', 'Sangue'),
    exam('urinalysis', 'Urina tipo I', 'laboratory', [number('specific_gravity', 'Densidade relativa', '', True), number('ph', 'pH', ''), notes('glucose', 'Glicose'), notes('protein', 'Proteínas'), notes('ketones', 'Cetonas'), notes('blood', 'Sangue'), notes('microscopy', 'Microscopia')], 20, 'Tabelas 3 e 5', 'Urina'),
    exam('blood_group', 'Tipagem sanguínea ABO e Rh', 'laboratory', [choice('abo', 'Grupo ABO', [('a', 'A'), ('b', 'B'), ('ab', 'AB'), ('o', 'O')], True), choice('rh', 'Fator Rh', [('positive', 'Positivo'), ('negative', 'Negativo'), ('indeterminate', 'Indeterminado')], True)], 21, 'Tabela 4', 'Sangue'),
    exam('infectious_screening', 'Triagem de doenças infecciosas', 'laboratory', [choice(code, label, [('non_reactive', 'Não reagente'), ('reactive', 'Reagente'), ('indeterminate', 'Indeterminado'), ('not_performed', 'Não realizado')]) for code, label in [('syphilis', 'Sífilis'), ('hbsag', 'Hepatite B — HBsAg'), ('anti_hbc', 'Hepatite B — anti-HBc'), ('anti_hbs', 'Hepatite B — anti-HBs'), ('hepatitis_c', 'Hepatite C'), ('hiv', 'HIV'), ('tuberculosis', 'Tuberculose (TST/IGRA)')]] + [notes('methods', 'Métodos, valores e interpretação do laboratório', True)], 19, 'Tabelas 3 e 5', 'Conforme teste', description='Registrar apenas os testes indicados e seus respectivos métodos.'),
    exam('hemoglobin_electrophoresis', 'Eletroforese de hemoglobina', 'laboratory', [number(code, label, '%', code == 'hemoglobin_a') for code, label in [('hemoglobin_a', 'Hemoglobina A'), ('hemoglobin_a2', 'Hemoglobina A2'), ('hemoglobin_f', 'Hemoglobina F'), ('hemoglobin_s', 'Hemoglobina S'), ('hemoglobin_c', 'Hemoglobina C'), ('hemoglobin_e', 'Hemoglobina E')]] + [notes()], 19, 'Tabela 3', 'Sangue'),
    exam('resting_ecg', 'Eletrocardiograma de repouso (12 derivações)', 'cardiology', [number('heart_rate', 'Frequência cardíaca', 'bpm'), number('pr_interval', 'Intervalo PR', 'ms'), number('qrs_duration', 'Duração QRS', 'ms'), number('qtc', 'QT corrigido', 'ms'), notes('rhythm', 'Ritmo'), notes('findings', 'Interpretação do traçado', True)], 40, 'Seção 6.1.6 e Tabela 6', preparation='Registrar posição, repouso e condições de aquisição do traçado.'),
    exam('echocardiogram', 'Ecocardiograma com Doppler', 'cardiology', [number('ejection_fraction', 'Fração de ejeção', '%'), notes('structure', 'Estrutura e função cardíaca'), notes('doppler', 'Achados Doppler'), notes('findings', 'Conclusão do especialista', True)], 24, 'Tabela 6'),
    exam('ambulatory_ecg', 'Holter de 24 horas', 'cardiology', [number('duration', 'Duração do registro', 'h', True), number('minimum_heart_rate', 'Frequência mínima', 'bpm'), number('mean_heart_rate', 'Frequência média', 'bpm'), number('maximum_heart_rate', 'Frequência máxima', 'bpm'), notes('arrhythmias', 'Arritmias registradas'), notes('findings', 'Conclusão', True)], 24, 'Tabela 6'),
    exam('cardiorespiratory_fitness', 'Avaliação da capacidade cardiorrespiratória', 'cardiology', [number('vo2_max', 'VO₂ máximo', 'mL/kg/min', True), number('maximum_heart_rate', 'Frequência cardíaca máxima', 'bpm'), notes('exercise_protocol', 'Protocolo de exercício', True), notes('findings', 'Achados e sintomas')], 24, 'Tabela 6'),
    exam('pulmonary_function', 'Prova de função pulmonar', 'pulmonology', [number('fvc', 'Capacidade vital forçada (CVF)', 'L', True), number('fev1', 'VEF₁', 'L'), number('fev1_fvc', 'VEF₁/CVF', '%'), notes('findings', 'Qualidade, referência e interpretação', True)], 24, 'Tabela 6'),
    exam('ophthalmologic_assessment', 'Avaliação oftalmológica', 'ophthalmology', [dict(code='visual_acuity_right', label='Acuidade visual — olho direito', type='text', required=True), dict(code='visual_acuity_left', label='Acuidade visual — olho esquerdo', type='text', required=True), number('intraocular_pressure_right', 'Pressão intraocular direita', 'mmHg'), number('intraocular_pressure_left', 'Pressão intraocular esquerda', 'mmHg'), notes('refraction', 'Refração e correção utilizada'), notes('color_vision', 'Visão de cores e teste utilizado'), notes('fundus', 'Fundo de olho'), notes('visual_field', 'Campo visual'), notes('oct', 'Tomografia de coerência óptica (OCT)'), notes()], 23, 'Tabela 6', preparation='Informar a escala de acuidade e se há correção óptica.'),
    exam('pure_tone_audiometry', 'Audiometria tonal', 'otolaryngology', [number(f'{side}_{frequency}', f'{label} — {frequency} Hz', 'dB HL') for side, label in [('right', 'Ouvido direito'), ('left', 'Ouvido esquerdo')] for frequency in (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)] + [notes('findings', 'Interpretação e condições do teste', True)], 41, 'Seção 6.1.7 e Tabela 6', preparation='Registrar equipamento, calibração e condições acústicas no método do exame.'),
    exam('tympanometry', 'Timpanometria', 'otolaryngology', [number('right_peak_pressure', 'Pressão de pico direita', 'daPa'), number('left_peak_pressure', 'Pressão de pico esquerda', 'daPa'), notes('right_curve', 'Curva direita'), notes('left_curve', 'Curva esquerda'), notes('findings', 'Interpretação', True)], 23, 'Tabela 6 e seção 6.1.7'),
    exam('dental_assessment', 'Avaliação odontológica', 'dental', [notes('oral_exam', 'Exame oral', True), notes('panoramic_findings', 'Radiografia panorâmica, quando realizada'), notes('treatment_status', 'Tratamentos e pendências'), notes('findings', 'Conclusão do odontologista')], 24, 'Tabela 6'),
    exam('bone_densitometry', 'Densitometria óssea (DXA)', 'imaging', [number('lumbar_bmd', 'Densidade mineral óssea lombar', 'g/cm²'), number('lumbar_t_score', 'T-score lombar', ''), number('lumbar_z_score', 'Z-score lombar', ''), number('hip_bmd', 'Densidade mineral óssea do quadril', 'g/cm²'), number('hip_t_score', 'T-score do quadril', ''), number('hip_z_score', 'Z-score do quadril', ''), notes('findings', 'Região, método e conclusão', True)], 26, 'Tabela 6'),
    exam('abdominal_ultrasound', 'Ultrassonografia abdominal e pélvica', 'imaging', [notes('liver', 'Fígado e vias biliares'), notes('kidneys', 'Rins e vias urinárias'), notes('pelvis', 'Pelve'), notes('findings', 'Laudo e conclusão', True)], 26, 'Tabela 6'),
    exam('chest_radiography', 'Radiografia de tórax', 'imaging', [notes('technique', 'Técnica e projeções'), notes('findings', 'Laudo e conclusão', True)], 26, 'Tabela 6'),
    exam('neurologic_assessment', 'Avaliação neurológica', 'clinical_assessment', [notes('symptoms', 'Sintomas e início'), notes('cranial_nerves', 'Nervos cranianos e movimentos oculares'), notes('coordination', 'Coordenação e provas cerebelares'), notes('balance', 'Equilíbrio, Romberg e marcha'), notes('findings', 'Conclusão do examinador', True)], 39, 'Seção 6.1.4'),
    exam('behavioral_assessment', 'Avaliação de saúde comportamental', 'behavioral_health', [notes('history', 'Histórico e contexto'), notes('assessment', 'Avaliação psicológica ou psiquiátrica', True), notes('instruments', 'Instrumentos utilizados'), notes('follow_up', 'Acompanhamento definido pelo especialista')], 25, 'Tabela 6'),
    exam('aeromedical_assessment', 'Exame clínico aeromédico', 'clinical_assessment', [notes('medical_history', 'Histórico médico e cirúrgico', True), notes('medications', 'Medicamentos e suplementos'), notes('systems_review', 'Revisão de sistemas'), notes('physical_exam', 'Exame físico', True), notes('findings', 'Conclusão e pendências')], 18, 'Tabela 2'),
]
