# Finance Soul — исходники плагина

Пользователи ставят плагин через `/plugin` из маркетплейса `aibatjardem/finance-soul`. Здесь его исходники; сборки нет — `plugins/finance-soul/` и есть плагин.

- Ядро: `plugins/finance-soul/kernel/finsoul/` (Python ≥ 3.9, расчёты только на stdlib, `openpyxl` — лениво, только в `excel.py`). Любое изменение расчёта — сначала тест в `tests/kernel/`.
- Контент: `plugins/finance-soul/{hooks,skills,agents,templates,profiles}`. Тексты на русском, `description` — на английском (русские фразы-триггеры только в кавычках). Во frontmatter агентов только `name`, `description`, `tools`, `model`, `skills`.
- После любой правки: `python3 -m pytest`.
- Изменил ядро или пример — пересобери пример, иначе тест `test_example_up_to_date` упадёт:
  `python3 plugins/finance-soul/kernel/run.py build examples/edtech/.finsoul/models/main/inputs.json --out examples/edtech/.finsoul/models/main/out`
- Попробовать вживую: `claude --plugin-dir plugins/finance-soul` в тестовой папке.
- Дизайн и план: `docs/superpowers/specs/`, `docs/superpowers/plans/`.
