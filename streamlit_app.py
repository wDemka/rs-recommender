# Приложение рекомендательной системы на Streamlit.
# Работает через API: сначала запускаем run_api.bat, потом run_app.bat

import requests
import streamlit as st

API = "http://127.0.0.1:8000"


def get(path, params=None):
    try:
        r = requests.get(API + path, params=params, timeout=60)
    except requests.ConnectionError:
        st.error("Сервер API не отвечает. Запустите run_api.bat (порт 8000)")
        st.stop()
    if r.status_code == 404:
        st.warning(r.json().get("detail", "Не найдено"))
        return None
    return r.json()


def show_table(rows, score_name="Балл"):
    if not rows:
        return
    table = []
    for r in rows:
        row = {"ID": r["movieId"], "Фильм": r["title"], "Жанры": r.get("genres", "")}
        if "score" in r:
            row[score_name] = r["score"]
        if "ratingsCount" in r:
            row["Оценок"] = r["ratingsCount"]
            row["Средний балл"] = r["avgRating"]
        table.append(row)
    st.dataframe(table, hide_index=True, width="stretch")


def search_box(key):
    word = st.text_input("Найти фильм", key=key)
    movies = get("/api/movies", {"search": word, "limit": 100}) if word else []
    if not movies:
        st.info("Начните вводить название фильма")
        return None
    choice = st.selectbox(
        "Фильм",
        range(len(movies)),
        format_func=lambda i: f"{movies[i]['movieId']} — {movies[i]['title']}",
    )
    return movies[choice]["movieId"]


st.set_page_config(page_title="Рекомендательная система фильмов", layout="wide")
st.title("Рекомендательная система фильмов")

users = get("/api/users")
user_ids = [u["userId"] for u in users]
info = {u["userId"]: u for u in users}
sel_user = st.sidebar.selectbox(
    "Пользователь",
    user_ids,
    format_func=lambda u: f"{u} ({info[u]['ratingsCount']} оценок, средний {info[u]['avgRating']})",
)
st.sidebar.caption("API: http://127.0.0.1:8000, документация: /docs")

tab_top, tab_users, tab_items, tab_content, tab_personal, tab_rate, tab_help = st.tabs(
    ["Топ-10", "По пользователям", "По фильмам", "По контенту", "Персональные", "Оценить фильм", "Справка"]
)

with tab_top:
    show_table(get("/api/top10", {"limit": 10}))

with tab_users:
    if st.button("Показать рекомендации", key="bu"):
        show_table(get(f"/api/recommend/user_based/{sel_user}"))

with tab_items:
    if st.button("Показать рекомендации", key="bi"):
        show_table(get(f"/api/recommend/item_based/{sel_user}"))

with tab_content:
    movie_id = search_box("sc")
    if movie_id and st.button("Показать похожие", key="bc"):
        show_table(get(f"/api/recommend/content/{movie_id}"))

with tab_personal:
    st.caption("Смешиваются рекомендации по похожим пользователям и по похожим фильмам")
    if st.button("Показать рекомендации", key="bp"):
        show_table(get(f"/api/personal/{sel_user}"))

with tab_rate:
    movie_id = search_box("sr")
    if movie_id:
        rating = st.slider("Оценка", 0.5, 5.0, 5.0, step=0.5)
        if st.button("Сохранить оценку"):
            body = {"user_id": sel_user, "movie_id": movie_id, "rating": rating}
            try:
                r = requests.post(API + "/api/rate", json=body, timeout=30)
            except requests.ConnectionError:
                r = None
            if r is not None and r.status_code < 400:
                st.success(f"Оценка {rating} сохранена в базе для пользователя {sel_user}")
            else:
                st.error("Не удалось сохранить оценку")

with tab_help:
    help_rows = get("/api/help")
    if help_rows:
        table = [{"Команда": h["command"], "Параметры": h["params"], "Что делает": h["description"]}
                 for h in help_rows]
        st.dataframe(table, hide_index=True, width="stretch")
