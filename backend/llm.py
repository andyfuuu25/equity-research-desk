import os
from google import genai
from google.genai import types

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


SYSTEM_PROMPT = (
    "You are an encouraging and accessible senior equity research analyst writing a company profile for beginners. "
    "Be concise and direct — avoid financial jargon where simple terms work, and briefly explain key business concepts when they appear (e.g., explain what a 'moat' or 'revenue stream' means in context). "
    "Ground every claim in the data provided. If a field is N/A, omit it cleanly rather than noting its absence. "
    "Write for a curious, novice investor who wants to understand how the business actually functions and makes money, rather than just reading a dry Wikipedia description."
)


# Primary model is quality-first (best free-tier analyst prose). If its daily
# quota is exhausted mid-session, we degrade to the high-quota fallback rather
# than failing the report. Override the primary via GEMINI_MODEL env var.
_PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_FALLBACK_MODEL = "gemini-2.0-flash"

# Error signatures that indicate quota/availability (worth falling back on),
# as opposed to bad requests (which would fail on any model).
_RETRIABLE_MARKERS = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500")


def _call_gemini(prompt: str, temperature: float) -> str:
    models = [_PRIMARY_MODEL]
    if _FALLBACK_MODEL != _PRIMARY_MODEL:
        models.append(_FALLBACK_MODEL)

    last_err: Exception | None = None
    for model in models:
        try:
            response = _get_client().models.generate_content(
                model=model,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=temperature,
                ),
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            last_err = e
            if any(m in str(e) for m in _RETRIABLE_MARKERS):
                continue  # quota/availability — try the fallback model
            raise RuntimeError(f"Gemini API error: {e}") from e

    raise RuntimeError(f"Gemini API unavailable: {last_err}") from last_err


# Sentinel that separates the two sections in a single combined completion.
# Chosen to never appear in normal analyst prose so the split is unambiguous.
_SECTION_DELIMITER = "===PIPELINE==="


def generate_report_sections(company_info: dict, pipeline_data: dict) -> tuple[str, str]:
    """Generate Executive Summary + Future Pipeline in ONE Gemini call.

    The free tier is request-per-day limited, so collapsing the two prompts
    into a single request roughly doubles the number of reports/day. The model
    is instructed to emit both sections separated by ``_SECTION_DELIMITER``,
    which we split back apart here. Returns ``(summary, pipeline)``.
    """
    earnings_date = pipeline_data.get("earnings_date", "Not available")
    articles = pipeline_data.get("articles", [])

    if articles:
        # Compact one-line-per-field block — trimmed upstream in data.py.
        articles_block = "\n\n".join(
            f"- {a['title']} ({a['date']}, {a['source']}, {a['sentiment']}"
            + (f", {', '.join(a['topics'])}" if a['topics'] else "")
            + f"): {a['summary']}"
            for a in articles
        )
    else:
        articles_block = "No recent news articles available."

    prompt = f"""Produce TWO sections for {company_info['company']} ({company_info['ticker']}), separated by a line containing exactly {_SECTION_DELIMITER}.

=== SECTION 1: EXECUTIVE SUMMARY ===
Three short paragraphs, no headers, no bullets:
1. What the business does and the markets it serves (1–2 sentences).
2. How it makes money: revenue model, margins, and scale — reference the figures below.
3. Competitive character from the numbers (cash generation, growth, volatility vs. market). No claims unsupported by the data.

COMPANY DATA:
Sector / Industry: {company_info['sector']} / {company_info['industry']} | Employees: {company_info['full_time_employees']}
Market Cap: {company_info['market_cap']} | Revenue (TTM): {company_info['total_revenue']} | Rev Growth YoY: {company_info['revenue_growth_yoy']}
Gross Margin: {company_info['gross_margin']} | Net Margin: {company_info['profit_margin']} | Free Cash Flow: {company_info['free_cashflow']} | Beta: {company_info['beta']}
Description: {company_info['description']}

=== SECTION 2: FUTURE PIPELINE ===
Build a forward-looking pipeline for {company_info['ticker']} from the news below.
- Include any article containing a specific fact, event, or development involving {company_info['company']} — even when the article also covers other companies or the broader market. Extract the {company_info['ticker']}-relevant angle and classify that.
- Exclude an article only if it carries no information relevant to this company.
- ALWAYS list the upcoming earnings date as the first Confirmed Catalyst when one is provided.
- Do not invent events beyond the articles and earnings data.
Each bullet: "- [Short label]: [one plain sentence on why it matters for {company_info['ticker']}]". If a bucket still has no items, write "None identified." Use exactly these headings:

Upcoming Earnings: {earnings_date}

Confirmed Catalysts:
- [item]: [description]

Developing Stories:
- [item]: [description]

Risk Events:
- [item]: [description]

NEWS ARTICLES:
{articles_block}

Return only the two sections and the {_SECTION_DELIMITER} line between them. No preamble, no commentary."""

    # Validation + single retry (SPEC §6.3 format enforcement / Phase 3).
    # A malformed response is regenerated once before we accept a best-effort split.
    raw = _call_gemini(prompt, temperature=0.25)
    result = _split_and_validate(raw, earnings_date)
    if result is None:
        raw = _call_gemini(prompt, temperature=0.25)
        result = _split_and_validate(raw, earnings_date)
    if result is None:
        result = _best_effort_split(raw, earnings_date)

    summary, pipeline = result
    return summary, _ensure_earnings_catalyst(pipeline, earnings_date)


def _ensure_earnings_catalyst(pipeline: str, earnings_date: str) -> str:
    """Guarantee the known earnings date appears as a Confirmed Catalyst.

    A scheduled earnings report IS a confirmed catalyst (SPEC §5.2 lists it as
    the canonical example), but the model reliably leaves the bucket empty when
    no article mentions it. Deterministic post-processing beats prompt hope.
    """
    if not earnings_date or earnings_date == "Not available":
        return pipeline
    import re

    return re.sub(
        r"Confirmed Catalysts:\s*\n\s*None identified\.",
        f"Confirmed Catalysts:\n- Earnings Report ({earnings_date}): "
        "A confirmed reporting date — quarterly results and guidance "
        "routinely move the stock.",
        pipeline,
        count=1,
    )


_PIPELINE_HEADINGS = ("Confirmed Catalysts:", "Developing Stories:", "Risk Events:")


def _split_and_validate(raw: str, earnings_date: str) -> tuple[str, str] | None:
    """Split a combined completion and check both sections meet the format spec.

    Returns ``(summary, pipeline)`` when valid, else ``None`` to trigger a retry.
    """
    if _SECTION_DELIMITER not in raw:
        return None
    summary, pipeline = (part.strip() for part in raw.split(_SECTION_DELIMITER, 1))

    # Summary: three substantive paragraphs per spec (accept 2+ to tolerate merges).
    paragraphs = [p for p in summary.split("\n\n") if p.strip()]
    if len(paragraphs) < 2:
        return None

    # Pipeline: all three classification headings must be present.
    if not all(h in pipeline for h in _PIPELINE_HEADINGS):
        return None

    return summary, pipeline


def _best_effort_split(raw: str, earnings_date: str) -> tuple[str, str]:
    """Last-resort split when validation failed twice — salvage what we can."""
    if _SECTION_DELIMITER in raw:
        summary, pipeline = raw.split(_SECTION_DELIMITER, 1)
        return summary.strip(), pipeline.strip()
    marker = "Upcoming Earnings:"
    if marker in raw:
        idx = raw.index(marker)
        return raw[:idx].strip(), raw[idx:].strip()
    return raw.strip(), f"Upcoming Earnings: {earnings_date}\n\n(Pipeline unavailable.)"
