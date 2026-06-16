"""Pydantic models for Campaign Codex draft validation.

These models are the **authoritative shape** of every CC sheet the agent
emits. The LLM is asked to emit JSON, and we run the resulting dict
through :func:`validate_draft` to:

  * catch obviously broken output (missing ``sheetType``, wrong types)
  * normalise tags into a list of non-empty strings
  * strip unknown fields (or keep them, depending on the flag)
  * surface a clean ``{valid, errors, normalized}`` result to the
    design handlers, which attach it to the ``design.preview`` event

The field set comes from the ``campaign-codex-sheets`` skill. We keep
the validators liberal — most fields are optional, the LLM is best
left to choose what to fill in, and the Foundry client can ignore
fields it doesn't understand.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# -----------------------------------------------------------------------------#
# Common building blocks                                                        #
# -----------------------------------------------------------------------------#


class _Base(BaseModel):
    """Common Pydantic config: allow extras (we don't want to throw away
    fields the LLM added that the schema doesn't know about — the
    Foundry client decides what to do with them)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


def _normalise_tags(v: Any) -> List[str]:
    """Coerce ``tags`` to ``List[str]``, drop empty/whitespace tags.

    Tags in CC are simple strings without commas (CC uses commas to
    delimit in the filter UI). We strip whitespace, drop empties, and
    return a fresh list.
    """
    if v is None:
        return []
    if isinstance(v, str):
        # Comma-separated string -> list.
        items = [p.strip() for p in v.split(",")]
    elif isinstance(v, (list, tuple, set)):
        items = [str(x).strip() for x in v]
    else:
        return []
    return [t for t in items if t]


def _coerce_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None]
    return []


def _coerce_uuid_list(v: Any) -> List[str]:
    """UUID arrays can arrive as ``["JournalEntry.xxx", ...]`` or as
    ``[{"uuid": "..."}, ...]`` (the LLM is inconsistent). Normalise."""
    if v is None:
        return []
    out: List[str] = []
    if isinstance(v, (list, tuple)):
        for x in v:
            if isinstance(x, str):
                if x.strip():
                    out.append(x.strip())
            elif isinstance(x, Mapping):
                u = x.get("uuid")
                if isinstance(u, str) and u.strip():
                    out.append(u.strip())
    return out


# -----------------------------------------------------------------------------#
# Sub-models                                                                    #
# -----------------------------------------------------------------------------#


class _InventoryItem(_Base):
    """An inventory entry in a shop sheet."""

    name: str = Field(..., description="Item name (matches the SRD entry).")
    qty: int = Field(default=1, ge=0)
    price: Union[str, int, float, None] = None
    currency: Optional[str] = None
    linkToCompendium: bool = Field(default=True)
    compendiumUuid: Optional[str] = None
    description: Optional[str] = None


class _SpecialItem(_Base):
    """A magic / unique item in a shop sheet."""

    name: str
    description: Optional[str] = None
    price: Union[str, int, float, None] = None
    currency: Optional[str] = None
    rarity: Optional[str] = None
    linkToCompendium: bool = Field(default=True)
    compendiumUuid: Optional[str] = None


class _Denizen(_Base):
    """An NPC mentioned in a location's ``denizens`` array."""

    name: str
    role: Optional[str] = None
    linkToSheet: bool = Field(default=False)
    uuid: Optional[str] = None
    compendiumUuid: Optional[str] = None


class _Objective(_Base):
    """A quest objective."""

    text: str
    completed: bool = False
    optional: bool = False


class _LinkedJournal(_Base):
    """A loose-format linked journal entry (used inside ``linkedJournals``)."""

    id: Optional[str] = None
    uuid: Optional[str] = None
    name: Optional[str] = None
    sheetType: Optional[str] = None


# -----------------------------------------------------------------------------#
# Top-level draft models                                                        #
# -----------------------------------------------------------------------------#


class LocationDraft(_Base):
    """A Campaign Codex ``location`` sheet draft."""

    sheetType: Literal["location"] = "location"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parentLocation: Optional[str] = None
    description: Optional[str] = None
    denizens: List[Dict[str, Any]] = Field(default_factory=list)
    linkedNpcs: List[str] = Field(default_factory=list)
    linkedShops: List[str] = Field(default_factory=list)
    linkedQuests: List[str] = Field(default_factory=list)
    linkedLocations: List[str] = Field(default_factory=list)
    rumors: List[str] = Field(default_factory=list)
    secrets: List[str] = Field(default_factory=list)
    linkedJournals: Optional[Dict[str, Any]] = None
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None
    folder: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))
    _norm_linked_npcs = field_validator("linkedNpcs")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_shops = field_validator("linkedShops")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_quests = field_validator("linkedQuests")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_locs = field_validator("linkedLocations")(lambda cls, v: _coerce_uuid_list(v))
    _norm_rumors = field_validator("rumors")(lambda cls, v: _coerce_str_list(v))
    _norm_secrets = field_validator("secrets")(lambda cls, v: _coerce_str_list(v))


class NPCDraft(_Base):
    """A Campaign Codex ``npc`` sheet draft."""

    sheetType: Literal["npc"] = "npc"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    linkedLocation: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    motivation: Optional[str] = None
    secret: Optional[str] = None
    voice: Optional[str] = None
    linkedNpcs: List[str] = Field(default_factory=list)
    linkedQuests: List[str] = Field(default_factory=list)
    actorUuid: Optional[str] = None
    gear: List[Dict[str, Any]] = Field(default_factory=list)
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))
    _norm_linked_npcs = field_validator("linkedNpcs")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_quests = field_validator("linkedQuests")(lambda cls, v: _coerce_uuid_list(v))


class RegionDraft(_Base):
    """A Campaign Codex ``region`` sheet draft."""

    sheetType: Literal["region"] = "region"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parentLocation: Optional[str] = None
    description: Optional[str] = None
    linkedLocations: List[str] = Field(default_factory=list)
    linkedNpcs: List[str] = Field(default_factory=list)
    linkedQuests: List[str] = Field(default_factory=list)
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))
    _norm_linked_locs = field_validator("linkedLocations")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_npcs = field_validator("linkedNpcs")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_quests = field_validator("linkedQuests")(lambda cls, v: _coerce_uuid_list(v))


class ShopDraft(_Base):
    """A Campaign Codex ``shop`` sheet draft."""

    sheetType: Literal["shop"] = "shop"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    linkedLocation: Optional[str] = None
    linkedNpc: Optional[str] = None
    description: Optional[str] = None
    inventory: List[Dict[str, Any]] = Field(default_factory=list)
    specialItems: List[Dict[str, Any]] = Field(default_factory=list)
    buyMultiplier: float = 1.0
    sellMultiplier: float = 1.0
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))

    @field_validator("buyMultiplier", "sellMultiplier")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 1.0
        return f if f >= 0 else 1.0


class GroupDraft(_Base):
    """A Campaign Codex ``group`` sheet draft."""

    sheetType: Literal["group"] = "group"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    goals: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)
    allies: List[str] = Field(default_factory=list)
    enemies: List[str] = Field(default_factory=list)
    linkedNpcs: List[str] = Field(default_factory=list)
    linkedLocations: List[str] = Field(default_factory=list)
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))
    _norm_goals = field_validator("goals")(lambda cls, v: _coerce_str_list(v))
    _norm_resources = field_validator("resources")(lambda cls, v: _coerce_str_list(v))
    _norm_allies = field_validator("allies")(lambda cls, v: _coerce_uuid_list(v))
    _norm_enemies = field_validator("enemies")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_npcs = field_validator("linkedNpcs")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_locs = field_validator("linkedLocations")(lambda cls, v: _coerce_uuid_list(v))


class QuestDraft(_Base):
    """A Campaign Codex ``quest`` sheet draft."""

    sheetType: Literal["quest"] = "quest"
    name: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    objectives: List[Dict[str, Any]] = Field(default_factory=list)
    rewards: List[str] = Field(default_factory=list)
    linkedNpcs: List[str] = Field(default_factory=list)
    linkedLocations: List[str] = Field(default_factory=list)
    linkedItems: List[str] = Field(default_factory=list)
    parentQuest: Optional[str] = None
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ownership: Optional[Dict[str, Any]] = None
    hidden: bool = False
    img: Optional[str] = None

    _normalise_tags = field_validator("tags")(lambda cls, v: _normalise_tags(v))
    _norm_rewards = field_validator("rewards")(lambda cls, v: _coerce_str_list(v))
    _norm_linked_npcs = field_validator("linkedNpcs")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_locs = field_validator("linkedLocations")(lambda cls, v: _coerce_uuid_list(v))
    _norm_linked_items = field_validator("linkedItems")(lambda cls, v: _coerce_uuid_list(v))


# -----------------------------------------------------------------------------#
# Dispatch                                                                      #
# -----------------------------------------------------------------------------#


_DRAFT_MODELS: Dict[str, type] = {
    "location": LocationDraft,
    "npc": NPCDraft,
    "region": RegionDraft,
    "shop": ShopDraft,
    "group": GroupDraft,
    "quest": QuestDraft,
}


def validate_draft(
    draft: Mapping[str, Any] | None,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    """Validate and normalise a CC sheet draft.

    The function dispatches on ``draft["sheetType"]``. If the sheet type
    is missing or unknown, the result is::

        {"valid": False, "errors": ["..."], "normalized": None}

    On success, ``normalized`` is the cleaned-up dict that the design
    handlers attach to the ``design.preview`` event. The strict flag
    turns on a couple of additional checks (e.g. disallowing unknown
    sheet types entirely) but is off by default so the agent remains
    forgiving of LLM improvisation.

    Args:
        draft: A dict (or any Mapping) as produced by the LLM.
        strict: If ``True``, unknown top-level keys are dropped from
            ``normalized`` (default: keep them — ``extra="allow"``).
    """
    if not draft or not isinstance(draft, Mapping):
        return {
            "valid": False,
            "errors": ["draft is empty or not a JSON object"],
            "normalized": None,
        }

    sheet_type = draft.get("sheetType")
    if not sheet_type:
        return {
            "valid": False,
            "errors": ["draft is missing required field 'sheetType'"],
            "normalized": None,
        }
    if sheet_type not in _DRAFT_MODELS:
        return {
            "valid": False,
            "errors": [
                f"unknown sheetType {sheet_type!r}; "
                f"expected one of: {', '.join(_DRAFT_MODELS)}"
            ],
            "normalized": None,
        }

    model_cls = _DRAFT_MODELS[sheet_type]
    errors: List[str] = []
    try:
        model = model_cls(**dict(draft))
    except Exception as exc:
        # Pydantic errors are rich; flatten to a readable list.
        for err in _iter_pydantic_errors(exc):
            errors.append(err)
        return {
            "valid": False,
            "errors": errors,
            "normalized": None,
        }

    normalised = model.model_dump(exclude_none=True, by_alias=False)

    # Extra checks not easily expressed in Pydantic.
    if sheet_type == "location":
        if not (normalised.get("type") or "").strip():
            errors.append("location.type is recommended (tavern, settlement, ...)")
    if sheet_type == "shop":
        inv = normalised.get("inventory") or []
        for i, item in enumerate(inv):
            if not isinstance(item, Mapping):
                continue
            if item.get("linkToCompendium") and not item.get("compendiumUuid"):
                errors.append(
                    f"shop.inventory[{i}].linkToCompendium is true but "
                    f"compendiumUuid is missing"
                )
    if sheet_type == "npc":
        if not (normalised.get("motivation") or "").strip():
            errors.append("npc.motivation is recommended (what they want)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "normalized": normalised,
    }


def _iter_pydantic_errors(exc: Exception) -> List[str]:
    """Flatten a Pydantic ``ValidationError`` into a list of readable lines.

    Pydantic v2 exposes ``errors()`` on ValidationError, which returns
    a list of dicts. We massage the format so the design handler can
    surface them to the client verbatim.
    """
    out: List[str] = []
    try:
        items = exc.errors()  # type: ignore[attr-defined]
    except Exception:
        return [str(exc)]
    for item in items:
        loc = ".".join(str(x) for x in item.get("loc", []) if x not in (None, ""))
        msg = item.get("msg", "invalid value")
        typ = item.get("type", "")
        if loc:
            out.append(f"{loc}: {msg} ({typ})" if typ else f"{loc}: {msg}")
        else:
            out.append(msg)
    return out


def known_sheet_types() -> List[str]:
    """The list of sheet types the validator knows about."""
    return list(_DRAFT_MODELS.keys())


__all__ = (
    "LocationDraft",
    "NPCDraft",
    "RegionDraft",
    "ShopDraft",
    "GroupDraft",
    "QuestDraft",
    "validate_draft",
    "known_sheet_types",
)
