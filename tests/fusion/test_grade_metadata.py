from alpha_agent.fusion.grades import (
    DIMENSION_GROUPS, _LIVE_STD_FLOOR, _MIN_UNIVERSE, _Z_BANDS,
    compute_dimension_thresholds, dimension_missing_reasons, grade_dimensions,
    grade_method_metadata, score_dimensions,
)


def test_metadata_comes_from_the_unchanged_grading_constants():
    metadata = grade_method_metadata()
    assert [(b['min_z'], b['grade']) for b in metadata['bands'][:-1]] == list(_Z_BANDS)
    assert metadata['bands'][-1] == {'grade': 'F', 'min_z': None}
    assert metadata['min_universe'] == _MIN_UNIVERSE == 20
    assert metadata['flatness_floor'] == _LIVE_STD_FLOOR
    assert metadata['dimensions'] == {k: list(v) for k, v in DIMENSION_GROUPS.items()}
    metadata['dimensions']['Momentum'].clear()
    assert grade_method_metadata()['dimensions']['Momentum'] == ['factor']


def test_scores_and_missing_reasons_match_existing_grades():
    universe = [[{'signal': 'factor', 'z': float(i)}] for i in range(25)]
    thresholds = compute_dimension_thresholds(universe)
    scores = score_dimensions(universe[0], thresholds)
    reasons = dimension_missing_reasons(universe[0], thresholds)
    grades = grade_dimensions(universe[0], thresholds)
    assert scores['Momentum'] < -1 and grades['Momentum'] == 'F'
    assert reasons['Flow'] == 'universe_not_gradeable'
    assert dimension_missing_reasons([], thresholds)['Momentum'] == 'ticker_lacks_live_member'
