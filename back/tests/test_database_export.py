from scripts.prepare_database_export import clean_value, email_for, mission_name, person_name


def test_names_and_addresses_are_unique_and_stable():
    names = [person_name(index) for index in range(149)]
    assert len(set(names)) == 149
    assert len({email_for(name) for name in names}) == 149
    assert email_for('João Almeida') == 'joao.almeida@crew.salus.example'
    assert len({mission_name(index) for index in range(50)}) == 50


def test_nested_labels_preserve_values_dates_and_evidence_identifiers():
    payload = {'stock': 'Salus Synthetic Vessel 01', 'quantity': 1200, 'collected_at': '2026-11-15T12:00:00+00:00',
               'source': [{'id': 42, 'note': 'Acompanhamento ficcional da semana.'}], 'status': 'completed'}
    result = clean_value(payload, [('Salus Synthetic Vessel 01', 'Asteria 01'),
                                   ('Acompanhamento ficcional da semana.', 'Revisão semanal de adaptação.')])
    assert result['stock'] == 'Asteria 01'
    assert result['quantity'] == payload['quantity']
    assert result['collected_at'] == payload['collected_at']
    assert result['source'][0]['id'] == 42
    assert result['status'] == 'completed'
    assert payload['stock'] == 'Salus Synthetic Vessel 01'
    assert clean_value(result, []) == result


def test_schema_source_and_clinical_profile_codes_are_preserved():
    assert clean_value('simulation', []) == 'simulation'
    assert clean_value('simulation-v2', []) == 'simulation-v2'
