"""Unit tests for :mod:`fab_agent.validators`.

These tests cover the *minimum surface* the agent relies on: the
behaviour of :func:`validate_draft` plus a quick round-trip through
each of the six draft models. We do not require any network access or
the litellm / websockets dependencies; ``validators`` is a pure
pydantic module.

Run with::

    cd agent
    uv run pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

# Import the module under test. We import the package directly so we
# don't pull in handlers/llm/server (which would force a lot of
# optional dependencies).
from fab_agent.validators import (
    GroupDraft,
    LocationDraft,
    NPCDraft,
    QuestDraft,
    RegionDraft,
    ShopDraft,
    known_sheet_types,
    validate_draft,
)


# -----------------------------------------------------------------------------#
# Fixtures                                                                       #
# -----------------------------------------------------------------------------#


def _location_payload(**overrides: Any) -> Dict[str, Any]:
    """A minimal valid ``location`` draft."""
    base: Dict[str, Any] = {
        "sheetType": "location",
        "name": "The Drowned Lantern",
        "type": "structure",
        "tags": ["tavern", "smuggler", "port", "lawless"],
        "parentLocation": "Saltcliff - Dock Ward",
        "description": "A low-beamed dockside tavern lit by bioluminescent jellyfish tanks.",
        "denizens": [
            {"name": "Vaelen Kett", "role": "Innkeeper (smuggler)"},
            {"name": "Old Maren", "role": "Bouncer, ex-naval"},
        ],
        "rumors": [
            "They say the lanterns in the cellar never go out, even when you snuff them.",
        ],
        "secrets": [
            "The cellar connects to a sea cave via an old smuggler's tunnel.",
        ],
        "pages": [
            {
                "name": "Overview",
                "type": "text",
                "text": {
                    "format": 1,
                    "content": "<h2>The Drowned Lantern</h2><p>A dockside tavern.</p>",
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _npc_payload(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "sheetType": "npc",
        "name": "Vaelen Kett",
        "type": "neutral",
        "tags": ["half-elf", "criminal", "Saltcliff"],
        "linkedLocation": "JournalEntry.saltcliff-dock-ward",
        "description": "Sharp-featured half-elf, mid-40s, with a leather glove over the right hand that isn't there.",
        "personality": "Wry, watchful, fast with a joke but slower with trust.",
        "motivation": "To keep the Lantern running and her crew fed.",
        "secret": "Vaelen is not her real name.",
        "voice": "Slight coastal drawl, drops articles.",
        "linkedNpcs": ["JournalEntry.old-maren"],
    }
    base.update(overrides)
    return base


def _shop_payload(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "sheetType": "shop",
        "name": "Lantern Cellar Wares",
        "type": "black-market",
        "tags": ["Saltcliff", "black-market"],
        "linkedLocation": "JournalEntry.drowned-lantern",
        "linkedNpc": "JournalEntry.vaelen-kett",
        "description": "Contraband sold out of the Drowned Lantern's cellar.",
        "inventory": [
            {
                "name": "Smoked eel",
                "qty": 6,
                "price": "5 sp",
                "currency": "sp",
                "linkToCompendium": True,
                "compendiumUuid": "Compendium.dnd5e.items.food.eel",
            },
            {
                "name": "Iron hand",
                "qty": 1,
                "price": "25 gp",
                "currency": "gp",
                "linkToCompendium": True,
                "compendiumUuid": "Compendium.dnd5e.items.iron-hand",
            },
        ],
        "specialItems": [
            {
                "name": "Lantern of Revealing",
                "description": "Reveals invisible creatures and objects within 30 ft.",
                "price": "500 gp",
                "currency": "gp",
                "rarity": "uncommon",
                "linkToCompendium": True,
                "compendiumUuid": "Compendium.dnd5e.items.lantern-of-revealing",
            }
        ],
        "buyMultiplier": 1.0,
        "sellMultiplier": 0.5,
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------------#
# Smoke: known_sheet_types                                                       #
# -----------------------------------------------------------------------------#


def test_known_sheet_types_has_six() -> None:
    types = known_sheet_types()
    assert set(types) == {"location", "npc", "region", "shop", "group", "quest"}
    assert len(types) == 6


# -----------------------------------------------------------------------------#
# validate_draft — input validation                                             #
# -----------------------------------------------------------------------------#


def test_validate_draft_rejects_none() -> None:
    res = validate_draft(None)
    assert res["valid"] is False
    assert res["normalized"] is None
    assert any("empty" in e or "object" in e for e in res["errors"])


def test_validate_draft_rejects_unknown_sheet_type() -> None:
    res = validate_draft({"sheetType": "memes", "name": "x"})
    assert res["valid"] is False
    assert res["normalized"] is None
    assert any("sheetType" in e for e in res["errors"])


def test_validate_draft_rejects_missing_sheet_type() -> None:
    res = validate_draft({"name": "Lost Sheet"})
    assert res["valid"] is False
    assert res["normalized"] is None
    assert any("sheetType" in e for e in res["errors"])


# -----------------------------------------------------------------------------#
# validate_draft — location                                                     #
# -----------------------------------------------------------------------------#


def test_validate_draft_accepts_valid_location() -> None:
    res = validate_draft(_location_payload())
    assert res["valid"] is True, res["errors"]
    norm = res["normalized"]
    assert norm is not None
    assert norm["sheetType"] == "location"
    assert norm["name"] == "The Drowned Lantern"
    assert "tavern" in norm["tags"]
    assert isinstance(norm["denizens"], list)
    assert len(norm["denizens"]) == 2
    # tags were normalised: trimmed, no empties
    assert all(isinstance(t, str) and t for t in norm["tags"])


def test_validate_draft_normalises_comma_string_tags() -> None:
    payload = _location_payload(tags="coastal, smuggler, port")
    res = validate_draft(payload)
    assert res["valid"] is True
    assert res["normalized"]["tags"] == ["coastal", "smuggler", "port"]


def test_validate_draft_location_rejects_missing_name() -> None:
    payload = _location_payload()
    payload.pop("name", None)
    res = validate_draft(payload)
    assert res["valid"] is False
    assert any("name" in e for e in res["errors"])


def test_validate_draft_location_strips_blank_secrets() -> None:
    payload = _location_payload(secrets=["real secret", "", "   "])
    res = validate_draft(payload)
    assert res["valid"] is True
    assert res["normalized"]["secrets"] == ["real secret"]


def test_validate_draft_location_warns_when_type_missing() -> None:
    payload = _location_payload()
    payload["type"] = None
    res = validate_draft(payload)
    # Still valid (type is optional), but should carry a recommendation.
    assert res["valid"] is True
    assert any("type" in e for e in res["errors"])


# -----------------------------------------------------------------------------#
# validate_draft — npc                                                           #
# -----------------------------------------------------------------------------#


def test_validate_draft_accepts_valid_npc() -> None:
    res = validate_draft(_npc_payload())
    assert res["valid"] is True, res["errors"]
    norm = res["normalized"]
    assert norm["sheetType"] == "npc"
    assert norm["name"] == "Vaelen Kett"
    assert "half-elf" in norm["tags"]
    assert "motivation" in norm and "secret" in norm


def test_validate_draft_npc_warns_when_motivation_missing() -> None:
    payload = _npc_payload()
    payload["motivation"] = None
    res = validate_draft(payload)
    # Still valid (motivation is optional) but a warning is surfaced.
    assert res["valid"] is True
    assert any("motivation" in e for e in res["errors"])


def test_validate_draft_npc_coerces_uuid_arrays_from_objects() -> None:
    payload = _npc_payload(
        linkedNpcs=[{"uuid": "JournalEntry.a"}, {"uuid": "JournalEntry.b"}]
    )
    res = validate_draft(payload)
    assert res["valid"] is True
    assert res["normalized"]["linkedNpcs"] == [
        "JournalEntry.a",
        "JournalEntry.b",
    ]


# -----------------------------------------------------------------------------#
# validate_draft — shop                                                          #
# -----------------------------------------------------------------------------#


def test_validate_draft_accepts_valid_shop() -> None:
    res = validate_draft(_shop_payload())
    assert res["valid"] is True, res["errors"]
    norm = res["normalized"]
    assert norm["sheetType"] == "shop"
    assert norm["buyMultiplier"] == 1.0
    assert norm["sellMultiplier"] == 0.5
    inv = norm["inventory"]
    assert isinstance(inv, list) and len(inv) == 2
    assert inv[0]["compendiumUuid"] == "Compendium.dnd5e.items.food.eel"
    assert inv[0]["linkToCompendium"] is True


def test_validate_draft_shop_flags_inventory_without_compendium_uuid() -> None:
    payload = _shop_payload(
        inventory=[
            {
                "name": "Mystery Item",
                "qty": 1,
                "price": "1 gp",
                "currency": "gp",
                "linkToCompendium": True,
                # no compendiumUuid
            }
        ]
    )
    res = validate_draft(payload)
    # The draft is structurally valid (no Pydantic errors) but a
    # warning is surfaced for the missing compendiumUuid.
    assert res["valid"] is True
    assert any("compendiumUuid" in e for e in res["errors"])


def test_validate_draft_shop_normalises_negative_multipliers() -> None:
    payload = _shop_payload(buyMultiplier=-2, sellMultiplier="oops")
    res = validate_draft(payload)
    assert res["valid"] is True
    # Both fall back to 1.0 (negative is invalid; non-numeric is invalid).
    assert res["normalized"]["buyMultiplier"] == 1.0
    assert res["normalized"]["sellMultiplier"] == 1.0


# -----------------------------------------------------------------------------#
# Round-trip: every draft model can build + dump                                #
# -----------------------------------------------------------------------------#


@pytest.mark.parametrize(
    "model_cls, payload",
    [
        (LocationDraft, _location_payload()),
        (NPCDraft, _npc_payload()),
        (RegionDraft, {
            "sheetType": "region",
            "name": "Saltcliff",
            "type": "city",
            "tags": ["coastal", "lawless"],
            "description": "A smuggler's port city.",
        }),
        (ShopDraft, _shop_payload()),
        (GroupDraft, {
            "sheetType": "group",
            "name": "The Lantern Crew",
            "type": "faction",
            "goals": ["smuggle goods", "stay alive"],
            "resources": ["three ships", "corrupt guard captain"],
            "linkedNpcs": ["JournalEntry.vaelen-kett"],
        }),
        (QuestDraft, {
            "sheetType": "quest",
            "name": "The Drowned Lantern Job",
            "type": "side",
            "description": "The crew needs a courier for a hot cargo run.",
            "objectives": [
                {"text": "Find the dockmaster's ledger", "completed": False, "optional": False},
                {"text": "Survive the harbour patrol", "completed": False, "optional": False},
            ],
            "rewards": ["100 gp", "favor with the Lantern Crew"],
            "linkedNpcs": ["JournalEntry.vaelen-kett"],
            "linkedLocations": ["JournalEntry.drowned-lantern"],
        }),
    ],
)
def test_draft_models_round_trip(model_cls, payload: Dict[str, Any]) -> None:
    """Each draft model should accept a valid payload and serialise to JSON."""
    model = model_cls(**payload)
    as_dict = model.model_dump(exclude_none=True)
    # Sheet type is preserved.
    assert as_dict["sheetType"] == payload["sheetType"]
    # Name is preserved.
    assert as_dict["name"] == payload["name"]
    # And the round-trip survives a JSON encode/decode.
    encoded = json.dumps(as_dict)
    decoded = json.loads(encoded)
    assert decoded["name"] == payload["name"]
    assert decoded["sheetType"] == payload["sheetType"]


# -----------------------------------------------------------------------------#
# Reference JSON templates exist + parse                                         #
# -----------------------------------------------------------------------------#


@pytest.mark.parametrize(
    "template_path",
    [
        "templates/dnd5e/actor.json",
        "templates/dnd5e/item.json",
        "templates/dnd5e/journal-page.json",
    ],
)
def test_template_files_exist_and_parse(template_path: str) -> None:
    """The three reference JSON templates ship as valid JSON files."""
    here = Path(__file__).resolve().parent.parent
    full = here / "src" / "fab_agent" / template_path
    assert full.exists(), f"missing reference template: {full}"
    raw = full.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    # Every template must declare a `name` — that's how the LLM will
    # pattern-match the shape when it needs to emit a new entry.
    assert "name" in parsed and isinstance(parsed["name"], str) and parsed["name"]
