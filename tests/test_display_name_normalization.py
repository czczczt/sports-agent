from parser_running.normalize import format_display_name


def test_format_display_name_fixes_caps_and_lowercase():
    assert format_display_name("ИВАНОВА АНЖЕЛИКА") == "Иванова Анжелика"
    assert format_display_name("ИВАНОВА Анжелика") == "Иванова Анжелика"
    assert format_display_name("иванова   анжелика") == "Иванова Анжелика"
    assert format_display_name("ИВАНОВ-ПЕТРОВ ИВАН") == "Иванов-Петров Иван"
    assert format_display_name("анна-мария сидорова") == "Анна-Мария Сидорова"


def test_format_display_name_preserves_intentional_mixed_case():
    assert format_display_name("Иван McDonald") == "Иван McDonald"
    assert format_display_name("Анна de la Cruz") == "Анна de la Cruz"
    assert format_display_name("Иванова Анжелика") == "Иванова Анжелика"


def test_format_display_name_handles_empty_values():
    assert format_display_name(None) == ""
    assert format_display_name("") == ""
    assert format_display_name("   ") == ""
