"""Strict provider response shapes; local validators retain evidence decisions."""

FEATURES = ['body_layout', 'handle_control', 'bin_mechanism', 'display_layout',
            'cyclone_filter', 'identifier', 'head_architecture']


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def _array(items, maximum=None, minimum=None):
    schema = {'type': 'array', 'items': items}
    if maximum is not None:
        schema['maxItems'] = maximum
    if minimum is not None:
        schema['minItems'] = minimum
    return schema


def _enum(values):
    return {'type': 'string', 'enum': list(values)}


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def _box(nullable=False):
    schema = _array({'type': 'number', 'minimum': 0, 'maximum': 1000}, 4, 4)
    return _nullable(schema) if nullable else schema


def inventory_schema(view_ids=()):
    observation = _object({'feature': _enum(FEATURES), 'visible': {'type': 'boolean'},
                           'detail': {'type': 'string', 'minLength': 1}, 'box_2d': _box(True)})
    machine = _object({'object_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,64}$'},
                      'role': _enum(['machine', 'partial_machine', 'accessory']),
                      'parent_id': _nullable({'type': 'string', 'minLength': 1}),
                      'box_2d': _box(),
                      'visibility': _enum(['whole_machine', 'main_body', 'part_only']),
                      'observations': _array(observation, 4), 'readable_identifier': {'type': 'string'}})
    objects = _array(machine, 20)
    if view_ids:
        view = _object({'view_id': _enum(view_ids), 'objects': objects})
        return _object({'views': _array(view, len(view_ids), len(view_ids))})
    return _object({'objects': objects})


def comparison_schema(object_ids, candidate_ids, view_ids=(), available_originals=()):
    decision = _object({
        'status': _enum(['match', 'not_sure', 'not_in_catalogue']),
        'product': _nullable(_enum(candidate_ids)),
        'confidence': {'type': 'integer', 'minimum': 0, 'maximum': 100},
        'top_two': _array(_enum(candidate_ids), 2),
        'evidence': _array({'type': 'string'}), 'missing_evidence': _array({'type': 'string'}),
        'contradictions': _array({'type': 'string'}), 'retake': {'type': 'string'}})
    candidate = _object({'product': _enum(candidate_ids),
                         'outcome': _enum(['confirmed', 'contradicted', 'insufficient_evidence']),
                         'evidence': {'type': 'string', 'minLength': 1}})
    feature = {'product': _enum(candidate_ids), 'feature': _enum(FEATURES),
               'query_visible': {'type': 'boolean'}, 'query_box_2d': _box(True),
               'reference_visible': {'type': 'boolean'},
               'reference_view': _enum(['plate', 'original_detail'] if available_originals else ['plate']),
               'reference_box_2d': _box(True), 'detail': {'type': 'string', 'minLength': 1}}
    if view_ids:
        feature['query_view'] = _enum(view_ids)
    result = {'decision': decision,
              'candidate_checks': _array(candidate, len(candidate_ids), len(candidate_ids)),
              'decisive_region': _box(True), 'refinement_reason': {'type': 'string'},
              'evidence_conflict': {'type': 'boolean'},
              'feature_checks': _array(_object(feature), 4)}
    if view_ids:
        result['decisive_view'] = _nullable(_enum(view_ids))
        result['cross_view_consistency'] = _object({
            'status': _enum(['consistent', 'conflicting', 'insufficient_evidence']),
            'evidence': {'type': 'string', 'minLength': 1}})
    row = _object({'object_id': _enum(object_ids), 'result': _object(result)})
    return _object({'results': _array(row, len(object_ids), len(object_ids))})
