"""
Country / EU-membership facts.

Policy documents state RULES ("remote work outside the EU requires HR
approval") but never enumerate which countries are in the EU. Leaving that
gap for the language model to fill from world knowledge is exactly the kind
of ungrounded reasoning this system is built to avoid -- a smaller model
may not know, and a larger one might be confidently wrong about edge cases
(Norway, Switzerland, post-Brexit UK).

So EU membership is structured reference data, resolved deterministically
here and passed to the generator as an explicit fact alongside the policy
text. This keeps the "is Turkey in the EU?" question out of the model's
hands entirely.
"""

EU_MEMBER_STATES = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia",
    "czech republic", "denmark", "estonia", "finland", "france", "germany",
    "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
    "luxembourg", "malta", "netherlands", "poland", "portugal", "romania",
    "slovakia", "slovenia", "spain", "sweden",
}

# Countries frequently assumed to be in the EU but which are not.
NOTABLE_NON_EU = {
    "turkey", "united kingdom", "uk", "switzerland", "norway", "iceland",
    "serbia", "ukraine", "albania", "north macedonia", "montenegro",
    "bosnia", "moldova", "georgia", "russia",
}

COUNTRY_ALIASES = {
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "england": "united kingdom",
    "scotland": "united kingdom",
    "wales": "united kingdom",
    "holland": "netherlands",
    "türkiye": "turkey",
    "turkiye": "turkey",
    "deutschland": "germany",
}

KNOWN_COUNTRIES = EU_MEMBER_STATES | NOTABLE_NON_EU | set(COUNTRY_ALIASES.keys())


def normalize_country(name: str) -> str:
    key = name.strip().lower()
    return COUNTRY_ALIASES.get(key, key)


def is_eu_member(country: str) -> bool | None:
    """True/False for known countries, None when we genuinely don't know."""
    normalized = normalize_country(country)
    if normalized in EU_MEMBER_STATES:
        return True
    if normalized in NOTABLE_NON_EU:
        return False
    return None


def extract_countries(question: str) -> list[str]:
    """Find country mentions in a question, longest-match first."""
    lowered = question.lower()
    found: list[str] = []
    for candidate in sorted(KNOWN_COUNTRIES, key=len, reverse=True):
        if candidate in lowered:
            normalized = normalize_country(candidate)
            if normalized not in found:
                found.append(normalized)
    return found


def geo_facts_for_question(question: str) -> list[str]:
    """
    Deterministic geographic facts to hand the generator, so it never has to
    infer EU membership itself.
    """
    facts = []
    for country in extract_countries(question):
        eu = is_eu_member(country)
        if eu is True:
            facts.append(f"{country.title()} is a member state of the European Union.")
        elif eu is False:
            facts.append(f"{country.title()} is NOT a member state of the European Union.")
    return facts
