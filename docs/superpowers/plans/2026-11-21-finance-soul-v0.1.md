# Finance Soul v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Плагин Claude Code `finance-soul`: душа финансиста + skills + 3 субагента + Python-ядро, которое из `inputs.json` строит связанные три формы, юнит-экономику, cash/runway и три сценария, пишет `report.md`, `checks.json` и `model.xlsx` с живыми формулами.

**Architecture:** Ядро держит модель как набор именованных строк-выражений над входами и периодами (`finsoul.graph`). Одно и то же выражение и считается в Python (`eval`), и рендерится в формулу Excel (`to_excel`) — поэтому числа в отчёте и в xlsx совпадают по построению, а тест с `pycel` это подтверждает. Плагинная часть повторяет agentsoul: хук SessionStart отдаёт сжатую душу и сводку `.finsoul/`, skills — знание и опросы, агенты — исполнители.

**Tech Stack:** Python ≥ 3.9 (stdlib), `openpyxl` (xlsx), dev: `pytest`, `pycel`. Bash для хука. GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-21-finance-soul-design.md` (раздел «Этапы → v0.1» и «Решения исполнителя для v0.1» сильнее остального текста).

## Global Constraints

- Python ≥ 3.9: без `match`, без `tomllib`, без `X | Y` в аннотациях (используй `Optional`/`Union` из `typing`); расчёты — только stdlib; `openpyxl` импортируется лениво, только в `excel.py`.
- Плагин без шага сборки: `plugins/finance-soul/` — исходник. Префикс в текстах — `finance-soul:<имя>`.
- Данные проекта — в `.finsoul/` проекта; плагин их не перезаписывает (setup только создаёт отсутствующие файлы).
- Тексты skills/агентов/души — на русском; поле `description` — на английском.
- Во frontmatter агентов — только `name`, `description`, `tools`, `model`, `skills`. `model: inherit`.
- Бюджет `additionalContext` хука — < 9 000 символов (жёсткий лимит платформы 10 000).
- Лицензия MIT. Из `ai-startup-skills`, `business-plan-skill`, `burnless`, `CanvasDesk` не копируется ни текст, ни код. Переиспользованное из Apache/MIT источников — в `NOTICE`.
- НДС сквозной (входы без НДС); КПН — ставка из входов с источником, с переносом убытка; одна валюта модели (поле `currency`, по умолчанию `KZT`); необязательный блок `fx` в схеме допускается и игнорируется.
- Ядро запускается через `kernel/run.py`; лаунчер ищет `python3`, затем `python`, требует ≥ 3.9.
- Коммиты заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Опечатка или пропуск поля в `inputs.json` → понятная ошибка на русском с путём поля (`revenue_streams[0].price: обязательное число`), код выхода 2, без traceback. — Task 3.
2. Деление на ноль: отток 0 (LTV бесконечен), маржинальный доход ≤ 0 (безубыточности нет), нулевая выручка → значение `None` + предупреждение в `checks.json`, а не падение или `inf`. — Task 5.
3. Кэш уходит в минус → модель всё равно строится, `checks.json` содержит предупреждение `negative_cash` с месяцем, отчёт показывает пиковую потребность в финансировании. — Task 5.
4. IRR без смены знака потока → `None`, в отчёте «не определена». — Task 2.
5. Переключатель сценария в Excel переключён на `downside` → пересчёт `pycel` совпадает с ядром для сценария downside. — Task 7.

---

## File Structure

```
plugins/finance-soul/
  .claude-plugin/plugin.json
  hooks/hooks.json, hooks/run-hook.cmd, hooks/session-start, hooks/soul-core.md
  skills/{setup,soul,kernel-reference,assumptions,three-statement-guide,unit-economics-guide,cash-runway-guide,business-plan-guide}/SKILL.md
  agents/{model-builder,model-auditor,cfo-reviewer}.md
  templates/{company.md,metrics.md,assumptions.md,local/rules.md}
  profiles/{blank,edtech}/{profile.json,company.md,metrics.md,inputs.json}
  kernel/run.py                 лаунчер: проверка версии, вызов finsoul.cli
  kernel/finsoul/__init__.py
  kernel/finsoul/graph.py       выражения: eval + to_excel
  kernel/finsoul/tvm.py         NPV, IRR, окупаемость, аннуитет
  kernel/finsoul/inputs.py      загрузка и валидация inputs.json
  kernel/finsoul/statements.py  построение строк трёх форм
  kernel/finsoul/metrics.py     юнит-экономика и cash-метрики
  kernel/finsoul/scenarios.py   множители сценариев
  kernel/finsoul/checks.py      проверки целостности → checks.json
  kernel/finsoul/excel.py       запись xlsx
  kernel/finsoul/report.py      report.md
  kernel/finsoul/cli.py         команды
tests/kernel/test_*.py, tests/plugin/test_*.py, tests/fixtures/*.json
examples/edtech/.finsoul/...
.claude-plugin/marketplace.json, .github/workflows/ci.yml
README.md, NOTICE, LICENSE, CLAUDE.md, pytest.ini, requirements-dev.txt
```

`pytest.ini`: `testpaths = tests`, `pythonpath = plugins/finance-soul/kernel`.

---

### Task 1: Каркас репозитория и слой выражений `graph`

**Files:**
- Create: `pytest.ini`, `requirements-dev.txt` (`pytest>=8`, `pycel>=1.0b30`, `openpyxl>=3.1`), `.gitignore` (`__pycache__/`, `._*`, `.DS_Store`, `out/`), `LICENSE` (MIT, aibatjardem 2026), `plugins/finance-soul/kernel/finsoul/__init__.py` (`__version__ = "0.1.0"`), `plugins/finance-soul/kernel/finsoul/graph.py`
- Test: `tests/kernel/test_graph.py`

**Interfaces:**
- Produces (`finsoul.graph`):
  - `class Expr` с `eval(ctx: "Ctx", t: int) -> float` и `to_excel(ctx: "Ctx", t: int) -> str`; операторы `+ - * /` и унарный `-` возвращают `Expr`; числа автоматически оборачиваются в `Const`.
  - `Const(v: float)`, `Input(name: str)` — скаляр со листа «Входы»; `Series(name: str)` — входной ряд по периодам (строка на листе «Входы»); `Ref(name: str, lag: int = 0)` — строка модели, при `t - lag < 0` даёт `0` (в Excel — `0`); `Max(*e)`, `Min(*e)`, `If(cond: Expr, a: Expr, b: Expr)` где `cond` — `Gt(a,b)`/`Ge(a,b)`/`Eq(a,b)`; `Pick(selector: Input, options: list[Expr])` → `CHOOSE(sel, ...)`, в Python — `options[int(sel)-1]`; `Sum(name: str)` — накопленная сумма строки за периоды 0..t (`SUM(B5:x5)`).
  - `@dataclass Line(name: str, label: str, expr: Expr, section: str, fmt: str = "money")` — `fmt` ∈ {`money`, `pct`, `num`}.
  - `class Ctx` — `inputs: dict[str, float]`, `series: dict[str, list[float]]`, `lines: dict[str, Line]`, `periods: int`, кэш значений; `addr_input(name) -> str` (например `'Входы'!$C$4`), `addr_series(name, t) -> str`, `addr_line(name, t) -> str` — адреса задаёт раскладка из Task 7 через `Ctx.layout: Layout`; по умолчанию `Layout.default(ctx)`: лист «Модель», строка = порядок `lines` + 2, столбец B = период 0.
  - `evaluate(ctx: Ctx) -> dict[str, list[float]]` — значения всех строк; цикл через `Ref` без лага → `ValueError("цикл: a -> b -> a")`.

- [ ] **Step 1: Тесты** в `tests/kernel/test_graph.py`:
  - `test_arithmetic_and_lag`: строки `a = Series("v")`, `b = Ref("a") * 2 + Ref("b", lag=1)` при `v=[1,2,3]` → `b == [2, 6, 12]`.
  - `test_to_excel_renders_addresses`: дефолтная раскладка — строка 1 заголовок, строки модели с 2-й в порядке объявления (`a` — 2, `b` — 3), период 0 — колонка B, ряд `Series` лежит на «Входы» в той же логике. Для `b` в периоде 1: `"='Модель'!C2*2+'Модель'!B3"`; в периоде 0 ссылка с лагом рендерится как `0`: `"='Модель'!B2*2+0"`.
  - `test_pick_and_if`: `Pick(Input("s"), [Const(1), Const(5)])` при `s=2` → `5`, Excel → `CHOOSE('Входы'!$C$..,1,5)`; `If(Gt(Ref("a"),Const(1)), Const(10), Const(0))` → `[0,10,10]`.
  - `test_cycle_detected`: `a = Ref("b")`, `b = Ref("a")` → `ValueError` с «цикл».
  - `test_cum_sum`: `Sum("a")` при `v=[1,2,3]` → `[1,3,6]`.
- [ ] **Step 2:** `python3 -m pytest tests/kernel/test_graph.py -v` → FAIL (нет модуля).
- [ ] **Step 3:** Реализовать `graph.py`. Мемоизация по `(name, t)`; детекция цикла — стек вычисляемых `(name, t)`.
- [ ] **Step 4:** `python3 -m pytest tests/kernel/test_graph.py -v` → PASS.
- [ ] **Step 5:** Коммит `feat(kernel): expression graph with python eval and excel rendering`.

### Task 2: `tvm` — деньги во времени

**Files:** Create `plugins/finance-soul/kernel/finsoul/tvm.py`; Test `tests/kernel/test_tvm.py`

**Interfaces:**
- Produces: `npv(rate: float, flows: list[float]) -> float` (flows[0] — в момент 0, без дисконта; **отличается от Excel NPV**, в Excel рендерится как `=B+NPV(r, C:..)`), `irr(flows: list[float]) -> Optional[float]` (None, если нет смены знака или не сошлось), `payback_period(flows) -> Optional[float]` (дробные периоды, линейная интерполяция), `discounted_payback(rate, flows) -> Optional[float]`, `annuity_payment(rate_per_period: float, n: int, principal: float) -> float`, `monthly_rate(annual: float) -> float` (= annual/12, номинальная — так считают банки РК).

- [ ] **Step 1: Тесты:**
  - `npv(0.1, [-100, 60, 60]) == pytest.approx(4.1322, abs=1e-4)`
  - `irr([-100, 60, 60]) == pytest.approx(0.130662, abs=1e-6)`
  - `irr([100, 50]) is None`; `irr([-100, -50]) is None`
  - `payback_period([-100, 40, 40, 40]) == pytest.approx(2.5)`; `payback_period([-100, 10, 10]) is None`
  - `annuity_payment(0.01, 12, 1_000_000) == pytest.approx(88848.79, abs=0.01)`; при ставке 0 → `principal / n`
- [ ] **Step 2:** запустить → FAIL.
- [ ] **Step 3:** Реализовать; IRR — бисекция на [-0.9999, 10] после проверки смены знака, затем до 1e-10.
- [ ] **Step 4:** → PASS. **Step 5:** Коммит `feat(kernel): time value of money`.

### Task 3: `inputs` — схема и валидация входов

**Files:** Create `kernel/finsoul/inputs.py`; Test `tests/kernel/test_inputs.py`; Fixture `tests/fixtures/edtech_inputs.json` (та же, что `profiles/edtech/inputs.json` в Task 10 — Task 10 копирует её).

**Interfaces:**
- Produces: `class InputError(Exception)` с `.path: str`, `.message: str`; `load_inputs(path: str) -> ModelInputs`; `parse_inputs(raw: dict) -> ModelInputs` (собирает **все** ошибки, бросает `InputError` с первой и `.all: list[InputError]`).
- `ModelInputs` (dataclasses), поля и значения по умолчанию:
  ```
  name: str; currency: str = "KZT"; start: str ("YYYY-MM"); months: int (1..120)
  opening_cash: float = 0
  scenario: str = "base"   # одно из ключей scenarios
  scenarios: {"base"|"upside"|"downside": {price, volume, variable_costs, fixed_costs}} — множители, default 1.0; по умолчанию upside {1.0,1.2,1.0,1.0}, downside {0.9,0.8,1.15,1.1}
  revenue_streams: [ {name, unit, price, variable_cost, ramp: [числа] (обязателен, ≥1), growth_monthly: float = 0, capacity: Optional[float]} ]
      объём месяца t: ramp[t] если t < len(ramp), иначе ramp[-1]*(1+growth)^(t-len(ramp)+1), затем min(capacity)
  fixed_costs: [ {name, monthly, growth_annual: float = 0, start_month: int = 1} ]   # рост ступенькой раз в 12 мес
  capex: [ {name, month, amount, life_months} ]   # линейная амортизация с месяца после покупки
  financing: {equity: [{month, amount}], loans: [{name, month, amount, rate_annual, term_months}]}
  working_capital: {dso_days: 0, dpo_days: 0}   # AR = выручка_t*dso/30, AP = (перем.+пост. затраты)_t*dpo/30
  tax: {cit_rate: 0.2, source: str (обязателен, если cit_rate > 0)}
  unit_economics: {cac: Optional, churn_monthly: Optional, marketing_line: Optional[str]}
  discount_rate_annual: float = 0.25
  assumptions_ref: Optional[str]; fx: Optional[dict] (игнорируется в v0.1)
  ```
  Месяцы во входах — 1-базные (1 = первый месяц модели); внутри ядра t = month-1.

- [ ] **Step 1: Тесты:**
  - `test_loads_edtech_fixture`: `load_inputs("tests/fixtures/edtech_inputs.json").months == 36`, `currency == "KZT"`.
  - `test_missing_price_reports_path`: без `revenue_streams[0].price` → `InputError`, `.path == "revenue_streams[0].price"`, в `.message` есть «обязательное».
  - `test_collects_all_errors`: два плохих поля → `len(e.all) == 2`.
  - `test_unknown_scenario`: `scenario: "best"` → ошибка по `scenario`, в сообщении перечислены допустимые.
  - `test_tax_source_required`: `cit_rate: 0.2` без `source` → ошибка `tax.source`.
  - `test_unknown_top_level_key_is_error`: ключ `revnue_streams` → ошибка с подсказкой «возможно, revenue_streams» (`difflib.get_close_matches`).
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать (ручная валидация, без внешних библиотек). Fixture: EdTech-школа, 36 мес., поток «подписка» price 25000, variable_cost 3000, ramp [40,70,110,150,190,230], growth 0.05, capacity 2000; fixed: ФОТ 4 500 000 (growth_annual 0.1), аренда 600 000, маркетинг 1 500 000, софт 300 000; capex ноутбуки 6 000 000 мес.1 life 36; equity 60 000 000 мес.1; loan 30 000 000 мес.3 ставка 0.22 срок 24; dso 5, dpo 20; tax cit 0.2 source «НК РК 2026, ст. КПН — проверить»; unit_economics cac 18000, churn 0.06, marketing_line «маркетинг».
- [ ] **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): inputs schema and validation`.

### Task 4: `statements` — связанные три формы + `checks`

**Files:** Create `kernel/finsoul/statements.py`, `kernel/finsoul/checks.py`; Test `tests/kernel/test_statements.py`

**Interfaces:**
- Consumes: `graph.*`, `inputs.ModelInputs`, `tvm.annuity_payment`, `tvm.monthly_rate`.
- Produces: `build_model(mi: ModelInputs) -> Ctx` — заполняет `ctx.inputs` (скаляры + множители всех сценариев + `scenario_index` 1/2/3), `ctx.series` (ramp-объёмы, график capex, equity, выдачи/графики кредитов — посчитанные в Python и записанные как входные ряды), `ctx.lines` с секциями `pl`, `bs`, `cf`. Обязательные имена строк (на них ссылаются Task 5/7/8):
  `revenue, variable_costs, gross_profit, fixed_costs, ebitda, depreciation, ebit, interest, ebt, tax_loss_pool, taxable_income, tax, net_income` (P&L);
  `cash, receivables, fixed_assets_net, total_assets, payables, debt, equity_paid, retained_earnings, total_liabilities_equity` (BS);
  `cf_operating, cf_investing, cf_financing, net_cash_flow` (CF);
  `balance_diff = total_assets - total_liabilities_equity`.
  Активные множители: `price_mult = Pick(Input("scenario_index"), [Input("base_price"), Input("upside_price"), Input("downside_price")])` и т. д. — так переключатель в Excel работает.
  КПН с переносом убытка: `tax_loss_pool_t = Max(0, pool_{t-1} - ebt_t)`, `taxable_income_t = Max(0, ebt_t - pool_{t-1})`, `tax = taxable_income * cit_rate`. Налог платится в том же месяце (упрощение v0.1, указать в отчёте).
  Кредит: проценты = остаток_{t-1} × ставка/12; погашение тела — аннуитет; ряды `loan_draw`, `loan_principal` — входные ряды, `interest` — формула от `debt` с лагом.
- `run_checks(ctx: Ctx, values: dict) -> list[dict]` — элементы `{"id", "level": "error"|"warning", "message", "period": Optional[int]}`; `error` для `balance_diff` по модулю > 0.5 в любом периоде и для `cash_t != cash_{t-1} + net_cash_flow_t`.

- [ ] **Step 1: Тесты** на fixture edtech:
  - `test_balance_balances_every_month`: `max(abs(x) for x in values["balance_diff"]) < 0.5`.
  - `test_cash_ties_to_cash_flow`: для всех t: `cash[t] == approx(cash[t-1] + net_cash_flow[t])`, `cash[0] == approx(opening_cash + net_cash_flow[0])`.
  - `test_retained_earnings_rollforward`: `retained_earnings[t] == approx(retained_earnings[t-1] + net_income[t])`.
  - `test_month1_revenue`: `revenue[0] == 40 * 25000 == 1_000_000`.
  - `test_loss_carryforward`: ручной мини-input: ebt = [-100, 60, 60], cit 0.2 → `tax == [0, 0, 4]`.
  - `test_depreciation_linear`: capex 6 000 000 life 36 мес.1 → `depreciation[0] == 0`, `depreciation[1] == approx(166_666.67)`.
  - `test_run_checks_flags_imbalance`: подменить значение `balance_diff[5] = 10` → есть `error` c `period == 5`.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): linked three statements with integrity checks`.

### Task 5: `metrics` — юнит-экономика и деньги

**Files:** Create `kernel/finsoul/metrics.py`; Test `tests/kernel/test_metrics.py`

**Interfaces:**
- Consumes: `build_model`, `evaluate`, `tvm.*`.
- Produces: `unit_economics(mi, values) -> dict` с ключами `contribution_per_unit`, `contribution_margin` (по первому потоку и средневзвешенно по выручке), `breakeven_units_per_month` (fixed первого месяца / средневзв. contribution; `None` если contribution ≤ 0), `ltv` (`contribution_per_unit / churn`; `None` если churn нет или 0), `ltv_cac`, `cac_payback_months` (`cac / contribution_per_unit`), `warnings: list[str]`;
  `cash_metrics(mi, values) -> dict`: `min_cash`, `min_cash_month` (1-базный), `peak_funding_need` (= `max(0, -min(cash_before_financing_cum))`, где без equity/кредитов), `runway_months` (месяцев до первого `cash < 0`, `None` если не уходит в минус), `breakeven_month` (первый месяц с `ebitda > 0`), `npv_fcf`, `irr_fcf` (FCF = cf_operating + cf_investing, ставка `discount_rate_annual` → месячная `(1+r)^(1/12)-1`), `payback_month`;
  `metric_checks(ue, cm) -> list[dict]` — warnings `negative_cash` (с месяцем), `price_below_variable_cost`, `breakeven_above_capacity`, `ltv_cac_below_3`, `cac_payback_over_12`.

- [ ] **Step 1: Тесты:**
  - `test_contribution`: edtech → `contribution_per_unit == 22000`, `contribution_margin == approx(0.88)`.
  - `test_ltv_and_ratio`: `ltv == approx(22000/0.06)`, `ltv_cac == approx(366666.67/18000)`.
  - `test_zero_churn_gives_none`: churn 0 → `ltv is None`, в `warnings` есть строка про отток.
  - `test_negative_contribution`: price 1000 < variable 3000 → `breakeven_units_per_month is None` и `metric_checks` содержит `price_below_variable_cost`.
  - `test_negative_cash_warning`: equity 0, кредитов нет → `metric_checks` содержит `negative_cash` с `period`; `peak_funding_need > 0`; `runway_months` — целое.
  - `test_irr_none_when_never_positive`: FCF всё время < 0 → `irr_fcf is None`.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): unit economics and cash metrics`.

### Task 6: `scenarios` — три сценария и чувствительность

**Files:** Create `kernel/finsoul/scenarios.py`; Test `tests/kernel/test_scenarios.py`

**Interfaces:**
- Produces: `run_scenarios(mi) -> dict[str, dict]` — для `base`, `upside`, `downside`: `{"values", "unit_economics", "cash_metrics", "checks"}` (строит модель с `scenario_index` 1/2/3); `sensitivity(mi, metric: str = "npv_fcf", step: float = 0.1) -> list[dict]` — для драйверов `price`, `volume`, `variable_costs`, `fixed_costs`: `{"driver", "low", "high"}` при множителе ×(1−step) и ×(1+step) к базовому, отсортировано по размаху (торнадо).

- [ ] **Step 1: Тесты:** `downside` revenue за 36 мес. < `base` < `upside`; `sensitivity` возвращает 4 драйвера, первый по размаху — с максимальным `abs(high-low)`; у каждого сценария `balance_diff` < 0.5.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): scenarios and sensitivity`.

### Task 7: `excel` — xlsx с живыми формулами

**Files:** Create `kernel/finsoul/excel.py`; Test `tests/kernel/test_excel.py`

**Interfaces:**
- Consumes: `Ctx`, `Layout`, `evaluate`, `run_checks`.
- Produces: `write_xlsx(ctx: Ctx, path: str, checks: list[dict]) -> None`. Листы: «Входы» (скаляры: колонка B — подпись, C — значение; ячейка `scenario_index` с проверкой данных 1/2/3 и подписью «1 база, 2 оптимист, 3 пессимист»; ниже — входные ряды по месяцам, начиная с колонки C), «Модель» (секции P&L / Баланс / ДДС, колонка A — подпись, B.. — месяцы, заголовок — `YYYY-MM`), «Проверки» (`balance_diff` формулами + список `checks`). Перед записью устанавливает `ctx.layout`, чтобы `to_excel` давал реальные адреса. Форматы: `money` → `#,##0`, `pct` → `0.0%`. Входы — синий шрифт, формулы — чёрный. Ленивый импорт `openpyxl`; если нет — `RuntimeError("Нужен openpyxl: python3 -m pip install --user openpyxl")`.

- [ ] **Step 1: Тесты** (`pycel.ExcelCompiler`):
  - `test_formulas_not_hardcoded`: каждая ячейка строк `lines` на «Модель» начинается с `=`.
  - `test_pycel_matches_kernel_base`: для `revenue`, `net_income`, `cash`, `balance_diff` в месяцах 1, 12, 36 значение pycel == ядро (`abs=0.01`).
  - `test_pycel_matches_kernel_downside`: записать xlsx, через openpyxl выставить `scenario_index = 3`, сохранить, pycel → совпадает с `run_scenarios(mi)["downside"]["values"]`.
- [ ] **Step 2:** `python3 -m pip install --user -r requirements-dev.txt`, затем тесты → FAIL. **Step 3:** Реализовать. **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): xlsx export with live formulas`.

### Task 8: `report` + CLI + лаунчер

**Files:** Create `kernel/finsoul/report.py`, `kernel/finsoul/cli.py`, `kernel/run.py`; Test `tests/kernel/test_cli.py`

**Interfaces:**
- Produces: CLI `python3 kernel/run.py build <inputs.json> --out <dir> [--no-xlsx]` → пишет `<dir>/report.md`, `<dir>/checks.json` (`{"errors": [...], "warnings": [...], "scenario_results": {...}}`), `<dir>/model.xlsx`; выход 0 — ок, 1 — есть `error` в проверках (файлы всё равно пишутся), 2 — ошибка входов (сообщения на stderr по одному на строку `путь: сообщение`). `python3 kernel/run.py check-env` → печатает версию Python и наличие openpyxl, выход 0/1. `run.py` проверяет `sys.version_info >= (3, 9)` до импортов, добавляет свою папку в `sys.path`.
- `render_report(mi, scen: dict, sens: list) -> str` — разделы: «Итог» (5 строк: выручка за горизонт, месяц безубыточности по EBITDA, пиковая потребность в деньгах, NPV/IRR FCF, LTV/CAC), «Сценарии» (таблица 3 колонки), «Чувствительность», «Юнит-экономика», «Деньги», «P&L по годам», «Проверки», «Допущения и упрощения v0.1» (НДС сквозной, налог в месяце начисления, одна валюта), «Не является финансовой, налоговой или юридической консультацией». Числа — с пробелами-разделителями тысяч и валютой. `None` → «не определена».

- [ ] **Step 1: Тесты:** `build` на fixture во временную папку → код 0, три файла есть, в `report.md` есть «Итог» и «Сценарии»; битый input → код 2, stderr содержит `revenue_streams[0].price`, нет traceback (`"Traceback" not in stderr`); IRR None → в отчёте «не определена».
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** PASS. **Step 5:** Коммит `feat(kernel): report and cli`.

### Task 9: Оболочка плагина: манифесты, хук, душа, валидатор

**Files:**
- Create: `.claude-plugin/marketplace.json` (маркетплейс `finance-soul`, плагин `finance-soul`, source `./plugins/finance-soul`, license MIT, owner aibatjardem), `plugins/finance-soul/.claude-plugin/plugin.json` (name `finance-soul`, version `0.1.0`, description на русском), `hooks/hooks.json` и `hooks/run-hook.cmd` (скопировать из `/Volumes/TRANSCEND/claude/agentsoul/src/shared/hooks/`), `hooks/session-start` (адаптация agentsoul: каталог `.finsoul/`, только bash builtins, не следует симлинкам, всегда exit 0 и валидный JSON, бюджет 9000), `hooks/soul-core.md` (сжатая душа: красные линии из спеки, иерархия правил, «перед задачей», список skills и агентов с префиксом `finance-soul:`).
- Сводка хука: нет `.finsoul/` → «Finance Soul не настроен: предложи /finance-soul:setup»; есть → список файлов, отметка `TBD`, список `models/*/inputs.json`, содержимое `local/*.md` (по бюджету).
- Test: `tests/plugin/test_hook.py`, `tests/plugin/test_validate.py`

- [ ] **Step 1: Тесты:**
  - `test_hook_no_finsoul`: запуск `bash hooks/session-start` с `CLAUDE_PROJECT_DIR=<tmp>` → JSON, `hookSpecificOutput.additionalContext` содержит `/finance-soul:setup`, длина < 9000.
  - `test_hook_with_finsoul_lists_models`: tmp с `.finsoul/company.md` и `.finsoul/models/m1/inputs.json` → контекст упоминает `m1`.
  - `test_hook_ignores_symlink`: `.finsoul/local/x.md` → симлинк на файл с `SECRET` → `SECRET` не в выводе.
  - `test_frontmatter`: каждый `agents/*.md` и `skills/*/SKILL.md` имеет `name` = имя файла/папки и английский `description` (ASCII-проверка); у агентов нет полей кроме разрешённых.
  - `test_core_budget`: `len(soul-core.md) < 6000` (запас под сводку).
- [ ] **Step 2:** `python3 -m pytest tests/plugin -v` → FAIL. (`test_references_exist` пишется в Task 11, когда skills и агенты уже есть.)
- [ ] **Step 3:** Реализовать. **Step 4:** `python3 -m pytest tests/plugin -v` → PASS. **Step 5:** Коммит `feat(plugin): manifests, session-start hook, compact soul`.

### Task 10: Skills, шаблоны, профили

**Files:** Create `skills/{setup,soul,kernel-reference,assumptions,three-statement-guide,unit-economics-guide,cash-runway-guide,business-plan-guide}/SKILL.md`, `templates/*`, `profiles/{blank,edtech}/*`.

Содержание (на русском, своими словами; методика — из `financial-services` 3-statement/audit-xls, `openfpa` cfo-judgment/cash-runway, `founder-skill` founder-cfo — указать в `NOTICE`):
- `setup` — диалог: новый бизнес или действующий; отрасль → профиль (`blank`/`edtech`); для кого модель (инвестор/банк/госпрограмма/себе); валюта; ставка КПН и источник. Создаёт `.finsoul/` из шаблонов, не перезаписывая существующее; кладёт `models/main/inputs.json` из профиля; в конце — запуск `kernel-reference` → `build`.
- `soul` — полный текст души и карта команды.
- `kernel-reference` — команды CLI с `${CLAUDE_PLUGIN_ROOT}/kernel/run.py`, полная схема `inputs.json` (из Task 3), коды выхода, как читать `checks.json`, правило «нет функции — не считаем руками».
- `assumptions` — формат реестра (`| параметр | значение | ед. | источник | уверенность: факт/публичная цена/оценка | дата |`), иерархия источников, ramp как главное место для лжи.
- Гайды: три формы (связи, проверки, типичные ошибки — D&A, оборотный капитал, перенос убытка), юнит-экономика (определения, пороги LTV/CAC ≥ 3, окупаемость CAC ≤ 12 мес.), cash/runway (прибыль ≠ деньги, пиковая потребность, 13 недель — как идея на v0.2), бизнес-план (структура разделов под инвестора и под банк РК; каждая цифра — ссылка на `report.md`).
- Шаблоны `company.md`, `metrics.md`, `assumptions.md` с маркерами `TBD`; `local/rules.md`.
- Профиль `edtech`: `inputs.json` = `tests/fixtures/edtech_inputs.json`; `metrics.md` — MRR, ARPU, отток, LTV, CAC, LTV/CAC, окупаемость CAC, маржинальность, загрузка преподавателей; `blank` — пустые шаблоны и минимальный `inputs.json` с одним потоком.

- [ ] **Step 1:** Добавить тест `tests/plugin/test_profiles.py::test_profile_inputs_valid` — каждый `profiles/*/inputs.json` проходит `parse_inputs`, а `build` на нём даёт код 0 или 1 (не 2).
- [ ] **Step 2:** FAIL. **Step 3:** Написать файлы. **Step 4:** `python3 -m pytest tests/plugin -v` → frontmatter и профили PASS. **Step 5:** Коммит `feat(plugin): skills, templates, profiles`.

### Task 11: Субагенты

**Files:** Create `agents/model-builder.md` (tools: Read, Write, Edit, Bash, Glob, Skill; skills: `finance-soul:kernel-reference`, `finance-soul:three-statement-guide`, `finance-soul:assumptions`), `agents/model-auditor.md` (Read, Grep, Glob, Bash, Skill; skills: `kernel-reference`, `three-statement-guide` — проверяет `checks.json`, что ключевые ячейки xlsx — формулы, что у каждого входа есть строка в `assumptions.md`; RO), `agents/cfo-reviewer.md` (Read, Grep, Glob, Bash, Skill; skills: `unit-economics-guide`, `cash-runway-guide` — рефлексы CFO по мотивам cfo-judgment, переписанные под стартап/малый бизнес: ramp, прибыль vs деньги, пиковая потребность, LTV/CAC, концентрация допущений-оценок; RO).
Каждый агент: блок «Контекст проекта — прочитать ПЕРВЫМ» (`.finsoul/local`, `company.md`, `metrics.md`, `assumptions.md`) и stop-режим при `TBD`/отсутствии → подсказать `/finance-soul:setup`; формат ответа.

- [ ] **Step 1:** Добавить в `tests/plugin/test_validate.py` тест `test_references_exist`: каждое `finance-soul:<x>` во всех `plugins/**/*.md` — существующий skill или агент; запустить → FAIL (агентов нет). **Step 2:** Написать агентов. **Step 3:** весь `pytest` → PASS. **Step 4:** Коммит `feat(plugin): model-builder, model-auditor, cfo-reviewer agents`.

### Task 12: Пример, документация, CI

**Files:** Create `examples/edtech/.finsoul/{company.md,metrics.md,assumptions.md,models/main/inputs.json}` (заполненные, без `TBD`) и `examples/edtech/.finsoul/models/main/out/` (сгенерировать `build`, закоммитить report.md и checks.json, xlsx тоже), `README.md` (что это, установка 3 шага, быстрый старт, пример вывода отчёта, архитектура слоёв, ограничения v0.1, план v0.2, лицензии), `NOTICE` (источники: anthropics/financial-services Apache-2.0, JeffBrines/openfpa MIT, Jakeschincariol/founder-skill MIT, aibatjardem/agentsoul MIT — что именно взято), `CLAUDE.md` (как разрабатывать: правь `plugins/finance-soul/`, после правки `python3 -m pytest`; живой запуск `claude --plugin-dir plugins/finance-soul`), `.github/workflows/ci.yml` (matrix python 3.9 и 3.12, `pip install -r requirements-dev.txt`, `pytest`, плюс шаг: `build` примера и `git diff --exit-code examples/` — пример не устарел; сравнивать только `report.md` и `checks.json`).
Test: `tests/plugin/test_example.py::test_example_up_to_date` — `build` примера во tmp, `report.md` совпадает с закоммиченным.

- [ ] **Step 1:** тест → FAIL. **Step 2:** создать файлы, сгенерировать вывод. **Step 3:** весь `pytest` → PASS. **Step 4:** Коммит `docs: example, readme, notice, ci`.

### Task 13: Живая проверка и публикация

- [ ] **Step 1:** Во временной пустой папке: `claude -p --plugin-dir <repo>/plugins/finance-soul "/finance-soul:setup ..."` невозможно интерактивно — поэтому проверить: (а) `bash plugins/finance-soul/hooks/session-start` в пустой папке и в `examples/edtech` даёт ожидаемую сводку; (б) `claude --plugin-dir plugins/finance-soul -p "Перечисли skills и агентов плагина finance-soul"` в `examples/edtech` — ответ называет их с префиксом. Зафиксировать вывод в отчёте владельцу.
- [ ] **Step 2:** `gh repo create aibatjardem/finance-soul --public --source . --description "Finance Soul — душа финансиста для Claude Code: финмодели, бизнес-планы, юнит-экономика, runway. Числа считает протестированное ядро." --push`.
- [ ] **Step 3:** `gh run watch` — CI зелёный на 3.9 и 3.12.
