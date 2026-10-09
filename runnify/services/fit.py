"""Helpers for reading Garmin ``.fit`` activity files."""

from fitparse import FitFile


def _ema(values, alpha=0.2):  # exponential moving average smoothing
    """Smooth a series with an exponential moving average.

    ``None`` gaps are filled with the previous smoothed value.

    Args:
        values: Numeric values (may contain ``None``).
        alpha: Smoothing factor; higher reacts faster to changes.

    Returns:
        A list the same length as ``values``.
    """
    ema_values = []
    prev_ema = None
    for value in values:
        if value is None:
            ema_values.append(prev_ema)
            continue
        if prev_ema is None:  # start with first available value
            prev_ema = value
        else:
            # alpha x current value + (1 - alpha) x previous ema
            prev_ema = alpha * value + (1 - alpha) * prev_ema
        ema_values.append(prev_ema)
    return ema_values  # smoothed list output


def read_fit_to_series(
    fit_file_path,
):  # extracts timestamps, heart rate, and pace from a fit file
    """Extract time series from a FIT file.

    Pace comes from the recorded (enhanced) speed, or from the change in
    distance between records when speed is missing, and is EMA-smoothed.

    Args:
        fit_file_path: Path to a ``.fit`` file.

    Returns:
        A ``(timestamps, heart_rates, paces_seconds_per_km)`` tuple of
        equal-length lists, sorted by time. Heart rate and pace entries can be
        ``None``. All three lists are empty if the file has no records.
    """
    fit_file = FitFile(fit_file_path)
    record_rows = []

    for record in fit_file.get_messages("record"):
        fields = {field.name: field.value for field in record}
        timestamp = fields.get("timestamp")
        heart_rate = fields.get("heart_rate")
        speed = fields.get(
            "enhanced_speed", fields.get("speed")
        )  # use enhanced speed if available
        distance = fields.get("distance")
        if timestamp is not None:
            record_rows.append((timestamp, heart_rate, speed, distance))

    record_rows.sort(key=lambda row: row[0])  # ensure sorted
    if not record_rows:
        return [], [], []

    timestamps = [row[0] for row in record_rows]
    heart_rates = [row[1] for row in record_rows]

    paces_seconds_per_km = []
    for index, (timestamp, _, speed, distance) in enumerate(record_rows):
        pace = None
        if speed and speed > 0:  # convert speed to pace
            pace = 1000.0 / speed
        elif index > 0:
            prev_timestamp, _, _, prev_distance = record_rows[index - 1]
            if distance is not None and prev_distance is not None:
                distance_delta = distance - prev_distance
                time_delta = (timestamp - prev_timestamp).total_seconds() or 1
                if distance_delta > 0.5:  # avoid zero or noise values
                    meters_per_second = distance_delta / time_delta
                    if meters_per_second > 0:
                        pace = 1000.0 / meters_per_second
        paces_seconds_per_km.append(pace)

    # smooth noise with EMA
    paces_seconds_per_km = _ema(paces_seconds_per_km, alpha=0.2)

    return timestamps, heart_rates, paces_seconds_per_km
