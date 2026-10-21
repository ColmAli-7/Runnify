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
    from runnify.services.analysis import rescore_runs

    runs = Run.query.filter_by(user_id=user_id) if user_id else Run.query
    total = rescore_runs([run_id for (run_id,) in runs.with_entities(Run.id)])
    db.session.commit()
    click.echo(f"Scored {total} song play{'s' if total != 1 else ''}.")


laps_cli = AppGroup("laps", help="Manage runs' laps.")


@laps_cli.command("refetch")
@click.option("--user", "user_id", type=int, help="Only this user's runs.")
@click.option("--pause", default=1.0, show_default=True, help="Seconds between downloads.")
def refetch_laps(user_id, pause):
    """Download old runs' FIT files from Garmin again, for the watch's laps and cadence."""
    from runnify.models import User
    from runnify.services.garmin import GarminError, refetch_runs

    users = User.query.filter(User.garmin_username.isnot(None))
    if user_id:
        users = users.filter(User.id == user_id)
    total = 0
    for user in users.all():
        try:
            total += refetch_runs(user, pause=pause)
        except GarminError as error:
            click.echo(f"Skipped user {user.id}: {error}")
    click.echo(f"Refreshed {total} run{'s' if total != 1 else ''} from Garmin.")


demo_cli = AppGroup("demo", help="Synthetic demo data for local development (never production).")


@demo_cli.command("seed")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password for the demo account (demo@runnify.test).",
)
def seed_demo(password):
    """Create a demo account with four months of synthetic runs, songs and friends."""
    from flask import current_app

    from runnify.services.demo import DEMO_EMAIL, DemoError, seed

    try:
        seed(current_app, password)
    except DemoError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Demo account ready: sign in as {DEMO_EMAIL}.")


def register_cli(app: Flask):
    """Attach the maintenance command groups to ``app``."""
    app.cli.add_command(streams_cli)
    app.cli.add_command(scores_cli)
    app.cli.add_command(laps_cli)
    app.cli.add_command(demo_cli)
