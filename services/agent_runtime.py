"""Budget, cost and cap primitives for the agent runtime (SPEC §6.5, task A9).

SPEC §6.5 lists four caps. Task A8 already implemented the first one --
verktygsvarv per underlag (tool turns per item) -- directly inside
`services/agent_session.py`'s `run_session` loop, and A9 added the second one
(ut-token per underlag / output tokens per item) to that same loop, since
both can only be measured turn by turn.

This module holds the other two:

- Cost calculation (`compute_cost_ore`): a pure function from a model id and
  a `Usage` to an integer öre amount, using the price table in
  `services/llm/__init__.py`.
- The daily budget cap / "dygnstaket" (`ensure_daily_budget_available`,
  `DailyBudgetExhaustedError`): SPEC §6.5's "kostnad per dygn" cap. "Vid
  dygnstaket: stanna, aldrig nedgradera modell" (§6.5, §12.5) -- this module
  never adjusts the model; it only decides whether a pass, or the next item
  in one, is allowed to spend more today.

The fourth cap -- "underlag per pass" (items per pass, default
`config.settings.agent_max_items_per_pass`) -- is *not* implemented here.
SPEC §9's table describes it as a plain loop bound ("stop after N items,
leave the rest queued"), and the queue-iteration loop it bounds doesn't exist
yet -- that is task A10's worker (`AgentWorker`/`AgentRunner`), not this
module. Building a stub function with no real caller here would just be dead
code for A10 to delete; the cap's home is the `for item in
queue[:settings.agent_max_items_per_pass]` (or equivalent counter) inside
A10's pass loop, once that loop exists.

This module never imports `anthropic`/`openai`, has no HTTP concepts, and
does no SQL of its own -- it only reads through `AgentRunRepository`'s
existing methods. Nothing here ever runs inside a `with db.transaction():`
block; there is none in this module, matching `services/agent_session.py`
(SPEC §6.5: "aldrig inuti `with db.transaction():`").
"""

from config import settings
from repositories.agent_run_repo import AgentRunRepository
from services.llm import Usage, get_model_info

# ---------------------------------------------------------------------------
# Cost calculation (SPEC §5: "cost_ore beräknas ur usage och prislistan")
# ---------------------------------------------------------------------------


def compute_cost_ore(model: str, usage: Usage) -> int:
    """Compute the integer öre cost of one `Usage` on `model`.

    Looks up `model`'s price row via `services.llm.get_model_info` and
    applies the formula documented on `ModelPrice`
    (`services/llm/__init__.py`): each token category is priced
    independently at its own per-million-tokens rate with integer floor
    division, and the three results are summed at the end -- never summed
    first and divided once, which would round differently.

    Critically, `usage.cache_read_input_tokens` is priced at
    `price.cache_read_ore_per_million_tokens`, *not*
    `price.input_ore_per_million_tokens` -- conflating the two would silently
    misprice every cached turn from the second item in a pass onward
    (SPEC §6.6).

    Raises `services.llm.UnknownModelError` unhandled if `model` has no price
    row -- SPEC §2: "en modell utan prisrad är ett fel, inte ett
    standardvärde." A pass on an unpriced model is a hard stop; it is not
    this function's job to catch that and fall back to a cost of 0.
    """
    price = get_model_info(model).price
    input_cost_ore = (
        usage.input_tokens * price.input_ore_per_million_tokens // 1_000_000
    )
    output_cost_ore = (
        usage.output_tokens * price.output_ore_per_million_tokens // 1_000_000
    )
    cache_read_cost_ore = (
        usage.cache_read_input_tokens
        * price.cache_read_ore_per_million_tokens
        // 1_000_000
    )
    return input_cost_ore + output_cost_ore + cache_read_cost_ore


# ---------------------------------------------------------------------------
# Daily budget cap / "dygnstaket" (SPEC §6.5, §9 test case 8)
# ---------------------------------------------------------------------------


class DailyBudgetExhaustedError(Exception):
    """Raised when today's spend already meets or exceeds the daily budget.

    Carries `spent_ore` and `budget_ore` so a caller can log or report the
    refusal (SPEC §9 test case 8: "passet startar inte" -- and that refusal
    must be logged, never silently swallowed). Never carries anything from
    `Usage` or the LLM response itself -- just the two öre amounts needed to
    explain the refusal.
    """

    def __init__(self, spent_ore: int, budget_ore: int) -> None:
        super().__init__(
            f"Daily budget exhausted: spent {spent_ore} öre of a "
            f"{budget_ore} öre daily budget."
        )
        self.spent_ore = spent_ore
        self.budget_ore = budget_ore


def ensure_daily_budget_available(
    agent_run_repo: type[AgentRunRepository] = AgentRunRepository,
) -> None:
    """Raise `DailyBudgetExhaustedError` if today's spend already meets or
    exceeds `config.settings.agent_daily_budget_ore` (SPEC §6.5's "kostnad
    per dygn" cap, 5000 öre / 50 kr by default).

    `agent_run_repo` accepts `AgentRunRepository` itself (all of its methods
    are `@staticmethod`, so the class is callable exactly like an instance --
    see `repositories/agent_run_repo.py`) and defaults to it; a test may pass
    a different object exposing the same `sum_cost_today_ore() -> int` shape
    if it ever needs to.

    This function does not, by itself, wire up *when* it gets called -- it
    is meant to be invoked from two distinct points once A10 builds the
    worker's pass loop around `services/agent_runtime.py`:

    1. **Before a pass starts, before the `agent_runs` row is created.**
       SPEC §9 test case 8: "Dygnstaket redan nått" -> "Passet startar inte,
       ingen agent_runs-rad, loggat." A10's worker calls this first thing
       inside its "passet startas" step (SPEC §6.2), before
       `AgentRunRepository.create(...)`, and logs the refusal (this
       exception's `spent_ore`/`budget_ore`) rather than swallowing it.
    2. **Between items, after finishing each one, for the rest of the
       pass.** SPEC §6.5's table: "Kostnad per dygn -> Avsluta passet,
       status='completed', logga budget_exhausted." A10's per-item loop
       (SPEC §6.2's "för varje post, en i taget") calls this again after each
       item's session finishes (and its cost has been added via
       `AgentRunRepository.add_usage`), and on this exception ends the pass
       cleanly with `status='completed'` -- never mid-item, never inside the
       item's own `with db.transaction():`.

    Comparison is `>=`, not `>`: a spend exactly equal to the budget has
    exhausted it, matching SPEC §6.5's "redan nått" framing in test case 8.
    """
    spent_ore = agent_run_repo.sum_cost_today_ore()
    if spent_ore >= settings.agent_daily_budget_ore:
        raise DailyBudgetExhaustedError(
            spent_ore=spent_ore, budget_ore=settings.agent_daily_budget_ore
        )
