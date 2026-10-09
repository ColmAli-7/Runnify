"""Maintenance commands, run with ``flask --app runnify <group> <command>``."""

import click
from flask import Flask
from flask.cli import AppGroup

from runnify.extensions import db
from runnify.models import Run, RunStream

streams_cli = AppGroup(
    "streams", help="Manage stored run streams (second-by-second pace and heart rate)."
)


@streams_cli.command("backfill")
def backfill_streams():
    """Store streams for runs that only have a legacy FIT file on disk."""
    from runnify.services.streams import backfill_from_fit_files

    runs = (
        Run.query.filter(Run.fit_file_path.isnot(None))
        .outerjoin(RunStream)
        .filter(RunStream.run_id.is_(None))
    )
    created = backfill_from_fit_files(runs.all())
    db.session.commit()
    click.echo(f"Stored streams for {created} run{'s' if created != 1 else ''}.")


scores_cli = AppGroup("scores", help="Manage stored song effects.")


@scores_cli.command("rebuild")
@click.option("--user", "user_id", type=int, help="Only rebuild this user's runs.")
def rebuild_scores(user_id):
    """Recompute every song's effect with the current scoring method."""
    from runnify.services.analysis import rescore_run

    runs = Run.query.filter_by(user_id=user_id) if user_id else Run.query
    total = sum(rescore_run(run) for run in runs.all())
    db.session.commit()
    click.echo(f"Scored {total} song play{'s' if total != 1 else ''}.")


def register_cli(app: Flask):
    """Attach the maintenance command groups to ``app``."""
    app.cli.add_command(streams_cli)
    app.cli.add_command(scores_cli)
