"""
PrintTown Math Engine - Core betting math functions.
"""
from typing import List, Dict, Tuple

# ═══ 1. ODDS CONVERSION ═══

def american_to_implied_prob(odds: int) -> float:
    if odds == 0: raise ValueError("American odds cannot be 0")
    if odds > 0: return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)

def implied_prob_to_american(prob: float) -> int:
    if prob <= 0 or prob >= 1: raise ValueError(f"Prob must be (0,1), got {prob}")
    if prob > 0.5: return round(-(prob / (1.0 - prob)) * 100.0)
    if prob < 0.5: return round(((1.0 - prob) / prob) * 100.0)
    return 100

def american_to_decimal(odds: int) -> float:
    if odds == 0: raise ValueError("American odds cannot be 0")
    if odds > 0: return (odds / 100.0) + 1.0
    return (100.0 / abs(odds)) + 1.0

def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds <= 1.0: raise ValueError(f"Decimal odds must be > 1.0, got {decimal_odds}")
    if decimal_odds >= 2.0: return round((decimal_odds - 1.0) * 100.0)
    return round(-100.0 / (decimal_odds - 1.0))

def decimal_to_implied_prob(decimal_odds: float) -> float:
    if decimal_odds <= 1.0: raise ValueError(f"Decimal odds must be > 1.0, got {decimal_odds}")
    return 1.0 / decimal_odds

# ═══ 2. VIG REMOVAL ═══

def remove_vig_multiplicative(outcomes: List[Dict]) -> List[Dict]:
    """Remove vig via normalization. Input: [{'name':'A','american_odds':-110}, ...]"""
    if len(outcomes) < 2: raise ValueError("Need at least 2 outcomes")
    for o in outcomes:
        o['implied_prob'] = american_to_implied_prob(o['american_odds'])
    total = sum(o['implied_prob'] for o in outcomes)
    if total <= 0: raise ValueError("Total implied probability must be positive")
    for o in outcomes:
        o['devigged_prob'] = o['implied_prob'] / total
    return outcomes

def calculate_overround(outcomes: List[Dict]) -> float:
    """Vig as percentage. Input: [{'american_odds': -110}, ...]"""
    total = sum(american_to_implied_prob(o['american_odds']) for o in outcomes)
    return (total - 1.0) * 100.0

# ═══ 3. SHARP-BOOK WEIGHTED CONSENSUS ═══

BOOK_WEIGHTS = {
    'pinnacle': 1.00, 'circa': 0.85, 'bookmaker': 0.80, 'betonlineag': 0.60,
    'bovada': 0.55, 'draftkings': 0.50, 'fanduel': 0.50, 'betmgm': 0.45,
    'williamhill_us': 0.40, 'caesars': 0.40, 'pointsbetus': 0.40,
    'betrivers': 0.35, 'unibet_us': 0.35, 'wynnbet': 0.35,
    'superbook': 0.70, 'betway': 0.40, 'bet365': 0.65, 'marathonbet': 0.60,
}

def get_book_weight(sportsbook: str) -> float:
    key = sportsbook.lower().strip()
    if key in BOOK_WEIGHTS: return BOOK_WEIGHTS[key]
    for bk, w in BOOK_WEIGHTS.items():
        if bk in key or key in bk: return w
    return 0.30

def build_consensus(book_lines: List[Dict]) -> float:
    """Weighted avg of devigged probs. Input: [{'sportsbook':'pinnacle','devigged_prob':0.55}, ...]"""
    if not book_lines: raise ValueError("Need at least 1 book line")
    ws, wt = 0.0, 0.0
    for line in book_lines:
        w = get_book_weight(line['sportsbook'])
        ws += w * line['devigged_prob']
        wt += w
    if wt <= 0: raise ValueError("Total weight must be positive")
    return max(0.001, min(0.999, ws / wt))

def build_consensus_for_market(market_lines: Dict[str, List[Dict]]) -> Dict[str, float]:
    """Build consensus for all outcomes, normalized to sum=1.0."""
    raw = {name: build_consensus(lines) for name, lines in market_lines.items()}
    total = sum(raw.values())
    if total <= 0: raise ValueError("Total consensus must be positive")
    return {name: prob / total for name, prob in raw.items()}

# ═══ 4. EXPECTED VALUE ═══

def calculate_ev(consensus_prob: float, offered_odds: int) -> float:
    """EV = (true_prob * decimal_odds) - 1"""
    return (consensus_prob * american_to_decimal(offered_odds)) - 1.0

def calculate_ev_percent(consensus_prob: float, offered_odds: int) -> float:
    return calculate_ev(consensus_prob, offered_odds) * 100.0

def is_positive_ev(consensus_prob: float, offered_odds: int, min_ev_percent: float = 1.0) -> bool:
    return calculate_ev_percent(consensus_prob, offered_odds) >= min_ev_percent

# ═══ 5. KELLY CRITERION ═══

def kelly_criterion(consensus_prob: float, offered_odds: int) -> float:
    """Full Kelly: f* = (b*p - q) / b where b = decimal - 1"""
    b = american_to_decimal(offered_odds) - 1.0
    if b <= 0: return 0.0
    return max(0.0, (b * consensus_prob - (1.0 - consensus_prob)) / b)

def kelly_fractional(consensus_prob: float, offered_odds: int,
                     fraction: float = 0.25, max_bet_fraction: float = 0.05) -> float:
    """Fractional Kelly, capped at max_bet_fraction."""
    return min(kelly_criterion(consensus_prob, offered_odds) * fraction, max_bet_fraction)

def kelly_bet_amount(bankroll: float, consensus_prob: float, offered_odds: int,
                     fraction: float = 0.25, max_bet_fraction: float = 0.05) -> float:
    """Dollar amount to bet."""
    return round(bankroll * kelly_fractional(consensus_prob, offered_odds, fraction, max_bet_fraction), 2)

# ═══ 6. CLV ═══

def calculate_clv(closing_consensus_prob: float, pick_decimal_odds: float) -> float:
    """CLV = (closing_prob * pick_decimal) - 1"""
    return (closing_consensus_prob * pick_decimal_odds) - 1.0

def calculate_clv_percent(closing_consensus_prob: float, pick_decimal_odds: float) -> float:
    return calculate_clv(closing_consensus_prob, pick_decimal_odds) * 100.0

def calculate_clv_from_american(closing_consensus_prob: float, pick_american_odds: int) -> float:
    return calculate_clv(closing_consensus_prob, american_to_decimal(pick_american_odds))

# ═══ 7. PARLAY MATH ═══

def parlay_combined_odds(legs: List[Dict]) -> float:
    """Multiply decimal odds of all legs."""
    combined = 1.0
    for leg in legs:
        if 'decimal_odds' in leg: combined *= leg['decimal_odds']
        elif 'american_odds' in leg: combined *= american_to_decimal(leg['american_odds'])
        else: raise ValueError("Each leg needs 'american_odds' or 'decimal_odds'")
    return combined

def parlay_combined_prob(legs: List[Dict]) -> float:
    """Product of independent true probs."""
    combined = 1.0
    for leg in legs: combined *= leg['consensus_prob']
    return combined

def parlay_ev(legs: List[Dict]) -> float:
    return (parlay_combined_prob(legs) * parlay_combined_odds(legs)) - 1.0

def parlay_ev_percent(legs: List[Dict]) -> float:
    return parlay_ev(legs) * 100.0

def parlay_combined_american(legs: List[Dict]) -> int:
    return decimal_to_american(parlay_combined_odds(legs))

def parlay_kelly(legs: List[Dict], fraction: float = 0.25, max_bet_fraction: float = 0.03) -> float:
    """Fractional Kelly for parlays (tighter 3% default cap)."""
    cp = parlay_combined_prob(legs)
    b = parlay_combined_odds(legs) - 1.0
    if b <= 0: return 0.0
    fk = (b * cp - (1.0 - cp)) / b
    return min(max(0.0, fk) * fraction, max_bet_fraction)

# ═══ 8. CORRELATION ═══

def leg_correlation(leg_a: Dict, leg_b: Dict) -> float:
    """Same game/market=1.0, same game/diff market=0.7, same sport=0.15, cross-sport=0.0"""
    if leg_a['game_id'] == leg_b['game_id']:
        return 1.0 if leg_a['market_type'] == leg_b['market_type'] else 0.7
    if leg_a['sport_key'] == leg_b['sport_key']: return 0.15
    return 0.0

def parlay_avg_correlation(legs: List[Dict]) -> float:
    if len(legs) < 2: return 0.0
    corrs = [leg_correlation(legs[i], legs[j]) for i in range(len(legs)) for j in range(i+1, len(legs))]
    return sum(corrs) / len(corrs)

def is_valid_parlay(legs: List[Dict], max_legs: int = 4, max_avg_correlation: float = 0.2,
                    min_ev_per_leg: float = 2.0, min_combined_ev: float = 5.0) -> Tuple[bool, str]:
    if len(legs) < 2: return False, "Parlay must have at least 2 legs"
    if len(legs) > max_legs: return False, f"Exceeds maximum of {max_legs} legs"
    for i, leg in enumerate(legs):
        lev = calculate_ev_percent(leg['consensus_prob'], leg['american_odds'])
        if lev < min_ev_per_leg: return False, f"Leg {i+1} EV ({lev:.1f}%) below {min_ev_per_leg}%"
    ac = parlay_avg_correlation(legs)
    if ac > max_avg_correlation: return False, f"Correlation ({ac:.2f}) exceeds {max_avg_correlation}"
    cev = parlay_ev_percent(legs)
    if cev < min_combined_ev: return False, f"Combined EV ({cev:.1f}%) below {min_combined_ev}%"
    return True, "Valid"

# ═══ 9. SIGNAL SCORING ═══

def _normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val: return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

def calculate_signal_score(ev_percent: float, kelly_fraction: float, num_sharp_books_agree: int,
                           line_movement: str = 'stable', market_width: float = 0.0) -> float:
    """Composite signal 0-100. 35% EV, 25% Kelly, 20% sharp, 10% movement, 10% width."""
    movement_map = {'toward': 1.0, 'stable': 0.5, 'against': 0.0}
    signal = (
        0.35 * _normalize(ev_percent, 1.0, 15.0)
        + 0.25 * _normalize(kelly_fraction, 0.0, 0.15)
        + 0.20 * _normalize(num_sharp_books_agree, 1.0, 5.0)
        + 0.10 * movement_map.get(line_movement, 0.5)
        + 0.10 * _normalize(market_width, 0.0, 10.0)
    ) * 100.0
    return round(max(0.0, min(100.0, signal)), 1)

def signal_tier(score: float) -> str:
    if score >= 70: return 'strong'
    if score >= 40: return 'moderate'
    return 'weak'

# ═══ 10. UTILITIES ═══

def calculate_pnl(result: str, offered_odds: int, bet_amount: float) -> float:
    if result == 'push': return 0.0
    if result == 'loss': return -bet_amount
    if result == 'win': return bet_amount * (american_to_decimal(offered_odds) - 1.0)
    raise ValueError(f"Invalid result: {result}")

def format_american_odds(odds: int) -> str:
    return f"+{odds}" if odds > 0 else str(odds)

def format_ev(ev_percent: float) -> str:
    return f"{'+' if ev_percent >= 0 else ''}{ev_percent:.1f}%"

def format_kelly(fraction: float) -> str:
    return f"{fraction * 100:.2f}%"
