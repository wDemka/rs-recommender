import numpy as np
import database

TOP_ITEM_NEIGHBORS = 40
MIN_SUPPORT = 3

class RecEngine:

    def load(self):
        movies, ratings = database.get_all()
        self.titles = {m[0]: m[1] for m in movies}
        self.genres = {m[0]: m[2].split("|") for m in movies}

        users = sorted({r[0] for r in ratings})
        rated_movies = sorted({r[1] for r in ratings})
        self.user_index = {u: i for i, u in enumerate(users)}
        self.movie_index = {m: j for j, m in enumerate(rated_movies)}
        self.index_movie = rated_movies

        matrix = np.zeros((len(users), len(rated_movies)))
        for u, m, r in ratings:
            matrix[self.user_index[u], self.movie_index[m]] = r
        self.matrix = matrix
        self.mask = matrix > 0

        self.user_mean = np.zeros(len(users))
        np.divide(self.matrix.sum(axis=1), self.mask.sum(axis=1), out=self.user_mean)
        self.centered = np.where(self.mask, matrix - self.user_mean[:, None], 0.0)

        self._build_user_sim()
        self._build_item_neighbors()
        self._build_content_model()

    def _build_user_sim(self):
        norms = np.linalg.norm(self.centered, axis=1) + 1e-9
        self.user_sim = (self.centered @ self.centered.T) / np.outer(norms, norms)

    def _build_item_neighbors(self):
        col_norms = np.linalg.norm(self.centered, axis=0) + 1e-9
        n = len(self.movie_index)
        top_idx = np.zeros((n, TOP_ITEM_NEIGHBORS), dtype=np.int32)
        top_sim = np.zeros((n, TOP_ITEM_NEIGHBORS))
        chunk = 512
        for start in range(0, n, chunk):
            stop = min(start + chunk, n)
            block = self.centered[:, start:stop].T @ self.centered
            block /= col_norms[start:stop, None] * col_norms[None, :]
            np.fill_diagonal(block[:, start:stop], 0.0)
            idx = np.argsort(-block, axis=1)[:, :TOP_ITEM_NEIGHBORS]
            top_idx[start:stop] = idx
            top_sim[start:stop] = np.take_along_axis(block, idx, axis=1)
        self.item_top_idx = top_idx
        self.item_top_sim = top_sim

    def _build_content_model(self):
        genre_names = sorted({g for gs in self.genres.values() for g in gs})
        self.genre_index = {g: i for i, g in enumerate(genre_names)}
        self.movie_ids = sorted(self.genres)
        self.movie_row = {m: i for i, m in enumerate(self.movie_ids)}

        doc_freq = np.zeros(len(genre_names))
        for gs in self.genres.values():
            for g in set(gs):
                doc_freq[self.genre_index[g]] += 1
        self.idf = np.log(len(self.genres) / (1.0 + doc_freq)) + 1.0

        vecs = np.zeros((len(self.movie_ids), len(genre_names)))
        for m, gs in self.genres.items():
            for g in set(gs):
                vecs[self.movie_row[m], self.genre_index[g]] = self.idf[self.genre_index[g]]
        norms = np.linalg.norm(vecs, axis=1) + 1e-9
        self.content_vecs = vecs / norms[:, None]

    def _user_row(self, user_id):
        return self.user_index.get(user_id)

    def user_based(self, user_id, limit=10):
        row = self._user_row(user_id)
        if row is None:
            return None
        sims = self.user_sim[row].copy()
        sims[row] = 0.0
        neighbors = np.argsort(-sims)[:30]
        neighbors = [nb for nb in neighbors if sims[nb] > 0]
        if not neighbors:
            return []

        scores = np.zeros(len(self.movie_index))
        denom = np.zeros(len(self.movie_index))
        support = np.zeros(len(self.movie_index))
        for nb in neighbors:
            rated = self.mask[nb]
            scores[rated] += sims[nb] * self.centered[nb, rated]
            denom[rated] += abs(sims[nb])
            support[rated] += 1
        scores = np.divide(scores, denom, out=np.zeros_like(scores), where=denom > 0)
        scores[self.mask[row]] = -np.inf
        return self._top_from_scores(scores, limit, support)

    def item_based(self, user_id, limit=10):
        row = self._user_row(user_id)
        if row is None:
            return None
        scores = np.zeros(len(self.movie_index))
        denom = np.zeros(len(self.movie_index))
        support = np.zeros(len(self.movie_index))
        rated_cols = np.nonzero(self.mask[row])[0]
        user_ratings = self.centered[row]
        for col in rated_cols:
            for nb_col, sim in zip(self.item_top_idx[col], self.item_top_sim[col]):
                if sim <= 0:
                    break
                scores[nb_col] += sim * user_ratings[col]
                denom[nb_col] += abs(sim)
                support[nb_col] += 1
        scores = np.divide(scores, denom, out=np.zeros_like(scores), where=denom > 0)
        scores[self.mask[row]] = -np.inf
        return self._top_from_scores(scores, limit, support)

    def content_based(self, movie_id, limit=10):
        if movie_id not in self.movie_row:
            return None
        vec = self.content_vecs[self.movie_row[movie_id]]
        sims = self.content_vecs @ vec
        sims[self.movie_row[movie_id]] = -np.inf
        order = np.argsort(-sims)[:limit]
        return [self._movie_info(self.movie_ids[i], round(float(sims[i]), 3)) for i in order]

    def personal(self, user_id, limit=10):
        user_list = self.user_based(user_id, 50)
        item_list = self.item_based(user_id, 50)
        if user_list is None or item_list is None:
            return None
        combined = {}
        for ranked in (user_list, item_list):
            for position, rec_item in enumerate(ranked):
                movie_id = rec_item["movieId"]
                combined[movie_id] = combined.get(movie_id, 0.0) + 1.0 / (20 + position + 1)
        top = sorted(combined.items(), key=lambda kv: -kv[1])[:limit]
        return [self._movie_info(m, round(s, 4)) for m, s in top]

    def _top_from_scores(self, scores, limit, support=None):
        thresholds = (MIN_SUPPORT, 1) if support is not None else (1,)
        for threshold in thresholds:
            eligible = scores.copy()
            if support is not None:
                eligible[support < threshold] = -np.inf
            order = np.argsort(-eligible)[:limit]
            result = []
            for col in order:
                if eligible[col] == -np.inf or eligible[col] <= 0:
                    continue
                result.append(self._movie_info(self.index_movie[col], round(float(scores[col]), 3)))
            if result:
                return result
        return []

    def _movie_info(self, movie_id, score):
        return {
            "movieId": movie_id,
            "title": self.titles.get(movie_id, f"Фильм {movie_id}"),
            "genres": "|".join(self.genres.get(movie_id, [])),
            "score": score,
        }

    def add_rating(self, user_id, movie_id, rating):
        if movie_id not in self.movie_row:
            return
        row = self._user_row(user_id)
        if row is None:
            return
        col = self.movie_index.get(movie_id)
        if col is None:
            return
        self.matrix[row, col] = rating
        self.mask[row, col] = True
        count = self.mask[row].sum()
        self.user_mean[row] = self.matrix[row].sum() / count
        self.centered[row] = np.where(self.mask[row], self.matrix[row] - self.user_mean[row], 0.0)
        norms = np.linalg.norm(self.centered, axis=1) + 1e-9
        self.user_sim[row] = (self.centered @ self.centered[row]) / (norms * norms[row])
        self.user_sim[:, row] = self.user_sim[row]
