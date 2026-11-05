import csv
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "recsys.db"
DATA_DIR = BASE_DIR / "data" / "ml-latest-small"

def connect():
    return sqlite3.connect(DB_PATH)

def init():
    con = connect()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            movie_id INTEGER PRIMARY KEY,
            title    TEXT NOT NULL,
            genres   TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id   INTEGER NOT NULL,
            movie_id  INTEGER NOT NULL,
            rating    REAL    NOT NULL,
            timestamp INTEGER NOT NULL,
            PRIMARY KEY (user_id, movie_id)
        )
    """)
    if cur.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 0:
        _load_csv(cur)
    con.commit()
    con.close()

def _load_csv(cur):
    with open(DATA_DIR / "movies.csv", encoding="utf-8") as f:
        cur.executemany(
            "INSERT INTO movies (movie_id, title, genres) VALUES (?, ?, ?)",
            ((int(r["movieId"]), r["title"], r["genres"])
             for r in csv.DictReader(f)),
        )
    with open(DATA_DIR / "ratings.csv", encoding="utf-8") as f:
        cur.executemany(
            "INSERT INTO ratings (user_id, movie_id, rating, timestamp) VALUES (?, ?, ?, ?)",
            ((int(r["userId"]), int(r["movieId"]), float(r["rating"]), int(r["timestamp"]))
             for r in csv.DictReader(f)),
        )

def get_users():
    con = connect()
    rows = con.execute(
        "SELECT user_id, COUNT(*), ROUND(AVG(rating), 2) FROM ratings GROUP BY user_id ORDER BY user_id"
    ).fetchall()
    con.close()
    return [{"userId": r[0], "ratingsCount": r[1], "avgRating": r[2]} for r in rows]

def search_movies(search: str = "", limit: int = 50):
    con = connect()
    if search:
        rows = con.execute(
            "SELECT movie_id, title, genres FROM movies WHERE title LIKE ? ORDER BY movie_id LIMIT ?",
            (f"%{search}%", limit),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT movie_id, title, genres FROM movies ORDER BY movie_id LIMIT ?", (limit,)
        ).fetchall()
    con.close()
    return [{"movieId": r[0], "title": r[1], "genres": r[2]} for r in rows]

def get_movie(movie_id: int):
    con = connect()
    row = con.execute(
        "SELECT movie_id, title, genres FROM movies WHERE movie_id = ?", (movie_id,)
    ).fetchone()
    con.close()
    if row is None:
        return None
    return {"movieId": row[0], "title": row[1], "genres": row[2]}

def get_user_ratings(user_id: int):
    con = connect()
    rows = con.execute(
        """SELECT r.movie_id, m.title, r.rating FROM ratings r
           JOIN movies m ON m.movie_id = r.movie_id
           WHERE r.user_id = ? ORDER BY r.rating DESC""",
        (user_id,),
    ).fetchall()
    con.close()
    return [{"movieId": r[0], "title": r[1], "rating": r[2]} for r in rows]

def top_popular(limit: int = 10):
    con = connect()
    rows = con.execute(
        """SELECT r.movie_id, m.title, m.genres, COUNT(*) AS cnt, ROUND(AVG(r.rating), 2) AS avg
           FROM ratings r JOIN movies m ON m.movie_id = r.movie_id
           GROUP BY r.movie_id ORDER BY cnt DESC, avg DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    con.close()
    return [{"movieId": r[0], "title": r[1], "genres": r[2],
             "ratingsCount": r[3], "avgRating": r[4]} for r in rows]

def save_rating(user_id: int, movie_id: int, rating: float):
    con = connect()
    movie = con.execute("SELECT 1 FROM movies WHERE movie_id = ?", (movie_id,)).fetchone()
    if movie is None:
        con.close()
        return False
    con.execute(
        """INSERT INTO ratings (user_id, movie_id, rating, timestamp) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = excluded.rating, timestamp = excluded.timestamp""",
        (user_id, movie_id, rating, int(time.time())),
    )
    con.commit()
    con.close()
    return True

def get_all():
    con = connect()
    movies = con.execute("SELECT movie_id, title, genres FROM movies").fetchall()
    ratings = con.execute("SELECT user_id, movie_id, rating FROM ratings").fetchall()
    con.close()
    return movies, ratings
