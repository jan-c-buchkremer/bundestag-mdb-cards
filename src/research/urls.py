"""The canonical path of every entity and fact, relative to the site root (docs/plan.md section 11.2). Pages put
their own `root` ("", "../") in front. One entity, one URL: nothing else in the site builds these paths by hand."""

from __future__ import annotations

import re

from research.data import decision_href, land_slug, page_id

GOVERNMENT = "gremien/bundesregierung.html"
PLACES = "orte/index.html"
PERIOD = "sitzungen/index.html"
PROCEDURES = "vorgaenge/index.html"
THEMES = "themen/index.html"


def person(pid: str) -> str:
    return f"{pid}.html"


def rede(speech_id: str) -> str:
    """ "ID1-3" -> "ID1": the rede a part belongs to."""
    return re.sub(r"-\d+$", "", speech_id)


def speech(speech_id: str) -> str:
    """The full text of a rede; a part of it (a Zwischenfrage, a turn in the Befragung) is an anchor there. A
    Fragestunde turn's id has slashes ("21/3/5/f1"), hence page_id."""
    r = rede(speech_id)
    return f"reden/{page_id(r)}.html" + ("" if r == speech_id else f"#{speech_id}")


def sitting(sitting_id: str, position: int | None = None, label: str | None = None) -> str:
    """A sitting, zoomed in to an agenda item (#top-<position>) or one of its sub-items (#top-<position>-<label>)."""
    anchor = "" if position is None else f"#top-{position}" + (f"-{label}" if label else "")
    return f"sitzungen/{page_id(sitting_id)}.html{anchor}"


def week(iso_week: str) -> str:
    return f"woche/{iso_week}.html"


def vorgang(vorgang_id: str) -> str:
    return f"vorgaenge/{vorgang_id}.html"


def decision(d: dict) -> str:
    """A decision's point on its Vorgang's timeline, or its own page (D15)."""
    return d.get("href") or decision_href(d["page"], d.get("vorgaenge") or [])


def land(code: str) -> str:
    return f"orte/{land_slug(code)}.html"


def wahlkreis(number: int | str) -> str:
    return f"orte/wahlkreis-{number}.html"


def theme(theme_id: int | str) -> str:
    return f"themen/{theme_id}.html"
