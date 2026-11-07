# Music Mystery

A music guessing game built for a Human-Computer Interaction course at Maastricht University (2025). I built the app and the guessing game; Frank Lambert wrote the second game, where players drag songs into order on a timeline (the ranking modes). Players hear a 30-second snippet and guess the artist, title or release year, or drag songs into order by popularity, while an on-screen buddy reacts and gives hints.

The game exists in two versions to compare in a user study: a **random** version and a **personalised** version that adapts to the player (an Elo rating per mode, more practice on missed songs and weak decades, fewer hints and shorter snippets as the player improves).

## What it does

- Four modes: guessing and ranking, each in a random and a personalised version
- Songs from Deezer (no account needed, 30-second previews) or from the player's own Spotify playlists
- Elo rating per mode, scoreboard, list of missed songs to practise
- Buddy with two personalities (friendly or strict) that comments and offers hints

## Stack

Python, Flask, Flask-SQLAlchemy (SQLite) · Jinja, Bootstrap · Deezer API, Spotify Web API (spotipy), MusicBrainz API · pytest

## Run it

Requirements: Python 3.11+.

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
flask --app src.app run           # http://127.0.0.1:5000
```

Register an account and press a game button; the first game loads today's Deezer charts. Spotify is optional: copy `.env.example` to `.env` and add a Spotify app's client ID and secret (redirect URI `http://127.0.0.1:5000/spotify/callback`). Tests: `pytest`.

## Changes after the course

The course version needed a Spotify login for every game. Since late 2024 Spotify no longer gives new apps song previews, and it limits apps in development mode to 25 approved users, so I reworked it to be playable by anyone:

- Deezer as the default music source, with a play button that keeps title and artist hidden
- Release years from MusicBrainz (the first release of the recording), because album dates on Deezer and Spotify are often those of a later compilation or remaster (1983's "Girls Just Want to Have Fun" shows up with a 2014 album date). Best effort: when MusicBrainz has no match, the album year is used.
- Each player has their own song list (the course version shared one list between everyone on the server)
- Passwords are stored as salted hashes, the session key comes from the environment, and a database download route that was protected only by a password written in the code is gone
- The ranking mode can no longer loop forever on playlists with too few different songs
- Tests for these fixes
