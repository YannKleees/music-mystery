import pytest

from src import music


def fake_tracks(prefix, n=6, popularity=None):
    return [{"id": f"{prefix}{i}", "deezer_id": i, "title": f"{prefix} song {i}", "artist": f"{prefix} artist {i}",
             "year": 1980 + i, "album_id": i, "preview_url": "https://example.org/p.mp3",
             "popularity": i if popularity is None else popularity, "source": "deezer"} for i in range(n)]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SECRET_KEY", "test")
    # No network in tests: Deezer and MusicBrainz are replaced by fixed songs
    monkeypatch.setattr(music, "refresh", lambda t: t)
    import src.routes.quiz_base as qb
    import src.routes.quiz_main as qm
    import src.routes.quiz_personalized as qp
    import src.routes.quiz_ranking as qr
    for mod in (qb, qm, qp, qr):
        monkeypatch.setattr(mod, "refresh", lambda t: t, raising=False)
    monkeypatch.setattr(qb, "load_deezer", lambda choice: (f"Playlist {choice}", fake_tracks(choice)))
    music._lists.clear()
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


def login(client, name):
    client.post("/register", data={"username": name, "password": "pw-" + name})
    return client.post("/login", data={"username": name, "password": "pw-" + name})


def test_passwords_are_hashed(app):
    client = app.test_client()
    login(client, "anna")
    from src.models import User
    with app.app_context():
        user = User.query.filter_by(username="anna").first()
        assert user.password != "pw-anna"
        assert user.check_password("pw-anna")
    bad = app.test_client().post("/login", data={"username": "anna", "password": "wrong"}, follow_redirects=True)
    assert b"Invalid credentials" in bad.data


def test_each_player_keeps_their_own_songs(app):
    a, b = app.test_client(), app.test_client()
    login(a, "anna")
    login(b, "ben")
    a.post("/choose_playlist", data={"choice_source": "deezer", "deezer_preset": "80s hits"})
    b.post("/choose_playlist", data={"choice_source": "deezer", "deezer_preset": "rock classics"})
    page_a = a.get("/dashboard").data
    page_b = b.get("/dashboard").data
    assert b"Playlist 80s hits" in page_a and b"Playlist rock classics" not in page_a
    assert b"Playlist rock classics" in page_b


def test_a_round_works_without_spotify(app):
    client = app.test_client()
    login(client, "clara")
    page = client.get("/random_version")
    assert page.status_code == 200
    assert b"mm-play" in page.data                      # Deezer play button, not a Spotify embed
    assert b"open.spotify.com/embed" not in page.data


def test_ranking_gives_up_instead_of_hanging(app, monkeypatch):
    import src.routes.quiz_base as qb
    monkeypatch.setattr(qb, "load_deezer", lambda choice: ("Same", fake_tracks("x", popularity=5)))
    client = app.test_client()
    login(client, "dora")
    response = client.get("/random_rank", follow_redirects=True)
    assert b"Not enough different songs" in response.data


def test_database_download_route_is_gone(app):
    client = app.test_client()
    login(client, "eve")
    assert client.get("/admin/download_db?pw=some_strong_password_here").status_code == 404


@pytest.mark.parametrize("text, expected", [
    ("https://www.deezer.com/en/playlist/1913763402", "1913763402"),
    ("1913763402", "1913763402"),
    ("80s hits", None),
])
def test_parse_deezer_playlist(text, expected):
    assert music.parse_deezer_playlist(text) == expected


@pytest.mark.parametrize("title, base", [
    ("Back In Black - 2003 Remaster", "Back In Black"),
    ("Tainted Love (Single Version)", "Tainted Love"),
    ("Jump", "Jump"),
])
def test_base_title(title, base):
    assert music._base_title(title) == base
