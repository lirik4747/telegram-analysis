# Telegram CSV — одна ячейка Google Colab
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
OUTPUT_DIR = Path("/content/telegram_analysis")
TZ = "Europe/Moscow"
DPI = 220
BLUE, ORANGE, INK, GRID = "#2458BC", "#BA591F", "#172B4D", "#E7EDF5"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
METRICS = ["views", "comments", "reactions_total", "forwards"]
CONFIG = dict(displaylogo=False, responsive=True, scrollZoom=True,
    toImageButtonOptions=dict(format="png", width=1600, height=950, scale=2))
pio.templates.default = "plotly_white"
if IN_COLAB:
    pio.renderers.default = "colab"
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
    return pd.DataFrame(counts.most_common(20), columns=["Термин", "Записей"])

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
        "Число пар для взвешенного показателя", "Порог просмотров таблицы реакций"],
        "Значение": [level, content, TZ, str(d.views.notna().sum()), str(d.comments.notna().sum()),
        fmt(d.comments.median()), fmt(d.forwards.median()), fmt(weighted_rate, 3), str(valid_rate.sum()), str(min_views)]})
    tables = {"summary": summary, "monthly": monthly.reset_index(),
        "top_views": top_table(d.dropna(subset=["views"]).nlargest(10, "views")),
        "top_reaction_rate": top_table(d.loc[d.views.ge(min_views)].dropna(subset=["Rate"]).nlargest(10, "Rate")),
        "reactions": reaction_table, "words": words, "hashtags": tags, "quality": quality}
    return dict(data=d, specs=specs, tables=tables, cards=cards, period=period, scope=scope,
        settings=dict(start=str(start), end=str(end), level=level, content=content,
                      min_views=min_views, log_views=log_views, timezone=TZ), metadata=metadata)

# 4. ДВА РЕНДЕРЕРА ОДНИХ ДАННЫХ
def plotly_chart(s, report):
    f = go.Figure()
    kind = s["kind"]
    if kind in ["line", "stack"]:
        for i, (name, values) in enumerate(s["series"].items()):
            color = [BLUE, ORANGE][i % 2]
            trace = (go.Bar(x=s["x"], y=values, name=name, marker_color=color) if kind == "stack"
                     else go.Scatter(x=s["x"], y=values, name=name, mode="lines",
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
        f.add_trace(go.Histogram(x=s["values"], nbinsx=60, marker_color=BLUE))
    elif kind == "bar":
        f.add_trace(go.Bar(x=s["values"][::-1], y=s["labels"][::-1], orientation="h",
            marker_color=BLUE, text=[fmt(v, 1 if s.get("percent") else 0) for v in s["values"][::-1]],
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
    height = max(560, len(s.get("labels", [])) * 26 + 240)
    f.update_layout(template="plotly_white", height=height, font=dict(family="Arial", size=14, color=INK),
        title=dict(text=f"<b>{s['title']}</b><br><sup>{report['period']} · {report['scope']}</sup>", x=.03),
        margin=dict(l=100 if kind == "bar" else 70, r=45, t=120, b=115),
        legend=dict(orientation="h", y=1.04, x=0), bargap=.08)
    f.update_xaxes(title=s.get("xlabel", ""), type="log" if s.get("log_x") else None)
    f.update_yaxes(title=s.get("ylabel", ""), gridcolor=GRID, type="log" if s.get("log_y") else None)
    if kind == "heat":
        f.update_yaxes(autorange="reversed")
    if kind in ["line", "stack", "hist", "band"] and not s.get("log_y"):
        f.update_yaxes(rangemode="tozero")
    f.add_annotation(x=0, y=-.24, xref="paper", yref="paper", xanchor="left", showarrow=False,
        text="<br>".join(textwrap.wrap(s["note"], 115)), align="left", font=dict(size=12, color="#53657D"))
    if (kind == "bar" and not len(s["labels"])) or (kind == "scatter" and not len(s["x"])):
        f.add_annotation(text="Нет данных для этого графика", x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
    return f

def save_png(s, report, path):
    kind = s["kind"]
    fig, ax = plt.subplots(figsize=(14, max(7, len(s.get("labels", [])) * .32 + 2.6)))
    ax.grid(axis="x" if kind == "bar" else "y", alpha=.7)
    if kind in ["line", "stack"]:
        bottom = np.zeros(len(s["x"]))
        for i, (name, values) in enumerate(s["series"].items()):
            if kind == "line":
                ax.plot(s["x"], values, color=[BLUE, ORANGE][i % 2], label=name,
                        linestyle="-" if i == 0 else "--", linewidth=1.7)
            else:
                ax.bar(s["x"], values, bottom=bottom, color=[BLUE, ORANGE][i % 2], label=name)
                bottom += np.asarray(values, dtype=float)
        ax.legend(frameon=False, loc="upper left", ncol=2)
        if kind == "stack":
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
        ax.hist(s["values"], bins=60, color=BLUE)
    elif kind == "bar":
        labels, values = s["labels"][::-1], s["values"][::-1]
        ax.barh(labels, values, color=BLUE)
        for i, value in enumerate(values):
            ax.text(value, i, " " + fmt(value, 1 if s.get("percent") else 0), va="center", fontsize=10)
        ax.set_xlim(0, 108 if s.get("percent") else max(values, default=1) * 1.17)
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
    ax.set_xlabel(s.get("xlabel", "")); ax.set_ylabel(s.get("ylabel", ""))
    if s.get("log_x"): ax.set_xscale("log")
    if s.get("log_y"): ax.set_yscale("log")
    elif kind in ["line", "stack", "band", "hist"]: ax.set_ylim(bottom=0)
    fig.suptitle(s["title"], x=.06, y=.97, ha="left", fontsize=19, weight="bold")
    fig.text(.06, .90, report["period"] + "\n" + report["scope"], fontsize=10, color="#53657D")
    fig.text(.06, .025, textwrap.fill(s["note"], 135) + "\nИсточник: CSV канала; время Europe/Moscow.",
             fontsize=9, color="#53657D", va="bottom")
    fig.subplots_adjust(left=.25 if kind == "bar" else .09, right=.93, top=.80,
                        bottom=.24 if kind == "stack" else .19)
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
    html = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Анализ Telegram</title><body style="max-width:1500px;margin:20px auto;padding:20px;background:white">', header_html(r)]
    for i, spec in enumerate(r["specs"]):
        html.append(pio.to_html(plotly_chart(spec, r), full_html=False,
            include_plotlyjs=(i == 0), config=CONFIG, div_id="tg-" + spec["key"]))
        save_png(spec, r, folder / "png" / f"{i+1:02d}_{spec['key']}.png")
    for key, frame in r["tables"].items():
        frame.to_csv(folder / "tables" / f"{key}.csv", index=False, encoding="utf-8-sig")
        html.append(f"<h2>{TABLE_NAMES[key]}</h2>" + table_html(frame))
        for page, offset in enumerate(range(0, len(frame), 18), start=1):
            table_png(frame.iloc[offset:offset+18], TABLE_NAMES[key],
                "Весь CSV" if key == "quality" else r["period"] + " · " + r["scope"],
                folder / "png" / f"table_{key}_{page}.png")
    selected = r["data"].copy()
    selected["ReactionMap"] = selected.ReactionMap.map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else "")
    selected.to_csv(folder / "selected_data.csv", index=False, encoding="utf-8-sig")
    html.append("<h2>Методика</h2><pre style='white-space:pre-wrap'>" + escape(METHODS) + "</pre></body></html>")
    (folder / "report.html").write_text("\n".join(html), encoding="utf-8")
    (folder / "METHODS.txt").write_text(METHODS, encoding="utf-8")
    (folder / "STOPWORDS.txt").write_text("\n".join(sorted(STOPWORDS)), encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(dict(settings=r["settings"], source=r["metadata"],
        created_at_utc=datetime.now(timezone.utc).isoformat()), ensure_ascii=False, indent=2), encoding="utf-8")
    return Path(shutil.make_archive(str(folder), "zip", folder))

SECTIONS = {"Активность": ["activity", "monthly", "hours"],
    "Просмотры": ["views", "distribution", "formats"],
    "Реакции": ["reactions", "engagement"], "Тексты": ["words", "hashtags", "length"],
    "Таблицы и качество": ["availability"]}

def launch(source, quality, metadata):
    start = W.DatePicker(description="С даты", value=source.Date.min().date())
    end = W.DatePicker(description="По дату", value=source.Date.max().date())
    level = W.Dropdown(description="Единица", options=["Записи CSV", "Группы по времени"], layout=W.Layout(width="300px"))
    content = W.Dropdown(description="Содержание", options=["Все", "С текстом", "Без текста"])
    section = W.Dropdown(description="Раздел", options=list(SECTIONS))
    threshold = W.BoundedIntText(description="Мин. просмотров", value=300, min=0, max=10**9,
        style={"description_width": "115px"}, layout=W.Layout(width="250px"))
    log = W.Checkbox(description="Логшкала просмотров", value=True, indent=False)
    update = W.Button(description="Обновить", button_style="primary", icon="refresh")
    export = W.Button(description="Экспорт PNG + HTML + CSV", icon="download", layout=W.Layout(width="270px"))
    out, status, state = W.Output(), W.Output(), {}
    def current():
        if start.value is None or end.value is None: raise ValueError("Укажите обе даты.")
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
                    if spec["key"] in SECTIONS[section.value]: plotly_chart(spec, r).show(config=CONFIG)
                if section.value == "Таблицы и качество":
                    for key in ["summary", "monthly", "top_views", "top_reaction_rate", "quality"]:
                        display(HTML(f"<h3>{TABLE_NAMES[key]}</h3>" + table_html(r["tables"][key])))
            except ValueError as error:
                state.pop("report", None); display(HTML("<p>" + escape(str(error)) + "</p>"))
    def save(_=None):
        export.disabled = True
        with status:
            clear_output(wait=True)
            try:
                print("Создаю 12 графиков, таблицы, HTML и ZIP…")
                archive = export_report(current())
                print("Готово:", archive)
                if IN_COLAB:
                    from google.colab import files
                    files.download(str(archive))
                else: display(FileLink(str(archive)))
            except Exception as error:
                print(f"Экспорт не завершён: {type(error).__name__}: {error}")
            finally: export.disabled = False
    update.on_click(render); export.on_click(save); section.observe(render, names="value")
    display(HTML(CSS + '<div class="tg"><h1>Исследуйте данные канала</h1>'
        'Выберите даты и фильтры → «Обновить». Экспорт сохраняет все разделы.<br>'
        '<small>Значок камеры сохраняет отдельный график. Порог просмотров применяется только к таблице лидеров по доле реакций.</small></div>'))
    display(W.VBox([W.HBox([start, end, section], layout=W.Layout(flex_flow="row wrap")),
        W.HBox([level, content, log], layout=W.Layout(flex_flow="row wrap")),
        W.HBox([threshold, update, export], layout=W.Layout(flex_flow="row wrap")), status, out]))
    render()
    return dict(state=state, render=render, save=save,
                controls=dict(start=start, end=end, section=section, level=level, content=content))

if __name__ == "__main__":
    SOURCE, QUALITY, SOURCE_INFO = load_data()
    print(f"Загружено {len(SOURCE):,} записей; файл: {SOURCE_INFO['path']}".replace(",", " "))
    print("Все графики времени: Europe/Moscow. Для скачивания материалов нажмите «Экспорт».")
    APP = launch(SOURCE, QUALITY, SOURCE_INFO)
