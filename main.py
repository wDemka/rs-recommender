# API рекомендательной системы на FastAPI.
# Запуск: run_api.bat (или .venv\Scripts\python -m uvicorn main:app --port 8000)
# Документация: http://127.0.0.1:8000/docs

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import database
import engine

rec = engine.RecEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init()
    rec.load()
    yield


app = FastAPI(title="Рекомендательная система фильмов", lifespan=lifespan)

HELP = [
    {"command": "GET /api/top10", "params": "limit (1-50, по умолчанию 10)",
     "description": "Топ популярных фильмов по числу оценок"},
    {"command": "GET /api/recommend/user_based/{user_id}", "params": "limit (1-50, по умолчанию 10)",
     "description": "Рекомендации коллаборативной фильтрации по похожим пользователям"},
    {"command": "GET /api/recommend/item_based/{user_id}", "params": "limit (1-50, по умолчанию 10)",
     "description": "Рекомендации коллаборативной фильтрации по похожим фильмам"},
    {"command": "GET /api/recommend/content/{movie_id}", "params": "limit (1-50, по умолчанию 10)",
     "description": "10 похожих фильмов по контенту (жанрам)"},
    {"command": "GET /api/personal/{user_id}", "params": "limit (1-50, по умолчанию 10)",
     "description": "Персональные рекомендации: смесь двух видов коллаборативной фильтрации"},
    {"command": "GET /api/users", "params": "-",
     "description": "Список пользователей с числом и средним баллом оценок"},
    {"command": "GET /api/users/{user_id}/ratings", "params": "-",
     "description": "Оценки пользователя"},
    {"command": "GET /api/movies", "params": "search (строка), limit (1-200)",
     "description": "Поиск фильмов по названию"},
    {"command": "GET /api/movies/{movie_id}", "params": "-",
     "description": "Данные одного фильма"},
    {"command": "POST /api/rate", "params": "JSON: user_id (int), movie_id (int), rating (0.5-5, шаг 0.5)",
     "description": "Сохранить оценку фильма в базу и обновить рекомендации"},
    {"command": "GET /api/help", "params": "-",
     "description": "Эта справка по командам API"},
]


class Rating(BaseModel):
    user_id: int
    movie_id: int
    rating: float = Field(ge=0.5, le=5.0)


@app.get("/")
def root():
    return {"service": "Рекомендательная система фильмов",
            "help": "GET /api/help", "docs": "/docs"}


@app.get("/api/help")
def help_all():
    return HELP


@app.get("/api/users")
def users():
    return database.get_users()


@app.get("/api/top10")
def top10(limit: int = Query(10, ge=1, le=50)):
    return database.top_popular(limit)


@app.get("/api/movies")
def movies(search: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=200)):
    return database.search_movies(search, limit)


@app.get("/api/movies/{movie_id}")
def movie(movie_id: int):
    found = database.get_movie(movie_id)
    if found is None:
        raise HTTPException(404, "Фильм не найден")
    return found


@app.get("/api/users/{user_id}/ratings")
def user_ratings(user_id: int):
    if not database.get_user_ratings(user_id) and user_id not in rec.user_index:
        raise HTTPException(404, "Пользователь не найден")
    return database.get_user_ratings(user_id)


@app.get("/api/recommend/user_based/{user_id}")
def recommend_user_based(user_id: int, limit: int = Query(10, ge=1, le=50)):
    result = rec.user_based(user_id, limit)
    if result is None:
        raise HTTPException(404, "Пользователь не найден или у него нет оценок")
    return result


@app.get("/api/recommend/item_based/{user_id}")
def recommend_item_based(user_id: int, limit: int = Query(10, ge=1, le=50)):
    result = rec.item_based(user_id, limit)
    if result is None:
        raise HTTPException(404, "Пользователь не найден или у него нет оценок")
    return result


@app.get("/api/recommend/content/{movie_id}")
def recommend_content(movie_id: int, limit: int = Query(10, ge=1, le=50)):
    result = rec.content_based(movie_id, limit)
    if result is None:
        raise HTTPException(404, "Фильм не найден")
    return result


@app.get("/api/personal/{user_id}")
def personal(user_id: int, limit: int = Query(10, ge=1, le=50)):
    result = rec.personal(user_id, limit)
    if result is None:
        raise HTTPException(404, "Пользователь не найден или у него нет оценок")
    return result


@app.post("/api/rate")
def rate(rating: Rating):
    if not database.save_rating(rating.user_id, rating.movie_id, rating.rating):
        raise HTTPException(404, "Фильм не найден")
    rec.add_rating(rating.user_id, rating.movie_id, rating.rating)
    return {"status": "ok", "saved": rating.model_dump()}
