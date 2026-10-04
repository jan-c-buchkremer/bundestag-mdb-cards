"""HTML for the sub-TOPs of a block agenda item on a sitting page (data in subtops.py). Called from pages.py."""

from __future__ import annotations

from research import facts, urls
from research.pages import vorgaenge_line
from research.ui import e

NO_DEBATE_NOTE = (
    "Nach dem Protokoll ist für diese Vorlagen keine Aussprache vorgesehen: Sie werden ohne Aussprache zur "
    "Abstimmung aufgerufen. Die Beschlüsse stehen bei den einzelnen Unterpunkten."
)
BLOCK_SPEECH_NOTE = (
    "Wortmeldung während des Abstimmungsblocks. Sie gehört zu keiner Aussprache über diese Vorlagen, denn "
    "dafür ist keine vorgesehen."
)
BLOCK_SPEECH_NOTE_DEBATE = "Diese Reden sind dem ganzen Block zugeordnet, nicht einer einzelnen Vorlage."


def anchor(item: dict, sub: dict | None = None) -> str:
    return f"top-{item['position']}" + (f"-{sub['label']}" if sub else "")


def href(sitting: str, position: int, label: str, root: str = "../") -> str:
    """Link to a sub-TOP on its sitting page."""
    return f"{root}{urls.sitting(sitting, position, label)}"


def no_debate_note(i: dict) -> str:
    """An item with no debate and no sub-TOPs: say so, so its votes do not read as the end of a debate."""
    if not i.get("no_debate") or i.get("sub_items"):
        return ""
    return f'<p class="explain">{e(NO_DEBATE_NOTE.split(" Die Beschlüsse")[0])}</p>'


def sub_top(item: dict, sub: dict, s: dict) -> str:
    parts = [f'<div class="subtop" id="{anchor(item, sub)}"><h4><span class="lbl">{e(sub["label"])}</span> '
             f'{e(sub["title"])}']  # fmt: skip
    if sub["no_debate"] and not item["no_debate"]:
        parts.append(' <span class="badge none">ohne Aussprache</span>')
    parts.append("</h4>")
    if sub["segments"] and (len(sub["segments"]) > 1 or sub["segments"][0] != sub["title"]):
        parts.append('<details class="full"><summary>Vollständiger Titel</summary>'
                     + "".join(f"<p>{e(x)}</p>" for x in sub["segments"]) + "</details>")  # fmt: skip
    if sub["drucksachen"]:
        parts.append(f'<div class="drs"><span class="k">Drucksachen</span> '
                     f"{facts.drucksache_list(sub['drucksachen'], '../')}</div>")  # fmt: skip
    parts.append(vorgaenge_line(sub.get("vorgaenge") or []))
    if sub["decisions"]:
        parts.append('<div class="decs"><div class="k">Beschluss</div>'
                     + "".join(facts.decision(d, "../", when=False, agenda=False) for d in sub["decisions"])
                     + "</div>")  # fmt: skip
    if sub["speeches"]:
        parts.append(facts.speech_block(sub["speeches"], f"{item['position']}-{sub['label']}"))
    parts.append("</div>")
    return "".join(parts)


def block(i: dict, s: dict) -> str:
    """The sub-TOPs of an item, each with its Drucksachen, decisions and (where the store knows them) speeches."""
    intro = ""
    if i["no_debate"]:
        intro = (f'<p class="explain">{e(NO_DEBATE_NOTE)} '
                 f'<a href="{e(s["pdf"])}">Plenarprotokoll {e(s["cite"])} (PDF)</a></p>')  # fmt: skip
    return intro + '<div class="subtops">' + "".join(sub_top(i, sub, s) for sub in i["sub_items"]) + "</div>"


def block_speeches(i: dict, s: dict) -> str:
    """Speeches the store cannot place under one sub-TOP: shown under the block with a note on what they are."""
    sps = i["block_speeches"]
    if not sps:
        return ""
    note = BLOCK_SPEECH_NOTE if i["no_debate"] else BLOCK_SPEECH_NOTE_DEBATE
    return f'<p class="explain">{e(note)}</p>' + facts.speech_block(sps, str(i["position"]))
