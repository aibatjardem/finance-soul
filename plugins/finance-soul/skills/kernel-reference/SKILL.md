---
name: kernel-reference
description: Reference for the Finance Soul calculation kernel - CLI commands, the full inputs.json schema, exit codes and how to read checks.json and report.md. Load before building, changing or explaining any financial model with Finance Soul.
---

# Ядро Finance Soul

Все числа модели считает ядро — протестированный Python-код. Ты готовишь входы, запускаешь ядро и объясняешь результат. Нет нужного расчёта в ядре — так и говоришь; не считаешь «в уме» и не подставляешь цифры руками.

## Где ядро

Путь сообщает хук при старте сессии: строка «Ядро на этой машине: python3 "…/kernel/run.py"». Если строки нет: `find ~/.claude/plugins -path '*finance-soul*/kernel/run.py' 2>/dev/null | head -1`. Нужен Python 3.9+, для Excel — `openpyxl`.

## Команды

```bash
python3 "<run.py>" check-env                                   # версия Python, есть ли openpyxl
python3 "<run.py>" build <inputs.json> --out <папка>           # report.md, checks.json, model.xlsx
python3 "<run.py>" build <inputs.json> --out <папка> --no-xlsx # без Excel
```

Коды выхода: **0** — готово; **1** — модель не прошла проверки целостности (файлы записаны, но выводы не делаем) или не удалось записать Excel; **2** — ошибка во входах (по строке на ошибку в stderr: `путь.к.полю: что не так`); **3** — внутренняя ошибка ядра: результат не записан, файлы в `out/` могут быть от прошлого запуска — **не цитируй их**, покажи сообщение пользователю.

Принято: модель лежит в `.finsoul/models/<имя>/inputs.json`, расчёт — в `.finsoul/models/<имя>/out/`.

## Схема inputs.json

Месяцы во входах считаются с 1 (1 — первый месяц модели). Суммы — в валюте модели, **без НДС**.

| Поле | Тип | По умолчанию | Смысл |
|---|---|---|---|
| `name` | строка | — | название модели |
| `currency` | строка | `KZT` | валюта (одна на модель) |
| `start` | `ГГГГ-ММ` | — | первый месяц |
| `months` | целое 1..120 | — | горизонт |
| `opening_cash` | число | 0 | деньги на начало (считаются вложенным капиталом) |
| `scenario` | `base` / `upside` / `downside` | `base` | сценарий отчёта и Excel |
| `scenarios.<имя>.{price,volume,variable_costs,fixed_costs}` | множители | base 1/1/1/1, upside 1/1,2/1/1, downside 0,9/0,8/1,15/1,1 | сценарии |
| `revenue_streams[]` | список, ≥1 | — | потоки выручки |
| `  .name`, `.unit` | строки | unit=`единица` | название, единица продажи |
| `  .price`, `.variable_cost` | числа ≥0 | variable_cost=0 | цена и переменные затраты на единицу |
| `  .ramp` | список чисел, ≥1 | — | объём по месяцам на выходе на план |
| `  .growth_monthly` | доля от −1 до 1 | 0 | рост объёма в месяц после ramp |
| `  .capacity` | число | нет | потолок объёма в месяц |
| `fixed_costs[]` | `{name, monthly, growth_annual=0, start_month=1}` | — | постоянные затраты; рост ступенькой раз в 12 мес. |
| `capex[]` | `{name, month, amount, life_months}` | — | капвложения; амортизация линейная с месяца после покупки |
| `financing.equity[]` | `{month, amount}` | — | взносы в капитал |
| `financing.loans[]` | `{name, month, amount, rate_annual, term_months}` | — | кредиты: аннуитет с месяца после получения, ставка номинальная (годовая/12) |
| `working_capital` | `{dso_days=0, dpo_days=0}` | — | дебиторка = выручка×дни/30, кредиторка = затраты×дни/30 |
| `tax` | `{cit_rate=0.2, source}` | — | ставка КПН; `source` обязателен, если ставка > 0 |
| `unit_economics` | `{cac, churn_monthly, marketing_line}` | — | для LTV/CAC; `marketing_line` — имя статьи в `fixed_costs` |
| `discount_rate_annual` | доля | 0,25 | ставка дисконтирования для NPV |
| `assumptions_ref` | строка | — | путь к реестру допущений (попадает в отчёт) |
| `fx` | объект | — | зарезервировано под валюты, в v0.1 игнорируется |

Неизвестное поле — ошибка с подсказкой («возможно, revenue_streams»).

## Что выдаёт ядро

- **report.md** — «Итог», «Сценарии», «Чувствительность NPV» (±10% по каждому драйверу), «Юнит-экономика», «Деньги», «P&L по годам», «Проверки», «Допущения и упрощения v0.1». Цитируй числа отсюда, не пересчитывай.
- **checks.json** — `errors` (баланс, деньги и ДДС, нераспределённая прибыль), `warnings` (`negative_cash`, `price_below_variable_cost`, `breakeven_above_capacity`, `ltv_cac_below_3`, `cac_payback_over_12`, `unit_economics_note` — пояснения, почему показатель не определён), `scenario_results` (метрики всех трёх сценариев), `sensitivity`. У предупреждения `period` — месяц с 0.
- **model.xlsx** — листы «Входы» (синие ячейки — входы; ячейка «Сценарий» 1/2/3 переключает всю модель), «Модель» (P&L, ДДС, баланс — всё формулами), «Проверки». Значения в Excel совпадают с ядром — это проверяется тестами.

## Упрощения v0.1 (говори о них, когда они важны для вывода)

НДС сквозной; КПН платится в месяце начисления с переносом убытка; одна валюта; деньги на начало = капитал; график кредита не зависит от сценария; нет запасов, нет DCF с терминальной стоимостью, нет план-факта — это v0.2.
