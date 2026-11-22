"""Allow-listed sources for the collection worker."""
from enum import StrEnum
from importlib import import_module

from parser_running.rr_platform import SOURCES as RR_SOURCES


class SourceCode(StrEnum):
    russiarunning = "russiarunning"
    timerman = "timerman"
    legkovrace = "legkovrace"
    pionercup = "pionercup"
    probeg = "probeg"
    ironstar = "ironstar"
    grom = "grom"
    russialoppet = "russialoppet"
    myrunstats = "myrunstats"


SOURCE_CONFIG = {
    **{code: (base.removesuffix("/api"), "rr_api", "api",
              "run" if code == "russiarunning" else "run,ski,trail,triathlon")
       for code, base in RR_SOURCES.items()},
    SourceCode.probeg: ("https://probeg.org", "probeg", "html", "run"),
    SourceCode.ironstar: ("https://iron-star.com", "ironstar", "api", "triathlon"),
    SourceCode.grom: ("https://grom.place", "grom", "html", "run,triathlon"),
    SourceCode.russialoppet: ("https://russialoppet.ru", "russialoppet", "html", "ski"),
    SourceCode.myrunstats: ("https://myrunstats.ru", "myrunstats", "api", "run"),
}


def fetch_event(source: str, event_code: str) -> dict:
    if source in RR_SOURCES:
        from app.pipeline.russia_running import fetch_event as fetch_rr_event

        return fetch_rr_event(event_code, source=source)
    adapter = import_module(f"app.pipeline.{SourceCode(source).value}")
    return adapter.fetch_event(event_code)
