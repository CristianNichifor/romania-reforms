"""How a locality's zones are labelled when the study does not label them itself.

Most chambers name their zones and this is not needed: Alba writes `Zona A`, Brașov writes
`Zona B`, and the dialect carries the letter across. The ones that need it are the chambers
that price a city by street rather than by zone — Craiova with thirteen sections and Galați
with twenty-six — where the document gives each section a name and no letter, and something
has to stand in the zone field.

**Letters run out.** A–Z is twenty-six and Galați uses all of them. The next chamber to be read,
or the same one next year with one more street section, would have walked off the end of the
alphabet and produced `[` as a zone label — which the schema would have caught, but only after
the fact and only because the pattern happens to be strict. So past twenty-six the labels become
`Z01`, `Z02`, and the whole locality is numbered that way rather than half lettered and half not.

București is not this: it carries its chamber's own grid references — `25-A3`, `25-A3 N` — and
labels itself.
"""

from __future__ import annotations

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def zone_labels(count: int) -> list[str]:
    """`count` zone labels, lettered while the alphabet lasts and numbered after."""
    if count <= len(LETTERS):
        return list(LETTERS[:count])
    return [f"Z{position:02d}" for position in range(1, count + 1)]
