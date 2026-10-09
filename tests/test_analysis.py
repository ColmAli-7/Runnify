"""Storing song effects for runs (idempotent rescoring)."""

from datetime import datetime, timedelta

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory
from runnify.services.analysis import rescore_run
from runnify.services.fit import Series
from runnify.services.streams import save_stream

START = datetime(2026, 10, 1, 7, 0, 0)


def _setup(app, user):
    """A 13-minute run with one faster song in the middle (minutes 5-8)."""
    paces = [300.0] * 300 + [290.0] * 180 + [300.0] * 300
    series = Series(
        timestamps=[START + timedelta(seconds=i) for i in range(len(paces))],
        heart_rates=[150] * len(paces),
        paces=paces,
    )
    with app.app_context():
        run = Run(user_id=user, activity_id="1", date_time=START, duration=780, distance=2600)
        db.session.add_all([run, Song(id="lift", name="Lift", artist="A")])
        db.session.flush()
        save_stream(run, series)
        db.session.add(
            UserSongHistory(
                user_id=user,
                song_id="lift",
                run_id=run.id,
                played_at=START + timedelta(seconds=300),
                time_played=179,
            )
        )
        db.session.commit()
        return run.id


def test_rescoring_stores_the_effect(app, user):
    run_id = _setup(app, user)
    with app.app_context():
        assert rescore_run(db.session.get(Run, run_id)) == 1
        db.session.commit()
        analysis = RunSongAnalysis.query.one()
        assert analysis.pace_delta == 10.0
        assert analysis.performance_score > 50
        assert analysis.method_version == 2
        assert analysis.position > 0.3


def test_rescoring_is_idempotent(app, user):
    run_id = _setup(app, user)
    with app.app_context():
        run = db.session.get(Run, run_id)
        rescore_run(run)
        rescore_run(run)
        db.session.commit()
        assert RunSongAnalysis.query.count() == 1


def test_rebuild_command(app, user):
    _setup(app, user)
    result = app.test_cli_runner().invoke(args=["scores", "rebuild"])
    assert "Scored 1 song play." in result.output
