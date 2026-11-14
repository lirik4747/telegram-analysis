# МосУ МВД · 36 визуализаций + автономный HTML · одна ячейка Google Colab
# Путь пользователя: /Messages_МосУ_МВД_России_имени_В_Я_Кикотя.csv
import sys, subprocess
try:
    import google.colab
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
if IN_COLAB:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
        "pandas>=2.2,<4", "numpy>=1.26,<3", "plotly>=5.24,<8",
        "ipywidgets>=8.1,<9", "matplotlib>=3.9,<4", "nbformat>=5,<6"])
    from google.colab import output
    output.enable_custom_widget_manager()

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from html import escape
import ast, csv, hashlib, json, re, shutil, textwrap
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import ipywidgets as W
from IPython.display import display, HTML, clear_output, FileLink
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 1. НАСТРОЙКИ
DATA_PATH = Path("/Messages_МосУ_МВД_России_имени_В_Я_Кикотя.csv")
OUTPUT_DIR = Path("/content/telegram_analysis") if IN_COLAB else Path.cwd() / "telegram_analysis_output"
TZ = "Europe/Moscow"
DPI = 220
BLUE, ORANGE, INK, GRID = "#2458BC", "#BA591F", "#172B4D", "#E7EDF5"
PALETTE = [BLUE, ORANGE, "#148A81", "#8257B5", "#CB4872", "#68843B", "#41788E"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
METRICS = ["views", "comments", "reactions_total", "forwards"]
CONFIG = dict(displaylogo=False, responsive=True, scrollZoom=True,
    toImageButtonOptions=dict(format="png", width=1600, height=950, scale=2))
pio.templates.default = "plotly_white"
pio.renderers.default = "colab" if IN_COLAB else "plotly_mimetype"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": GRID, "grid.color": GRID, "text.color": INK,
    "axes.labelcolor": INK, "figure.facecolor": "white"})
CSS = """<style>
.tg{font:15px/1.6 Arial,sans-serif;color:#172B4D;background:#F5F7FB;padding:24px;
border-radius:16px;margin:14px 0}.tg h1{font-size:28px;line-height:1.25;margin:8px 0}
.tg-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0}
.tg-card{background:white;border:1px solid #E7EDF5;border-radius:10px;padding:16px}
.tg-card small,.tg-note{color:#53657D}.tg-value{font-size:25px;font-weight:bold}
.tg-table{font:13px/1.5 Arial,sans-serif;border-collapse:collapse;width:100%;color:#172B4D;
background:white;margin:16px 0}.tg-table th{background:#172B4D;color:white;text-align:left;padding:10px}
.tg-table td{padding:9px;border-bottom:1px solid #E7EDF5;vertical-align:top}
.tg-table tr:nth-child(even){background:#F5F7FB}</style>"""
STOPWORDS = set("""который которая которые также этого этой своих свои всех всем очень
более были было будет быть есть после перед между через когда чтобы потому сегодня
вчера завтра этот этой этих наши наша наше наши вами вами нас вас для при или как что
это они она его ему нее ним над под уже еще всё все так только имени россии российской
российского российские московского московском московский университета университет
университете университетом мосу мвд кикотя мосумвд мосумвдроссии университетмвд
mosumvd https http подробнее читайте официальный официальном сайте сайт ссылка
ссылке press sluzhba novosti item состоялась состоялось состоялся прошла прошло""".split())
REACTION_NAMES = {":red_heart:": "Сердце", ":fire:": "Огонь", ":thumbs_up:": "Одобрение",
    ":clapping_hands:": "Аплодисменты", ":party_popper:": "Праздник", ":trophy:": "Кубок",
    "\\U0001fae1": "Приветствие", ":smiling_face_with_hearts:": "Улыбка с сердцами",
    ":star-struck:": "Восхищение", ":folded_hands:": "Благодарность",
    ":red_heart:\\u200d:fire:": "Горящее сердце", ":smiling_face_with_heart-eyes:": "Влюблённость",
    ":hundred_points:": "Сто баллов", ":thumbs_down:": "Неодобрение"}

def fmt(x, decimals=1, suffix=""):
    return "—" if pd.isna(x) else f"{x:,.{decimals}f}".replace(",", " ") + suffix

def reaction_map(value):
    if not str(value).strip():
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(str(value))
            if not isinstance(obj, dict):
                continue
            result = {}
            for key, number in obj.items():
                number = float(number)
                if not np.isfinite(number) or number < 0 or number != int(number):
                    raise ValueError("Некорректный счётчик реакции")
                result[str(key)] = int(number)
            return result
        except (ValueError, TypeError, SyntaxError, RecursionError, OverflowError):
            continue
    return None

# 2. ЧТЕНИЕ И КОНТРОЛЬ КАЧЕСТВА
def load_data(requested=DATA_PATH):
    paths = [Path(requested), Path("/content") / Path(requested).name,
             Path.cwd() / Path(requested).name]
    path = next((p for p in paths if p.is_file()), None)
    if path is None and IN_COLAB:
        from urllib.request import urlretrieve
        from urllib.parse import quote
        target = Path("/content") / Path(requested).name
        url = "https://raw.githubusercontent.com/lirik4747/telegram-analysis/main/" + quote(target.name)
        print("Скачиваю исходный CSV из репозитория…")
        urlretrieve(url, target)
        expected = "cd5b84c3e47fa3c2d0c206e5ec3c35bca96352556bfcdcd0f2471e4037179846"
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            target.unlink(missing_ok=True)
            raise ValueError("Контрольная сумма скачанной базы не совпала. Загрузите свой CSV вручную.")
        path = target
    if path is None:
        raise FileNotFoundError("Загрузите CSV в Colab. Проверены пути: " + ", ".join(map(str, paths)))
    for encoding in ["utf-8-sig", "cp1251"]:
        try:
            with path.open(encoding=encoding) as file:
                sample = file.read(30000)
            try:
                separator = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
            except csv.Error:
                separator = ";"
            raw = pd.read_csv(path, sep=separator, encoding=encoding, dtype=str, keep_default_na=False)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Не удалось определить кодировку CSV.")
    raw.columns = raw.columns.str.strip().str.lower()
    required = {"date", "message_id", "message", "views", "reactions_total", "forwards"}
    if not required.issubset(raw.columns):
        raise ValueError("Отсутствуют столбцы: " + str(sorted(required - set(raw.columns))))
    for name in ["comments", "reactions", "channel_id", "channel_name", "channel_members_count"]:
        if name not in raw:
            raw[name] = ""
    quality = {"Строк в CSV": len(raw)}
    d = raw.copy()
    d["DateUTC"] = pd.to_datetime(d.date, utc=True, errors="coerce", format="mixed")
    quality["Исключено: некорректная дата"] = int(d.DateUTC.isna().sum())
    d = d.loc[d.DateUTC.notna()].copy()
    # Дедупликация только по непустому ID внутри канала.
    d["ChannelKey"] = d.channel_id.where(d.channel_id.str.strip().ne(""), d.channel_name)
    duplicate = d.duplicated(["ChannelKey", "message_id"], keep="last")
    duplicate &= d.message_id.str.strip().ne("")
    quality["Исключено: повтор ID внутри канала"] = int(duplicate.sum())
    d = d.loc[~duplicate].copy()
    for name in METRICS + ["channel_members_count"]:
        text = d[name].str.strip()
        number = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
        good = np.isfinite(number) & number.ge(0) & number.eq(np.floor(number))
        quality[f"Некорректных значений {name}"] = int((text.ne("") & ~good).sum())
        d[name] = number.where(good)
    d["ReactionMap"] = d.reactions.map(reaction_map)
    parsed = d.ReactionMap.map(lambda v: sum(v.values()) if isinstance(v, dict) else np.nan)
    quality["Неразобранных непустых словарей реакций"] = int((d.reactions.str.strip().ne("") & parsed.isna()).sum())
    quality["Расхождений суммы реакций и словаря"] = int((parsed.notna() & d.reactions_total.notna() & parsed.ne(d.reactions_total)).sum())
    quality["Счётчиков реакций восстановлено из словаря"] = int((d.reactions_total.isna() & parsed.notna()).sum())
    d["reactions_total"] = d.reactions_total.fillna(parsed)
    d["Text"] = d.message.str.strip().where(~d.message.str.strip().str.lower().eq("mediamessage"), "")
    d["Date"] = d.DateUTC.dt.tz_convert(TZ)
    d["UnitSize"] = 1
    d = d.sort_values("DateUTC", kind="stable").reset_index(drop=True)
    quality["Принято записей"] = len(d)
    assert len(d) + quality["Исключено: некорректная дата"] + quality["Исключено: повтор ID внутри канала"] == len(raw)
    quality["Записей с маркером MediaMessage"] = int(d.message.str.strip().str.lower().eq("mediamessage").sum())
    quality["Пустых комментариев: неизвестное значение"] = int(d.comments.isna().sum())
    if d.empty:
        raise ValueError("Не осталось записей с корректными датами.")
    metadata = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_start=d.Date.min().isoformat(), source_end=d.Date.max().isoformat(),
        subscribers_values=sorted(d.channel_members_count.dropna().unique().tolist()))
    return d, pd.DataFrame(list(quality.items()), columns=["Проверка всего CSV", "Значение"]), metadata

def select_data(source, start, end, level="Записи CSV", content="Все"):
    left = pd.Timestamp(start, tz=TZ)
    right = pd.Timestamp(end, tz=TZ) + pd.Timedelta(days=1)
    if left >= right:
        raise ValueError("Начальная дата позже конечной.")
    if left.date() < source.Date.min().date() or pd.Timestamp(end).date() > source.Date.max().date():
        raise ValueError("Выберите даты внутри диапазона исходного CSV.")
    d = source.loc[source.Date.ge(left) & source.Date.lt(right)].copy()
    if level != "Записи CSV":
        units = []
        for _, g in d.groupby(["ChannelKey", "DateUTC"], sort=False, dropna=False):
            row = g.iloc[0].copy()
            for metric in METRICS:
                row[metric] = g[metric].max()
            best = g.sort_values("reactions_total", ascending=False, na_position="last").iloc[0]
            row["ReactionMap"] = best.ReactionMap
            row["Text"] = "\n\n".join(dict.fromkeys(t for t in g.Text if t))
            row["UnitSize"] = int(g.UnitSize.sum())
            units.append(row)
        d = pd.DataFrame(units, columns=d.columns)
    if content == "С текстом":
        d = d.loc[d.Text.ne("")].copy()
    elif content == "Без текста":
        d = d.loc[d.Text.eq("")].copy()
    if d.empty:
        raise ValueError("В выбранном периоде и фильтре нет записей.")
    d["Kind"] = np.where(d.Text.ne(""), "С текстом", "Без текста")
    d["Length"] = d.Text.str.len()
    d["Rate"] = (100 * d.reactions_total / d.views).where(d.views.gt(0))
    return d.sort_values("DateUTC", kind="stable").reset_index(drop=True)

def frequencies(d, hashtags=False):
    counts = Counter()
    for text in d.Text:
        if hashtags:
            tokens = re.findall(r"(?<!\w)#([\w]+)", text.lower())
        else:
            clean = re.sub(r"https?://\S+|www\.\S+|#[\w]+|@[\w]+", " ", text.lower())
            tokens = [t for t in re.findall(r"[а-яёa-z]{4,}", clean)
                      if t not in STOPWORDS]
        counts.update(set(tokens))
    return pd.DataFrame(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20], columns=["Термин", "Записей"])

def table_html(frame):
    return frame.to_html(index=False, border=0, classes="tg-table", escape=True,
        na_rep="—", float_format=lambda x: fmt(x, 2))

# 3. ОБЩИЕ ДАННЫЕ ГРАФИКОВ: ОДНИ РАСЧЁТЫ ДЛЯ PLOTLY И PNG
def build_report(source, quality, metadata, start, end, level, content, min_views=300, log_views=True):
    d = select_data(source, start, end, level, content)
    period = f"{start:%d.%m.%Y} — {end:%d.%m.%Y} · {TZ}"
    scope = f"{level} · {content}"
    start_day, end_day = pd.Timestamp(start), pd.Timestamp(end)
    days = pd.date_range(start_day, end_day, freq="D")
    local_days = d.Date.dt.tz_localize(None).dt.normalize()
    activity = d.groupby(local_days).size().reindex(days, fill_value=0)
    temp = d.assign(Month=d.Date.dt.strftime("%Y-%m"))
    months = pd.period_range(start_day, end_day, freq="M").astype(str)
    composition = pd.crosstab(temp.Month, temp.Kind).reindex(index=months,
        columns=["С текстом", "Без текста"], fill_value=0).fillna(0)
    monthly = temp.groupby("Month").agg(Записей=("views", "size"),
        Известных_просмотров=("views", "count"), Медиана_просмотров=("views", "median"),
        Q25=("views", lambda v: v.quantile(.25)), Q75=("views", lambda v: v.quantile(.75)))
    monthly = monthly.reindex(months)
    monthly["Записей"] = composition.sum(axis=1)
    monthly["Дней_в_фильтре"] = [sum(days.strftime("%Y-%m") == month) for month in months]
    monthly["Записей_в_день"] = monthly.Записей / monthly.Дней_в_фильтре
    monthly.index.name = "Месяц"
    heat = pd.crosstab(d.Date.dt.day_of_week, d.Date.dt.hour).reindex(
        index=range(7), columns=range(24), fill_value=0).fillna(0)
    reactions = Counter()
    for item in d.ReactionMap:
        if isinstance(item, dict):
            reactions.update(item)
    reaction_table = pd.DataFrame(reactions.most_common(15), columns=["Ключ", "Количество"])
    reaction_table["Реакция"] = reaction_table.Ключ.map(
        lambda k: REACTION_NAMES.get(k, k.encode("ascii", "backslashreplace").decode("ascii")))
    words, tags = frequencies(d), frequencies(d, True)
    if not tags.empty:
        tags["Термин"] = "#" + tags.Термин
    valid_rate = d.views.gt(0) & d.reactions_total.notna()
    weighted_rate = (100 * d.loc[valid_rate, "reactions_total"].sum()
                     / d.loc[valid_rate, "views"].sum()) if valid_rate.any() else np.nan
    cards = {"Единиц анализа": fmt(len(d), 0), "С текстом": fmt(d.Text.ne("").sum(), 0),
        "Медиана просмотров": fmt(d.views.median(), 0),
        "Реакций на 100 просмотров": fmt(weighted_rate, 2),
        "Комментариев известно": fmt(d.comments.notna().mean() * 100, 1, "%"),
        "Строк CSV в выборе": fmt(d.UnitSize.sum(), 0)}
    specs = []
    def add(key, kind, title, note, **values):
        specs.append(dict(key=key, kind=kind, title=title, note=note, **values))
    add("activity", "line", "Активность по дням", "Нули означают отсутствие записей в CSV, а не доказанное отсутствие публикаций.",
        x=days, series={"Единиц в день": activity, "Среднее за 7 дней": activity.rolling(7, min_periods=7).mean()}, ylabel="Единиц анализа")
    add("monthly", "stack", "Состав выгрузки по месяцам", "Крайние месяцы могут быть неполными. Сопоставляйте также число единиц в день в таблице.",
        x=list(months), series={k: composition[k] for k in composition}, ylabel="Единиц анализа")
    add("views", "band", "Просмотры по месяцам: медиана и разброс", "Полоса — 25–75-й перцентили наблюдений, не доверительный интервал. Возраст сообщений различается.",
        x=pd.to_datetime(months), y=monthly.Медиана_просмотров, lo=monthly.Q25,
        hi=monthly.Q75, n=monthly.Известных_просмотров, ylabel="Просмотры", log_y=log_views)
    add("hours", "heat", "Дни недели и часы публикации", "Число единиц анализа по времени публикации. Часы московские; это не рекомендация оптимального времени.",
        z=heat.to_numpy(), xlabel="Час по Москве", ylabel="День недели")
    add("distribution", "hist", "Распределение просмотров", "Счётчики накопленные; дата их измерения в CSV не указана. Все наблюдения сохранены.",
        values=d.views.dropna().to_numpy(), xlabel="Просмотры", ylabel="Число единиц")
    add("reactions", "bar", "Какие реакции встречаются чаще", "Только успешно разобранные словари. Отсутствующий словарь не заменяется нулевым набором реакций.",
        labels=reaction_table.Реакция.tolist(), values=reaction_table.Количество.tolist(), xlabel="Количество реакций")
    scatter = d.loc[d.views.gt(0) & d.reactions_total.notna()]
    add("engagement", "scatter", "Просмотры и реакции", "Одна точка — выбранная единица анализа. Реакции не равны числу уникальных пользователей.",
        x=scatter.views.to_numpy(), y=scatter.reactions_total.to_numpy(),
        group=scatter.Kind.to_numpy(), dates=scatter.Date.dt.strftime("%d.%m.%Y %H:%M").to_numpy(),
        xlabel="Просмотры", ylabel="Реакции", log_x=log_views)
    groups = {kind: g.views.dropna().loc[lambda s: s.gt(0) if log_views else s.ge(0)].to_numpy()
              for kind, g in d.groupby("Kind")}
    add("formats", "box", "Просмотры записей с текстом и без текста", "Группы описательные. MediaMessage не позволяет отличить фото от видео; влияние формата не доказано.",
        groups=groups, ylabel="Просмотры", log_y=log_views)
    add("words", "bar", "Частые слова в текстах", "Число текстов со словом; повторы внутри текста не суммируются. Словоформы без лемматизации; стоп-слова удалены.",
        labels=words.Термин.tolist(), values=words.Записей.tolist(), xlabel="Текстов со словом")
    add("hashtags", "bar", "Частые хештеги", "Число текстов с хештегом; одинаковый хештег учитывается один раз в тексте.",
        labels=tags.Термин.tolist(), values=tags.Записей.tolist(), xlabel="Текстов с хештегом")
    lengths = d.loc[d.Length.gt(0) & d.views.notna() & (d.views.gt(0) if log_views else d.views.ge(0))]
    add("length", "scatter", "Длина текста и просмотры", "Длина исходного текста в символах, включая ссылки и хештеги. Корреляция не означает причинность.",
        x=lengths.Length.to_numpy(), y=lengths.views.to_numpy(), group=lengths.Kind.to_numpy(),
        dates=lengths.Date.dt.strftime("%d.%m.%Y %H:%M").to_numpy(),
        xlabel="Символов в тексте", ylabel="Просмотры", log_y=log_views)
    available = {"Просмотры": d.views.notna().mean(), "Комментарии": d.comments.notna().mean(),
        "Всего реакций": d.reactions_total.notna().mean(), "Пересылки": d.forwards.notna().mean(),
        "Словарь реакций": d.ReactionMap.map(lambda x: isinstance(x, dict)).mean()}
    add("availability", "bar", "Полнота счётчиков выбранных данных", "Пустые и некорректные значения неизвестны. Ноль является известным значением.",
        labels=list(available), values=[100 * v for v in available.values()], xlabel="Известно, %", percent=True)
    def top_table(frame):
        frame = frame.copy()
        frame["Дата"] = frame.Date.dt.strftime("%d.%m.%Y %H:%M")
        frame["Текст"] = frame.Text.map(lambda t: textwrap.shorten(re.sub(r"\s+", " ", t), width=95) if t else "MediaMessage / без текста")
        return frame[["Дата", "message_id", "views", "reactions_total", "forwards", "Rate", "Текст"]].rename(
            columns={"message_id": "ID", "views": "Просмотры", "reactions_total": "Реакции", "forwards": "Пересылки", "Rate": "Реакций / 100 просмотров"})
    summary = pd.DataFrame({"Показатель": ["Единица анализа", "Фильтр содержания", "Часовой пояс",
        "Записей с известными просмотрами", "Записей с известными комментариями",
        "Медиана комментариев среди известных", "Медиана пересылок", "Взвешенные реакции на 100 просмотров",
        "Число пар для взвешенного показателя", "Порог просмотров для доли реакций"],
        "Значение": [level, content, TZ, str(d.views.notna().sum()), str(d.comments.notna().sum()),
        fmt(d.comments.median()), fmt(d.forwards.median()), fmt(weighted_rate, 3), str(valid_rate.sum()), str(min_views)]})
    tables = {"summary": summary, "monthly": monthly.reset_index().rename(columns={"Известных_просмотров": "Известных просмотров", "Медиана_просмотров": "Медиана просмотров", "Q25": "25-й перцентиль", "Q75": "75-й перцентиль", "Дней_в_фильтре": "Дней в фильтре", "Записей_в_день": "Записей в день"}),
        "top_views": top_table(d.dropna(subset=["views"]).nlargest(10, "views")),
        "top_reaction_rate": top_table(d.loc[d.views.ge(min_views)].dropna(subset=["Rate"]).nlargest(10, "Rate")),
        "reactions": reaction_table, "words": words, "hashtags": tags, "quality": quality}
    # Дополнительные представления используют тот же отфильтрованный набор d.
    add("cumulative", "line", "Накопленное число единиц анализа", "Накопление строк или временных групп в выбранном периоде; это не рост подписчиков.",
        x=days, series={"Накоплено": activity.cumsum()}, ylabel="Единиц анализа", fill=True)
    weekday_days = pd.Series(days.dayofweek).value_counts().reindex(range(7), fill_value=0)
    weekday_count = d.groupby(d.Date.dt.dayofweek).size().reindex(range(7), fill_value=0)
    weekday_mean = weekday_count / weekday_days.replace(0, np.nan)
    add("weekday_mean", "bar", "Средняя активность по дням недели", "Число единиц делится на число соответствующих календарных дней внутри фильтра, включая дни без записей.",
        labels=WEEKDAYS, values=weekday_mean.tolist(), xlabel="Единиц на календарный день", decimals=2)
    hour_count = d.groupby(d.Date.dt.hour).size().reindex(range(24), fill_value=0)
    add("hourly", "columns", "Распределение публикаций по часам", "Время московское. Частота публикаций не показывает время чтения сообщений.",
        x=list(range(24)), y=hour_count.tolist(), xlabel="Час по Москве", ylabel="Единиц анализа")
    add("daily_distribution", "hist", "Насколько насыщены дни выгрузки", "Включены все календарные дни фильтра, в том числе дни с нулём записей.",
        values=activity.to_numpy(), xlabel="Единиц анализа за день", ylabel="Календарных дней", bins=30)
    add("monthly_daily", "columns", "Средняя активность по месяцам", "Знаменатель — число календарных дней месяца, попавших в фильтр; крайние месяцы могут быть неполными.",
        x=list(months), y=monthly.Записей_в_день.tolist(), xlabel="Месяц", ylabel="Единиц в день")
    add("content_share", "stack100", "Доля записей с текстом по месяцам", "Доли рассчитаны от числа единиц месяца. Месяцы без записей оставлены пустыми.",
        x=list(months), series={k: 100 * composition[k] / composition.sum(axis=1).replace(0, np.nan) for k in composition}, ylabel="Доля единиц, %")
    calendar = pd.DataFrame({"date": days, "n": activity.to_numpy()})
    calendar["week"] = calendar.date - pd.to_timedelta(calendar.date.dt.dayofweek, unit="D")
    weeks = pd.date_range(calendar.week.min(), calendar.week.max(), freq="7D")
    calendar_z = np.full((7, len(weeks)), np.nan)
    calendar_dates = np.full(calendar_z.shape, "Вне выбранного периода", dtype=object)
    for row in calendar.itertuples():
        j = int((row.week - weeks[0]).days // 7)
        calendar_z[row.date.dayofweek, j] = row.n
        calendar_dates[row.date.dayofweek, j] = row.date.strftime("%d.%m.%Y")
    add("calendar", "matrix", "Календарь активности", "Каждая клетка — календарный день. Пустые клетки находятся вне выбранного периода; ноль означает отсутствие записей в CSV.",
        z=calendar_z, x=weeks.strftime("%d.%m.%y").tolist(), y=WEEKDAYS,
        custom=calendar_dates, xlabel="Неделя с понедельника", ylabel="День недели", colorlabel="Единиц", colorscale="Blues")
    unique_times = d.DateUTC.drop_duplicates().sort_values()
    gaps = unique_times.diff().dt.total_seconds().dropna() / 3600
    add("gaps", "hist", "Интервалы между разными моментами публикации", "Совпадающие временные метки объединены только для расчёта интервалов. Показаны интервалы между соседними моментами внутри фильтра.",
        values=gaps.to_numpy(), xlabel="Часов между моментами", ylabel="Интервалов", bins=50)
    ecdf = np.sort(d.views.dropna().to_numpy())
    add("ecdf", "curve", "Какая доля записей набрала заданное число просмотров", "Эмпирическая функция распределения: доля единиц с просмотрами не выше значения на оси X. Включены известные нулевые просмотры.",
        x=ecdf, y=100 * np.arange(1, len(ecdf) + 1) / max(len(ecdf), 1), xlabel="Просмотры", ylabel="Доля единиц, %", step=True)
    month_groups = {m: g.views.dropna().to_numpy() for m, g in temp.groupby("Month")}
    add("monthly_box", "box", "Разброс просмотров внутри каждого месяца", "Коробка — Q25–Q75 и медиана; точки за усами — наблюдения за пределами 1,5 межквартильного размаха. Счётчики разного возраста.",
        groups=month_groups, ylabel="Просмотры", xlabel="Месяц")
    weekday_groups = {WEEKDAYS[k]: g.views.dropna().to_numpy() for k, g in d.groupby(d.Date.dt.dayofweek)}
    add("weekday_violin", "violin", "Распределение просмотров по дням недели", "Ширина показывает сглаженную плотность наблюдений; внутри отмечена медиана. Это описательное сравнение, не доказательство влияния дня недели.",
        groups=weekday_groups, ylabel="Просмотры")
    leaders = d.dropna(subset=["views"]).nlargest(15, "views")
    add("top_views_chart", "bar", "15 лидеров по просмотрам", "ID обозначает единицу выбранного режима; при группировке это ID первой строки временной группы.",
        labels=[f"{row.Date:%d.%m.%y} · ID {row.message_id}" for row in leaders.itertuples()],
        values=leaders.views.tolist(), xlabel="Просмотры")
    ordered = np.sort(d.views.dropna().to_numpy())
    total = ordered.sum()
    add("lorenz", "curve", "Концентрация счётчиков просмотров", "Кривая Лоренца для счётчиков выбранных единиц. Повторные просмотры и счётчики медиагрупп не превращаются в уникальный охват.",
        x=np.linspace(0, 100, len(ordered) + 1), y=np.r_[0, np.cumsum(ordered) / total * 100] if total > 0 else np.full(len(ordered)+1, np.nan),
        xlabel="Доля единиц, от меньших просмотров к большим, %", ylabel="Накопленная доля счётчиков, %", equality=True)
    paired = temp.loc[temp.views.gt(0) & temp.reactions_total.notna()].copy()
    rate_month = paired.groupby("Month").agg(v=("views", "sum"), r=("reactions_total", "sum"), n=("views", "size")).reindex(months)
    add("monthly_rate", "line", "Реакций на 100 просмотров по месяцам", "100 × сумма реакций / сумма просмотров по единицам с обеими известными метриками и просмотрами > 0. Это не среднее процентов строк.",
        x=list(months), series={"Реакций на 100 просмотров": 100 * rate_month.r / rate_month.v.replace(0, np.nan)}, ylabel="Реакций / 100 просмотров")
    add("reaction_distribution", "hist", "Распределение общего числа реакций", "Известные нулевые счётчики сохранены; неизвестные значения исключены.",
        values=d.reactions_total.dropna().to_numpy(), xlabel="Реакций на единицу", ylabel="Единиц анализа", bins=45)
    add("forward_distribution", "hist", "Распределение числа пересылок", "Счётчик forwards показывает пересылки сообщения; это отдельная метрика от признака forwarded.",
        values=d.forwards.dropna().to_numpy(), xlabel="Пересылок на единицу", ylabel="Единиц анализа", bins=45)
    forwarded = d.loc[d.views.notna() & d.forwards.notna()]
    add("forwards_views", "scatter", "Просмотры и пересылки", "Сопоставление накопленных счётчиков. Общая дата их измерения и причинная связь не установлены.",
        x=forwarded.views.to_numpy(), y=forwarded.forwards.to_numpy(), group=forwarded.Kind.to_numpy(),
        dates=forwarded.Date.dt.strftime("%d.%m.%Y %H:%M").to_numpy(), xlabel="Просмотры", ylabel="Пересылки")
    rates = d.loc[d.views.ge(min_views) & d.views.gt(0) & d.Rate.notna()]
    add("rate_views", "scatter", "Доля реакций и число просмотров", f"Только единицы с просмотрами ≥ {min_views}. Порог уменьшает влияние очень маленьких знаменателей; процент не равен доле уникальных людей.",
        x=rates.views.to_numpy(), y=rates.Rate.to_numpy(), group=rates.Kind.to_numpy(), dates=rates.Date.dt.strftime("%d.%m.%Y %H:%M").to_numpy(),
        xlabel="Просмотры", ylabel="Реакций / 100 просмотров")
    correlation_columns = ["views", "reactions_total", "forwards", "comments", "Length"]
    correlation_labels = ["Просмотры", "Реакции", "Пересылки", "Комментарии", "Длина текста"]
    correlation = pd.DataFrame(np.nan, index=correlation_columns, columns=correlation_columns)
    pairs = pd.DataFrame(0, index=correlation_columns, columns=correlation_columns)
    for a in correlation_columns:
        for b in correlation_columns:
            pair = d[[a]].join(d[[b]].rename(columns={b: "second"})).dropna()
            pairs.loc[a, b] = len(pair)
            if len(pair) >= 3 and pair.iloc[:, 0].nunique() > 1 and pair.iloc[:, 1].nunique() > 1:
                correlation.loc[a, b] = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
    add("correlation", "matrix", "Связи между показателями: корреляция Спирмена", "Для каждой пары использованы её полные наблюдения (n в подсказке). Константы и пары с n < 3 пустые. Корреляция не доказывает причинность.",
        z=correlation.to_numpy(), x=correlation_labels, y=correlation_labels, custom=pairs.to_numpy(),
        xlabel="", ylabel="", colorlabel="ρ", colorscale="RdBu", zmin=-1, zmax=1, correlation=True)
    add("length_distribution", "hist", "Распределение длины текстов", "Только непустые тексты. Длина в символах включает ссылки, хештеги и разметку исходного сообщения.",
        values=d.loc[d.Length.gt(0), "Length"].to_numpy(), xlabel="Символов в тексте", ylabel="Текстов", bins=50)
    kind_count = d.Kind.value_counts().reindex(["С текстом", "Без текста"], fill_value=0)
    add("content_donut", "donut", "Состав выбранных единиц по наличию текста", "MediaMessage учитывается как запись без доступного текста. Тип вложения по этому маркеру не определяется.",
        labels=kind_count.index.tolist(), values=kind_count.tolist())
    text_data = d.loc[d.Length.gt(0)].copy()
    text_data["LengthBin"] = pd.cut(text_data.Length, bins=[0, 300, 700, 1200, np.inf], labels=["1–300", "301–700", "701–1200", ">1200"])
    length_groups = {str(label): g.views.dropna().to_numpy() for label, g in text_data.groupby("LengthBin", observed=True)}
    add("length_box", "box", "Просмотры текстов разной длины", "Границы групп заданы в символах. Группы могут различаться темами и возрастом; причинный эффект длины не оценивается.",
        groups=length_groups, xlabel="Символов в тексте", ylabel="Просмотры")
    links = text_data.Text.str.contains(r"https?://|www\.", regex=True, case=False)
    link_groups = {name: text_data.loc[links.eq(flag), "views"].dropna().to_numpy() for flag, name in [(True, "Есть ссылка"), (False, "Без ссылки")]}
    add("links_box", "box", "Просмотры текстов со ссылками и без них", "Проверены только непустые тексты. Ссылка определяется по http(s):// или www.; сравнение описательное.",
        groups=link_groups, ylabel="Просмотры")
    availability_month = temp.groupby("Month")[METRICS].agg(lambda v: 100 * v.notna().mean()).reindex(months)
    add("availability_month", "matrix", "Полнота счётчиков по месяцам", "Процент известных значений среди единиц месяца. В месяце без единиц клетка пустая; пропуски не заменены нулями.",
        z=availability_month.to_numpy().T, x=list(months), y=["Просмотры", "Комментарии", "Реакции", "Пересылки"],
        xlabel="Месяц", ylabel="Показатель", colorlabel="Известно, %", colorscale="Blues", zmin=0, zmax=100)
    tables.update(weekday=pd.DataFrame({"День недели": WEEKDAYS, "Единиц": weekday_count.to_numpy(), "Дней в фильтре": weekday_days.to_numpy(), "Единиц в день": weekday_mean.to_numpy()}),
        correlations=correlation.set_axis(correlation_labels).set_axis(correlation_labels, axis=1).reset_index(names="Показатель"),
        correlation_pairs=pairs.set_axis(correlation_labels).set_axis(correlation_labels, axis=1).reset_index(names="Показатель"))

    return dict(data=d, specs=specs, tables=tables, cards=cards, period=period, scope=scope,
        settings=dict(start=str(start), end=str(end), level=level, content=content,
                      min_views=min_views, log_views=log_views, timezone=TZ), metadata=metadata)

# 4. ДВА РЕНДЕРЕРА ОДНИХ ДАННЫХ
def plotly_chart(s, report):
    f = go.Figure()
    kind = s["kind"]
    if kind in ["line", "stack", "stack100"]:
        for i, (name, values) in enumerate(s["series"].items()):
            color = [BLUE, ORANGE][i % 2]
            trace = (go.Bar(x=s["x"], y=values, name=name, marker_color=color) if kind in ["stack", "stack100"]
                     else go.Scatter(x=s["x"], y=values, name=name, mode="lines+markers" if len(s["x"]) < 3 else "lines", fill="tozeroy" if s.get("fill") else None,
                          line=dict(color=color, width=2, dash="solid" if i == 0 else "dash")))
            f.add_trace(trace)
        f.update_layout(barmode="stack")
    elif kind == "band":
        f.add_trace(go.Scatter(x=s["x"], y=s["hi"], mode="lines", line_width=0, showlegend=False, hoverinfo="skip"))
        f.add_trace(go.Scatter(x=s["x"], y=s["lo"], mode="lines", line_width=0,
            fill="tonexty", fillcolor="rgba(36,88,188,.14)", name="25–75-й перцентили", hoverinfo="skip"))
        f.add_trace(go.Scatter(x=s["x"], y=s["y"], name="Медиана", mode="lines+markers",
            line_color=BLUE, customdata=s["n"], hovertemplate="%{x|%Y-%m}<br>Медиана: %{y:,.1f}<br>n=%{customdata}<extra></extra>"))
    elif kind == "heat":
        f.add_trace(go.Heatmap(z=s["z"], x=list(range(24)), y=WEEKDAYS,
            colorscale="Blues", zmin=0, colorbar_title="Записей",
            hovertemplate="%{y}, %{x}:00<br>Единиц: %{z}<extra></extra>"))
        f.update_xaxes(dtick=1)
        f.update_yaxes(autorange="reversed")
    elif kind == "hist":
        f.add_trace(go.Histogram(x=s["values"], nbinsx=s.get("bins", 60), marker_color=BLUE))
    elif kind == "bar":
        f.add_trace(go.Bar(x=s["values"][::-1], y=s["labels"][::-1], orientation="h",
            marker_color=BLUE, text=[fmt(v, s.get("decimals", 1 if s.get("percent") else 0)) for v in s["values"][::-1]],
            textposition="auto"))
        f.update_xaxes(range=[0, 100] if s.get("percent") else None, rangemode="tozero")
    elif kind == "scatter":
        for i, group in enumerate(pd.unique(s["group"])):
            mask = s["group"] == group
            f.add_trace(go.Scatter(x=s["x"][mask], y=s["y"][mask], name=str(group), mode="markers",
                marker=dict(color=[BLUE, ORANGE][i % 2], size=7, opacity=.55), customdata=s["dates"][mask],
                hovertemplate="%{customdata}<br>x=%{x:,.0f}<br>y=%{y:,.0f}<extra>%{fullData.name}</extra>"))
    elif kind == "box":
        for name, values in s["groups"].items():
            f.add_trace(go.Box(y=values, name=f"{name} · n={len(values)}", quartilemethod="linear",
                marker_color=BLUE, boxpoints="outliers", showlegend=False))
    elif kind == "columns":
        f.add_trace(go.Bar(x=s["x"], y=s["y"], marker_color=BLUE,
            hovertemplate="%{x}<br>%{y:,.2f}<extra></extra>"))
    elif kind == "curve":
        f.add_trace(go.Scatter(x=s["x"], y=s["y"], mode="lines", name="Наблюдения",
            line=dict(color=BLUE, width=3, shape="hv" if s.get("step") else "linear")))
        if s.get("equality"):
            f.add_trace(go.Scatter(x=[0, 100], y=[0, 100], name="Равномерное распределение", mode="lines",
                line=dict(color="#7B879D", dash="dash", width=1.5)))
        f.update_yaxes(range=[0, 100])
    elif kind == "matrix":
        options = dict(z=s["z"], x=s["x"], y=s["y"], colorscale=s["colorscale"],
            zmin=s.get("zmin", 0), zmax=s.get("zmax"), colorbar_title=s["colorlabel"], hoverongaps=False)
        if s.get("correlation"):
            options.update(customdata=s["custom"], texttemplate="%{z:.2f}",
                hovertemplate="%{y} × %{x}<br>ρ=%{z:.3f}<br>n=%{customdata}<extra></extra>")
        elif "custom" in s:
            options.update(customdata=s["custom"], hovertemplate="%{customdata}<br>Единиц: %{z}<extra></extra>")
        else:
            options.update(hovertemplate="%{y} · %{x}<br>%{z:.1f}<extra></extra>")
        f.add_trace(go.Heatmap(**options))
        f.update_yaxes(autorange="reversed")
        f.update_xaxes(nticks=14, tickangle=-30)
    elif kind == "donut":
        f.add_trace(go.Pie(labels=s["labels"], values=s["values"], hole=.63, sort=False,
            marker_colors=PALETTE, textinfo="label+percent", textposition="outside",
            hovertemplate="%{label}<br>Единиц: %{value}<br>%{percent}<extra></extra>"))
        f.add_annotation(text=f"<b>{sum(s['values']):,}</b><br>единиц", x=.5, y=.5,
            xref="paper", yref="paper", showarrow=False, font_size=24)
        f.update_layout(showlegend=False)
    elif kind == "violin":
        for i, (name, values) in enumerate(s["groups"].items()):
            values = np.asarray(values, dtype=float)
            values = values[np.isfinite(values)]
            if len(values) >= 3 and np.ptp(values) > 0:
                f.add_trace(go.Violin(y=values, name=f"{name} · n={len(values)}", box_visible=True,
                    meanline_visible=False, points=False, line_color=PALETTE[i % len(PALETTE)],
                    spanmode="hard", showlegend=False))
            elif len(values):
                f.add_trace(go.Scatter(x=[f"{name} · n={len(values)}"] * len(values), y=values,
                    mode="markers", marker_color=PALETTE[i % len(PALETTE)], showlegend=False))

    height = max(580, len(s.get("labels", [])) * 26 + 240)
    f.update_layout(template="plotly_white", height=height, font=dict(family="Arial", size=14, color=INK),
        title=dict(text=f"<b>{s['title']}</b><br><sup>{report['period']} · {report['scope']}</sup>", x=.03),
        margin=dict(l=100 if kind == "bar" else 70, r=45, t=120, b=115),
        legend=dict(orientation="h", y=1.04, x=0), bargap=.08)
    f.update_xaxes(title=s.get("xlabel", ""), type="log" if s.get("log_x") else None)
    f.update_yaxes(title=s.get("ylabel", ""), gridcolor=GRID, type="log" if s.get("log_y") else None)
    if kind in ["heat", "matrix"]:
        f.update_yaxes(autorange="reversed")
    if kind in ["line", "stack", "hist", "band"] and not s.get("log_y"):
        f.update_yaxes(rangemode="tozero")
    f.add_annotation(x=0, y=-.24, xref="paper", yref="paper", xanchor="left", showarrow=False,
        text="<br>".join(textwrap.wrap(s["note"], 115)), align="left", font=dict(size=12, color="#53657D"))
    if (kind == "bar" and not len(s["labels"])) or (kind == "scatter" and not len(s["x"])):
        f.add_annotation(text="Нет данных для этого графика", x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
    if kind == "stack100":
        f.update_yaxes(range=[0, 100])
    if kind == "box" and len(s["groups"]) > 7:
        f.update_xaxes(tickangle=-35)
    if kind in ["box", "violin"] and not any(len(v) for v in s["groups"].values()):
        f.add_annotation(text="Нет известных значений в выбранных группах", x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
    if kind == "hist" and not len(s["values"]):
        f.add_annotation(text="Нет данных для распределения", x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
    return f

def save_png(s, report, path):
    kind = s["kind"]
    fig, ax = plt.subplots(figsize=(14, max(7, len(s.get("labels", [])) * .32 + 2.6)))
    ax.grid(axis="x" if kind == "bar" else "y", alpha=.7)
    if kind in ["line", "stack", "stack100"]:
        bottom = np.zeros(len(s["x"]))
        for i, (name, values) in enumerate(s["series"].items()):
            if kind == "line":
                ax.plot(s["x"], values, color=[BLUE, ORANGE][i % 2], label=name,
                        linestyle="-" if i == 0 else "--", linewidth=1.7)
                if s.get("fill"):
                    ax.fill_between(s["x"], values, color=BLUE, alpha=.12)
            else:
                ax.bar(s["x"], values, bottom=bottom, color=[BLUE, ORANGE][i % 2], label=name)
                bottom += np.asarray(values, dtype=float)
        ax.legend(frameon=False, loc="upper left", ncol=2)
        if kind in ["stack", "stack100"]:
            ax.tick_params(axis="x", labelrotation=45)
    elif kind == "band":
        ax.fill_between(s["x"], s["lo"], s["hi"], color=BLUE, alpha=.13, label="25–75-й перцентили")
        ax.plot(s["x"], s["y"], color=BLUE, marker="o", markersize=4, label="Медиана")
        ax.legend(frameon=False, loc="upper left")
    elif kind == "heat":
        image = ax.imshow(s["z"], aspect="auto", cmap="Blues", vmin=0)
        ax.set_xticks(range(24)); ax.set_yticks(range(7), WEEKDAYS)
        ax.grid(False); fig.colorbar(image, ax=ax, pad=.02, label="Единиц анализа")
    elif kind == "hist":
        ax.hist(s["values"], bins=s.get("bins", 60), color=BLUE)
    elif kind == "bar":
        labels, values = s["labels"][::-1], s["values"][::-1]
        ax.barh(labels, values, color=BLUE)
        for i, value in enumerate(values):
            if np.isfinite(value):
                ax.text(value, i, " " + fmt(value, s.get("decimals", 1 if s.get("percent") else 0)), va="center", fontsize=10)
        ax.set_xlim(0, 108 if s.get("percent") else max([v for v in values if np.isfinite(v)] + [1]) * 1.17)
    elif kind == "scatter":
        for i, group in enumerate(pd.unique(s["group"])):
            mask = s["group"] == group
            ax.scatter(s["x"][mask], s["y"][mask], color=[BLUE, ORANGE][i % 2],
                       s=18, alpha=.45, label=str(group), linewidths=0)
        if len(s["x"]):
            ax.legend(frameon=False)
    elif kind == "box":
        groups = s["groups"]
        if groups:
            ax.boxplot(list(groups.values()), tick_labels=[f"{k}\nn={len(v)}" for k, v in groups.items()],
                patch_artist=True, boxprops=dict(facecolor="#E7EFFC", edgecolor=BLUE),
                medianprops=dict(color=ORANGE), flierprops=dict(marker="o", markersize=3, alpha=.4))
    elif kind == "columns":
        ax.bar(s["x"], s["y"], color=BLUE)
        ax.tick_params(axis="x", labelrotation=35)
        ax.set_ylim(bottom=0)
    elif kind == "curve":
        ax.plot(s["x"], s["y"], color=BLUE, linewidth=2,
            drawstyle="steps-post" if s.get("step") else "default")
        if s.get("equality"):
            ax.plot([0, 100], [0, 100], "--", color="#7B879D", label="Равномерное распределение")
            ax.legend(frameon=False)
        ax.set_ylim(0, 100)
    elif kind == "matrix":
        image = ax.imshow(np.ma.masked_invalid(s["z"]), aspect="auto", interpolation="nearest",
            cmap="RdBu" if s.get("correlation") else "Blues", vmin=s.get("zmin", 0), vmax=s.get("zmax"))
        step = max(1, int(np.ceil(len(s["x"]) / 16)))
        ax.set_xticks(range(0, len(s["x"]), step), s["x"][::step], rotation=35, ha="right")
        ax.set_yticks(range(len(s["y"])), s["y"])
        ax.grid(False)
        fig.colorbar(image, ax=ax, pad=.02, label=s["colorlabel"])
        if s.get("correlation"):
            for y, row in enumerate(s["z"]):
                for x, value in enumerate(row):
                    if np.isfinite(value):
                        ax.text(x, y, f"{value:.2f}", ha="center", va="center",
                            color="white" if abs(value) > .65 else INK, fontsize=11)
    elif kind == "donut":
        positive = [(label, value) for label, value in zip(s["labels"], s["values"]) if value > 0]
        if positive:
            ax.pie([v for _, v in positive], labels=[k for k, _ in positive], colors=PALETTE,
                autopct="%1.1f%%", startangle=90, wedgeprops=dict(width=.36, edgecolor="white"))
            ax.text(0, 0, f"{sum(s['values']):,}\nединиц", ha="center", va="center", fontsize=20)
        ax.grid(False)
        ax.set_aspect("equal")
    elif kind == "violin":
        for i, (name, values) in enumerate(s["groups"].items(), start=1):
            values = np.asarray(values, dtype=float)
            values = values[np.isfinite(values)]
            if len(values) >= 3 and np.ptp(values) > 0:
                violin = ax.violinplot(values, positions=[i], showmedians=True, showextrema=False)
                for body in violin["bodies"]:
                    body.set_facecolor(PALETTE[(i-1) % len(PALETTE)]); body.set_alpha(.45)
            elif len(values):
                ax.scatter([i] * len(values), values, color=BLUE)
        ax.set_xticks(range(1, len(s["groups"]) + 1),
            [f"{k}\nn={len(v)}" for k, v in s["groups"].items()])

    ax.set_xlabel(s.get("xlabel", "")); ax.set_ylabel(s.get("ylabel", ""))
    if s.get("log_x"): ax.set_xscale("log")
    if s.get("log_y"): ax.set_yscale("log")
    elif kind in ["line", "stack", "band", "hist"]: ax.set_ylim(bottom=0)
    if kind == "stack100": ax.set_ylim(0, 100)
    if kind == "box" and len(s["groups"]) > 7: ax.tick_params(axis="x", labelrotation=35)
    fig.suptitle(s["title"], x=.06, y=.97, ha="left", fontsize=19, weight="bold")
    fig.text(.06, .90, report["period"] + "\n" + report["scope"], fontsize=10, color="#53657D")
    fig.text(.06, .025, textwrap.fill(s["note"], 135) + "\nИсточник: CSV канала; время Europe/Moscow.",
             fontsize=9, color="#53657D", va="bottom")
    fig.subplots_adjust(left=.25 if kind == "bar" else .09, right=.93, top=.80,
                        bottom=.24 if kind in ["stack", "stack100"] else .19)
    fig.savefig(path, dpi=DPI); plt.close(fig)

def table_png(frame, title, scope, path):
    if frame.empty:
        return
    values = frame.copy()
    for column in values:
        values[column] = values[column].map(lambda x: "—" if pd.isna(x) else fmt(x, 2) if isinstance(x, (float, np.floating)) else str(x))
        # Стандартный шрифт PNG не содержит цветных эмодзи.
        # Исходный текст полностью сохраняется в HTML и CSV.
        values[column] = values[column].map(lambda x: textwrap.fill(
            re.sub(r"[^\u0020-\u024F\u0400-\u052F\u2000-\u206F\n]", "", x), 34))
    headers = [textwrap.fill(c, 18) for c in values.columns]
    weights = [max(h.count("\n") + 1 for h in headers) + .6]
    weights += [max(str(x).count("\n") + 1 for x in row) + .5 for row in values.to_numpy()]
    fig, ax = plt.subplots(figsize=(max(14, len(values.columns) * 2.1), max(4, sum(weights) * .28 + 2.5)))
    ax.axis("off")
    tab = ax.table(cellText=values.values, colLabels=headers,
        cellLoc="left", colLoc="left", bbox=[0, 0, 1, .80])
    tab.auto_set_font_size(False); tab.set_fontsize(10 if len(values.columns) < 7 else 9)
    tab.auto_set_column_width(list(range(len(values.columns))))
    for (row, _), cell in tab.get_celld().items():
        cell.set_height(weights[row])
        cell.set_edgecolor("white")
        cell.set_facecolor(INK if row == 0 else "#F5F7FB" if row % 2 == 0 else "white")
        if row == 0: cell.get_text().set_color("white")
    fig.suptitle(title, x=.04, ha="left", y=.97, fontsize=18, weight="bold")
    fig.text(.04, .89, scope, fontsize=10, color="#53657D")
    fig.subplots_adjust(left=.04, right=.96, top=.86, bottom=.05)
    fig.savefig(path, dpi=DPI); plt.close(fig)

# 5. ЭКСПОРТ И ПАНЕЛЬ
METHODS = """Единица по умолчанию — строка CSV, а не подтверждённая самостоятельная публикация.
MediaMessage — служебный маркер; он не позволяет различить фото и видео.
Режим «Группы по времени» — эвристика: объединение внутри канала по точному времени UTC.
Идентификатора альбома в файле нет. Совпадение времени не доказывает принадлежность одному альбому.
При группировке счётчики берутся по максимуму, а не суммируются; это приближение.
Словарь реакций берётся из строки с наибольшим общим счётчиком реакций.
Разные тексты в группе объединяются без точных повторов. Дата → группировка → фильтр текста.
Время отображается в Europe/Moscow. Границы фильтра включают весь день.
Пустые комментарии неизвестны. Ноль — известное значение. Пропуски не заполняются нулями.
Взвешенные реакции на 100 просмотров = 100 × сумма реакций / сумма просмотров
по единицам, у которых обе метрики известны и просмотры > 0. Это не среднее процентов строк.
Просмотры не равны уникальным зрителям. Реакции не равны уникальным пользователям.
Суммирование просмотров медиагрупп может дублировать счётчики; общий охват аудитории не оценивается.
Счётчики накопленные. Дата измерения неизвестна; старые и новые сообщения разного возраста.
Месячная полоса показывает перцентили наблюдений, а не доверительный интервал.
Крайние месяцы могут быть неполными. Записей в день рассчитано по дням внутри фильтра.
Отсутствие записей в выгрузке не доказывает отсутствие публикаций в канале.
Слова и хештеги считаются по числу текстов, содержащих термин хотя бы один раз.
Для PNG-таблиц эмодзи в цитатах опущены; исходные тексты сохранены в HTML и CSV.
Словоформы не объединяются; стоп-слова сохранены отдельно. Это не тематическая классификация.
Длина текста включает ссылки и хештеги. Корреляция не является причинной связью.
Число подписчиков в CSV — значения источника без подтверждения исторической даты снимка.
График роста подписчиков и ERR по исторической базе подписчиков не строятся.
Корреляция Спирмена рассчитана по рангам отдельно для каждой пары полных наблюдений.
Пары с n < 3 и постоянные признаки не получают искусственного коэффициента.
Календарные клетки вне фильтра и месяцы без записей остаются пустыми.
В графике интервалов используются уникальные моменты публикации, без нулей из медиагрупп.
Взвешенный месячный показатель реакций использует те же парные наблюдения, что и общий.
Группы длины текста: 1–300, 301–700, 701–1200 и более 1200 символов.
Сглаженные скрипичные диаграммы не показываются для постоянных групп и групп с n < 3: вместо них точки.
Порог просмотров применяется к таблице лидеров по доле реакций и диаграмме доли реакций.
HTML и PNG фиксируют фильтры панели. Изменение масштаба графика не пересчитывает KPI.
Камера Plotly сохраняет текущий масштаб отдельного графика.
Документация: https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html
https://plotly.com/python-api-reference/generated/plotly.io.to_html.html
"""
TABLE_NAMES = dict(summary="Сводная статистика", monthly="Месячные показатели",
    top_views="Лидеры по просмотрам", top_reaction_rate="Лидеры по реакциям на 100 просмотров",
    reactions="Типы реакций", words="Частые слова", hashtags="Хештеги", quality="Качество всего CSV")

def header_html(r):
    cards = "".join(f'<div class="tg-card"><small>{escape(k)}</small><div class="tg-value">{escape(v)}</div></div>'
                    for k, v in r["cards"].items())
    return (CSS + '<div class="tg"><small>ИССЛЕДОВАНИЕ TELEGRAM-ВЫГРУЗКИ</small>'
        '<h1>МосУ МВД России имени В. Я. Кикотя</h1>'
        f'<div>{escape(r["period"])}<br>{escape(r["scope"])}</div><div class="tg-grid">{cards}</div>'
        '<div class="tg-note">Просмотры накопленные; единицы анализа могут быть частями медиагрупп. '
        'Пустые комментарии неизвестны. Число подписчиков не является историческим рядом.</div></div>')

def export_report(r, output_dir=OUTPUT_DIR):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    folder = Path(output_dir) / f"telegram_{stamp}"
    for sub in ["png", "tables"]: (folder / sub).mkdir(parents=True, exist_ok=True)
    for i, spec in enumerate(r["specs"]):
        save_png(spec, r, folder / "png" / f"{i+1:02d}_{spec['key']}.png")
    for key, frame in r["tables"].items():
        frame.to_csv(folder / "tables" / f"{key}.csv", index=False, encoding="utf-8-sig")
        for page, offset in enumerate(range(0, len(frame), 18), start=1):
            table_png(frame.iloc[offset:offset+18], TABLE_NAMES[key],
                "Весь CSV" if key == "quality" else r["period"] + " · " + r["scope"],
                folder / "png" / f"table_{key}_{page}.png")
    selected = r["data"].copy()
    selected["ReactionMap"] = selected.ReactionMap.map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else "")
    selected.to_csv(folder / "selected_data.csv", index=False, encoding="utf-8-sig")
    write_html_report(r, folder / "report.html")
    (folder / "METHODS.txt").write_text(METHODS, encoding="utf-8")
    (folder / "STOPWORDS.txt").write_text("\n".join(sorted(STOPWORDS)), encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(dict(settings=r["settings"], source=r["metadata"],
        created_at_utc=datetime.now(timezone.utc).isoformat()), ensure_ascii=False, indent=2), encoding="utf-8")
    return Path(shutil.make_archive(str(folder), "zip", folder))

# 5. САМОСТОЯТЕЛЬНЫЙ HTML: Plotly включён внутрь файла, интернет не нужен.
SECTIONS = {
    "Активность": ["activity", "monthly", "hours", "cumulative", "weekday_mean", "hourly", "daily_distribution", "monthly_daily", "calendar", "gaps"],
    "Просмотры": ["views", "distribution", "formats", "ecdf", "monthly_box", "weekday_violin", "top_views_chart", "lorenz"],
    "Реакции и пересылки": ["reactions", "engagement", "monthly_rate", "reaction_distribution", "forward_distribution", "forwards_views", "rate_views", "correlation"],
    "Тексты и состав": ["words", "hashtags", "length", "content_share", "length_distribution", "content_donut", "length_box", "links_box"],
    "Качество и таблицы": ["availability", "availability_month"],
}
TABLE_NAMES.update(weekday="Активность по дням недели", correlations="Корреляции Спирмена", correlation_pairs="Число наблюдений для каждой корреляции")

HTML_STYLE = """
:root{--ink:#142b4c;--muted:#526781;--blue:#2458bc;--border:#e1e8f1;--paper:#f3f6fb}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Arial,sans-serif}
main{max-width:1420px;margin:auto;padding:28px 26px 64px}.tg{padding:28px 32px;background:white;border:1px solid var(--border);border-radius:18px}
.tg h1{max-width:900px;font-size:clamp(25px,3vw,38px);letter-spacing:-1px;margin:12px 0 16px}.tg>small{color:var(--blue);letter-spacing:1.5px;font-weight:bold}
.tg-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.tg-card{background:#f4f7fc;border:0;border-radius:12px;padding:18px}
.tg-value{font-size:30px}.tg-card small{font-size:13px}.tg-note{max-width:1100px;font-size:13px}
.toolbar{position:sticky;top:0;z-index:30;background:rgba(243,246,251,.97);padding:16px 0;backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.controls,.tabs{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.controls{margin-top:10px;justify-content:space-between}
button,.action{font:inherit;cursor:pointer;border:1px solid #cdd9ea;border-radius:9px;padding:9px 14px;background:white;color:var(--ink);text-decoration:none}
button:hover,button:focus-visible,.action:hover{border-color:var(--blue);color:var(--blue)}button.active{background:var(--blue);color:white;border-color:var(--blue)}
input{font:inherit;padding:11px 14px;border:1px solid #cdd9ea;border-radius:9px;background:white;color:var(--ink);min-width:300px;max-width:100%}
#counter{font-size:13px;color:var(--muted)}.chart-card{background:white;border:1px solid var(--border);border-radius:16px;padding:16px;margin:20px 0;overflow:hidden;box-shadow:0 8px 30px rgba(20,43,76,.035)}
.chart-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #edf1f6;padding:0 6px 10px;font-size:13px;color:var(--muted)}
.chart-meta button{padding:6px 10px;font-size:12px}.chart{min-height:580px;width:100%}.chart-card.expanded{position:fixed;inset:0;z-index:999;overflow:auto;background:white;border-radius:0}.chart-card.expanded .chart{height:calc(100vh - 100px)}.chart-card:fullscreen{overflow:auto;border-radius:0;padding:20px;background:white}.chart-card:fullscreen .chart{height:calc(100vh - 100px)}
.table-card,details{background:white;border:1px solid var(--border);border-radius:14px;padding:24px;margin-top:20px}.table-wrap{overflow-x:auto}.tg-table{font-size:13px;min-width:700px}.tg-table th{cursor:pointer;white-space:normal}
h2{font-size:24px;margin:0 0 8px}pre{white-space:pre-wrap;font:13px/1.65 Arial,sans-serif;color:var(--muted)}summary{cursor:pointer;font-size:20px;font-weight:bold}
.table-search{margin:12px 0}footer{color:var(--muted);font-size:12px;margin-top:24px;overflow-wrap:anywhere}[hidden]{display:none!important}
.empty{padding:40px;text-align:center;color:var(--muted)}.intro{margin:12px 0;color:var(--muted);font-size:13px}
@media(max-width:760px){main{padding:14px 10px 40px}.tg{padding:20px}.tg-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.tg-value{font-size:23px}.tabs button{font-size:12px;padding:8px}.chart-card{padding:4px}.chart{min-height:600px}input{min-width:0;width:100%}.toolbar{position:static}}
@media print{.toolbar,.chart-meta button{display:none}.chart-card,.table-card{break-inside:avoid;box-shadow:none}body{background:white}}
"""
HTML_SCRIPT = r"""
const specs=JSON.parse(document.getElementById('chart-payload').textContent);
let currentSection='Все разделы';
const rendered=new Set(), pending=new Map();
const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting&&!e.target.hidden)renderChart(e.target)}),{rootMargin:'600px'});
async function renderChart(card){
 const key=card.dataset.key;if(rendered.has(key))return;if(pending.has(key))return pending.get(key);
 const p=(async()=>{const spec=specs[key];const holder=card.querySelector('.chart');
 try{await Plotly.newPlot(holder,spec.data,spec.layout,{responsive:true,displaylogo:false,scrollZoom:true,
 toImageButtonOptions:{format:'png',width:1800,height:1100,scale:2}});rendered.add(key);observer.unobserve(card)}
 catch(error){holder.textContent='Не удалось отобразить график: '+error.message;pending.delete(key)}})();
 pending.set(key,p);return p;
}
function filterCharts(){
 const q=document.getElementById('chart-search').value.trim().toLocaleLowerCase('ru');let count=0;
 document.querySelectorAll('.chart-card').forEach(card=>{const show=(currentSection==='Все разделы'||card.dataset.section===currentSection)&&card.dataset.search.includes(q);
 card.hidden=!show;if(show){count++;if(rendered.has(card.dataset.key))Plotly.Plots.resize(card.querySelector('.chart'));else observer.observe(card)}});
 document.getElementById('counter').textContent='Показано графиков: '+count+' / '+Object.keys(specs).length;
 document.getElementById('no-charts').hidden=count>0;
}
document.querySelectorAll('[data-section-button]').forEach(button=>button.addEventListener('click',()=>{
 currentSection=button.dataset.sectionButton;document.querySelectorAll('[data-section-button]').forEach(b=>b.classList.toggle('active',b===button));filterCharts()}));
document.getElementById('chart-search').addEventListener('input',filterCharts);
document.querySelectorAll('[data-fullscreen]').forEach(button=>button.addEventListener('click',async()=>{
 const card=button.closest('.chart-card');await renderChart(card);
 if(document.fullscreenElement===card){await document.exitFullscreen();button.textContent='Во весь экран';return}
 if(card.classList.contains('expanded')){card.classList.remove('expanded');button.textContent='Во весь экран';Plotly.Plots.resize(card.querySelector('.chart'));return}
 try{if(!card.requestFullscreen)throw Error('fullscreen unavailable');await card.requestFullscreen()}
 catch(error){card.classList.add('expanded')}
 button.textContent='Свернуть';Plotly.Plots.resize(card.querySelector('.chart'))}));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.chart-card.expanded').forEach(c=>{c.classList.remove('expanded');c.querySelector('[data-fullscreen]').textContent='Во весь экран';Plotly.Plots.resize(c.querySelector('.chart'))})});
document.addEventListener('fullscreenchange',()=>{document.querySelectorAll('[data-fullscreen]').forEach(b=>b.textContent=document.fullscreenElement===b.closest('.chart-card')?'Свернуть':'Во весь экран');setTimeout(()=>document.querySelectorAll('.chart-card:not([hidden]) .chart').forEach(c=>{if(c.data)Plotly.Plots.resize(c)}),100)});
document.querySelectorAll('.table-card').forEach(card=>{
 const table=card.querySelector('table'), search=card.querySelector('input');
 search.addEventListener('input',()=>{const q=search.value.toLocaleLowerCase('ru');table.querySelectorAll('tbody tr').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase('ru').includes(q))});
 table.querySelectorAll('th').forEach((th,index)=>{th.tabIndex=0;th.title='Нажмите для сортировки';
 const sort=()=>{const asc=th.dataset.direction!=='asc';table.querySelectorAll('th').forEach(h=>h.removeAttribute('aria-sort'));th.dataset.direction=asc?'asc':'desc';th.setAttribute('aria-sort',asc?'ascending':'descending');
 const rows=Array.from(table.tBodies[0].rows), number=t=>{if(t.trim()==='—')return NaN;return Number(t.replace(/\s|%/g,'').replace(',','.'))};
 rows.sort((a,b)=>{const x=a.cells[index].textContent,y=b.cells[index].textContent,nx=number(x),ny=number(y);return (Number.isFinite(nx)&&Number.isFinite(ny)?nx-ny:x.localeCompare(y,'ru',{numeric:true}))*(asc?1:-1)});
 rows.forEach(row=>table.tBodies[0].append(row))};th.addEventListener('click',sort);th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();sort()}})});
});
filterCharts();
"""

def write_html_report(r, path):
    """Сохраняет все графики и таблицы; Python для просмотра файла не требуется."""
    from plotly.offline import get_plotlyjs
    figures, cards = {}, []
    section_for = {key: name for name, keys in SECTIONS.items() for key in keys}
    for index, spec in enumerate(r["specs"], 1):
        figures[spec["key"]] = json.loads(pio.to_json(plotly_chart(spec, r)))
        section = section_for[spec["key"]]
        search = (spec["title"] + " " + spec["note"] + " " + section).lower()
        cards.append(f'<article class="chart-card" data-key="{spec["key"]}" data-section="{escape(section, quote=True)}" data-search="{escape(search, quote=True)}">'
            f'<div class="chart-meta"><span>{index:02d} / {len(r["specs"])} · {escape(section)}</span>'
            '<button type="button" data-fullscreen>Во весь экран</button></div>'
            f'<div class="chart" aria-label="{escape(spec["title"], quote=True)}"></div></article>')
    payload = json.dumps(figures, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    tabs = "".join(f'<button type="button" data-section-button="{escape(name, quote=True)}" class="{"active" if i == 0 else ""}">{escape(name)}</button>'
        for i, name in enumerate(["Все разделы", *SECTIONS]))
    tables = "".join(f'<section class="table-card"><h2>{escape(TABLE_NAMES[key])}</h2>'
        '<input class="table-search" type="search" placeholder="Поиск в этой таблице" aria-label="Поиск по таблице">'
        f'<div class="table-wrap">{table_html(frame)}</div></section>' for key, frame in r["tables"].items())
    document = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>МосУ МВД · интерактивный анализ</title><style>' + HTML_STYLE + '</style></head><body><main>'
        + header_html(r) + '<nav class="toolbar" aria-label="Разделы отчёта"><div class="tabs">' + tabs + '</div>'
        '<div class="controls"><input id="chart-search" type="search" placeholder="Найти график: календарь, реакции, длина…" aria-label="Поиск графиков">'
        '<span id="counter" aria-live="polite"></span><a class="action" href="#tables">К таблицам ↓</a></div></nav>'
        '<p class="intro">Наведение показывает значения; легенда включает и скрывает ряды. Камера на графике сохраняет PNG. '
        'Разделы и поиск выбирают графики; период и показатели зафиксированы при создании этого отчёта.</p>'
        '<p id="no-charts" class="empty" hidden>По этому запросу графики не найдены.</p>'
        + "".join(cards) + '<div id="tables"></div>' + tables
        + '<details><summary>Методика и ограничения</summary><pre>' + escape(METHODS) + '</pre></details>'
        + '<footer>Источник: предоставленный CSV · SHA-256: ' + escape(r["metadata"]["sha256"])
        + '<br>Отчёт создан: ' + datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC") + '</footer></main>'
        '<script>' + get_plotlyjs() + '</script><script id="chart-payload" type="application/json">' + payload
        + '</script><script>' + HTML_SCRIPT + '</script></body></html>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path


def create_html_report(r, output_dir=OUTPUT_DIR):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return write_html_report(r, Path(output_dir) / f"mvd_report_{stamp}.html")


def report_server(output_dir):
    """Сервер обслуживает только папку готовых отчётов, запускается по требованию."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    global _MVD_HTML_SERVER
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    previous = globals().get("_MVD_HTML_SERVER")
    if previous and previous[0] == str(directory):
        return previous[1].server_address[1]
    if previous:
        previous[1].shutdown(); previous[1].server_close()
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    Thread(target=server.serve_forever, daemon=True).start()
    _MVD_HTML_SERVER = (str(directory), server)
    return server.server_address[1]


def launch(source, quality, metadata):
    start = W.DatePicker(description="С даты", value=source.Date.min().date())
    end = W.DatePicker(description="По дату", value=source.Date.max().date())
    level = W.Dropdown(description="Единица", options=["Записи CSV", "Группы по времени"], layout=W.Layout(width="300px"))
    content = W.Dropdown(description="Содержание", options=["Все", "С текстом", "Без текста"])
    section = W.Dropdown(description="Раздел", options=list(SECTIONS), layout=W.Layout(width="310px"))
    threshold = W.BoundedIntText(description="Мин. просмотров", value=300, min=0, max=10**9,
        style={"description_width": "115px"}, layout=W.Layout(width="250px"))
    log = W.Checkbox(description="Логшкала просмотров", value=True, indent=False)
    update = W.Button(description="Обновить", button_style="primary", icon="refresh")
    open_html = W.Button(description="Открыть HTML-отчёт", button_style="success", icon="external-link", layout=W.Layout(width="230px"))
    download_html = W.Button(description="Скачать HTML", icon="download", layout=W.Layout(width="180px"))
    export = W.Button(description="Экспорт PNG + HTML + CSV", icon="archive", layout=W.Layout(width="270px"))
    out, status, html_view, state = W.Output(), W.Output(), W.Output(), {}
    def current():
        if start.value is None or end.value is None:
            raise ValueError("Укажите обе даты.")
        return build_report(source, quality, metadata, start.value, end.value,
                            level.value, content.value, threshold.value, log.value)
    def render(_=None):
        with out:
            clear_output(wait=True)
            try:
                r = current(); state["report"] = r
                display(HTML(header_html(r)))
                if level.value != "Записи CSV":
                    display(HTML('<p class="tg-note">Группировка по времени — приближение к медиагруппам, а не подтверждённые альбомы.</p>'))
                for spec in r["specs"]:
                    if spec["key"] in SECTIONS[section.value]:
                        plotly_chart(spec, r).show(config=CONFIG)
                if section.value == "Качество и таблицы":
                    for key in ["summary", "monthly", "weekday", "top_views", "top_reaction_rate", "quality"]:
                        display(HTML(f"<h3>{TABLE_NAMES[key]}</h3>" + table_html(r["tables"][key])))
            except ValueError as error:
                state.pop("report", None)
                display(HTML("<p>" + escape(str(error)) + "</p>"))
    def html_path():
        # Каждое открытие использует текущие фильтры, а не старый экспорт.
        r = current()
        path = create_html_report(r, OUTPUT_DIR)
        state.update(html_path=path, html_report=r)
        return path
    def show_html(_=None):
        open_html.disabled = True
        with html_view:
            clear_output(wait=True)
            try:
                path = html_path()
                port = report_server(OUTPUT_DIR)
                from urllib.parse import quote
                display(HTML('<p><b>HTML-отчёт открыт ниже.</b> Внутри доступны разделы, поиск, подсказки и сохранение PNG. '
                    'Чтобы открыть файл отдельно в браузере, нажмите «Скачать HTML».</p>'))
                if IN_COLAB:
                    # Официальный iframe API Colab: открытие порта в новой вкладке устарело.
                    from google.colab import output
                    output.serve_kernel_port_as_iframe(port, path="/" + quote(path.name), height="900")
                else:
                    from IPython.display import IFrame
                    display(IFrame(src=f"http://127.0.0.1:{port}/{quote(path.name)}", width="100%", height=900))
            except Exception as error:
                print(f"HTML не открыт: {type(error).__name__}: {error}. Файл также можно получить кнопкой «Скачать HTML».")
            finally:
                open_html.disabled = False
    def download(_=None):
        download_html.disabled = True
        with status:
            clear_output(wait=True)
            try:
                path = html_path()
                print("HTML готов. Скачанный файл открывается двойным щелчком в браузере.")
                if IN_COLAB:
                    from google.colab import files
                    files.download(str(path))
                else:
                    display(FileLink(str(path)))
            except Exception as error:
                print(f"Не удалось скачать HTML: {type(error).__name__}: {error}")
            finally:
                download_html.disabled = False
    def save(_=None):
        export.disabled = True
        with status:
            clear_output(wait=True)
            try:
                r = current()
                print(f"Создаю {len(r['specs'])} графиков, таблицы, автономный HTML и ZIP…")
                archive = export_report(r)
                print("Готово:", archive)
                if IN_COLAB:
                    from google.colab import files
                    files.download(str(archive))
                else:
                    display(FileLink(str(archive)))
            except Exception as error:
                print(f"Экспорт не завершён: {type(error).__name__}: {error}")
            finally:
                export.disabled = False
    update.on_click(render)
    open_html.on_click(show_html)
    download_html.on_click(download)
    export.on_click(save)
    section.observe(render, names="value")
    display(HTML(CSS + '<div class="tg"><h1>36 графиков для исследования канала</h1>'
        'Выберите даты и фильтры → «Обновить». «Открыть HTML-отчёт» показывает все разделы ниже в отдельном окне просмотра.<br>'
        '<small>«Скачать HTML» сохраняет автономный файл. Камера на графике сохраняет PNG. '
        'Порог просмотров применяется к таблице лидеров по доле реакций и графику доли реакций.</small></div>'))
    display(W.VBox([W.HBox([start, end, section], layout=W.Layout(flex_flow="row wrap")),
        W.HBox([level, content, log], layout=W.Layout(flex_flow="row wrap")),
        W.HBox([threshold, update], layout=W.Layout(flex_flow="row wrap")),
        W.HBox([open_html, download_html, export], layout=W.Layout(flex_flow="row wrap")), status, html_view, out]))
    render()
    return dict(state=state, render=render, save=save, show_html=show_html, download_html=download,
        controls=dict(start=start, end=end, section=section, level=level, content=content, threshold=threshold,
            log=log, open_html=open_html, download_html=download_html, export=export))

if __name__ == "__main__":
    SOURCE, QUALITY, SOURCE_INFO = load_data()
    print(f"Загружено {len(SOURCE):,} записей; файл: {SOURCE_INFO['path']}".replace(",", " "))
    print("Время: Europe/Moscow. Нажмите «Открыть HTML-отчёт», чтобы исследовать все 36 графиков.")
    APP = launch(SOURCE, QUALITY, SOURCE_INFO)
