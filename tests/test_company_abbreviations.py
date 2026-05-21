from app.company_abbreviations import abbreviate_company, company_abbreviation, company_full_name


def test_company_abbreviation_matches_exact_company_name():
    assert company_abbreviation("Leon's Car Care") == "LCC"


def test_company_abbreviation_matches_acronis_group_suffix_difference():
    assert company_abbreviation("Schmidbauer Lumber Company") == "SLI"


def test_company_abbreviation_matches_nested_acronis_group():
    assert company_abbreviation("Biztech > R Brown Construction") == "RB"


def test_company_abbreviation_matches_number_word_variant():
    assert company_abbreviation("Marimba One") == "M1"


def test_abbreviate_company_falls_back_to_original_name():
    assert abbreviate_company("Unknown Company") == "Unknown Company"


def test_company_full_name_resolves_abbreviation():
    assert company_full_name("M1") == "Marimba 1"


def test_company_full_name_matches_nested_acronis_group():
    assert company_full_name("Biztech > R Brown Construction") == "R Brown"
